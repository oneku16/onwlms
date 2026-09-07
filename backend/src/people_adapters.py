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


class PeopleAcademicProfileAdapter:
    """Validate Academics profile references through the People boundary."""

    def __init__(self, references: PeopleReferenceService) -> None:
        self._references = references

    async def teacher_profile_exists(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> bool:
        """Return whether the identifier is a teacher in the exact tenant."""

        existing = await self._references.existing_teacher_profile_ids(
            organization_id=organization_id,
            teacher_profile_ids=frozenset({teacher_profile_id}),
        )
        return teacher_profile_id in existing

    async def student_profile_exists(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> bool:
        """Return whether the identifier is a student in the exact tenant."""

        existing = await self._references.existing_student_profile_ids(
            organization_id=organization_id,
            student_profile_ids=frozenset({student_profile_id}),
        )
        return student_profile_id in existing


__all__ = [
    "PeopleAcademicProfileAdapter",
    "PeopleSchedulingTeacherAdapter",
]
