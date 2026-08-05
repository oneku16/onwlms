"""Role- and ownership-aware people read application service."""

from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from people.application.read_models import OwnedProfileSummary
from people.application.read_ports import MembershipPersonResolver
from people.application.read_ports import PeopleOwnershipReadRepository
from people.domain.models import ProfileKind

STUDENT_SELF_READ = "academics.student.read_own"
TEACHER_ASSIGNED_READ = "academics.teacher.read_assigned"
GUARDIAN_LINKED_READ = "academics.guardian.read_linked"

_PROFILE_PERMISSIONS = {
    ProfileKind.STUDENT: STUDENT_SELF_READ,
    ProfileKind.TEACHER: TEACHER_ASSIGNED_READ,
    ProfileKind.GUARDIAN: GUARDIAN_LINKED_READ,
}


class PeopleOwnershipReadService:
    """Resolve actor profiles and minimum related-person projections."""

    def __init__(
        self,
        *,
        repository: PeopleOwnershipReadRepository,
        memberships: MembershipPersonResolver,
    ) -> None:
        self._repository = repository
        self._memberships = memberships

    async def resolve_actor_profile(
        self,
        *,
        actor: TenantActorContext,
        kind: ProfileKind,
    ) -> OwnedProfileSummary:
        """Resolve a role-matching profile through the revalidated membership."""

        permission = _PROFILE_PERMISSIONS.get(kind)
        if permission is None or permission not in actor.permissions:
            raise AuthorizationError
        person_id = await self._memberships.resolve_person_id(actor=actor)
        profile = await self._repository.get_profile_for_person(
            organization_id=actor.organization_id,
            person_id=person_id,
            kind=kind,
        )
        if profile is None:
            raise NotFoundError("Owned profile was not found")
        return profile

    async def list_linked_students(
        self,
        *,
        actor: TenantActorContext,
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return only students explicitly linked to the actor's guardian profile."""

        guardian = await self.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.GUARDIAN,
        )
        return await self._repository.list_linked_students(
            organization_id=actor.organization_id,
            guardian_profile_id=guardian.profile_id,
        )

    async def list_assigned_roster_students(
        self,
        *,
        actor: TenantActorContext,
        student_profile_ids: frozenset[UUID],
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return minimum identities after an assignment-safe academic query."""

        if TEACHER_ASSIGNED_READ not in actor.permissions:
            raise AuthorizationError
        if not student_profile_ids:
            return ()
        values = await self._repository.list_student_summaries(
            organization_id=actor.organization_id,
            student_profile_ids=student_profile_ids,
        )
        if {value.profile_id for value in values} != set(student_profile_ids):
            raise NotFoundError("Assigned roster contains an unknown student")
        return values


__all__ = [
    "GUARDIAN_LINKED_READ",
    "STUDENT_SELF_READ",
    "TEACHER_ASSIGNED_READ",
    "PeopleOwnershipReadService",
]
