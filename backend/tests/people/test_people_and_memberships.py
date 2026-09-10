"""Behavioral tests for PII serialization, multi-role access, and tenant denial."""

import asyncio
from collections.abc import Callable
from datetime import date
from typing import cast
from uuid import UUID
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.http import install_error_handlers
from identity.presentation.dependencies import PLATFORM_ADMIN_PERMISSIONS
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf
from people.application.reference_service import PeopleReferenceService
from people.application.service import APPOINT_OWNER_PERMISSION
from people.application.service import MANAGE_MEMBERSHIPS_PERMISSION
from people.application.service import MANAGE_OWNER_LIFECYCLE_PERMISSION
from people.application.service import MANAGE_PEOPLE_PERMISSION
from people.application.service import READ_PEOPLE_PERMISSION
from people.application.service import ContactInput
from people.application.service import MembershipService
from people.application.service import PeopleService
from people.domain.exceptions import InvalidMembershipError
from people.domain.exceptions import MembershipNotFoundError
from people.domain.exceptions import PersonNotFoundError
from people.domain.models import ROLE_PERMISSIONS
from people.domain.models import ContactKind
from people.domain.models import GuardianRelationship
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind
from people.infrastructure.repositories import SQLAlchemyPeopleRepository
from people.presentation.router import router as people_router
from people.presentation.router import serialize_membership_discovery
from people.presentation.router import serialize_person_safe
from people_adapters import PeopleSchedulingTeacherAdapter
from scheduling.application.ports import TeacherReferenceDirectory
from shared.database import Database


