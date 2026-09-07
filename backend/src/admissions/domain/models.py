"""Framework-independent admissions aggregates and policy values."""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from admissions.domain.exceptions import AdmissionsRuleError
from admissions.domain.exceptions import ApplicationTransitionError


class ApplicationSource(StrEnum):
    """Identify how an admissions application entered OwnSIS."""

    SELF_SUBMITTED = "self_submitted"
    ADMINISTRATOR_ENTERED = "administrator_entered"


class ApplicationStatus(StrEnum):
    """Describe the lifecycle of one admissions application."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    AWAITING_EXAM = "awaiting_exam"
    AWAITING_INTERVIEW = "awaiting_interview"
    UNDER_REVIEW = "under_review"
    WAITLISTED = "waitlisted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"


class ReviewStage(StrEnum):
    """Name an optional configured admissions assessment stage."""

    DOCUMENT_REVIEW = "document_review"
    EXAM = "exam"
    INTERVIEW = "interview"


class ReviewOutcome(StrEnum):
    """Describe the outcome of one completed admissions review."""

    PASSED = "passed"
    FAILED = "failed"
    NEEDS_MORE_INFORMATION = "needs_more_information"


class AdmissionDecisionOutcome(StrEnum):
    """Describe the official decision made on an application."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WAITLISTED = "waitlisted"


class ReservationStatus(StrEnum):
    """Describe whether a quota seat remains allocated."""

    ACTIVE = "active"
    RELEASED = "released"
    CONSUMED = "consumed"


