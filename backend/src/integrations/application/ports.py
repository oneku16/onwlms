"""Moodle gateway, storage, and owning-domain acceptance ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from integrations.domain.moodle import GradeEvidenceDisposition
from integrations.domain.moodle import GradeEvidenceReceipt
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleCourseGradeObservation
from integrations.domain.moodle import MoodleDeadlineEvidence
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeEvidenceRecord
from integrations.domain.moodle import MoodleGradeReconciliationRun


class MoodleGateway(Protocol):
    """Translate supported Moodle APIs into OwnSIS application language."""

    async def ensure_user(
        self,
        *,
        external_username: str,
        display_name: str,
        email: str | None,
        idempotency_key: str,
    ) -> str:
        """Create or resolve a Moodle learning user."""
        ...

    async def ensure_course(
        self,
        *,
        course_code: str,
        course_title: str,
        idempotency_key: str,
    ) -> str:
        """Create or resolve a Moodle course shell."""
        ...

    async def set_enrollment(
        self,
        *,
        external_user_id: str,
        external_course_id: str,
        role: str,
        active: bool,
        idempotency_key: str,
    ) -> None:
        """Apply an idempotent learner or teacher enrollment state."""
        ...

    async def list_deadlines(
        self,
        *,
        external_user_id: str,
    ) -> list[MoodleDeadlineEvidence]:
        """Return learning deadline evidence without claiming ERP ownership."""
        ...

    async def list_course_grades(
        self,
        *,
        external_course_id: str,
    ) -> list[MoodleCourseGradeObservation]:
        """Return course-total grade observations for one Moodle course shell."""
        ...


class MoodleGatewayFactory(Protocol):
    """Build a tenant-specific gateway from protected configuration."""

    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleGateway:
        """Return a configured gateway or fail explicitly."""
        ...


class MoodleIntegrationRepository(Protocol):
    """Persist configuration, mappings, evidence, and synchronization state."""

    async def configure(
        self,
        *,
        organization_id: UUID,
        base_url: str,
        encrypted_token: str,
    ) -> MoodleConfiguration:
        """Create or rotate tenant configuration without exposing credentials."""
        ...

    async def get_configuration(
        self,
        organization_id: UUID,
    ) -> MoodleConfiguration | None:
        """Return safe tenant configuration metadata."""
        ...

    async def get_encrypted_token(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return protected credential material to the infrastructure boundary."""
        ...

    async def set_grade_event_secret(
        self,
        *,
        organization_id: UUID,
        encrypted_secret: str,
    ) -> MoodleConfiguration:
        """Store or rotate the protected grade-event signing secret."""
        ...

    async def get_encrypted_grade_event_secret(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return the protected signing secret only to the application boundary."""
        ...

    async def put_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        external_id: str,
    ) -> None:
        """Persist one tenant-scoped internal-to-Moodle identifier mapping."""
        ...

    async def get_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> str | None:
        """Resolve one tenant-scoped mapping."""
        ...

    async def get_entity_id(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        external_id: str,
    ) -> UUID | None:
        """Resolve one tenant-scoped mapping from its Moodle identifier."""
        ...

    async def accept_grade_event_once(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
    ) -> bool:
        """Persist external evidence once before domain acceptance."""
        ...

    async def mark_grade_event_outcome(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
        status: GradeEvidenceStatus,
        reason_code: str | None,
    ) -> None:
        """Record the authoritative-domain intake outcome safely."""
        ...

    async def get_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return one stored evidence record from exactly one tenant."""
        ...

    async def get_grade_evidence_by_event(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return stored evidence for one tenant external event key."""
        ...

    async def list_grade_evidence(
        self,
        *,
        organization_id: UUID,
        status: GradeEvidenceStatus | None,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeEvidenceRecord, ...]:
        """Return a bounded stable page of tenant evidence records."""
        ...

    async def resolve_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        status: GradeEvidenceStatus,
        reason_code: str | None,
        final_grade_id: UUID | None,
        resolved_by: UUID,
        resolved_at: datetime,
    ) -> MoodleGradeEvidenceRecord:
        """Resolve pending evidence exactly once under a tenant row lock."""
        ...

    async def record_success(
        self,
        organization_id: UUID,
    ) -> None:
        """Record a successful tenant integration operation."""
        ...

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        error_code: str,
    ) -> None:
        """Record an opaque tenant integration failure."""
        ...


class MoodleReconciliationRunRepository(Protocol):
    """Persist operator-visible selected-term reconciliation state."""

    async def create_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist one newly started tenant reconciliation run."""
        ...

    async def complete_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist the terminal outcome and counts of one tenant run."""
        ...

    async def get_run(
        self,
        *,
        organization_id: UUID,
        run_id: UUID,
    ) -> MoodleGradeReconciliationRun | None:
        """Return one run from exactly one tenant."""
        ...

    async def list_runs(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeReconciliationRun, ...]:
        """Return a bounded newest-first page of tenant runs."""
        ...


class FinalGradeEvidenceReceiver(Protocol):
    """Submit external evidence to the grading module's official policy."""

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> GradeEvidenceDisposition:
        """Return how official grading policy dispositioned the evidence."""
        ...


class ExternalGradeEvidenceIntake(Protocol):
    """Accept translated evidence through duplicate-safe tenant intake."""

    async def receive_final_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> GradeEvidenceReceipt:
        """Store evidence once and report its intake outcome."""
        ...


class TermOfferingDirectory(Protocol):
    """Resolve the course offerings of one tenant term through Academics."""

    async def list_course_offering_ids(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> frozenset[UUID] | None:
        """Return offering identifiers, or None when the tenant term is unknown."""
        ...


class IntegrationClock(Protocol):
    """Supply explicit timezone-aware integration application time."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class MoodleIntegrationAuditSink(Protocol):
    """Append privacy-minimized evidence for integration governance."""

    async def record_moodle_configuration_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record configuration intent or outcome without sensitive material."""
        ...

    async def record_grade_evidence_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        evidence_reference: str,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record grade-evidence intake or resolution without grade values."""
        ...

    async def record_grade_reconciliation_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        run_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record reconciliation intent or outcome without provider payloads."""
        ...


__all__ = [
    "ExternalGradeEvidenceIntake",
    "FinalGradeEvidenceReceiver",
    "IntegrationClock",
    "MoodleGateway",
    "MoodleGatewayFactory",
    "MoodleIntegrationAuditSink",
    "MoodleIntegrationRepository",
    "MoodleReconciliationRunRepository",
    "TermOfferingDirectory",
]
