"""Framework-independent academic structure and enrollment models."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from academics.domain.exceptions import AcademicRuleError


class EducationMode(StrEnum):
    """Describe how a program determines course participation."""

    FIXED_CURRICULUM = "fixed_curriculum"
    FLEXIBLE_SELECTION = "flexible_selection"
    HYBRID = "hybrid"


class CurriculumCourseKind(StrEnum):
    """Classify one course requirement inside a program curriculum."""

    REQUIRED = "required"
    ELECTIVE = "elective"


class AcademicEnrollmentStatus(StrEnum):
    """Describe a student's participation in an academic program."""

    ACTIVE = "active"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class CourseEnrollmentStatus(StrEnum):
    """Describe a student's official participation in a course offering."""

    ENROLLED = "enrolled"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class CourseSelectionStatus(StrEnum):
    """Describe the approval state of a course-selection request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SelectionRuleCode(StrEnum):
    """Identify a deterministic enrollment validation result."""

    DEADLINE_PASSED = "deadline_passed"
    FIXED_CURRICULUM = "fixed_curriculum"
    MAXIMUM_CREDITS = "maximum_credits"
    PREREQUISITE_MISSING = "prerequisite_missing"
    SCHEDULE_CONFLICT = "schedule_conflict"


@dataclass(frozen=True, slots=True)
class Faculty:
    """Represent a tenant-owned faculty at an organization-owned campus."""

    id: UUID
    organization_id: UUID
    campus_id: UUID
    code: str
    name: str

    def __post_init__(self) -> None:
        """Reject blank faculty identifiers and display names."""

        if not self.code.strip() or not self.name.strip():
            raise AcademicRuleError("Faculty code and name are required.")


@dataclass(frozen=True, slots=True)
class Department:
    """Represent a department owned by one faculty."""

    id: UUID
    organization_id: UUID
    faculty_id: UUID
    code: str
    name: str

    def __post_init__(self) -> None:
        """Reject blank department identifiers and display names."""

        if not self.code.strip() or not self.name.strip():
            raise AcademicRuleError("Department code and name are required.")


@dataclass(frozen=True, slots=True)
class Program:
    """Represent a program and its configurable education mode."""

    id: UUID
    organization_id: UUID
    department_id: UUID
    code: str
    name: str
    education_mode: EducationMode
    credit_unit_label: str

    def __post_init__(self) -> None:
        """Reject blank program labels or credit-unit configuration."""

        if not self.code.strip() or not self.name.strip():
            raise AcademicRuleError("Program code and name are required.")
        if not self.credit_unit_label.strip():
            raise AcademicRuleError("A credit-unit label is required.")


@dataclass(frozen=True, slots=True)
class AcademicYear:
    """Represent a named academic year within one tenant."""

    id: UUID
    organization_id: UUID
    name: str
    starts_on: date
    ends_on: date

    def __post_init__(self) -> None:
        """Require a non-empty name and an increasing date range."""

        if not self.name.strip():
            raise AcademicRuleError("Academic year name is required.")
        if self.starts_on >= self.ends_on:
            raise AcademicRuleError("Academic year end must follow its start.")


@dataclass(frozen=True, slots=True)
class Term:
    """Represent an instructional term within an academic year."""

    id: UUID
    organization_id: UUID
    academic_year_id: UUID
    name: str
    starts_on: date
    ends_on: date
    enrollment_deadline: datetime
    is_closed: bool = False

    def __post_init__(self) -> None:
        """Require valid dates and a timezone-aware selection deadline."""

        if not self.name.strip():
            raise AcademicRuleError("Term name is required.")
        if self.starts_on >= self.ends_on:
            raise AcademicRuleError("Term end must follow its start.")
        _require_aware(self.enrollment_deadline, "Enrollment deadline")

    def close(self) -> Term:
        """Return this closed term without defining a reverse transition."""

        return self if self.is_closed else replace(self, is_closed=True)


@dataclass(frozen=True, slots=True)
class AcademicCalendarEvent:
    """Represent an organization-wide academic calendar boundary or event."""

    id: UUID
    organization_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    instruction_allowed: bool

    def __post_init__(self) -> None:
        """Require a named, timezone-aware, increasing event interval."""

        if not self.title.strip():
            raise AcademicRuleError("Calendar event title is required.")
        _require_aware(self.starts_at, "Calendar event start")
        _require_aware(self.ends_at, "Calendar event end")
        if self.starts_at >= self.ends_at:
            raise AcademicRuleError("Calendar event end must follow its start.")


@dataclass(frozen=True, slots=True)
class Course:
    """Represent one official course or subject definition."""

    id: UUID
    organization_id: UUID
    department_id: UUID
    code: str
    title: str
    credits: Decimal

    def __post_init__(self) -> None:
        """Require stable labels and a positive credit value."""

        if not self.code.strip() or not self.title.strip():
            raise AcademicRuleError("Course code and title are required.")
        if self.credits <= Decimal(0):
            raise AcademicRuleError("Course credits must be positive.")


@dataclass(frozen=True, slots=True)
class MeetingWindow:
    """Represent a weekly meeting window used for immediate conflict checks."""

    weekday: int
    starts_at: time
    ends_at: time

    def __post_init__(self) -> None:
        """Require an ISO weekday and increasing local wall-clock times."""

        if self.weekday < 1 or self.weekday > 7:
            raise AcademicRuleError("Meeting weekday must be between 1 and 7.")
        if self.starts_at >= self.ends_at:
            raise AcademicRuleError("Meeting end must follow its start.")

    def overlaps(self, other: MeetingWindow) -> bool:
        """Return whether two weekly meeting windows overlap."""

        return (
            self.weekday == other.weekday
            and self.starts_at < other.ends_at
            and other.starts_at < self.ends_at
        )


@dataclass(frozen=True, slots=True)
class CourseOffering:
    """Represent a term-specific section of an official course."""

    id: UUID
    organization_id: UUID
    course_id: UUID
    term_id: UUID
    campus_id: UUID
    section_code: str
    capacity: int
    meeting_windows: tuple[MeetingWindow, ...] = ()

    def __post_init__(self) -> None:
        """Require a section identifier and positive enrollment capacity."""

        if not self.section_code.strip():
            raise AcademicRuleError("Course offering section code is required.")
        if self.capacity <= 0:
            raise AcademicRuleError("Course offering capacity must be positive.")


@dataclass(frozen=True, slots=True)
class Cohort:
    """Represent a named student group within a program."""

    id: UUID
    organization_id: UUID
    program_id: UUID
    academic_year_id: UUID
    code: str
    name: str

    def __post_init__(self) -> None:
        """Reject blank cohort labels."""

        if not self.code.strip() or not self.name.strip():
            raise AcademicRuleError("Cohort code and name are required.")


@dataclass(frozen=True, slots=True)
class Room:
    """Represent a campus room usable by academic scheduling."""

    id: UUID
    organization_id: UUID
    campus_id: UUID
    code: str
    room_type: str
    capacity: int

    def __post_init__(self) -> None:
        """Require a usable room label, type, and capacity."""

        if not self.code.strip() or not self.room_type.strip():
            raise AcademicRuleError("Room code and type are required.")
        if self.capacity <= 0:
            raise AcademicRuleError("Room capacity must be positive.")


@dataclass(frozen=True, slots=True)
class TeacherAssignment:
    """Assign an organization teacher reference to a course offering."""

    id: UUID
    organization_id: UUID
    course_offering_id: UUID
    teacher_id: UUID
    role: str

    def __post_init__(self) -> None:
        """Require an explicit teaching role."""

        if not self.role.strip():
            raise AcademicRuleError("Teacher assignment role is required.")


@dataclass(frozen=True, slots=True)
class StudentAcademicEnrollment:
    """Represent a student's official enrollment in a program and cohort."""

    id: UUID
    organization_id: UUID
    student_id: UUID
    program_id: UUID
    academic_year_id: UUID
    cohort_id: UUID | None
    status: AcademicEnrollmentStatus
    enrolled_at: datetime

    def __post_init__(self) -> None:
        """Require an aware official enrollment timestamp."""

        _require_aware(self.enrolled_at, "Academic enrollment time")


