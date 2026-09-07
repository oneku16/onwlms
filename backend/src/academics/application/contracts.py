"""Academic-owned DTOs exposed to other application modules."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from academics.domain.exceptions import AcademicRuleError


@dataclass(frozen=True, slots=True)
class AcademicGradeTarget:
    """Expose official academic facts required to record one final grade."""

    organization_id: UUID
    student_academic_enrollment_id: UUID
    course_enrollment_id: UUID
    course_offering_id: UUID
    course_id: UUID
    term_id: UUID
    credits: Decimal

    def __post_init__(self) -> None:
        """Require positive official enrollment credits."""

        if self.credits <= Decimal(0):
            raise AcademicRuleError("Grade-target credits must be positive.")


@dataclass(frozen=True, slots=True)
class AcademicSchedulingRoom:
    """Expose one academic room without leaking persistence details."""

    organization_id: UUID
    room_id: UUID
    campus_id: UUID
    room_type: str
    capacity: int

    def __post_init__(self) -> None:
        """Require usable room type and capacity metadata."""

        if not self.room_type.strip() or self.capacity <= 0:
            raise AcademicRuleError("Scheduling room metadata is invalid.")


@dataclass(frozen=True, slots=True)
class AcademicInstructionWindow:
    """Expose one bounded interval where instruction is allowed."""

    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        """Require an increasing timezone-aware interval."""

        _require_aware(self.starts_at, "Instruction window start")
        _require_aware(self.ends_at, "Instruction window end")
        if self.starts_at >= self.ends_at:
            raise AcademicRuleError("Instruction window end must follow its start.")


@dataclass(frozen=True, slots=True)
class AcademicSchedulingReferences:
    """Expose bounded room and calendar inputs for scheduling constraints."""

    organization_id: UUID
    starts_at: datetime
    ends_at: datetime
    rooms: tuple[AcademicSchedulingRoom, ...]
    instruction_windows: tuple[AcademicInstructionWindow, ...]


@dataclass(frozen=True, slots=True)
class AcceptedStudentAcademicEnrollmentCommand:
    """Request one exact academic enrollment for an Admissions conversion."""

    idempotency_key: UUID
    organization_id: UUID
    academic_enrollment_id: UUID
    student_profile_id: UUID
    program_id: UUID
    intake_term_id: UUID
    enrolled_at: datetime


@dataclass(frozen=True, slots=True)
class AcceptedStudentAcademicEnrollmentResult:
    """Return the durable academic enrollment bound to the conversion."""

    academic_enrollment_id: UUID


def _require_aware(value: datetime, label: str) -> None:
    """Reject timestamps whose UTC offset cannot be determined."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise AcademicRuleError(f"{label} must be timezone-aware.")


__all__ = [
    "AcademicGradeTarget",
    "AcademicInstructionWindow",
    "AcademicSchedulingReferences",
    "AcademicSchedulingRoom",
    "AcceptedStudentAcademicEnrollmentCommand",
    "AcceptedStudentAcademicEnrollmentResult",
]
