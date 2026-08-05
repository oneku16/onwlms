"""Stable consumer-owned admissions collaboration contracts."""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AcceptedApplicantEnrollmentCommand:
    """Request idempotent creation of student and academic enrollment records."""

    idempotency_key: UUID
    organization_id: UUID
    application_id: UUID
    student_profile_id: UUID
    academic_enrollment_id: UUID
    program_id: UUID
    intake_id: UUID
    requested_at: datetime
    actor_subject_id: UUID
    correlation_id: str
    given_name: str
    family_name: str
    email: str | None = field(repr=False)
    phone: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class AcceptedApplicantEnrollmentResult:
    """Return stable identifiers created by the enrollment collaboration."""

    student_id: UUID
    academic_enrollment_id: UUID


__all__ = [
    "AcceptedApplicantEnrollmentCommand",
    "AcceptedApplicantEnrollmentResult",
]
