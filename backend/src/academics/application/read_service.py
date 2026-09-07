"""Ownership-aware academic query application service."""

from datetime import datetime
from uuid import UUID

from academics.application.read_models import AcademicCourseSummary
from academics.application.read_models import AcademicRoomSummary
from academics.application.read_models import AcademicSectionSummary
from academics.application.read_models import StudentAcademicSnapshot
from academics.application.read_ports import AcademicSelfServiceReadRepository
from academics.domain.models import AcademicCalendarEvent
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from people.application.read_service import GUARDIAN_LINKED_READ
from people.application.read_service import STUDENT_SELF_READ
from people.application.read_service import TEACHER_ASSIGNED_READ


class AcademicSelfServiceReadService:
    """Expose bounded student, teacher, and guardian academic projections."""

    def __init__(
        self,
        repository: AcademicSelfServiceReadRepository,
    ) -> None:
        self._repository = repository

    async def student_snapshot(
        self,
        *,
        actor: TenantActorContext,
        student_profile_id: UUID,
    ) -> StudentAcademicSnapshot:
        """Return one owned or guardian-linked student's enrollment projection."""

        _require_any(actor, STUDENT_SELF_READ, GUARDIAN_LINKED_READ)
        return await self._repository.get_student_snapshot(
            organization_id=actor.organization_id,
            student_profile_id=student_profile_id,
        )

    async def teacher_sections(
        self,
        *,
        actor: TenantActorContext,
        teacher_profile_id: UUID,
    ) -> tuple[AcademicSectionSummary, ...]:
        """Return only sections assigned to the addressed teacher profile."""

        _require_any(actor, TEACHER_ASSIGNED_READ)
        return await self._repository.list_teacher_sections(
            organization_id=actor.organization_id,
            teacher_profile_id=teacher_profile_id,
        )

    async def assigned_section_student_ids(
        self,
        *,
        actor: TenantActorContext,
        teacher_profile_id: UUID,
        section_id: UUID,
    ) -> tuple[UUID, ...]:
        """Return roster IDs only after section-specific assignment validation."""

        _require_any(actor, TEACHER_ASSIGNED_READ)
        identifiers = await self._repository.list_section_student_profile_ids(
            organization_id=actor.organization_id,
            teacher_profile_id=teacher_profile_id,
            section_id=section_id,
        )
        if identifiers is None:
            raise NotFoundError("Assigned section was not found")
        return identifiers

    async def upcoming_events(
        self,
        *,
        actor: TenantActorContext,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return bounded organization calendar events for a student actor."""

        _require_any(actor, STUDENT_SELF_READ, GUARDIAN_LINKED_READ)
        return await self._repository.list_upcoming_events(
            organization_id=actor.organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    async def describe_sections(
        self,
        *,
        actor: TenantActorContext,
        section_ids: frozenset[UUID],
    ) -> tuple[AcademicSectionSummary, ...]:
        """Describe sections already authorized by a self-service query."""

        _require_any(actor, STUDENT_SELF_READ, TEACHER_ASSIGNED_READ)
        return await self._repository.list_sections_by_id(
            organization_id=actor.organization_id,
            section_ids=section_ids,
        )

    async def describe_courses(
        self,
        *,
        actor: TenantActorContext,
        course_ids: frozenset[UUID],
    ) -> tuple[AcademicCourseSummary, ...]:
        """Describe courses already authorized by an official-grade query."""

        _require_any(actor, STUDENT_SELF_READ, GUARDIAN_LINKED_READ)
        return await self._repository.list_courses_by_id(
            organization_id=actor.organization_id,
            course_ids=course_ids,
        )

    async def describe_rooms(
        self,
        *,
        actor: TenantActorContext,
        room_ids: frozenset[UUID],
    ) -> tuple[AcademicRoomSummary, ...]:
        """Describe rooms already authorized by an owned schedule query."""

        _require_any(actor, STUDENT_SELF_READ, TEACHER_ASSIGNED_READ)
        return await self._repository.list_rooms_by_id(
            organization_id=actor.organization_id,
            room_ids=room_ids,
        )


def _require_any(
    actor: TenantActorContext,
    *permissions: str,
) -> None:
    """Fail closed unless a tenant actor has one exact read permission."""

    if not isinstance(actor, TenantActorContext) or not any(
        permission in actor.permissions for permission in permissions
    ):
        raise AuthorizationError


__all__ = ["AcademicSelfServiceReadService"]