class FakePeopleRepository:
    def __init__(self) -> None:
        self.people: dict[UUID, Person] = {}
        self.profiles: dict[UUID, PersonProfile] = {}
        self.relationships: list[GuardianRelationship] = []

    async def add_person(self, person: Person) -> None:
        self.people[person.id] = person

    async def get_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> Person | None:
        person = self.people.get(person_id)
        if person is None or person.organization_id != organization_id:
            return None
        return person

    async def list_people(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Person]:
        people = [
            person
            for person in self.people.values()
            if person.organization_id == organization_id
        ]
        return people[offset : offset + limit]

    async def person_exists(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> bool:
        return (
            await self.get_person(
                organization_id=organization_id,
                person_id=person_id,
            )
            is not None
        )

    async def add_profile(self, profile: PersonProfile) -> None:
        self.profiles[profile.id] = profile

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        return frozenset(
            profile.id
            for profile in self.profiles.values()
            if profile.organization_id == organization_id
            and profile.kind is ProfileKind.TEACHER
            and profile.id in teacher_profile_ids
        )

    async def existing_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        return frozenset(
            profile.id
            for profile in self.profiles.values()
            if profile.organization_id == organization_id
            and profile.kind is ProfileKind.STUDENT
            and profile.id in student_profile_ids
        )

    async def resolve_student_profile_id(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> UUID | None:
        return next(
            (
                profile.id
                for profile in self.profiles.values()
                if profile.organization_id == organization_id
                and profile.person_id == person_id
                and profile.kind is ProfileKind.STUDENT
            ),
            None,
        )

    async def get_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
        kind: ProfileKind,
    ) -> PersonProfile | None:
        profile = self.profiles.get(profile_id)
        if (
            profile is None
            or profile.organization_id != organization_id
            or profile.kind is not kind
        ):
            return None
        return profile

    async def list_profiles(
        self,
        *,
        organization_id: UUID,
        kind: ProfileKind,
        limit: int,
        offset: int,
    ) -> list[PersonProfile]:
        profiles = [
            profile
            for profile in self.profiles.values()
            if profile.organization_id == organization_id and profile.kind is kind
        ]
        return profiles[offset : offset + limit]

    async def add_guardian_relationship(
        self,
        relationship: GuardianRelationship,
    ) -> None:
        self.relationships.append(relationship)


def test_national_identifier_digest_is_tenant_and_domain_separated() -> None:
    repository = SQLAlchemyPeopleRepository(
        database=cast(Database, object()),
        encryption_key=Fernet.generate_key().decode("ascii"),
    )
    organization_one = uuid4()
    organization_two = uuid4()

    digest_one = repository._digest(organization_one, " PIN-123 ")
    digest_two = repository._digest(organization_two, "PIN-123")

    assert digest_one == repository._digest(organization_one, "PIN-123")
    assert digest_one != digest_two
    assert digest_one != repository._legacy_digest("PIN-123")


class FakeMembershipRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, Membership] = {}
        self.mutation_locks: dict[UUID, asyncio.Lock] = {}
        self.owner_locks: dict[UUID, asyncio.Lock] = {}

    async def add(self, membership: Membership) -> None:
        self.values[membership.id] = membership

    async def mutate_existing(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership], Membership],
    ) -> Membership:
        lock = self.mutation_locks.setdefault(membership_id, asyncio.Lock())
        async with lock:
            current = self.values.get(membership_id)
            if current is None or current.organization_id != organization_id:
                raise MembershipNotFoundError
            updated = mutation(current)
            self.values[membership_id] = updated
            return updated

    async def mutate_owner(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership, tuple[Membership, ...]], Membership],
    ) -> Membership:
        lock = self.owner_locks.setdefault(organization_id, asyncio.Lock())
        async with lock:
            owner_memberships = tuple(
                sorted(
                    (
                        membership
                        for membership in self.values.values()
                        if membership.organization_id == organization_id
                        and MembershipRole.ORGANIZATION_OWNER in membership.roles
                    ),
                    key=lambda membership: membership.id,
                )
            )
            current = next(
                (
                    membership
                    for membership in owner_memberships
                    if membership.id == membership_id
                ),
                None,
            )
            if current is None:
                raise MembershipNotFoundError
            updated = mutation(current, owner_memberships)
            self.values[membership_id] = updated
            return updated

    async def get(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        membership = self.values.get(membership_id)
        if membership is None or membership.organization_id != organization_id:
            return None
        return membership

    async def get_for_identity(
        self,
        *,
        organization_id: UUID,
        identity_subject_id: UUID,
    ) -> Membership | None:
        return next(
            (
                membership
                for membership in self.values.values()
                if membership.organization_id == organization_id
                and membership.identity_subject_id == identity_subject_id
            ),
            None,
        )

    async def list_for_identity(
        self,
        *,
        identity_subject_id: UUID,
    ) -> list[Membership]:
        return [
            membership
            for membership in self.values.values()
            if membership.identity_subject_id == identity_subject_id
            and membership.status is MembershipStatus.ACTIVE
        ]

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        values = [
            membership
            for membership in self.values.values()
            if membership.organization_id == organization_id
        ]
        return values[offset : offset + limit]

    async def list_owners_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        values = [
            membership
            for membership in self.values.values()
            if membership.organization_id == organization_id
            and MembershipRole.ORGANIZATION_OWNER in membership.roles
        ]
        return values[offset : offset + limit]


class FakeOrganizationAvailability:
    def __init__(self, active: set[UUID]) -> None:
        self.active = active

    async def is_active(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        return organization_id in self.active


class FakePeopleAuditSink:
    def __init__(self, *, fail_on_action: str | None = None) -> None:
        self.fail_on_action = fail_on_action
        self.events: list[tuple[str, str]] = []

    async def record_people_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert action and organization_id and actor_subject_id and target_id
        assert correlation_id
        if action == self.fail_on_action:
            raise RuntimeError("audit unavailable")
        self.events.append((action, outcome))


class RecordingProfileActivationWriter:
    def __init__(self, repository: FakePeopleRepository) -> None:
        self.repository = repository
        self.calls: list[tuple[PersonProfile, UUID, str]] = []

    async def add_profile_with_activation(
        self,
        *,
        profile: PersonProfile,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        self.calls.append((profile, actor_subject_id, correlation_id))
        await self.repository.add_profile(profile)


def _actor(organization_id: UUID, *permissions: str) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset(permissions),
    )


def _platform_owner_actor() -> PlatformActorContext:
    return PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset({MANAGE_OWNER_LIFECYCLE_PERMISSION}),
    )


async def test_person_safe_serializer_masks_sensitive_fields() -> None:
    organization_id = uuid4()
    repository = FakePeopleRepository()
    service = PeopleService(people=repository, audit=FakePeopleAuditSink())
    actor = _actor(
        organization_id,
        MANAGE_PEOPLE_PERMISSION,
        READ_PEOPLE_PERMISSION,
    )
    person = await service.create_person(
        actor=actor,
        given_name="Amina",
        family_name="Example",
        preferred_name=None,
        national_identifier="PIN-123456",
        date_of_birth=date(2001, 2, 3),
        contacts=(
            ContactInput(
                kind=ContactKind.EMAIL,
                value="amina@example.test",
                is_primary=True,
            ),
            ContactInput(
                kind=ContactKind.PHONE,
                value="+996555123456",
                whatsapp_capable=True,
            ),
        ),
    )

    payload = serialize_person_safe(person)
    rendered = str(payload)
    assert "PIN-123456" not in rendered
    assert "2001-02-03" not in rendered
    assert "amina@example.test" not in rendered
    assert "+996555123456" not in rendered
    assert "a***@example.test" in rendered
    assert "***3456" in rendered
    assert "PIN-123456" not in repr(person)
    assert "amina@example.test" not in repr(
        ContactInput(kind=ContactKind.EMAIL, value="amina@example.test")
    )


async def test_people_and_profile_lists_remain_tenant_scoped() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    repository = FakePeopleRepository()
    person_a = Person(
        id=uuid4(),
        organization_id=organization_a,
        given_name="Amina",
        family_name="A",
    )
    person_b = Person(
        id=uuid4(),
        organization_id=organization_b,
        given_name="Bermet",
        family_name="B",
    )
    repository.people = {person_a.id: person_a, person_b.id: person_b}
    profile_a = PersonProfile(
        id=uuid4(),
        organization_id=organization_a,
        person_id=person_a.id,
        kind=ProfileKind.STUDENT,
    )
    profile_b = PersonProfile(
        id=uuid4(),
        organization_id=organization_b,
        person_id=person_b.id,
        kind=ProfileKind.STUDENT,
    )
    repository.profiles = {profile_a.id: profile_a, profile_b.id: profile_b}
    service = PeopleService(people=repository, audit=FakePeopleAuditSink())
    actor = _actor(organization_a, READ_PEOPLE_PERMISSION)

    assert await service.list_people(actor=actor, limit=50, offset=0) == [person_a]
    assert await service.list_profiles(
        actor=actor,
        kind=ProfileKind.STUDENT,
        limit=50,
        offset=0,
    ) == [profile_a]


async def test_profile_creation_uses_atomic_activation_boundary() -> None:
    organization_id = uuid4()
    repository = FakePeopleRepository()
    person = Person(
        id=uuid4(),
        organization_id=organization_id,
        given_name="Amina",
        family_name="Example",
    )
    repository.people[person.id] = person
    activations = RecordingProfileActivationWriter(repository)
    service = PeopleService(
        people=repository,
        audit=FakePeopleAuditSink(),
        profile_activations=activations,
    )
    actor = _actor(organization_id, MANAGE_PEOPLE_PERMISSION)

    profile = await service.add_profile(
        actor=actor,
        person_id=person.id,
        kind=ProfileKind.STUDENT,
        reference_number="ST-001",
        title=None,
    )

    assert activations.calls == [(profile, actor.subject_id, actor.correlation_id)]
    assert repository.profiles[profile.id] == profile


def test_membership_combines_roles_without_platform_administration() -> None:
    membership = Membership(
        id=uuid4(),
        organization_id=uuid4(),
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STUDENT, MembershipRole.STAFF}),
    )

    assert "scheduling.read" in membership.permissions
    assert "people.read" in membership.permissions
    assert "organizations.platform.create" not in membership.permissions


