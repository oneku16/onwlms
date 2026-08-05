"""Academic read contracts that preserve tenant and ownership boundaries."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from academics.application.read_models import AcademicCourseSummary
from academics.application.read_models import AcademicRoomSummary
from academics.application.read_models import AcademicSectionSummary
from academics.application.read_models import StudentAcademicSnapshot
from academics.domain.models import AcademicCalendarEvent


class AcademicSelfServiceReadRepository(Protocol):
    """Project academic state for already authorized student and teacher reads."""

    async def get_student_snapshot(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> StudentAcademicSnapshot:
        """Return tenant academic enrollment facts for one student profile."""
        ...

    async def list_teacher_sections(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> tuple[AcademicSectionSummary, ...]:
        """Return only offerings explicitly assigned to one teacher profile."""
        ...

    async def list_section_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
        section_id: UUID,
    ) -> tuple[UUID, ...] | None:
        """Return roster IDs, or None when the teacher is not assigned."""
        ...

    async def list_upcoming_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return organization events intersecting a bounded horizon."""
        ...

    async def list_sections_by_id(
        self,
        *,
        organization_id: UUID,
        section_ids: frozenset[UUID],
    ) -> tuple[AcademicSectionSummary, ...]:
        """Describe an exact tenant section identifier set."""
        ...

    async def list_courses_by_id(
        self,
        *,
        organization_id: UUID,
        course_ids: frozenset[UUID],
    ) -> tuple[AcademicCourseSummary, ...]:
        """Describe an exact tenant course identifier set."""
        ...

    async def list_rooms_by_id(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
    ) -> tuple[AcademicRoomSummary, ...]:
        """Describe an exact tenant room identifier set."""
        ...


__all__ = ["AcademicSelfServiceReadRepository"]
