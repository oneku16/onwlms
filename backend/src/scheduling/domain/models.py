"""Framework-independent timetable, constraint, and generation models."""

from dataclasses import dataclass
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from scheduling.domain.exceptions import SchedulingRuleError

MAX_RECURRENCE_SPAN = timedelta(days=370)
MAX_TEACHER_AVAILABILITY_SPAN = timedelta(days=370)


class HardConstraintCode(StrEnum):
    """Identify an unsatisfied timetable requirement."""

    ACADEMIC_CALENDAR = "academic_calendar"
    REQUIRED_GROUP_OVERLAP = "required_group_overlap"
    ROOM_CAPACITY = "room_capacity"
    ROOM_OVERLAP = "room_overlap"
    ROOM_TYPE = "room_type"
    TEACHER_OVERLAP = "teacher_overlap"
    TEACHER_UNAVAILABLE = "teacher_unavailable"
    UNKNOWN_RESOURCE = "unknown_resource"
    UNSCHEDULED_ACTIVITY = "unscheduled_activity"


class SoftConstraintCode(StrEnum):
    """Identify a timetable quality preference violation."""

    MAXIMUM_CONSECUTIVE = "maximum_consecutive"
    PREFERRED_HOURS = "preferred_hours"
    STUDENT_GAP = "student_gap"
    TEACHER_GAP = "teacher_gap"
    WEEKLY_BALANCE = "weekly_balance"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Represent one timezone-aware interval available for instruction."""

    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        """Require a timezone-aware increasing interval."""

        _require_aware(self.starts_at, "Time-window start")
        _require_aware(self.ends_at, "Time-window end")
        if self.starts_at >= self.ends_at:
            raise SchedulingRuleError("Time-window end must follow its start.")

    def contains(self, other: TimeWindow) -> bool:
        """Return whether this interval fully contains another interval."""

        return self.starts_at <= other.starts_at and self.ends_at >= other.ends_at

    def overlaps(self, other: TimeWindow) -> bool:
        """Return whether two half-open intervals overlap."""

        return self.starts_at < other.ends_at and other.starts_at < self.ends_at


@dataclass(frozen=True, slots=True)
class DailyWindow:
    """Represent preferred local wall-clock hours on one ISO weekday."""

    weekday: int
    starts_at: time
    ends_at: time

    def __post_init__(self) -> None:
        """Require an ISO weekday and increasing times."""

        if self.weekday < 1 or self.weekday > 7:
            raise SchedulingRuleError("Daily-window weekday must be 1 through 7.")
        if self.starts_at >= self.ends_at:
            raise SchedulingRuleError("Daily-window end must follow its start.")

    def contains(self, occurrence: TimeWindow) -> bool:
        """Return whether an occurrence falls inside the preferred local hours."""

        return (
            occurrence.starts_at.isoweekday() == self.weekday
            and occurrence.starts_at.timetz().replace(tzinfo=None) >= self.starts_at
            and occurrence.ends_at.timetz().replace(tzinfo=None) <= self.ends_at
        )


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """Represent a bounded weekly recurrence for a scheduled session."""

    interval_weeks: int
    until: datetime

    def __post_init__(self) -> None:
        """Require a positive recurrence interval and aware boundary."""

        if self.interval_weeks <= 0:
            raise SchedulingRuleError("Recurrence interval must be positive.")
        _require_aware(self.until, "Recurrence boundary")


@dataclass(frozen=True, slots=True)
class RoomSpecification:
    """Describe the room facts scheduling may consume from academics."""

    organization_id: UUID
    room_id: UUID
    room_type: str
    capacity: int

    def __post_init__(self) -> None:
        """Require a room type and positive capacity."""

        if not self.room_type.strip():
            raise SchedulingRuleError("Room type is required.")
        if self.capacity <= 0:
            raise SchedulingRuleError("Room capacity must be positive.")


@dataclass(frozen=True, slots=True)
class TeacherAvailability:
    """Describe when one organization teacher is available."""

    organization_id: UUID
    teacher_id: UUID
    windows: tuple[TimeWindow, ...]


@dataclass(frozen=True, slots=True)
class TeacherAvailabilityWindow:
    """Persist one explicit UTC interval owned by Scheduling."""

    id: UUID
    organization_id: UUID
    teacher_id: UUID
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        """Require an increasing, bounded UTC interval."""

        _require_utc(self.starts_at, "Teacher-availability start")
        _require_utc(self.ends_at, "Teacher-availability end")
        if self.starts_at >= self.ends_at:
            raise SchedulingRuleError("Teacher-availability end must follow its start.")
        if self.ends_at - self.starts_at > MAX_TEACHER_AVAILABILITY_SPAN:
            raise SchedulingRuleError(
                "Teacher-availability window exceeds the supported span."
            )

    def as_time_window(self) -> TimeWindow:
        """Return the constraint-engine interval representation."""

        return TimeWindow(starts_at=self.starts_at, ends_at=self.ends_at)


@dataclass(frozen=True, slots=True)
class ScheduledSession:
    """Represent one manual or generated timetable lesson/session."""

    id: UUID
    organization_id: UUID
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
    recurrence: RecurrenceRule | None = None
    locked: bool = False
    version: int = 0

    def __post_init__(self) -> None:
        """Require coherent resources, interval, attendance, and version."""

        _require_aware(self.starts_at, "Session start")
        _require_aware(self.ends_at, "Session end")
        if self.starts_at >= self.ends_at:
            raise SchedulingRuleError("Session end must follow its start.")
        if not self.activity_type.strip() or not self.required_room_type.strip():
            raise SchedulingRuleError("Activity and required room types are required.")
        if self.expected_attendance <= 0:
            raise SchedulingRuleError("Expected attendance must be positive.")
        if len(self.teacher_ids) != len(set(self.teacher_ids)):
            raise SchedulingRuleError("A teacher cannot be assigned twice.")
        if len(self.group_ids) != len(set(self.group_ids)):
            raise SchedulingRuleError("A group cannot be assigned twice.")
        if not set(self.required_group_ids).issubset(self.group_ids):
            raise SchedulingRuleError("Required groups must be assigned groups.")
        if self.version < 0:
            raise SchedulingRuleError("Session version cannot be negative.")
        if self.recurrence is not None:
            if self.recurrence.until < self.starts_at:
                raise SchedulingRuleError("Recurrence cannot end before its session.")
            if self.recurrence.until - self.starts_at > MAX_RECURRENCE_SPAN:
                raise SchedulingRuleError("Recurrence exceeds the supported span.")

    def occurrences(self) -> tuple[TimeWindow, ...]:
        """Expand a bounded weekly recurrence into deterministic intervals."""

        duration = self.ends_at - self.starts_at
        if self.recurrence is None:
            return (TimeWindow(self.starts_at, self.ends_at),)
        step = timedelta(weeks=self.recurrence.interval_weeks)
        occurrence_start = self.starts_at
        occurrences: list[TimeWindow] = []
        while occurrence_start <= self.recurrence.until:
            occurrences.append(
                TimeWindow(
                    starts_at=occurrence_start,
                    ends_at=occurrence_start + duration,
                )
            )
            occurrence_start += step
        return tuple(occurrences)


@dataclass(frozen=True, slots=True)
class HardConflict:
    """Describe one deterministic unsatisfied hard constraint."""

    code: HardConstraintCode
    session_ids: tuple[UUID, ...]
    resource_id: UUID | None
    explanation: str


@dataclass(frozen=True, slots=True)
class SoftConstraintViolation:
    """Describe one preference violation used for schedule scoring."""

    code: SoftConstraintCode
    session_ids: tuple[UUID, ...]
    resource_id: UUID | None
    penalty: Decimal
    explanation: str

    def __post_init__(self) -> None:
        """Require a strictly positive schedule-quality penalty."""

        if self.penalty <= Decimal(0):
            raise SchedulingRuleError("Soft-constraint penalty must be positive.")


@dataclass(frozen=True, slots=True)
class ConstraintContext:
    """Provide tenant room, teacher, and calendar facts to the constraint engine."""

    organization_id: UUID
    rooms: tuple[RoomSpecification, ...]
    teacher_availability: tuple[TeacherAvailability, ...]
    academic_calendar_windows: tuple[TimeWindow, ...]

    def __post_init__(self) -> None:
        """Reject context resources from another tenant or duplicate rooms."""

        room_ids = [room.room_id for room in self.rooms]
        if len(room_ids) != len(set(room_ids)):
            raise SchedulingRuleError("Constraint context has duplicate rooms.")
        teacher_ids = [
            availability.teacher_id for availability in self.teacher_availability
        ]
        if len(teacher_ids) != len(set(teacher_ids)):
            raise SchedulingRuleError(
                "Constraint context has duplicate teacher availability."
            )
        if any(room.organization_id != self.organization_id for room in self.rooms):
            raise SchedulingRuleError("Room context tenant does not match.")
        if any(
            availability.organization_id != self.organization_id
            for availability in self.teacher_availability
        ):
            raise SchedulingRuleError("Teacher availability tenant does not match.")

    def room(self, room_id: UUID) -> RoomSpecification | None:
        """Return one room specification by stable identifier."""

        return next((room for room in self.rooms if room.room_id == room_id), None)

    def teacher_windows(self, teacher_id: UUID) -> tuple[TimeWindow, ...]:
        """Return all declared availability windows for one teacher."""

        return tuple(
            window
            for availability in self.teacher_availability
            if availability.teacher_id == teacher_id
            for window in availability.windows
        )


@dataclass(frozen=True, slots=True)
class SchedulingPolicy:
    """Configure soft scheduling preferences and penalty weights."""

    maximum_consecutive_sessions: int
    consecutive_break_threshold: timedelta
    preferred_gap_limit: timedelta
    preferred_hours: tuple[DailyWindow, ...]
    penalty_per_violation: Decimal = Decimal(5)

    def __post_init__(self) -> None:
        """Require positive counts, durations, and penalty."""

        if self.maximum_consecutive_sessions <= 0:
            raise SchedulingRuleError("Maximum consecutive sessions must be positive.")
        if self.consecutive_break_threshold < timedelta(0):
            raise SchedulingRuleError("Consecutive break threshold cannot be negative.")
        if self.preferred_gap_limit < timedelta(0):
            raise SchedulingRuleError("Preferred gap limit cannot be negative.")
        if self.penalty_per_violation <= Decimal(0):
            raise SchedulingRuleError("Soft-constraint penalty must be positive.")


@dataclass(frozen=True, slots=True)
class ActivityRequest:
    """Describe one activity that a schedule generator must place."""

    id: UUID
    organization_id: UUID
    course_offering_id: UUID
    teacher_ids: tuple[UUID, ...]
    group_ids: tuple[UUID, ...]
    required_group_ids: tuple[UUID, ...]
    activity_type: str
    required_room_type: str
    expected_attendance: int
    duration: timedelta
    sessions_required: int

    def __post_init__(self) -> None:
        """Require a bounded duration, attendance, and session count."""

        if self.duration <= timedelta(0) or self.duration > timedelta(hours=12):
            raise SchedulingRuleError("Activity duration is outside supported bounds.")
        if self.sessions_required <= 0 or self.sessions_required > 14:
            raise SchedulingRuleError("Activity session count is outside bounds.")
        if self.expected_attendance <= 0:
            raise SchedulingRuleError("Expected attendance must be positive.")
        if not set(self.required_group_ids).issubset(self.group_ids):
            raise SchedulingRuleError("Required groups must be assigned groups.")
        if not self.activity_type.strip() or not self.required_room_type.strip():
            raise SchedulingRuleError("Activity and room types are required.")


@dataclass(frozen=True, slots=True)
class CandidateSlot:
    """Represent one deterministic candidate start and maximum interval."""

    id: UUID
    organization_id: UUID
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        """Require a timezone-aware increasing candidate interval."""

        _require_aware(self.starts_at, "Candidate-slot start")
        _require_aware(self.ends_at, "Candidate-slot end")
        if self.starts_at >= self.ends_at:
            raise SchedulingRuleError("Candidate-slot end must follow its start.")


@dataclass(frozen=True, slots=True)
class ScheduleGenerationRequest:
    """Provide complete bounded input to a replaceable schedule generator."""

    organization_id: UUID
    activities: tuple[ActivityRequest, ...]
    candidate_slots: tuple[CandidateSlot, ...]
    existing_sessions: tuple[ScheduledSession, ...]
    locked_session_ids: frozenset[UUID]
    constraints: ConstraintContext
    policy: SchedulingPolicy

    def __post_init__(self) -> None:
        """Reject tenant mismatch, unknown locks, and duplicate activity identifiers."""

        if self.constraints.organization_id != self.organization_id:
            raise SchedulingRuleError("Constraint tenant does not match request.")
        if any(
            activity.organization_id != self.organization_id
            for activity in self.activities
        ):
            raise SchedulingRuleError("Activity tenant does not match request.")
        if any(
            slot.organization_id != self.organization_id
            for slot in self.candidate_slots
        ):
            raise SchedulingRuleError("Candidate-slot tenant does not match request.")
        if any(
            session.organization_id != self.organization_id
            for session in self.existing_sessions
        ):
            raise SchedulingRuleError("Existing-session tenant does not match request.")
        existing_ids = {session.id for session in self.existing_sessions}
        if not self.locked_session_ids.issubset(existing_ids):
            raise SchedulingRuleError("A requested schedule lock does not exist.")
        activity_ids = [activity.id for activity in self.activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise SchedulingRuleError("Generation activities must be unique.")


@dataclass(frozen=True, slots=True)
class ScheduleGenerationResult:
    """Return proposed sessions, conflicts, preference violations, and score."""

    proposed_sessions: tuple[ScheduledSession, ...]
    unresolved_hard_conflicts: tuple[HardConflict, ...]
    soft_constraint_violations: tuple[SoftConstraintViolation, ...]
    quality_score: Decimal
    explanation: str
    locked_session_ids: frozenset[UUID]
    expected_versions: tuple[tuple[UUID, int], ...]

    def __post_init__(self) -> None:
        """Require a bounded quality score and non-empty explanation."""

        if self.quality_score < Decimal(0) or self.quality_score > Decimal(100):
            raise SchedulingRuleError("Schedule quality score must be 0 through 100.")
        if not self.explanation.strip():
            raise SchedulingRuleError("Schedule result explanation is required.")
        identifiers = [identifier for identifier, _version in self.expected_versions]
        if len(identifiers) != len(set(identifiers)):
            raise SchedulingRuleError("Schedule version snapshot has duplicate IDs.")
        if any(version < 0 for _identifier, version in self.expected_versions):
            raise SchedulingRuleError("Schedule version snapshot cannot be negative.")


def _require_aware(
    value: datetime,
    label: str,
) -> None:
    """Reject timestamps whose UTC offset cannot be determined."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise SchedulingRuleError(f"{label} must be timezone-aware.")


def _require_utc(value: datetime, label: str) -> None:
    """Require an aware datetime with a zero UTC offset."""

    _require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise SchedulingRuleError(f"{label} must use UTC.")


__all__ = [
    "MAX_TEACHER_AVAILABILITY_SPAN",
    "ActivityRequest",
    "CandidateSlot",
    "ConstraintContext",
    "DailyWindow",
    "HardConflict",
    "HardConstraintCode",
    "RecurrenceRule",
    "RoomSpecification",
    "ScheduleGenerationRequest",
    "ScheduleGenerationResult",
    "ScheduledSession",
    "SchedulingPolicy",
    "SoftConstraintCode",
    "SoftConstraintViolation",
    "TeacherAvailability",
    "TeacherAvailabilityWindow",
    "TimeWindow",
]
