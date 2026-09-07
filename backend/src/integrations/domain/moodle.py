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


__all__ = [
    "IntegrationStatus",
    "MoodleConfiguration",
    "MoodleDeadlineEvidence",
    "MoodleFinalGradeEvidence",
]