def test_tenant_administrators_receive_exact_service_permissions() -> None:
    expected_permissions = {
        "organizations.read",
        "organizations.configure",
        "organizations.campuses.manage",
        "people.read",
        "people.manage",
        "people.memberships.manage",
        "people.guardians.manage",
        "academics.structure.manage",
        "academics.curriculum.manage",
        "academics.enrollment.manage",
        "academics.term.close",
        "academics.course_selection.submit",
        "academics.course_selection.approve",
        "academics.course_selection.override",
        "admissions.application.create",
        "admissions.application.submit",
        "admissions.document.manage",
        "admissions.review",
        "admissions.decision.manage",
        "admissions.policy.manage",
        "admissions.application.enroll",
        "grading.scale.manage",
        "grading.final_grade.record",
        "grading.final_grade.revise",
        "grading.transcript.read",
        "scheduling.session.manage",
        "scheduling.generate",
        "scheduling.generation.apply",
        "scheduling.read",
        "integrations.configure",
        "integrations.read",
        "integrations.grade_evidence.read",
        "integrations.grade_evidence.reconcile",
        "provisioning.read",
        "provisioning.retry",
        "notifications.read_own",
        "notifications.preferences.manage_own",
        "notifications.delivery.retry_own",
        "entitlements.read",
        "audit.read",
    }

    assert ROLE_PERMISSIONS[MembershipRole.ORGANIZATION_ADMIN] == expected_permissions
    assert ROLE_PERMISSIONS[MembershipRole.ORGANIZATION_OWNER] == (
        expected_permissions | {"grading.final_grade.revise_closed_term"}
    )


