"""Thin FastAPI routes for manual timetable and generation capabilities."""

from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
from typing import Annotated
from typing import cast
from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import Response
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from identity import ActorDep
from identity import CSRFDep
from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.service import TimetableService
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import DailyWindow
from scheduling.domain.models import RecurrenceRule
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationResult
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.models import TeacherAvailabilityWindow

PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]


class TeacherAvailabilityCreateBody(BaseModel):
    """Validate one explicit UTC teacher availability interval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    teacher_id: UUID
    starts_at: datetime
    ends_at: datetime


class TeacherAvailabilityResponse(BaseModel):
    """Serialize one tenant-owned availability window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    teacher_id: UUID
    starts_at: datetime
    ends_at: datetime

    @classmethod
    def from_domain(
        cls,
        window: TeacherAvailabilityWindow,
    ) -> TeacherAvailabilityResponse:
        """Map one validated window without exposing tenant internals."""

        return cls(
            id=window.id,
            teacher_id=window.teacher_id,
            starts_at=window.starts_at,
            ends_at=window.ends_at,
        )


class RecurrenceBody(BaseModel):
    """Validate a bounded weekly recurrence payload."""

    model_config = ConfigDict(frozen=True)

    interval_weeks: int = Field(ge=1, le=52)
    until: datetime


class SessionCreateBody(BaseModel):
    """Validate a manual timetable session payload."""

    model_config = ConfigDict(frozen=True)

    activity_id: UUID
    course_offering_id: UUID
    room_id: UUID
    teacher_ids: tuple[UUID, ...]
    group_ids: tuple[UUID, ...]
    required_group_ids: tuple[UUID, ...]
    starts_at: datetime
    ends_at: datetime
    activity_type: str = Field(min_length=1, max_length=64)
    required_room_type: str = Field(min_length=1, max_length=64)
    expected_attendance: int = Field(gt=0)
    recurrence: RecurrenceBody | None = None


class SessionMoveBody(BaseModel):
    """Validate drag-and-drop timetable movement data."""

    model_config = ConfigDict(frozen=True)

    starts_at: datetime
    ends_at: datetime
    version: int = Field(ge=0)


class SessionLockBody(BaseModel):
    """Validate whether generation must preserve a timetable session."""

    model_config = ConfigDict(frozen=True)

    locked: bool
    version: int = Field(ge=0)


class SessionResponse(BaseModel):
    """Serialize a supported timetable session representation."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    activity_id: UUID
    course_offering_id: UUID
    room_id: UUID
    teacher_ids: tuple[UUID, ...]
    group_ids: tuple[UUID, ...]
    required_group_ids: tuple[UUID, ...]
    starts_at: datetime
    ends_at: datetime
    activity_type: str
    required_room_type: str
    expected_attendance: int
    recurrence: RecurrenceBody | None
    locked: bool
    version: int

    @classmethod
    def from_domain(cls, session: ScheduledSession) -> SessionResponse:
        """Map a timetable session to an explicit response."""

        return cls(
            id=session.id,
            activity_id=session.activity_id,
            course_offering_id=session.course_offering_id,
            room_id=session.room_id,
            teacher_ids=session.teacher_ids,
            group_ids=session.group_ids,
            required_group_ids=session.required_group_ids,
            starts_at=session.starts_at,
            ends_at=session.ends_at,
            activity_type=session.activity_type,
            required_room_type=session.required_room_type,
            expected_attendance=session.expected_attendance,
            recurrence=(
                RecurrenceBody(
                    interval_weeks=session.recurrence.interval_weeks,
                    until=session.recurrence.until,
                )
                if session.recurrence is not None
                else None
            ),
            locked=session.locked,
            version=session.version,
        )


class ActivityRequestBody(BaseModel):
    """Validate one bounded generator activity request."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    course_offering_id: UUID
    teacher_ids: tuple[UUID, ...]
    group_ids: tuple[UUID, ...]
    required_group_ids: tuple[UUID, ...]
    activity_type: str = Field(min_length=1, max_length=64)
    required_room_type: str = Field(min_length=1, max_length=64)
    expected_attendance: int = Field(gt=0)
    duration_minutes: int = Field(gt=0, le=720)
    sessions_required: int = Field(gt=0, le=14)


