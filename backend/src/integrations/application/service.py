"""Moodle integration orchestration with explicit authority and idempotency."""

import hashlib
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.field_encryption import FieldCipher
from integrations.application.ports import FinalGradeEvidenceReceiver
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationAuditSink
from integrations.application.ports import MoodleIntegrationRepository
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence


class MoodleIntegrationService:
    """Configure Moodle and translate effects without transferring authority."""

    def __init__(
        self,
        *,
        repository: MoodleIntegrationRepository,
        gateway_factory: MoodleGatewayFactory,
        grade_receiver: FinalGradeEvidenceReceiver,
        cipher: FieldCipher,
        audit: MoodleIntegrationAuditSink,
    ) -> None:
        self._repository = repository
        self._gateway_factory = gateway_factory
        self._grade_receiver = grade_receiver
        self._cipher = cipher
        self._audit = audit

    async def configure(
        self,
        *,
        actor: TenantActorContext,
        base_url: str,
        token: str,
    ) -> MoodleConfiguration:
        """Activate tenant Moodle configuration after explicit authorization."""

        if "integrations.configure" not in actor.permissions:
            raise AuthorizationError
        self._validate_base_url(base_url)
        if not token:
            message = "Moodle token is required"
            raise ValueError(message)
        configuration = await self._repository.configure(
            organization_id=actor.organization_id,
            base_url=base_url.rstrip("/"),
            encrypted_token=self._cipher.encrypt(token),
        )
        await self._audit.record_moodle_configuration_event(
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
        )
        return configuration

    async def status(
        self,
        *,
        actor: TenantActorContext,
    ) -> MoodleConfiguration | None:
        """Return safe integration status without credentials."""

        if "integrations.read" not in actor.permissions:
            raise AuthorizationError
        return await self._repository.get_configuration(actor.organization_id)

    async def synchronize_enrollment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        course_offering_id: UUID,
        role: str,
        active: bool,
        idempotency_key: str,
    ) -> None:
        """Apply enrollment state through mapped identifiers and supported API."""

        external_user_id = await self._repository.get_mapping(
            organization_id=organization_id,
            entity_type="person",
            entity_id=user_id,
        )
        external_course_id = await self._repository.get_mapping(
            organization_id=organization_id,
            entity_type="course_offering",
            entity_id=course_offering_id,
        )
        if external_user_id is None or external_course_id is None:
            message = "Moodle enrollment mappings are incomplete"
            raise ValueError(message)
        gateway = await self._gateway_factory.create_for_organization(organization_id)
        try:
            await gateway.set_enrollment(
                external_user_id=external_user_id,
                external_course_id=external_course_id,
                role=role,
                active=active,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            await self._repository.record_failure(
                organization_id=organization_id,
                error_code=self._safe_error_code(exc),
            )
            raise
        await self._repository.record_success(organization_id)

    async def receive_final_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> bool:
        """Process a duplicate-safe event through the official grading policy."""

        is_new = await self._repository.accept_grade_event_once(
            organization_id=organization_id,
            evidence=evidence,
        )
        if not is_new:
            return False
        try:
            accepted = await self._grade_receiver.accept_moodle_evidence(
                organization_id=organization_id,
                evidence=evidence,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            await self._repository.mark_grade_event_outcome(
                organization_id=organization_id,
                external_event_id=evidence.external_event_id,
                accepted=False,
                reason_code=self._safe_error_code(exc),
            )
            raise
        await self._repository.mark_grade_event_outcome(
            organization_id=organization_id,
            external_event_id=evidence.external_event_id,
            accepted=accepted,
            reason_code=None if accepted else "rejected_by_grading_policy",
        )
        return accepted

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        """Require HTTPS and prohibit embedded credentials or path confusion."""

        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            message = "Moodle base URL must be a clean HTTPS origin"
            raise ValueError(message)

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        """Return an opaque failure class code without provider detail."""

        digest = hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest()[:12]
        return f"moodle_error_{digest}"


__all__ = ["MoodleIntegrationService"]