@pytest.mark.parametrize(
    ("role", "withheld_permission"),
    [
        (MembershipRole.STUDENT, "academics.course_selection.approve"),
        (MembershipRole.STUDENT, "grading.transcript.read"),
        (MembershipRole.GUEST, "admissions.application.submit"),
        (MembershipRole.TEACHER, "grading.final_grade.record"),
    ],
)
def test_self_service_permissions_are_withheld_without_resource_binding(
    role: MembershipRole,
    withheld_permission: str,
) -> None:
    assert withheld_permission not in ROLE_PERMISSIONS[role]


def test_only_owner_can_revise_grades_after_term_closure() -> None:
    permission = "grading.final_grade.revise_closed_term"

    assert permission in ROLE_PERMISSIONS[MembershipRole.ORGANIZATION_OWNER]
    assert permission not in ROLE_PERMISSIONS[MembershipRole.ORGANIZATION_ADMIN]


def test_student_can_submit_course_selection_without_admin_permissions() -> None:
    permissions = ROLE_PERMISSIONS[MembershipRole.STUDENT]

    assert "academics.course_selection.submit" in permissions
    assert "academics.enrollment.manage" not in permissions


async def test_tenant_membership_manager_cannot_assign_owner_role() -> None:
    organization_id = uuid4()
    service = MembershipService(
        memberships=FakeMembershipRepository(),
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )
    actor = _actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION)

    with pytest.raises(AuthorizationError):
        await service.create_membership(
            actor=actor,
            identity_subject_id=uuid4(),
            person_id=None,
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )


async def test_tenant_membership_manager_cannot_change_an_owner() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    owner = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
    )
    memberships.values[owner.id] = owner
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )

    with pytest.raises(AuthorizationError):
        await service.replace_roles(
            actor=_actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION),
            membership_id=owner.id,
            roles=frozenset({MembershipRole.STAFF}),
        )


async def test_platform_owner_recovery_preserves_existing_membership_roles() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    existing = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
        status=MembershipStatus.SUSPENDED,
    )
    memberships.values[existing.id] = existing
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )
    actor = PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset({APPOINT_OWNER_PERMISSION}),
    )

    recovered = await service.appoint_organization_owner(
        actor=actor,
        organization_id=organization_id,
        identity_subject_id=existing.identity_subject_id,
        person_id=None,
    )

    assert recovered.id == existing.id
    assert recovered.status is MembershipStatus.ACTIVE
    assert recovered.roles == frozenset(
        {MembershipRole.STAFF, MembershipRole.ORGANIZATION_OWNER}
    )