class CandidateSlotBody(BaseModel):
    """Validate one bounded generator candidate interval."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    starts_at: datetime
    ends_at: datetime


class PreferredHoursBody(BaseModel):
    """Validate one preferred weekday wall-clock window."""

    model_config = ConfigDict(frozen=True)

    weekday: int = Field(ge=1, le=7)
    starts_at: time
    ends_at: time


class GenerationBody(BaseModel):
    """Validate deterministic generator inputs while resources remain server-owned."""

    model_config = ConfigDict(frozen=True)

    activities: tuple[ActivityRequestBody, ...] = Field(min_length=1)
    candidate_slots: tuple[CandidateSlotBody, ...] = Field(min_length=1)
    locked_session_ids: frozenset[UUID] = frozenset()
    maximum_consecutive_sessions: int = Field(gt=0, le=12)
    consecutive_break_minutes: int = Field(ge=0, le=240)
    preferred_gap_minutes: int = Field(ge=0, le=720)
    preferred_hours: tuple[PreferredHoursBody, ...] = ()


class GenerationResultResponse(BaseModel):
    """Serialize proposals, unresolved conflicts, violations, and quality score."""

    model_config = ConfigDict(frozen=True)

    proposed_sessions: tuple[SessionResponse, ...]
    unresolved_hard_conflicts: tuple[str, ...]
    soft_constraint_violations: tuple[str, ...]
    quality_score: Decimal
    explanation: str
    locked_session_ids: frozenset[UUID]
    expected_versions: dict[UUID, int]

    @classmethod
    def from_domain(
        cls,
        result: ScheduleGenerationResult,
    ) -> GenerationResultResponse:
        """Map a generator result to an explicit response."""

        return cls(
            proposed_sessions=tuple(
                SessionResponse.from_domain(session)
                for session in result.proposed_sessions
            ),
            unresolved_hard_conflicts=tuple(
                conflict.code for conflict in result.unresolved_hard_conflicts
            ),
            soft_constraint_violations=tuple(
                violation.code for violation in result.soft_constraint_violations
            ),
            quality_score=result.quality_score,
            explanation=result.explanation,
            locked_session_ids=result.locked_session_ids,
            expected_versions=dict(result.expected_versions),
        )


class SessionProposalBody(SessionCreateBody):
    """Validate one complete versioned session in a generated proposal."""

    id: UUID
    locked: bool = False
    version: int = Field(ge=0)


class GenerationApplyBody(BaseModel):
    """Bind a proposal to the exact timetable version snapshot it used."""

    model_config = ConfigDict(frozen=True)

    proposed_sessions: tuple[SessionProposalBody, ...] = Field(min_length=1)
    locked_session_ids: frozenset[UUID] = frozenset()
    expected_versions: dict[UUID, int]


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    """Require a verified tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError("A tenant actor is required.")
    return actor


def _timetable_service(request: Request) -> TimetableService:
    """Resolve the explicitly composed timetable application service."""

    service: object = getattr(request.app.state, "timetable_service", None)
    if not isinstance(service, TimetableService):
        raise RuntimeError("TimetableService was not composed.")
    return service


def _teacher_availability_service(request: Request) -> TeacherAvailabilityService:
    """Resolve the explicitly composed availability application service."""

    service: object = getattr(
        request.app.state,
        "teacher_availability_service",
        None,
    )
    if not isinstance(service, TeacherAvailabilityService):
        raise RuntimeError("TeacherAvailabilityService was not composed.")
    return service


