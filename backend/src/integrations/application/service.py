"""Moodle integration orchestration with explicit authority and idempotency."""

import hashlib
import json
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.errors import ValidationError
from core.field_encryption import FieldCipher
from integrations.application.ports import FinalGradeEvidenceReceiver
from integrations.application.ports import IntegrationClock
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationAuditSink
from integrations.application.ports import MoodleIntegrationRepository
from integrations.domain.exceptions import GradeEventRejectedError
from integrations.domain.exceptions import GradeEventSignatureError
from integrations.domain.grade_events import MAX_GRADE_EVENT_BODY_BYTES
from integrations.domain.grade_events import MIN_GRADE_EVENT_SECRET_LENGTH
from integrations.domain.grade_events import parse_grade_event_payload
from integrations.domain.grade_events import parse_grade_event_timestamp
from integrations.domain.grade_events import verify_grade_event_signature
from integrations.domain.moodle import GradeEvidenceDisposition
from integrations.domain.moodle import GradeEvidenceReceipt
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeEvidenceRecord

INTEGRATIONS_CONFIGURE = "integrations.configure"
INTEGRATIONS_READ = "integrations.read"
GRADE_EVIDENCE_READ = "integrations.grade_evidence.read"
MAX_GRADE_EVIDENCE_PAGE_SIZE = 100
REVIEW_REQUIRED_REASON_CODE = "review_required"
REJECTED_BY_POLICY_REASON_CODE = "rejected_by_grading_policy"
_UNAUTHENTICATED_EVENT_REFERENCE = "unauthenticated"


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
        clock: IntegrationClock,
    ) -> None:
        self._repository = repository
        self._gateway_factory = gateway_factory
        self._grade_receiver = grade_receiver
        self._cipher = cipher
        self._audit = audit
        self._clock = clock

    async def configure(
        self,
        *,
        actor: TenantActorContext,
        base_url: str,
        token: str,
    ) -> MoodleConfiguration:
        """Activate tenant Moodle configuration after explicit authorization."""

        _authorize(actor, INTEGRATIONS_CONFIGURE)
        self._validate_base_url(base_url)
        if not token:
            message = "Moodle token is required"
            raise ValueError(message)
        await self._audit.record_moodle_configuration_event(
            action="integrations.moodle.configuration_update_requested",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="intent_recorded",
        )
        configuration = await self._repository.configure(
            organization_id=actor.organization_id,
            base_url=base_url.rstrip("/"),
            encrypted_token=self._cipher.encrypt(token),
        )
        await self._audit.record_moodle_configuration_event(
            action="integrations.moodle.configuration.updated",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return configuration

    async def configure_grade_event_secret(
        self,
        *,
        actor: TenantActorContext,
        secret: str,
    ) -> MoodleConfiguration:
        """Store the tenant's grade-event signing secret after authorization."""

        _authorize(actor, INTEGRATIONS_CONFIGURE)
        if len(secret) < MIN_GRADE_EVENT_SECRET_LENGTH or secret.strip() != secret:
            raise ValidationError(
                "Grade-event signing secret must be at least "
                f"{MIN_GRADE_EVENT_SECRET_LENGTH} characters without surrounding "
                "whitespace."
            )
        if await self._repository.get_configuration(actor.organization_id) is None:
            raise ValidationError(
                "Configure the Moodle integration before its grade-event secret."
            )
        await self._audit.record_moodle_configuration_event(
            action="integrations.moodle.grade_event_secret_update_requested",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="intent_recorded",
        )
        configuration = await self._repository.set_grade_event_secret(
            organization_id=actor.organization_id,
            encrypted_secret=self._cipher.encrypt(secret),
        )
        await self._audit.record_moodle_configuration_event(
            action="integrations.moodle.grade_event_secret.updated",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return configuration

    async def status(
        self,
        *,
        actor: TenantActorContext,
    ) -> MoodleConfiguration | None:
        """Return safe integration status without credentials."""

        _authorize(actor, INTEGRATIONS_READ)
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

    async def ingest_signed_grade_event(
        self,
        *,
        organization_id: UUID,
        body: bytes,
        timestamp: str,
        signature: str,
        correlation_id: str,
    ) -> GradeEvidenceReceipt:
        """Authenticate one Moodle-side grade event and store it once.

        The tenant signing secret authenticates the sender, the timestamp bounds
        replay to a short window, and the tenant plus external event key keeps a
        retried delivery from producing a second evidence record.
        """

        if len(body) > MAX_GRADE_EVENT_BODY_BYTES:
            raise GradeEventRejectedError("Grade event payload is too large")
        encrypted_secret = await self._repository.get_encrypted_grade_event_secret(
            organization_id
        )
        try:
            if encrypted_secret is None:
                raise GradeEventSignatureError(
                    "Grade events are not enabled for this organization"
                )
            parse_grade_event_timestamp(timestamp, now=self._clock.now())
            verify_grade_event_signature(
                secret=self._cipher.decrypt(encrypted_secret),
                timestamp=timestamp,
                body=body,
                signature=signature,
            )
        except GradeEventSignatureError:
            await self._audit.record_grade_evidence_event(
                action="integrations.moodle.grade_event_rejected",
                organization_id=organization_id,
                actor_subject_id=None,
                evidence_reference=_UNAUTHENTICATED_EVENT_REFERENCE,
                correlation_id=correlation_id,
                outcome="signature_invalid",
            )
            raise
        try:
            payload: object = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise GradeEventRejectedError("Grade event payload is not JSON") from exc
        try:
            evidence = parse_grade_event_payload(payload)
        except GradeEventRejectedError:
            await self._audit.record_grade_evidence_event(
                action="integrations.moodle.grade_event_rejected",
                organization_id=organization_id,
                actor_subject_id=None,
                evidence_reference="authenticated",
                correlation_id=correlation_id,
                outcome="payload_invalid",
            )
            raise
        return await self.receive_final_grade_evidence(
            organization_id=organization_id,
            evidence=evidence,
            correlation_id=correlation_id,
        )

    async def receive_final_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> GradeEvidenceReceipt:
        """Store one event exactly once and ask official grading policy."""

        is_new = await self._repository.accept_grade_event_once(
            organization_id=organization_id,
            evidence=evidence,
        )
        if not is_new:
            existing = await self._repository.get_grade_evidence_by_event(
                organization_id=organization_id,
                external_event_id=evidence.external_event_id,
            )
            return GradeEvidenceReceipt(
                external_event_id=evidence.external_event_id,
                duplicate=True,
                status=(
                    existing.status
                    if existing is not None
                    else GradeEvidenceStatus.PENDING
                ),
            )
        try:
            disposition = await self._grade_receiver.accept_moodle_evidence(
                organization_id=organization_id,
                evidence=evidence,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            await self._repository.mark_grade_event_outcome(
                organization_id=organization_id,
                external_event_id=evidence.external_event_id,
                status=GradeEvidenceStatus.REJECTED,
                reason_code=self._safe_error_code(exc),
            )
            raise
        status, reason_code = _intake_outcome(disposition)
        await self._repository.mark_grade_event_outcome(
            organization_id=organization_id,
            external_event_id=evidence.external_event_id,
            status=status,
            reason_code=reason_code,
        )
        await self._audit.record_grade_evidence_event(
            action="integrations.moodle.grade_evidence.received",
            organization_id=organization_id,
            actor_subject_id=None,
            evidence_reference=evidence.external_event_id,
            correlation_id=correlation_id,
            outcome=status.value,
        )
        return GradeEvidenceReceipt(
            external_event_id=evidence.external_event_id,
            duplicate=False,
            status=status,
        )

    async def list_grade_evidence(
        self,
        *,
        actor: TenantActorContext,
        status: GradeEvidenceStatus | None,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeEvidenceRecord, ...]:
        """Return a bounded page of tenant evidence for authorized reviewers."""

        _authorize(actor, GRADE_EVIDENCE_READ)
        if limit < 1 or limit > MAX_GRADE_EVIDENCE_PAGE_SIZE or offset < 0:
            raise ValidationError(
                f"Evidence page limit must be 1-{MAX_GRADE_EVIDENCE_PAGE_SIZE} "
                "and offset cannot be negative."
            )
        return await self._repository.list_grade_evidence(
            organization_id=actor.organization_id,
            status=status,
            course_offering_id=course_offering_id,
            limit=limit,
            offset=offset,
        )

    async def get_grade_evidence(
        self,
        *,
        actor: TenantActorContext,
        evidence_id: UUID,
    ) -> MoodleGradeEvidenceRecord:
        """Return one tenant evidence record for authorized reviewers."""

        _authorize(actor, GRADE_EVIDENCE_READ)
        record = await self._repository.get_grade_evidence(
            organization_id=actor.organization_id,
            evidence_id=evidence_id,
        )
        if record is None:
            raise NotFoundError("Moodle grade evidence was not found.")
        return record

    async def pending_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return evidence to the owning grading policy only while it is pending."""

        record = await self._repository.get_grade_evidence(
            organization_id=organization_id,
            evidence_id=evidence_id,
        )
        if record is None or record.status is not GradeEvidenceStatus.PENDING:
            return None
        return record

    async def record_grade_evidence_acceptance(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        final_grade_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> MoodleGradeEvidenceRecord:
        """Link accepted evidence to the official grade the owning domain wrote."""

        record = await self._repository.resolve_grade_evidence(
            organization_id=organization_id,
            evidence_id=evidence_id,
            status=GradeEvidenceStatus.ACCEPTED,
            reason_code=None,
            final_grade_id=final_grade_id,
            resolved_by=actor_subject_id,
            resolved_at=self._clock.now(),
        )
        await self._audit.record_grade_evidence_event(
            action="integrations.moodle.grade_evidence.accepted",
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            evidence_reference=record.external_event_id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )
        return record

    async def record_grade_evidence_rejection(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        reason_code: str,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> MoodleGradeEvidenceRecord:
        """Record an explicit reviewer rejection without discarding evidence."""

        record = await self._repository.resolve_grade_evidence(
            organization_id=organization_id,
            evidence_id=evidence_id,
            status=GradeEvidenceStatus.REJECTED,
            reason_code=reason_code,
            final_grade_id=None,
            resolved_by=actor_subject_id,
            resolved_at=self._clock.now(),
        )
        await self._audit.record_grade_evidence_event(
            action="integrations.moodle.grade_evidence.rejected",
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            evidence_reference=record.external_event_id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )
        return record

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


def _authorize(
    actor: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the verified tenant actor holds one permission."""

    if permission not in actor.permissions:
        raise AuthorizationError


def _intake_outcome(
    disposition: GradeEvidenceDisposition,
) -> tuple[GradeEvidenceStatus, str | None]:
    """Translate the owning domain's answer into stored evidence state."""

    if disposition is GradeEvidenceDisposition.ACCEPTED:
        return GradeEvidenceStatus.ACCEPTED, None
    if disposition is GradeEvidenceDisposition.REJECTED:
        return GradeEvidenceStatus.REJECTED, REJECTED_BY_POLICY_REASON_CODE
    return GradeEvidenceStatus.PENDING, REVIEW_REQUIRED_REASON_CODE


__all__ = [
    "GRADE_EVIDENCE_READ",
    "INTEGRATIONS_CONFIGURE",
    "INTEGRATIONS_READ",
    "MAX_GRADE_EVIDENCE_PAGE_SIZE",
    "REJECTED_BY_POLICY_REASON_CODE",
    "REVIEW_REQUIRED_REASON_CODE",
    "MoodleIntegrationService",
]