async def test_platform_owner_lifecycle_is_audited_and_revocation_is_terminal() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    target = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
    )
    replacement = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER, MembershipRole.STAFF}),
    )
    memberships.values = {
        target.id: target,
        replacement.id: replacement,
    }
    audit = FakePeopleAuditSink()
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=audit,
    )
    actor = _platform_owner_actor()

    suspended = await service.suspend_organization_owner(
        actor=actor,
        organization_id=organization_id,
        membership_id=target.id,
    )
    revoked = await service.revoke_organization_owner(
        actor=actor,
        organization_id=organization_id,
        membership_id=target.id,
    )

    assert suspended.status is MembershipStatus.SUSPENDED
    assert revoked.status is MembershipStatus.REVOKED
    assert revoked.roles == target.roles
    assert memberships.values[replacement.id].status is MembershipStatus.ACTIVE
    assert audit.events == [
        ("membership.owner_suspension_intent", "intent_recorded"),
        ("membership.owner_suspended", "succeeded"),
        ("membership.owner_revocation_intent", "intent_recorded"),
        ("membership.owner_revoked", "succeeded"),
    ]
    with pytest.raises(InvalidMembershipError, match="already revoked"):
        await service.revoke_organization_owner(
            actor=actor,
            organization_id=organization_id,
            membership_id=target.id,
        )


async def test_owner_lifecycle_intent_audit_failure_aborts_mutation() -> None:
    organization_id = uuid4()
    owners = tuple(
        Membership(
            id=uuid4(),
            organization_id=organization_id,
            identity_subject_id=uuid4(),
            person_id=None,
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )
        for _ in range(2)
    )
    memberships = FakeMembershipRepository()
    memberships.values = {owner.id: owner for owner in owners}
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(fail_on_action="membership.owner_suspension_intent"),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.suspend_organization_owner(
            actor=_platform_owner_actor(),
            organization_id=organization_id,
            membership_id=owners[0].id,
        )

    assert memberships.values[owners[0].id].status is MembershipStatus.ACTIVE


@pytest.mark.parametrize("operation", ["suspend", "revoke"])
async def test_platform_cannot_remove_the_only_active_owner(operation: str) -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    owner = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
    )
    memberships.values[owner.id] = owner
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )

    with pytest.raises(InvalidMembershipError, match="at least one active owner"):
        await getattr(service, f"{operation}_organization_owner")(
            actor=_platform_owner_actor(),
            organization_id=organization_id,
            membership_id=owner.id,
        )

    assert memberships.values[owner.id].status is MembershipStatus.ACTIVE


async def test_platform_owner_lifecycle_rejects_wrong_target() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    memberships = FakeMembershipRepository()
    non_owner = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    other_owner = Membership(
        id=uuid4(),
        organization_id=other_organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
    )
    memberships.values = {
        non_owner.id: non_owner,
        other_owner.id: other_owner,
    }
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability(
            {organization_id, other_organization_id}
        ),
        audit=FakePeopleAuditSink(),
    )
    actor = _platform_owner_actor()

    with pytest.raises(InvalidMembershipError, match="not an organization owner"):
        await service.suspend_organization_owner(
            actor=actor,
            organization_id=organization_id,
            membership_id=non_owner.id,
        )
    with pytest.raises(MembershipNotFoundError):
        await service.revoke_organization_owner(
            actor=actor,
            organization_id=organization_id,
            membership_id=other_owner.id,
        )


