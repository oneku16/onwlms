"""Tenant-safe people, profile, guardian, and membership application services."""

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from datetime import date
from uuid import UUID

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from people.application.ports import MembershipRepository
from people.application.ports import OrganizationAvailability
from people.application.ports import PeopleAuditSink
from people.application.ports import PeopleRepository
from people.application.ports import ProfileActivationWriter
from people.domain.exceptions import InvalidMembershipError
from people.domain.exceptions import MembershipNotFoundError
from people.domain.exceptions import PersonNotFoundError
from people.domain.models import ContactKind
from people.domain.models import ContactMethod
from people.domain.models import GuardianRelationship
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind

READ_PEOPLE_PERMISSION = "people.read"
MANAGE_PEOPLE_PERMISSION = "people.manage"
MANAGE_MEMBERSHIPS_PERMISSION = "people.memberships.manage"
MANAGE_GUARDIANS_PERMISSION = "people.guardians.manage"
APPOINT_OWNER_PERMISSION = "people.platform.appoint_owner"


@dataclass(frozen=True, slots=True)
class ContactInput:
    """Describe one contact method before an application identifier is assigned."""

    kind: ContactKind
    value: str = field(repr=False)
    label: str | None = None
    is_primary: bool = False
    whatsapp_capable: bool = False