def _proposal_session(
    *,
    context: TenantActorContext,
    body: SessionProposalBody,
) -> ScheduledSession:
    """Translate a typed proposal payload into a tenant-owned domain value."""

    return ScheduledSession(
        id=body.id,
        organization_id=context.organization_id,
        activity_id=body.activity_id,
        course_offering_id=body.course_offering_id,
        room_id=body.room_id,
        teacher_ids=body.teacher_ids,
        group_ids=body.group_ids,
        required_group_ids=body.required_group_ids,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        activity_type=body.activity_type,
        required_room_type=body.required_room_type,
        expected_attendance=body.expected_attendance,
        recurrence=(
            RecurrenceRule(
                interval_weeks=body.recurrence.interval_weeks,
                until=body.recurrence.until,
            )
            if body.recurrence is not None
            else None
        ),
        locked=body.locked,
        version=body.version,
    )


router = APIRouter(prefix="/api/v1/scheduling", tags=["scheduling"])


@router.post(
    "/teacher-availability",
    response_model=TeacherAvailabilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability(
    body: TeacherAvailabilityCreateBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> TeacherAvailabilityResponse:
    """Create one tenant teacher availability interval."""

    context = _tenant_actor(actor)
    window = await _teacher_availability_service(request).create_window(
        context=context,
        window=TeacherAvailabilityWindow(
            id=new_uuid7(),
            organization_id=context.organization_id,
            teacher_id=body.teacher_id,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
        ),
    )
    return TeacherAvailabilityResponse.from_domain(window)


@router.get(
    "/teacher-availability",
    response_model=tuple[TeacherAvailabilityResponse, ...],
)
async def list_teacher_availability(
    starts_at: datetime,
    ends_at: datetime,
    request: Request,
    actor: ActorDep,
    teacher_id: UUID | None = None,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> tuple[TeacherAvailabilityResponse, ...]:
    """List bounded tenant availability windows for administration."""

    windows = await _teacher_availability_service(request).list_windows(
        context=_tenant_actor(actor),
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=ends_at,
        limit=limit,
        offset=offset,
    )
    return tuple(TeacherAvailabilityResponse.from_domain(window) for window in windows)


@router.delete(
    "/teacher-availability/{window_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_teacher_availability(
    window_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> Response:
    """Delete one exact tenant-owned teacher availability interval."""

    await _teacher_availability_service(request).delete_window(
        context=_tenant_actor(actor),
        window_id=window_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: SessionCreateBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> SessionResponse:
    """Create a manual timetable session with immediate conflict feedback."""

    context = _tenant_actor(actor)
    recurrence = (
        RecurrenceRule(
            interval_weeks=body.recurrence.interval_weeks,
            until=body.recurrence.until,
        )
        if body.recurrence is not None
        else None
    )
    session = await _timetable_service(request).create_session(
        context=context,
        session=ScheduledSession(
            id=new_uuid7(),
            organization_id=context.organization_id,
            activity_id=body.activity_id,
            course_offering_id=body.course_offering_id,
            room_id=body.room_id,
            teacher_ids=body.teacher_ids,
            group_ids=body.group_ids,
            required_group_ids=body.required_group_ids,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            activity_type=body.activity_type,
            required_room_type=body.required_room_type,
            expected_attendance=body.expected_attendance,
            recurrence=recurrence,
        ),
    )
    return SessionResponse.from_domain(session)


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def move_session(
    session_id: UUID,
    body: SessionMoveBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> SessionResponse:
    """Move a timetable session for drag-and-drop editing."""

    session = await _timetable_service(request).move_session(
        context=_tenant_actor(actor),
        session_id=session_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        expected_version=body.version,
    )
    return SessionResponse.from_domain(session)


@router.get("/sessions", response_model=tuple[SessionResponse, ...])
async def list_sessions(
    week_start: date,
    request: Request,
    actor: ActorDep,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> tuple[SessionResponse, ...]:
    """Return sessions intersecting the requested seven-day UTC window."""

    starts_at = datetime.combine(week_start, time.min, tzinfo=UTC)
    ends_at = starts_at + timedelta(days=7)
    sessions = await _timetable_service(request).list_sessions_window(
        context=_tenant_actor(actor),
        starts_at=starts_at,
        ends_at=ends_at,
        limit=limit,
        offset=offset,
    )
    return tuple(SessionResponse.from_domain(session) for session in sessions)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    request: Request,
    actor: ActorDep,
) -> SessionResponse:
    """Return one exact tenant timetable session."""

    session = await _timetable_service(request).get_session(
        context=_tenant_actor(actor),
        session_id=session_id,
    )
    return SessionResponse.from_domain(session)


@router.patch("/sessions/{session_id}/lock", response_model=SessionResponse)
async def set_session_lock(
    session_id: UUID,
    body: SessionLockBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> SessionResponse:
    """Set whether regeneration must preserve a session."""

    session = await _timetable_service(request).set_session_lock(
        context=_tenant_actor(actor),
        session_id=session_id,
        locked=body.locked,
        expected_version=body.version,
    )
    return SessionResponse.from_domain(session)


@router.post("/generate", response_model=GenerationResultResponse)
async def generate_schedule(
    body: GenerationBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> GenerationResultResponse:
    """Generate a deterministic proposal from bounded candidate inputs."""

    context = _tenant_actor(actor)
    result = await _timetable_service(request).generate(
        context=context,
        activities=tuple(
            ActivityRequest(
                id=activity.id,
                organization_id=context.organization_id,
                course_offering_id=activity.course_offering_id,
                teacher_ids=activity.teacher_ids,
                group_ids=activity.group_ids,
                required_group_ids=activity.required_group_ids,
                activity_type=activity.activity_type,
                required_room_type=activity.required_room_type,
                expected_attendance=activity.expected_attendance,
                duration=timedelta(minutes=activity.duration_minutes),
                sessions_required=activity.sessions_required,
            )
            for activity in body.activities
        ),
        candidate_slots=tuple(
            CandidateSlot(
                id=slot.id,
                organization_id=context.organization_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
            )
            for slot in body.candidate_slots
        ),
        locked_session_ids=body.locked_session_ids,
        policy=SchedulingPolicy(
            maximum_consecutive_sessions=body.maximum_consecutive_sessions,
            consecutive_break_threshold=timedelta(
                minutes=body.consecutive_break_minutes
            ),
            preferred_gap_limit=timedelta(minutes=body.preferred_gap_minutes),
            preferred_hours=tuple(
                DailyWindow(
                    weekday=window.weekday,
                    starts_at=window.starts_at,
                    ends_at=window.ends_at,
                )
                for window in body.preferred_hours
            ),
            penalty_per_violation=Decimal(5),
        ),
    )
    return GenerationResultResponse.from_domain(result)


@router.post(
    "/generation/apply",
    response_model=tuple[SessionResponse, ...],
)
async def apply_generation(
    body: GenerationApplyBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> tuple[SessionResponse, ...]:
    """Revalidate and atomically apply one version-bound generated proposal."""

    context = _tenant_actor(actor)
    proposed = tuple(
        _proposal_session(context=context, body=session)
        for session in body.proposed_sessions
    )
    await _timetable_service(request).apply_proposal(
        context=context,
        proposed_sessions=proposed,
        locked_session_ids=body.locked_session_ids,
        expected_versions=body.expected_versions,
    )
    return tuple(SessionResponse.from_domain(session) for session in proposed)


cast(object, create_session)
cast(object, create_teacher_availability)
cast(object, delete_teacher_availability)
cast(object, list_sessions)
cast(object, list_teacher_availability)
cast(object, move_session)
cast(object, set_session_lock)
cast(object, generate_schedule)
cast(object, apply_generation)

__all__ = [
    "CandidateSlotBody",
    "GenerationApplyBody",
    "GenerationBody",
    "GenerationResultResponse",
    "SessionCreateBody",
    "SessionLockBody",
    "SessionMoveBody",
    "SessionProposalBody",
    "SessionResponse",
    "TeacherAvailabilityCreateBody",
    "TeacherAvailabilityResponse",
    "list_sessions",
    "router",
]