@pytest.mark.parametrize("operation", ["suspend", "revoke"])
async def test_concurrent_owner_removals_leave_one_active_owner_in_memory(
    operation: str,
) -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    owners = tuple(
        Membership(
            id=uuid4(),
            organization_id=organization_id,
            identity_subject_id=uuid4(),
            person_id=None,
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )
        for _ in range(2)
    )
    memberships.values = {owner.id: owner for owner in owners}
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )
    actor = _platform_owner_actor()

    results = await asyncio.gather(
        *(
            getattr(service, f"{operation}_organization_owner")(
                actor=actor,
                organization_id=organization_id,
                membership_id=owner.id,
            )
            for owner in owners
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, Membership) for result in results) == 1
    assert sum(isinstance(result, InvalidMembershipError) for result in results) == 1
    assert (
        sum(
            membership.status is MembershipStatus.ACTIVE
            for membership in memberships.values.values()
        )
        == 1
    )


def test_owner_lifecycle_permission_is_not_granted_by_any_tenant_role() -> None:
    assert MANAGE_OWNER_LIFECYCLE_PERMISSION in PLATFORM_ADMIN_PERMISSIONS
    assert all(
        MANAGE_OWNER_LIFECYCLE_PERMISSION not in permissions
        for permissions in ROLE_PERMISSIONS.values()
    )


async def test_platform_owner_lifecycle_api_is_safe_and_exact_tenant_scoped() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    memberships = FakeMembershipRepository()
    owners = tuple(
        Membership(
            id=uuid4(),
            organization_id=organization_id,
            identity_subject_id=uuid4(),
            person_id=uuid4(),
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )
        for _ in range(2)
    )
    other_owner = Membership(
        id=uuid4(),
        organization_id=other_organization_id,
        identity_subject_id=uuid4(),
        person_id=uuid4(),
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
    )
    memberships.values = {
        membership.id: membership for membership in (*owners, other_owner)
    }
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability(
            {organization_id, other_organization_id}
        ),
        audit=FakePeopleAuditSink(),
    )
    actor = _platform_owner_actor()
    app = FastAPI()
    install_error_handlers(app)
    app.state.membership_service = service
    app.include_router(people_router)

    async def actor_override() -> PlatformActorContext:
        return actor

    async def csrf_override() -> None:
        return None

    app.dependency_overrides[require_actor] = actor_override
    app.dependency_overrides[require_csrf] = csrf_override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        listed = await client.get(
            f"/api/v1/platform/organizations/{organization_id}/owners"
        )
        suspended = await client.post(
            "/api/v1/platform/organizations/"
            f"{organization_id}/owners/{owners[0].id}/suspend"
        )
        cross_tenant = await client.post(
            "/api/v1/platform/organizations/"
            f"{organization_id}/owners/{other_owner.id}/revoke"
        )

    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert all(
        set(owner) == {"id", "organization_id", "status"} for owner in listed.json()
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert cross_tenant.status_code == 404


async def test_membership_lifecycle_is_audited() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    original = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    memberships.values[original.id] = original
    audit = FakePeopleAuditSink()
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=audit,
    )
    actor = _actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION)

    suspended = await service.suspend(actor=actor, membership_id=original.id)
    assert suspended.status is MembershipStatus.SUSPENDED
    active = await service.reactivate(actor=actor, membership_id=original.id)
    assert active.status is MembershipStatus.ACTIVE
    revoked = await service.revoke(actor=actor, membership_id=original.id)

    assert revoked.status is MembershipStatus.REVOKED
    assert audit.events == [
        ("membership.suspension_intent", "intent_recorded"),
        ("membership.suspended", "succeeded"),
        ("membership.reactivation_intent", "intent_recorded"),
        ("membership.reactivated", "succeeded"),
        ("membership.revocation_intent", "intent_recorded"),
        ("membership.revoked", "succeeded"),
    ]


@pytest.mark.parametrize("operation", ["suspend", "reactivate", "revoke"])
async def test_tenant_membership_manager_cannot_mutate_owner_lifecycle(
    operation: str,
) -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    owner = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        status=(
            MembershipStatus.SUSPENDED
            if operation == "reactivate"
            else MembershipStatus.ACTIVE
        ),
    )
    memberships.values[owner.id] = owner
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )

    with pytest.raises(AuthorizationError):
        await getattr(service, operation)(
            actor=_actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION),
            membership_id=owner.id,
        )


