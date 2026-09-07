"""Bounded read-only values exposed through MCP tools."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScheduleItem:
    """Describe one authorized scheduled session."""

    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    room_name: str | None


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Describe the minimum authenticated person's own profile identity."""

    person_id: UUID
    display_name: str
    institutional_reference: str | None


@dataclass(frozen=True, slots=True)
class GradeSummary:
    """Describe one official accepted result without revision internals."""

    course_code: str
    course_title: str
    display_grade: str
    credits_attempted: str
    credits_earned: str
    grade_points: str | None


@dataclass(frozen=True, slots=True)
class GpaSummary:
    """Describe the authenticated student's official cumulative GPA facts."""

    credits_attempted: str
    credits_earned: str
    gpa_credits_attempted: str
    quality_points: str
    gpa: str | None


@dataclass(frozen=True, slots=True)
class UpcomingEvent:
    """Describe one organization calendar event visible to the actor."""

    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class MoodleDeadline:
    """Describe learning-platform deadline evidence and freshness."""

    external_reference: str
    title: str
    due_at: datetime
    observed_at: datetime
    source_version: str


@dataclass(frozen=True, slots=True)
class AssignedSection:
    """Describe a course offering assigned to the current teacher."""

    id: UUID
    course_code: str
    section_name: str
    term_name: str


@dataclass(frozen=True, slots=True)
class SectionStudent:
    """Describe the minimum roster identity needed by a teacher."""

    person_id: UUID
    display_name: str
    institutional_reference: str | None


@dataclass(frozen=True, slots=True)
class GradeSyncSummary:
    """Describe final-grade synchronization without exposing payloads."""

    section_id: UUID
    status: str
    last_observed_at: datetime | None
    unresolved_count: int


@dataclass(frozen=True, slots=True)
class GuardianStudentSummary:
    """Describe an explicitly linked student's official high-level summary."""

    student_person_id: UUID
    display_name: str
    current_program: str | None
    latest_official_grades: tuple[GradeSummary, ...]


__all__ = [
    "AssignedSection",
    "GpaSummary",
    "GradeSummary",
    "GradeSyncSummary",
    "GuardianStudentSummary",
    "MoodleDeadline",
    "ProfileSummary",
    "ScheduleItem",
    "SectionStudent",
    "UpcomingEvent",
]