class DepositStatus(StrEnum):
    """Describe external deposit evidence without owning payment processing."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    SATISFIED = "satisfied"
    WAIVED = "waived"


class EnrollmentConversionStatus(StrEnum):
    """Describe cross-module accepted-to-enrolled workflow progress."""

    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ApplicantProfile:
    """Represent admissions-owned applicant identity and contact information."""

    id: UUID
    organization_id: UUID
    given_name: str
    family_name: str
    email: str | None = field(repr=False)
    phone: str | None = field(repr=False)

    def __post_init__(self) -> None:
        """Require applicant names and at least one contact route."""

        if not self.given_name.strip() or not self.family_name.strip():
            raise AdmissionsRuleError("Applicant given and family names are required.")
        if not (self.email or self.phone):
            raise AdmissionsRuleError("Applicant email or phone is required.")


@dataclass(frozen=True, slots=True)
class DepositRequirement:
    """Describe a replaceable-provider deposit requirement and evidence state."""

    required: bool
    amount: Decimal | None
    currency: str | None
    due_at: datetime | None
    external_reference: str | None
    status: DepositStatus

    def __post_init__(self) -> None:
        """Require coherent metadata when a deposit is configured."""

        if not self.required:
            if self.status is not DepositStatus.NOT_REQUIRED:
                raise AdmissionsRuleError(
                    "A non-required deposit must have not-required status."
                )
            return
        if self.amount is None or self.amount <= Decimal(0):
            raise AdmissionsRuleError("Required deposit amount must be positive.")
        if not (self.currency or "").strip():
            raise AdmissionsRuleError("Required deposit currency is missing.")
        if self.due_at is None:
            raise AdmissionsRuleError("Required deposit due time is missing.")
        _require_aware(self.due_at, "Deposit due time")


@dataclass(frozen=True, slots=True)
class Application:
    """Represent a tenant application for one program and intake."""

    id: UUID
    organization_id: UUID
    applicant_profile_id: UUID
    program_id: UUID
    intake_id: UUID
    seat_category: str
    source: ApplicationSource
    status: ApplicationStatus
    created_at: datetime
    status_changed_at: datetime
    deposit: DepositRequirement

    def __post_init__(self) -> None:
        """Require a seat category and timezone-aware lifecycle times."""

        if not self.seat_category.strip():
            raise AdmissionsRuleError("Application seat category is required.")
        _require_aware(self.created_at, "Application creation time")
        _require_aware(self.status_changed_at, "Application status time")


@dataclass(frozen=True, slots=True)
class ApplicationDocument:
    """Represent safe metadata for an externally stored applicant document."""

    id: UUID
    organization_id: UUID
    application_id: UUID
    document_type: str
    file_reference: str
    media_type: str
    size_bytes: int
    checksum_sha256: str
    uploaded_at: datetime

    def __post_init__(self) -> None:
        """Require bounded file metadata without accepting document content."""

        if not self.document_type.strip() or not self.file_reference.strip():
            raise AdmissionsRuleError("Document type and file reference are required.")
        if not self.media_type.strip() or self.size_bytes <= 0:
            raise AdmissionsRuleError("Document media type and size are invalid.")
        if len(self.checksum_sha256) != 64:
            raise AdmissionsRuleError("Document checksum must be SHA-256 hexadecimal.")
        _require_aware(self.uploaded_at, "Document upload time")


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """Preserve one immutable application review result."""

    id: UUID
    organization_id: UUID
    application_id: UUID
    stage: ReviewStage
    outcome: ReviewOutcome
    reviewer_id: UUID
    completed_at: datetime
    explanation: str | None = None

    def __post_init__(self) -> None:
        """Require an aware review completion time."""

        _require_aware(self.completed_at, "Review completion time")
        if (
            self.outcome is not ReviewOutcome.PASSED
            and not (self.explanation or "").strip()
        ):
            raise AdmissionsRuleError("A non-passing review requires an explanation.")


@dataclass(frozen=True, slots=True)
class AdmissionsPolicy:
    """Configure required review stages, deposits, and reservation duration."""

    organization_id: UUID
    program_id: UUID
    intake_id: UUID
    required_stages: tuple[ReviewStage, ...]
    deposit_required: bool
    deposit_amount: Decimal | None
    deposit_currency: str | None
    reservation_duration: timedelta

    def __post_init__(self) -> None:
        """Require unique stages and a positive reservation duration."""

        if len(self.required_stages) != len(set(self.required_stages)):
            raise AdmissionsRuleError("Admissions stages cannot be repeated.")
        if self.reservation_duration <= timedelta(0):
            raise AdmissionsRuleError("Seat reservation duration must be positive.")
        if self.deposit_required:
            if self.deposit_amount is None or self.deposit_amount <= Decimal(0):
                raise AdmissionsRuleError("Deposit amount must be positive.")
            if not (self.deposit_currency or "").strip():
                raise AdmissionsRuleError("Deposit currency is required.")


@dataclass(frozen=True, slots=True)
class AdmissionQuota:
    """Limit seats for a program intake and configured seat category."""

    id: UUID
    organization_id: UUID
    program_id: UUID
    intake_id: UUID
    seat_category: str
    capacity: int

    def __post_init__(self) -> None:
        """Require a named category and positive seat capacity."""

        if not self.seat_category.strip():
            raise AdmissionsRuleError("Quota seat category is required.")
        if self.capacity <= 0:
            raise AdmissionsRuleError("Quota capacity must be positive.")


@dataclass(frozen=True, slots=True)
class SeatReservation:
    """Represent a concurrent-safe seat allocation for an accepted application."""

    id: UUID
    organization_id: UUID
    quota_id: UUID
    application_id: UUID
    status: ReservationStatus
    reserved_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        """Require coherent reservation times for the current status."""

        _require_aware(self.reserved_at, "Seat reservation time")
        _require_aware(self.expires_at, "Seat reservation expiry")
        if self.reserved_at >= self.expires_at:
            raise AdmissionsRuleError("Seat reservation expiry must follow creation.")
        if self.consumed_at is not None:
            _require_aware(self.consumed_at, "Seat reservation consumption time")
        if self.released_at is not None:
            _require_aware(self.released_at, "Seat reservation release time")
        if self.status is ReservationStatus.CONSUMED and self.consumed_at is None:
            raise AdmissionsRuleError("Consumed reservation requires its timestamp.")
        if self.status is ReservationStatus.RELEASED and self.released_at is None:
            raise AdmissionsRuleError("Released reservation requires its timestamp.")

    def is_active_at(self, at: datetime) -> bool:
        """Return whether the reservation still consumes quota at a time."""

        _require_aware(at, "Reservation evaluation time")
        return self.status is ReservationStatus.ACTIVE and at < self.expires_at


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Preserve one official acceptance, rejection, or waitlist decision."""

    id: UUID
    organization_id: UUID
    application_id: UUID
    outcome: AdmissionDecisionOutcome
    decided_by: UUID
    decided_at: datetime
    reason: str
    reservation_id: UUID | None = None

    def __post_init__(self) -> None:
        """Require an explanation and coherent reservation reference."""

        if not self.reason.strip():
            raise AdmissionsRuleError("Admissions decision reason is required.")
        _require_aware(self.decided_at, "Admissions decision time")
        if (
            self.outcome is AdmissionDecisionOutcome.ACCEPTED
            and self.reservation_id is None
        ):
            raise AdmissionsRuleError("Acceptance requires a seat reservation.")
        if (
            self.outcome is not AdmissionDecisionOutcome.ACCEPTED
            and self.reservation_id is not None
        ):
            raise AdmissionsRuleError("Only acceptance may reference a reservation.")