async def test_membership_intent_audit_failure_aborts_mutation() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    membership = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    memberships.values[membership.id] = membership
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(fail_on_action="membership.suspension_intent"),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.suspend(
            actor=_actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION),
            membership_id=membership.id,
        )

    assert memberships.values[membership.id].status is MembershipStatus.ACTIVE


async def test_revocation_immediately_denies_the_revoked_tenant_context() -> None:
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    membership = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    memberships.values[membership.id] = membership
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )

    await service.revoke(
        actor=_actor(organization_id, MANAGE_MEMBERSHIPS_PERMISSION),
        membership_id=membership.id,
    )

    assert memberships.values[membership.id].status is MembershipStatus.REVOKED
    with pytest.raises(MembershipNotFoundError):
        await service.resolve_tenant_context(
            identity_subject_id=membership.identity_subject_id,
            organization_id=organization_id,
            correlation_id="correlation-2",
        )


async def test_revocation_does_not_remove_another_tenant_membership() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    subject_id = uuid4()
    memberships = FakeMembershipRepository()
    membership_a = Membership(
        id=uuid4(),
        organization_id=organization_a,
        identity_subject_id=subject_id,
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    membership_b = Membership(
        id=uuid4(),
        organization_id=organization_b,
        identity_subject_id=subject_id,
        person_id=None,
        roles=frozenset({MembershipRole.STUDENT}),
    )
    memberships.values = {
        membership_a.id: membership_a,
        membership_b.id: membership_b,
    }
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_a, organization_b}),
        audit=FakePeopleAuditSink(),
    )

    await service.revoke(
        actor=_actor(organization_a, MANAGE_MEMBERSHIPS_PERMISSION),
        membership_id=membership_a.id,
    )

    actor_b = await service.resolve_tenant_context(
        identity_subject_id=subject_id,
        organization_id=organization_b,
        correlation_id="correlation-2",
    )
    assert actor_b.membership_id == membership_b.id


async def test_context_resolution_denies_membership_from_another_tenant() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    subject_id = uuid4()
    memberships = FakeMembershipRepository()
    membership_b = Membership(
        id=uuid4(),
        organization_id=organization_b,
        identity_subject_id=subject_id,
        person_id=None,
        roles=frozenset({MembershipRole.STUDENT}),
    )
    memberships.values[membership_b.id] = membership_b
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_a, organization_b}),
        audit=FakePeopleAuditSink(),
    )

    with pytest.raises(MembershipNotFoundError):
        await service.resolve_tenant_context(
            identity_subject_id=subject_id,
            organization_id=organization_a,
            correlation_id="correlation-1",
        )


async def test_membership_directory_is_authorized_and_tenant_scoped() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    memberships = FakeMembershipRepository()
    membership_a = Membership(
        id=uuid4(),
        organization_id=organization_a,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
        status=MembershipStatus.SUSPENDED,
    )
    membership_b = Membership(
        id=uuid4(),
        organization_id=organization_b,
        identity_subject_id=uuid4(),
        person_id=None,
        roles=frozenset({MembershipRole.STUDENT}),
    )
    memberships.values = {
        membership_a.id: membership_a,
        membership_b.id: membership_b,
    }
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_a, organization_b}),
        audit=FakePeopleAuditSink(),
    )

    listed = await service.list_memberships(
        actor=_actor(organization_a, MANAGE_MEMBERSHIPS_PERMISSION),
        limit=50,
        offset=0,
    )
    assert listed == [membership_a]

    with pytest.raises(AuthorizationError):
        await service.list_memberships(
            actor=_actor(organization_a, READ_PEOPLE_PERMISSION),
            limit=50,
            offset=0,
        )


