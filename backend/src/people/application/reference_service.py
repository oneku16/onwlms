"""Stable, privacy-minimized People reference boundary for other modules."""

from uuid import UUID

from people.application.ports import PeopleReferenceRepository


class PeopleReferenceService:
    """Expose tenant-scoped profile existence without sharing People internals."""

    def __init__(self, repository: PeopleReferenceRepository) -> None:
        self._repository = repository

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return only requested IDs that are teachers in the exact tenant."""

        return await self._repository.existing_teacher_profile_ids(
            organization_id=organization_id,
            teacher_profile_ids=teacher_profile_ids,
        )

    async def existing_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return only requested IDs that are students in the exact tenant."""

        return await self._repository.existing_student_profile_ids(
            organization_id=organization_id,
            student_profile_ids=student_profile_ids,
        )

    async def resolve_student_profile_id(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> UUID | None:
        """Return one tenant person's student profile ID, or None when absent."""

        return await self._repository.resolve_student_profile_id(
            organization_id=organization_id,
            person_id=person_id,
        )


__all__ = ["PeopleReferenceService"]
