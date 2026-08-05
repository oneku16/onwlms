"""Typed cookie-session routes over shared ownership-safe read policies."""

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict

from core.context import ActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from mcp_gateway.domain.read_models import GradeSummary


class ScheduleItemResponse(BaseModel):
    """Serialize one ownership-filtered scheduled session."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    room_name: str | None


class ProfileSummaryResponse(BaseModel):
    """Serialize only the current student's own minimum profile identity."""

    model_config = ConfigDict(extra="forbid")

    person_id: UUID
    display_name: str
    institutional_reference: str | None


class GradeSummaryResponse(BaseModel):
    """Serialize one current official result without revision internals."""

    model_config = ConfigDict(extra="forbid")

    course_code: str
    course_title: str
    display_grade: str
    credits_attempted: str
    credits_earned: str
    grade_points: str | None


class GpaSummaryResponse(BaseModel):
    """Serialize exact string-valued official GPA totals."""

    model_config = ConfigDict(extra="forbid")

    credits_attempted: str
    credits_earned: str
    gpa_credits_attempted: str
    quality_points: str
    gpa: str | None


class UpcomingEventResponse(BaseModel):
    """Serialize one visible upcoming academic event."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime


class MoodleDeadlineResponse(BaseModel):
    """Serialize deadline evidence with freshness metadata."""

    model_config = ConfigDict(extra="forbid")

    external_reference: str
    title: str
    due_at: datetime
    observed_at: datetime
    source_version: str


class AssignedSectionResponse(BaseModel):
    """Serialize one section assigned to the authenticated teacher."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_code: str
    section_name: str
    term_name: str


class SectionStudentResponse(BaseModel):
    """Serialize only the minimum roster identity fields."""

    model_config = ConfigDict(extra="forbid")

    person_id: UUID
    display_name: str
    institutional_reference: str | None


class GradeSyncResponse(BaseModel):
    """Serialize privacy-safe Moodle grade evidence status."""

    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    status: str
    last_observed_at: datetime | None
    unresolved_count: int


class GuardianStudentResponse(BaseModel):
    """Serialize one explicitly linked student's high-level summary."""

    model_config = ConfigDict(extra="forbid")

    student_person_id: UUID
    display_name: str
    current_program: str | None
    latest_official_grades: tuple[GradeSummaryResponse, ...]