async def test_discovery_returns_only_active_memberships_for_verified_subject() -> None:
    subject = uuid4()
    other_subject = uuid4()
    memberships = FakeMembershipRepository()
    expected = Membership(
        id=uuid4(),
        organization_id=uuid4(),
        identity_subject_id=subject,
        person_id=uuid4(),
        roles=frozenset({MembershipRole.TEACHER, MembershipRole.STAFF}),
    )
    other = Membership(
        id=uuid4(),
        organization_id=uuid4(),
        identity_subject_id=other_subject,
        person_id=None,
        roles=frozenset({MembershipRole.GUEST}),
    )
    memberships.values[expected.id] = expected
    memberships.values[other.id] = other
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability(
            {expected.organization_id, other.organization_id}
        ),
        audit=FakePeopleAuditSink(),
    )

    discovered = await service.list_active_memberships(
        identity_subject_id=subject,
    )
    assert discovered == [expected]
    payload = serialize_membership_discovery(expected)
    assert "identity_subject_id" not in payload
    assert "person_id" not in payload
    assert payload["permissions"] == sorted(expected.permissions)


async def test_discovery_excludes_membership_in_suspended_organization() -> None:
    subject = uuid4()
    organization_id = uuid4()
    memberships = FakeMembershipRepository()
    inaccessible = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=subject,
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    memberships.values[inaccessible.id] = inaccessible
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability(set()),
        audit=FakePeopleAuditSink(),
    )

    assert await service.list_active_memberships(identity_subject_id=subject) == []


async def test_resolve_person_id_revalidates_actor_subject_and_membership() -> None:
    organization_id = uuid4()
    membership = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=uuid4(),
        person_id=uuid4(),
        roles=frozenset({MembershipRole.STUDENT}),
    )
    memberships = FakeMembershipRepository()
    memberships.values[membership.id] = membership
    service = MembershipService(
        memberships=memberships,
        people=FakePeopleRepository(),
        organizations=FakeOrganizationAvailability({organization_id}),
        audit=FakePeopleAuditSink(),
    )
    forged_actor = TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=membership.id,
        correlation_id="correlation-1",
        permissions=frozenset(),
    )

    with pytest.raises(MembershipNotFoundError):
        await service.resolve_person_id(actor=forged_actor)


async def test_guardian_relationship_rejects_cross_tenant_profile() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    people = FakePeopleRepository()
    guardian = PersonProfile(
        id=uuid4(),
        organization_id=organization_a,
        person_id=uuid4(),
        kind=ProfileKind.GUARDIAN,
    )
    student = PersonProfile(
        id=uuid4(),
        organization_id=organization_b,
        person_id=uuid4(),
        kind=ProfileKind.STUDENT,
    )
    people.profiles[guardian.id] = guardian
    people.profiles[student.id] = student
    service = PeopleService(people=people, audit=FakePeopleAuditSink())
    actor = _actor(organization_a, "people.guardians.manage")

    with pytest.raises(PersonNotFoundError):
        await service.link_guardian(
            actor=actor,
            guardian_profile_id=guardian.id,
            student_profile_id=student.id,
            relationship_label="Parent",
        )


async def test_public_teacher_references_expose_only_same_tenant_teachers() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    teacher = PersonProfile(
        id=uuid4(),
        organization_id=organization_id,
        person_id=uuid4(),
        kind=ProfileKind.TEACHER,
    )
    staff = PersonProfile(
        id=uuid4(),
        organization_id=organization_id,
        person_id=uuid4(),
        kind=ProfileKind.STAFF,
    )
    other_teacher = PersonProfile(
        id=uuid4(),
        organization_id=other_organization_id,
        person_id=uuid4(),
        kind=ProfileKind.TEACHER,
    )
    repository = FakePeopleRepository()
    repository.profiles = {
        profile.id: profile for profile in (teacher, staff, other_teacher)
    }
    references: TeacherReferenceDirectory = PeopleSchedulingTeacherAdapter(
        PeopleReferenceService(repository)
    )

    existing = await references.existing_teacher_profile_ids(
        organization_id=organization_id,
        teacher_profile_ids=frozenset(
            {teacher.id, staff.id, other_teacher.id, uuid4()}
        ),
    )

    assert existing == frozenset({teacher.id})