@dataclass(frozen=True, slots=True)
class EnrollmentConversion:
    """Track an idempotent cross-module accepted-to-enrolled workflow."""

    id: UUID
    organization_id: UUID
    application_id: UUID
    status: EnrollmentConversionStatus
    requested_by: UUID
    correlation_id: str
    requested_at: datetime
    student_id: UUID
    academic_enrollment_id: UUID
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Require coherent conversion lifecycle fields."""

        if not self.correlation_id.strip() or len(self.correlation_id) > 128:
            raise AdmissionsRuleError("Enrollment conversion correlation is invalid.")
        _require_aware(self.requested_at, "Enrollment conversion request time")
        if self.completed_at is not None:
            _require_aware(self.completed_at, "Enrollment conversion completion time")
        if self.status is EnrollmentConversionStatus.COMPLETED:
            if self.completed_at is None:
                raise AdmissionsRuleError(
                    "Completed conversion requires enrollment identifier and time."
                )


_ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.SUBMITTED: frozenset(
        {
            ApplicationStatus.AWAITING_EXAM,
            ApplicationStatus.AWAITING_INTERVIEW,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WAITLISTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.AWAITING_EXAM: frozenset(
        {
            ApplicationStatus.AWAITING_INTERVIEW,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.AWAITING_INTERVIEW: frozenset(
        {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WAITLISTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.WAITLISTED: frozenset(
        {
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.ACCEPTED: frozenset(
        {ApplicationStatus.ENROLLED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.ENROLLED: frozenset(),
    ApplicationStatus.WITHDRAWN: frozenset(),
}


def transition_application(
    *,
    application: Application,
    target: ApplicationStatus,
    changed_at: datetime,
) -> Application:
    """Return the application in a valid next lifecycle state."""

    from dataclasses import replace

    _require_aware(changed_at, "Application transition time")
    if target not in _ALLOWED_TRANSITIONS[application.status]:
        raise ApplicationTransitionError(
            f"Cannot transition application from {application.status} to {target}."
        )
    return replace(
        application,
        status=target,
        status_changed_at=changed_at,
    )


def _require_aware(
    value: datetime,
    label: str,
) -> None:
    """Reject timestamps whose UTC offset cannot be determined."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise AdmissionsRuleError(f"{label} must be timezone-aware.")


__all__ = [
    "AdmissionDecision",
    "AdmissionDecisionOutcome",
    "AdmissionQuota",
    "AdmissionsPolicy",
    "ApplicantProfile",
    "Application",
    "ApplicationDocument",
    "ApplicationSource",
    "ApplicationStatus",
    "DepositRequirement",
    "DepositStatus",
    "EnrollmentConversion",
    "EnrollmentConversionStatus",
    "ReservationStatus",
    "ReviewOutcome",
    "ReviewRecord",
    "ReviewStage",
    "SeatReservation",
    "transition_application",
]
