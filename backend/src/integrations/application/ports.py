"""Moodle gateway, storage, and owning-domain acceptance ports."""

from typing import Protocol
from uuid import UUID

from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleDeadlineEvidence
from integrations.domain.moodle import MoodleFinalGradeEvidence


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
        accepted: bool,
        reason_code: str | None,
    ) -> None:
        """Record the authoritative-domain acceptance outcome safely."""
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


class FinalGradeEvidenceReceiver(Protocol):
    """Submit external evidence to the grading module's official policy."""

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> bool:
        """Return whether grading policy accepted the evidence officially."""
        ...


class MoodleIntegrationAuditSink(Protocol):
    """Append privacy-minimized evidence for integration configuration."""

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


__all__ = [
    "FinalGradeEvidenceReceiver",
    "MoodleGateway",
    "MoodleGatewayFactory",
    "MoodleIntegrationAuditSink",
    "MoodleIntegrationRepository",
]