def create_self_service_router(
    *,
    service: ActorOwnedReadService,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
) -> APIRouter:
    """Create typed portal routes with an injected cookie-session actor resolver."""

    router = APIRouter(prefix="/api/v1/self-service", tags=["self-service"])

    @router.get("/student/schedule")
    async def student_schedule(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[ScheduleItemResponse]:
        """Return only the current student's official timetable sessions."""

        values = await service.student_schedule(actor=_tenant_actor(actor))
        return [
            ScheduleItemResponse(
                id=value.id,
                title=value.title,
                starts_at=value.starts_at,
                ends_at=value.ends_at,
                room_name=value.room_name,
            )
            for value in values
        ]

    @router.get("/student/profile")
    async def student_profile(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> ProfileSummaryResponse:
        """Return the current student's own minimum profile summary."""

        value = await service.student_profile(actor=_tenant_actor(actor))
        return ProfileSummaryResponse(
            person_id=value.person_id,
            display_name=value.display_name,
            institutional_reference=value.institutional_reference,
        )

    @router.get("/student/official-grades")
    async def student_official_grades(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[GradeSummaryResponse]:
        """Return only the current student's official grade state."""

        values = await service.student_grades(actor=_tenant_actor(actor))
        return [_grade_response(value) for value in values]

    @router.get("/student/gpa")
    async def student_gpa(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> GpaSummaryResponse:
        """Return official cumulative GPA and credit totals."""

        value = await service.student_gpa(actor=_tenant_actor(actor))
        return GpaSummaryResponse(
            credits_attempted=value.credits_attempted,
            credits_earned=value.credits_earned,
            gpa_credits_attempted=value.gpa_credits_attempted,
            quality_points=value.quality_points,
            gpa=value.gpa,
        )

    @router.get("/student/upcoming-events")
    async def student_upcoming_events(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[UpcomingEventResponse]:
        """Return a bounded upcoming academic calendar."""

        values = await service.student_events(actor=_tenant_actor(actor))
        return [
            UpcomingEventResponse(
                id=value.id,
                title=value.title,
                starts_at=value.starts_at,
                ends_at=value.ends_at,
            )
            for value in values
        ]

    @router.get("/student/moodle-deadlines")
    async def student_moodle_deadlines(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[MoodleDeadlineResponse]:
        """Return Moodle deadline evidence for the current mapped person."""

        values = await service.student_moodle_deadlines(actor=_tenant_actor(actor))
        return [
            MoodleDeadlineResponse(
                external_reference=value.external_reference,
                title=value.title,
                due_at=value.due_at,
                observed_at=value.observed_at,
                source_version=value.source_version,
            )
            for value in values
        ]

    @router.get("/teacher/schedule")
    async def teacher_schedule(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[ScheduleItemResponse]:
        """Return only sessions assigned to the current teacher profile."""

        values = await service.teacher_schedule(actor=_tenant_actor(actor))
        return [
            ScheduleItemResponse(
                id=value.id,
                title=value.title,
                starts_at=value.starts_at,
                ends_at=value.ends_at,
                room_name=value.room_name,
            )
            for value in values
        ]

    @router.get("/teacher/assigned-sections")
    async def teacher_assigned_sections(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[AssignedSectionResponse]:
        """Return only sections assigned to the current teacher profile."""

        values = await service.teacher_sections(actor=_tenant_actor(actor))
        return [
            AssignedSectionResponse(
                id=value.id,
                course_code=value.course_code,
                section_name=value.section_name,
                term_name=value.term_name,
            )
            for value in values
        ]

    @router.get("/teacher/assigned-sections/{section_id}/students")
    async def teacher_section_students(
        section_id: UUID,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[SectionStudentResponse]:
        """Return a minimum roster after section-specific assignment checks."""

        values = await service.section_students(
            actor=_tenant_actor(actor),
            section_id=section_id,
        )
        return [
            SectionStudentResponse(
                person_id=value.person_id,
                display_name=value.display_name,
                institutional_reference=value.institutional_reference,
            )
            for value in values
        ]

    @router.get("/teacher/grade-synchronization")
    async def teacher_grade_synchronization(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[GradeSyncResponse]:
        """Return synchronization status only for assigned sections."""

        values = await service.teacher_grade_sync_status(actor=_tenant_actor(actor))
        return [
            GradeSyncResponse(
                section_id=value.section_id,
                status=value.status,
                last_observed_at=value.last_observed_at,
                unresolved_count=value.unresolved_count,
            )
            for value in values
        ]

    @router.get("/teacher/moodle-deadlines")
    async def teacher_moodle_deadlines(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[MoodleDeadlineResponse]:
        """Return Moodle deadlines for the current mapped teacher person."""

        values = await service.teacher_moodle_deadlines(actor=_tenant_actor(actor))
        return [
            MoodleDeadlineResponse(
                external_reference=value.external_reference,
                title=value.title,
                due_at=value.due_at,
                observed_at=value.observed_at,
                source_version=value.source_version,
            )
            for value in values
        ]

    @router.get("/guardian/upcoming-events")
    async def guardian_upcoming_events(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[UpcomingEventResponse]:
        """Return upcoming organization events for a verified guardian."""

        values = await service.guardian_events(actor=_tenant_actor(actor))
        return [
            UpcomingEventResponse(
                id=value.id,
                title=value.title,
                starts_at=value.starts_at,
                ends_at=value.ends_at,
            )
            for value in values
        ]

    @router.get("/guardian/linked-students")
    async def guardian_linked_students(
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[GuardianStudentResponse]:
        """Return only explicitly linked student summaries."""

        values = await service.guardian_students(actor=_tenant_actor(actor))
        return [
            GuardianStudentResponse(
                student_person_id=value.student_person_id,
                display_name=value.display_name,
                current_program=value.current_program,
                latest_official_grades=tuple(
                    _grade_response(grade) for grade in value.latest_official_grades
                ),
            )
            for value in values
        ]

    return router


def _tenant_actor(actor: ActorContext) -> TenantActorContext:
    """Reject platform context on role-specific organization self-service routes."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _grade_response(value: GradeSummary) -> GradeSummaryResponse:
    """Serialize one explicit grade read model."""

    return GradeSummaryResponse(
        course_code=value.course_code,
        course_title=value.course_title,
        display_grade=value.display_grade,
        credits_attempted=value.credits_attempted,
        credits_earned=value.credits_earned,
        grade_points=value.grade_points,
    )


__all__ = [
    "AssignedSectionResponse",
    "GpaSummaryResponse",
    "GradeSummaryResponse",
    "GradeSyncResponse",
    "GuardianStudentResponse",
    "MoodleDeadlineResponse",
    "ProfileSummaryResponse",
    "ScheduleItemResponse",
    "SectionStudentResponse",
    "UpcomingEventResponse",
    "create_self_service_router",
]
