"""OwnSIS-owned translations of Moodle evidence and integration status."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class IntegrationStatus(StrEnum):
    """Observable tenant integration lifecycle."""

    DISABLED = "disabled"
    CONFIGURED = "configured"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class MoodleDeadlineEvidence:
    """Represent Moodle-owned deadline evidence with provenance and freshness."""

    external_reference: str
    title: str
    due_at: datetime
    observed_at: datetime
    source_version: str


@dataclass(frozen=True, slots=True)
class MoodleFinalGradeEvidence:
    """Represent an untrusted Moodle result pending official grade policy."""

    external_event_id: str
    course_offering_id: UUID
    student_person_id: UUID
    grade_value: str
    observed_at: datetime
    source_version: str


@dataclass(frozen=True, slots=True)
class MoodleConfiguration:
    """Describe safe non-secret tenant Moodle configuration."""

    organization_id: UUID
    base_url: str
    status: IntegrationStatus
    last_success_at: datetime | None
    last_error_code: str | None
    grade_events_configured: bool = False


class GradeEvidenceStatus(StrEnum):
    """Describe whether official grading policy has resolved stored evidence."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class GradeEvidenceDisposition(StrEnum):
    """Describe the owning domain's immediate answer for received evidence."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"


class ReconciliationRunStatus(StrEnum):
    """Describe the lifecycle of one selected-term grade reconciliation."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MoodleCourseGradeObservation:
    """Represent one Moodle course-total grade observed for one learning user."""

    external_user_id: str
    grade_item_id: str
    grade_raw: str
    graded_at: datetime | None
    observed_at: datetime
    source_version: str


@dataclass(frozen=True, slots=True)
class GradeEvidenceReceipt:
    """Report how duplicate-safe intake handled one external grade event."""

    external_event_id: str
    duplicate: bool
    status: GradeEvidenceStatus


@dataclass(frozen=True, slots=True)
class MoodleGradeEvidenceRecord:
    """Describe stored Moodle grade evidence and its official resolution state."""

    id: UUID
    organization_id: UUID
    external_event_id: str
    course_offering_id: UUID
    student_person_id: UUID
    grade_value: str
    observed_at: datetime
    source_version: str
    status: GradeEvidenceStatus
    reason_code: str | None
    received_at: datetime
    accepted_final_grade_id: UUID | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MoodleGradeReconciliationRun:
    """Describe one operator-requested selected-term grade reconciliation."""

    id: UUID
    organization_id: UUID
    term_id: UUID
    requested_by: UUID
    status: ReconciliationRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    offering_count: int = 0
    unmapped_offering_count: int = 0
    observed_count: int = 0
    new_evidence_count: int = 0
    duplicate_count: int = 0
    unmapped_user_count: int = 0
    error_code: str | None = None


__all__ = [
    "GradeEvidenceDisposition",
    "GradeEvidenceReceipt",
    "GradeEvidenceStatus",
    "IntegrationStatus",
    "MoodleConfiguration",
    "MoodleCourseGradeObservation",
    "MoodleDeadlineEvidence",
    "MoodleFinalGradeEvidence",
    "MoodleGradeEvidenceRecord",
    "MoodleGradeReconciliationRun",
    "ReconciliationRunStatus",
]
