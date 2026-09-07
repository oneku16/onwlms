"""Ownership-safe people query contracts."""

from typing import Protocol
from uuid import UUID

from core.context import TenantActorContext
from people.application.read_models import OwnedProfileSummary
from people.domain.models import ProfileKind


class MembershipPersonResolver(Protocol):
    """Revalidate the person linked to one active membership context."""

    async def resolve_person_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        """Return the active membership's linked tenant person identifier."""
        ...


class PeopleOwnershipReadRepository(Protocol):
    """Read only profile identity and explicit guardian relationship facts."""

    async def get_profile_for_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
        kind: ProfileKind,
    ) -> OwnedProfileSummary | None:
        """Return one kind-specific profile owned by the tenant person."""
        ...

    async def list_linked_students(
        self,
        *,
        organization_id: UUID,
        guardian_profile_id: UUID,
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return students joined through explicit same-tenant relationships."""
        ...

    async def list_student_summaries(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return minimum roster identities for an authorized profile ID set."""
        ...


__all__ = [
    "MembershipPersonResolver",
    "PeopleOwnershipReadRepository",
]