@dataclass(frozen=True, slots=True)
class CourseEnrollment:
    """Represent official enrollment in one term course offering."""

    id: UUID
    organization_id: UUID
    student_academic_enrollment_id: UUID
    course_offering_id: UUID
    credits: Decimal
    status: CourseEnrollmentStatus
    enrolled_at: datetime
    selection_request_id: UUID | None = None

    def __post_init__(self) -> None:
        """Require positive credits and an aware enrollment timestamp."""

        if self.credits <= Decimal(0):
            raise AcademicRuleError("Course enrollment credits must be positive.")
        _require_aware(self.enrolled_at, "Course enrollment time")


@dataclass(frozen=True, slots=True)
class CurriculumCourse:
    """Describe one required or elective course in a program curriculum."""

    course_id: UUID
    kind: CurriculumCourseKind
    credits: Decimal
    prerequisite_course_ids: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        """Require positive curriculum credits and no self-prerequisite."""

        if self.credits <= Decimal(0):
            raise AcademicRuleError("Curriculum course credits must be positive.")
        if self.course_id in self.prerequisite_course_ids:
            raise AcademicRuleError("A course cannot be its own prerequisite.")


@dataclass(frozen=True, slots=True)
class ProgramCurriculum:
    """Represent the versioned curriculum active for a program and year."""

    id: UUID
    organization_id: UUID
    program_id: UUID
    academic_year_id: UUID
    courses: tuple[CurriculumCourse, ...]

    def __post_init__(self) -> None:
        """Require unique course membership within one curriculum."""

        course_ids = [course.course_id for course in self.courses]
        if len(course_ids) != len(set(course_ids)):
            raise AcademicRuleError("A curriculum cannot contain duplicate courses.")

    def course(self, course_id: UUID) -> CurriculumCourse | None:
        """Return one curriculum course by stable course identifier."""

        return next(
            (course for course in self.courses if course.course_id == course_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class CourseSelectionPolicy:
    """Configure tenant program selection rules for one term."""

    organization_id: UUID
    program_id: UUID
    term_id: UUID
    education_mode: EducationMode
    maximum_credits: Decimal
    deadline: datetime
    approval_required: bool

    def __post_init__(self) -> None:
        """Require a positive limit and timezone-aware deadline."""

        if self.maximum_credits <= Decimal(0):
            raise AcademicRuleError("Maximum credits must be positive.")
        _require_aware(self.deadline, "Course-selection deadline")


@dataclass(frozen=True, slots=True)
class SelectionRuleViolation:
    """Describe a failed selection rule without transport-specific details."""

    code: SelectionRuleCode
    related_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class AdministrativeOverride:
    """Record why an authorized actor bypassed named selection rules."""

    actor_id: UUID
    reason: str
    created_at: datetime
    violated_rules: tuple[SelectionRuleViolation, ...]

    def __post_init__(self) -> None:
        """Require a reason, timestamp, and at least one overridden rule."""

        if not self.reason.strip():
            raise AcademicRuleError("Administrative override reason is required.")
        _require_aware(self.created_at, "Administrative override time")
        if not self.violated_rules:
            raise AcademicRuleError("An override must identify violated rules.")


@dataclass(frozen=True, slots=True)
class CourseSelectionRequest:
    """Represent a student's requested set of term course offerings."""

    id: UUID
    organization_id: UUID
    student_academic_enrollment_id: UUID
    term_id: UUID
    offering_ids: tuple[UUID, ...]
    requested_credits: Decimal
    status: CourseSelectionStatus
    submitted_at: datetime
    submitted_by: UUID
    override: AdministrativeOverride | None = None
    decided_at: datetime | None = None
    decided_by: UUID | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        """Require a non-empty unique selection and coherent decision state."""

        if not self.offering_ids:
            raise AcademicRuleError("At least one course offering is required.")
        if len(self.offering_ids) != len(set(self.offering_ids)):
            raise AcademicRuleError("Course offerings cannot be selected twice.")
        if self.requested_credits <= Decimal(0):
            raise AcademicRuleError("Requested credits must be positive.")
        _require_aware(self.submitted_at, "Course-selection submission time")
        if self.decided_at is not None:
            _require_aware(self.decided_at, "Course-selection decision time")
        if self.status is CourseSelectionStatus.PENDING:
            if self.decided_at is not None or self.decided_by is not None:
                raise AcademicRuleError("A pending request cannot have a decision.")
        elif self.decided_at is None or self.decided_by is None:
            raise AcademicRuleError("A decided request must identify actor and time.")
        if (
            self.status is CourseSelectionStatus.REJECTED
            and not (self.rejection_reason or "").strip()
        ):
            raise AcademicRuleError("A rejected request requires a reason.")


@dataclass(frozen=True, slots=True)
class CourseSelectionApproval:
    """Preserve an immutable approval or rejection record."""

    id: UUID
    organization_id: UUID
    request_id: UUID
    actor_id: UUID
    approved: bool
    decided_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        """Require an aware timestamp and a reason for rejection."""

        _require_aware(self.decided_at, "Course-selection approval time")
        if not self.approved and not (self.reason or "").strip():
            raise AcademicRuleError("A rejection requires a reason.")


@dataclass(frozen=True, slots=True)
class SelectionEvaluation:
    """Return resolved offerings, credits, and deterministic rule violations."""

    offerings: tuple[CourseOffering, ...]
    requested_credits: Decimal
    violations: tuple[SelectionRuleViolation, ...] = field(default=())


def _require_aware(
    value: datetime,
    label: str,
) -> None:
    """Reject timestamps whose UTC offset cannot be determined."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise AcademicRuleError(f"{label} must be timezone-aware.")


__all__ = [
    "AcademicCalendarEvent",
    "AcademicEnrollmentStatus",
    "AcademicYear",
    "AdministrativeOverride",
    "Cohort",
    "Course",
    "CourseEnrollment",
    "CourseEnrollmentStatus",
    "CourseOffering",
    "CourseSelectionApproval",
    "CourseSelectionPolicy",
    "CourseSelectionRequest",
    "CourseSelectionStatus",
    "CurriculumCourse",
    "CurriculumCourseKind",
    "Department",
    "EducationMode",
    "Faculty",
    "MeetingWindow",
    "Program",
    "ProgramCurriculum",
    "Room",
    "SelectionEvaluation",
    "SelectionRuleCode",
    "SelectionRuleViolation",
    "StudentAcademicEnrollment",
    "TeacherAssignment",
    "Term",
]
