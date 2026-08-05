"""People-owned contracts for accepted-student registration."""

from dataclasses import dataclass
from dataclasses import field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AcceptedStudentRegistrationCommand:
    """Request one idempotent People student activation from Admissions."""

    idempotency_key: UUID
    organization_id: UUID
    student_profile_id: UUID
    actor_subject_id: UUID
    correlation_id: str
    given_name: str
    family_name: str
    email: str | None = field(repr=False)
    phone: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class AcceptedStudentRegistrationResult:
    """Return People identifiers durably bound to a conversion key."""

    person_id: UUID
    student_profile_id: UUID


__all__ = [
    "AcceptedStudentRegistrationCommand",
    "AcceptedStudentRegistrationResult",
]
