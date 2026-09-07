"""Stable academic reference boundary for collaborating application modules."""

from datetime import datetime
from datetime import timedelta
from uuid import UUID

from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicInstructionWindow
from academics.application.contracts import AcademicSchedulingReferences
from academics.application.contracts import AcademicSchedulingRoom
from academics.application.ports import AcademicReferenceRepository
from academics.domain.exceptions import AcademicRuleError
from academics.domain.models import AcademicCalendarEvent
from core.errors import NotFoundError

MAX_SCHEDULING_REFERENCE_HORIZON = timedelta(weeks=52)


class AcademicReferenceService:
    """Expose tenant-scoped academic facts without sharing internal aggregates."""

    def __init__(self, *, repository: AcademicReferenceRepository) -> None:
        self._repository = repository

    async def admissions_target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Validate a program and first-release intake-as-term reference pair."""

        return await self._repository.admissions_target_exists(
            organization_id=organization_id,
            program_id=program_id,
            intake_id=intake_id,
        )

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> AcademicGradeTarget | None:
        """Resolve official joined facts required by grading."""

        return await self._repository.get_grade_target(
            organization_id=organization_id,
            course_enrollment_id=course_enrollment_id,
        )

    async def is_term_closed(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool:
        """Return official term closure and fail closed for unknown terms."""

        closed = await self._repository.get_term_closure(
            organization_id=organization_id,
            term_id=term_id,
        )
        if closed is None:
            raise NotFoundError("Academic term was not found.")
        return closed

    async def scheduling_references(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> AcademicSchedulingReferences:
        """Return rooms and clipped instruction windows for a bounded horizon."""

        _validate_horizon(starts_at=starts_at, ends_at=ends_at)
        rooms = await self._repository.list_rooms(organization_id=organization_id)
        events = await self._repository.list_calendar_events(
            organization_id=organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        return AcademicSchedulingReferences(
            organization_id=organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
            rooms=tuple(
                AcademicSchedulingRoom(
                    organization_id=room.organization_id,
                    room_id=room.id,
                    campus_id=room.campus_id,
                    room_type=room.room_type,
                    capacity=room.capacity,
                )
                for room in rooms
            ),
            instruction_windows=_instruction_windows(
                events=events,
                starts_at=starts_at,
                ends_at=ends_at,
            ),
        )


def _validate_horizon(*, starts_at: datetime, ends_at: datetime) -> None:
    """Require a timezone-aware, increasing scheduling query interval."""

    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise AcademicRuleError("Scheduling horizon start must be timezone-aware.")
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise AcademicRuleError("Scheduling horizon end must be timezone-aware.")
    if starts_at >= ends_at:
        raise AcademicRuleError("Scheduling horizon end must follow its start.")
    if ends_at - starts_at > MAX_SCHEDULING_REFERENCE_HORIZON:
        raise AcademicRuleError("Scheduling horizon cannot exceed 52 weeks.")


def _instruction_windows(
    *,
    events: tuple[AcademicCalendarEvent, ...],
    starts_at: datetime,
    ends_at: datetime,
) -> tuple[AcademicInstructionWindow, ...]:
    """Clip allowed events, subtract closures, and merge remaining intervals."""

    allowed = [
        (max(event.starts_at, starts_at), min(event.ends_at, ends_at))
        for event in events
        if event.instruction_allowed
    ]
    blocked = tuple(
        (max(event.starts_at, starts_at), min(event.ends_at, ends_at))
        for event in events
        if not event.instruction_allowed
    )
    segments: list[tuple[datetime, datetime]] = []
    for allowed_start, allowed_end in allowed:
        current = [(allowed_start, allowed_end)]
        for blocked_start, blocked_end in blocked:
            next_segments: list[tuple[datetime, datetime]] = []
            for segment_start, segment_end in current:
                if blocked_end <= segment_start or blocked_start >= segment_end:
                    next_segments.append((segment_start, segment_end))
                    continue
                if blocked_start > segment_start:
                    next_segments.append((segment_start, blocked_start))
                if blocked_end < segment_end:
                    next_segments.append((blocked_end, segment_end))
            current = next_segments
        segments.extend(current)
    merged: list[tuple[datetime, datetime]] = []
    for segment_start, segment_end in sorted(segments):
        if segment_start >= segment_end:
            continue
        if not merged or segment_start > merged[-1][1]:
            merged.append((segment_start, segment_end))
            continue
        prior_start, prior_end = merged[-1]
        merged[-1] = (prior_start, max(prior_end, segment_end))
    return tuple(
        AcademicInstructionWindow(starts_at=start, ends_at=end) for start, end in merged
    )


__all__ = ["MAX_SCHEDULING_REFERENCE_HORIZON", "AcademicReferenceService"]
