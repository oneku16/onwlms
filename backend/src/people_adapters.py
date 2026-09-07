"""Explicit adapters from People references to consumer-owned ports."""

from uuid import UUID

from people.application.reference_service import PeopleReferenceService


class PeopleSchedulingTeacherAdapter:
    """Validate Scheduling teacher references through the People boundary."""

    def __init__(self, references: PeopleReferenceService) -> None:
        self._references = references

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return exact tenant teacher profiles in Scheduling's contract shape."""

        return await self._references.existing_teacher_profile_ids(
            organization_id=organization_id,
            teacher_profile_ids=teacher_profile_ids,
        )


__all__ = ["PeopleSchedulingTeacherAdapter"]