class PeopleService:
    """Coordinate tenant-owned people, profiles, and guardian relationships."""

    def __init__(
        self,
        *,
        people: PeopleRepository,
        audit: PeopleAuditSink,
        profile_activations: ProfileActivationWriter | None = None,
    ) -> None:
        self._people = people
        self._audit = audit
        self._profile_activations = profile_activations

    async def create_person(
        self,
        *,
        actor: TenantActorContext,
        given_name: str,
        family_name: str,
        preferred_name: str | None,
        national_identifier: str | None,
        date_of_birth: date | None,
        contacts: tuple[ContactInput, ...],
    ) -> Person:
        """Create sensitive person state only within the actor's tenant."""

        self._require_permission(actor, MANAGE_PEOPLE_PERMISSION)
        person = Person(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            given_name=given_name,
            family_name=family_name,
            preferred_name=preferred_name,
            national_identifier=national_identifier,
            date_of_birth=date_of_birth,
            contacts=tuple(
                ContactMethod(
                    id=new_uuid7(),
                    kind=contact.kind,
                    value=contact.value,
                    label=contact.label,
                    is_primary=contact.is_primary,
                    whatsapp_capable=contact.whatsapp_capable,
                )
                for contact in contacts
            ),
        )
        await self._people.add_person(person)
        await self._audit.record_people_event(
            action="person.created",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            target_id=person.id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return person

    async def get_person(
        self,
        *,
        actor: TenantActorContext,
        person_id: UUID,
    ) -> Person:
        """Return a person only through a matching tenant predicate."""

        self._require_permission(actor, READ_PEOPLE_PERMISSION)
        person = await self._people.get_person(
            organization_id=actor.organization_id,
            person_id=person_id,
        )
        if person is None:
            raise PersonNotFoundError
        return person

    async def list_people(
        self,
        *,
        actor: TenantActorContext,
        limit: int,
        offset: int,
    ) -> list[Person]:
        """List privacy-conscious people state for one authorized tenant."""

        self._require_permission(actor, READ_PEOPLE_PERMISSION)
        return await self._people.list_people(
            organization_id=actor.organization_id,
            limit=limit,
            offset=offset,
        )

    async def list_profiles(
        self,
        *,
        actor: TenantActorContext,
        kind: ProfileKind,
        limit: int,
        offset: int,
    ) -> list[PersonProfile]:
        """List one profile category for the actor's authorized tenant."""

        self._require_permission(actor, READ_PEOPLE_PERMISSION)
        return await self._people.list_profiles(
            organization_id=actor.organization_id,
            kind=kind,
            limit=limit,
            offset=offset,
        )

    async def add_profile(
        self,
        *,
        actor: TenantActorContext,
        person_id: UUID,
        kind: ProfileKind,
        reference_number: str | None,
        title: str | None,
    ) -> PersonProfile:
        """Attach a student, staff, teacher, or guardian profile to one person."""

        self._require_permission(actor, MANAGE_PEOPLE_PERMISSION)
        if not await self._people.person_exists(
            organization_id=actor.organization_id,
            person_id=person_id,
        ):
            raise PersonNotFoundError
        profile = PersonProfile(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            person_id=person_id,
            kind=kind,
            reference_number=reference_number,
            title=title,
        )
        if self._profile_activations is None:
            await self._people.add_profile(profile)
        else:
            await self._profile_activations.add_profile_with_activation(
                profile=profile,
                actor_subject_id=actor.subject_id,
                correlation_id=actor.correlation_id,
            )
        await self._audit.record_people_event(
            action=f"person.{kind.value}_profile_created",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            target_id=profile.id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return profile

    async def link_guardian(
        self,
        *,
        actor: TenantActorContext,
        guardian_profile_id: UUID,
        student_profile_id: UUID,
        relationship_label: str,
    ) -> GuardianRelationship:
        """Link guardian and student profiles after same-tenant kind validation."""

        self._require_permission(actor, MANAGE_GUARDIANS_PERMISSION)
        guardian = await self._people.get_profile(
            organization_id=actor.organization_id,
            profile_id=guardian_profile_id,
            kind=ProfileKind.GUARDIAN,
        )
        student = await self._people.get_profile(
            organization_id=actor.organization_id,
            profile_id=student_profile_id,
            kind=ProfileKind.STUDENT,
        )
        if guardian is None or student is None:
            raise PersonNotFoundError
        relationship = GuardianRelationship(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            guardian_profile_id=guardian.id,
            student_profile_id=student.id,
            relationship_label=relationship_label,
        )
        await self._people.add_guardian_relationship(relationship)
        await self._audit.record_people_event(
            action="guardian.relationship_created",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            target_id=relationship.id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return relationship

    @staticmethod
    def _require_permission(
        actor: TenantActorContext,
        permission: str,
    ) -> None:
        """Deny a people capability without its exact tenant permission."""

        if (
            not isinstance(actor, TenantActorContext)
            or permission not in actor.permissions
        ):
            raise AuthorizationError


class MembershipService:
    """Manage roles and establish permission-based tenant actor context."""

    def __init__(
        self,
        *,
        memberships: MembershipRepository,
        people: PeopleRepository,
        organizations: OrganizationAvailability,
        audit: PeopleAuditSink,
    ) -> None:
        self._memberships = memberships
        self._people = people
        self._organizations = organizations
        self._audit = audit

    async def create_membership(
        self,
        *,
        actor: TenantActorContext,
        identity_subject_id: UUID,
        person_id: UUID | None,
        roles: frozenset[MembershipRole],
    ) -> Membership:
        """Create one multi-role membership inside the actor's tenant."""

        self._require_tenant_permission(actor, MANAGE_MEMBERSHIPS_PERMISSION)
        self._require_tenant_assignable_roles(roles)
        await self._require_person_reference(
            organization_id=actor.organization_id,
            person_id=person_id,
        )
        membership = Membership(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            identity_subject_id=identity_subject_id,
            person_id=person_id,
            roles=roles,
        )
        await self._memberships.add(membership)
        await self._audit_membership(
            action="membership.created",
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            membership=membership,
        )
        return membership

    async def appoint_organization_owner(
        self,
        *,
        actor: PlatformActorContext,
        organization_id: UUID,
        identity_subject_id: UUID,
        person_id: UUID | None,
    ) -> Membership:
        """Appoint an owner through separate platform authority and audit path."""

        if (
            not isinstance(actor, PlatformActorContext)
            or APPOINT_OWNER_PERMISSION not in actor.permissions
        ):
            raise AuthorizationError
        if not await self._organizations.is_active(
            organization_id=organization_id,
        ):
            raise InvalidMembershipError("Organization is not active")
        existing = await self._memberships.get_for_identity(
            organization_id=organization_id,
            identity_subject_id=identity_subject_id,
        )
        effective_person_id = (
            person_id
            if person_id is not None or existing is None
            else existing.person_id
        )
        await self._require_person_reference(
            organization_id=organization_id,
            person_id=effective_person_id,
        )
        if existing is not None:
            recovered = replace(
                existing,
                person_id=effective_person_id,
                roles=existing.roles | {MembershipRole.ORGANIZATION_OWNER},
                status=MembershipStatus.ACTIVE,
            )
            await self._memberships.save(recovered)
            await self._audit_membership(
                action="membership.owner_recovered",
                actor_subject_id=actor.subject_id,
                correlation_id=actor.correlation_id,
                membership=recovered,
            )
            return recovered
        membership = Membership(
            id=new_uuid7(),
            organization_id=organization_id,
            identity_subject_id=identity_subject_id,
            person_id=person_id,
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )
        await self._memberships.add(membership)
        await self._audit_membership(
            action="membership.owner_appointed",
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            membership=membership,
        )
        return membership

    async def replace_roles(
        self,
        *,
        actor: TenantActorContext,
        membership_id: UUID,
        roles: frozenset[MembershipRole],
    ) -> Membership:
        """Replace a membership's complete built-in role set within one tenant."""

        self._require_tenant_permission(actor, MANAGE_MEMBERSHIPS_PERMISSION)
        self._require_tenant_assignable_roles(roles)
        membership = await self._memberships.get(
            organization_id=actor.organization_id,
            membership_id=membership_id,
        )
        if membership is None:
            raise MembershipNotFoundError
        if MembershipRole.ORGANIZATION_OWNER in membership.roles:
            raise AuthorizationError
        updated = replace(membership, roles=roles)
        await self._memberships.save(updated)
        await self._audit_membership(
            action="membership.roles_replaced",
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            membership=updated,
        )
        return updated

    async def resolve_tenant_context(
        self,
        *,
        identity_subject_id: UUID,
        organization_id: UUID,
        correlation_id: str,
    ) -> TenantActorContext:
        """Fail closed unless identity, organization, and active membership agree."""

        if not await self._organizations.is_active(
            organization_id=organization_id,
        ):
            raise MembershipNotFoundError
        membership = await self._memberships.get_for_identity(
            organization_id=organization_id,
            identity_subject_id=identity_subject_id,
        )
        if membership is None or membership.status is not MembershipStatus.ACTIVE:
            raise MembershipNotFoundError
        return membership.actor_context(correlation_id=correlation_id)

    async def resolve_person_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        """Re-read the active matching membership and return its linked person ID."""

        if not await self._organizations.is_active(
            organization_id=actor.organization_id,
        ):
            raise MembershipNotFoundError
        membership = await self._memberships.get(
            organization_id=actor.organization_id,
            membership_id=actor.membership_id,
        )
        if (
            membership is None
            or membership.status is not MembershipStatus.ACTIVE
            or membership.identity_subject_id != actor.subject_id
            or membership.person_id is None
        ):
            raise MembershipNotFoundError
        return membership.person_id

    async def list_active_memberships(
        self,
        *,
        identity_subject_id: UUID,
    ) -> list[Membership]:
        """Discover only one verified subject's active memberships without PII."""

        memberships = await self._memberships.list_for_identity(
            identity_subject_id=identity_subject_id,
        )
        active_memberships: list[Membership] = []
        for membership in memberships:
            if (
                membership.status is MembershipStatus.ACTIVE
                and membership.identity_subject_id == identity_subject_id
                and await self._organizations.is_active(
                    organization_id=membership.organization_id,
                )
            ):
                active_memberships.append(membership)
        return active_memberships

    async def _require_person_reference(
        self,
        *,
        organization_id: UUID,
        person_id: UUID | None,
    ) -> None:
        """Reject a person reference that does not belong to the same tenant."""

        if person_id is not None and not await self._people.person_exists(
            organization_id=organization_id,
            person_id=person_id,
        ):
            raise PersonNotFoundError

    async def _audit_membership(
        self,
        *,
        action: str,
        actor_subject_id: UUID,
        correlation_id: str,
        membership: Membership,
    ) -> None:
        """Record a membership change without role or personal-data payloads."""

        await self._audit.record_people_event(
            action=action,
            organization_id=membership.organization_id,
            actor_subject_id=actor_subject_id,
            target_id=membership.id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )

    @staticmethod
    def _require_tenant_permission(
        actor: TenantActorContext,
        permission: str,
    ) -> None:
        """Deny membership governance without its exact tenant permission."""

        if (
            not isinstance(actor, TenantActorContext)
            or permission not in actor.permissions
        ):
            raise AuthorizationError

    @staticmethod
    def _require_tenant_assignable_roles(
        roles: frozenset[MembershipRole],
    ) -> None:
        """Reserve owner appointment and recovery for the platform path."""

        if MembershipRole.ORGANIZATION_OWNER in roles:
            raise AuthorizationError


__all__ = [
    "APPOINT_OWNER_PERMISSION",
    "MANAGE_GUARDIANS_PERMISSION",
    "MANAGE_MEMBERSHIPS_PERMISSION",
    "MANAGE_PEOPLE_PERMISSION",
    "READ_PEOPLE_PERMISSION",
    "ContactInput",
    "MembershipService",
    "PeopleService",
]
