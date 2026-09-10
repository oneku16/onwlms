"""Moodle authority, credential safety, signed intake, and evidence resolution."""

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from uuid import uuid7

import pytest
from cryptography.fernet import Fernet

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.errors import ValidationError
from core.field_encryption import FieldCipher
from integrations.application.ports import MoodleGateway
from integrations.application.service import GRADE_EVIDENCE_READ
from integrations.application.service import MoodleIntegrationService
from integrations.domain.exceptions import GradeEventRejectedError
from integrations.domain.exceptions import GradeEventSignatureError
from integrations.domain.grade_events import compute_grade_event_signature
from integrations.domain.moodle import GradeEvidenceDisposition
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.infrastructure.memory import InMemoryMoodleIntegrationRepository

SIGNING_SECRET = "correct-horse-battery-staple-tenant-signing-secret"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Return one deterministic integration timestamp."""

    current: datetime

    def now(self) -> datetime:
        return self.current


class UnusedGatewayFactory:
    """Fail if a test unexpectedly invokes Moodle HTTP behavior."""

    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleGateway:
        del organization_id
        raise AssertionError("gateway should not be used")


class RecordingGradeReceiver:
    """Record evidence submitted to the authoritative grading boundary."""

    def __init__(
        self,
        disposition: GradeEvidenceDisposition = GradeEvidenceDisposition.ACCEPTED,
        *,
        fail: bool = False,
    ) -> None:
        self.disposition = disposition
        self.fail = fail
        self.received: list[MoodleFinalGradeEvidence] = []

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> GradeEvidenceDisposition:
        del organization_id, correlation_id
        if self.fail:
            raise RuntimeError("grading policy unavailable")
        self.received.append(evidence)
        return self.disposition


@dataclass(frozen=True, slots=True)
class RecordedEvidenceEvent:
    action: str
    organization_id: UUID
    actor_subject_id: UUID | None
    reference: str
    correlation_id: str
    outcome: str


class RecordingMoodleAuditSink:
    """Capture integration evidence without configuration or grade values."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, UUID, UUID, str, str]] = []
        self.evidence_events: list[RecordedEvidenceEvent] = []
        self.reconciliation_events: list[tuple[str, UUID, UUID, str]] = []

    async def record_moodle_configuration_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(
            (action, organization_id, actor_subject_id, correlation_id, outcome)
        )

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
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.evidence_events.append(
            RecordedEvidenceEvent(
                action=action,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                reference=evidence_reference,
                correlation_id=correlation_id,
                outcome=outcome,
            )
        )

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
        del correlation_id
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.reconciliation_events.append(
            (action, organization_id, actor_subject_id, f"{run_id}:{outcome}")
        )


def _actor(
    organization_id: UUID,
    permissions: frozenset[str] | None = None,
) -> TenantActorContext:
    """Create an authorized integration administrator."""

    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="test-correlation",
        permissions=permissions
        or frozenset(
            {"integrations.configure", "integrations.read", GRADE_EVIDENCE_READ}
        ),
    )


def _service(
    repository: InMemoryMoodleIntegrationRepository,
    *,
    receiver: RecordingGradeReceiver | None = None,
    audit: RecordingMoodleAuditSink | None = None,
    clock: FixedClock | None = None,
) -> MoodleIntegrationService:
    """Compose the service with in-memory adapters and a fresh cipher."""

    return MoodleIntegrationService(
        repository=repository,
        gateway_factory=UnusedGatewayFactory(),
        grade_receiver=receiver or RecordingGradeReceiver(),
        cipher=FieldCipher(Fernet.generate_key().decode("ascii")),
        audit=audit or RecordingMoodleAuditSink(),
        clock=clock or FixedClock(NOW),
    )


def _evidence(
    *,
    external_event_id: str = "moodle-event-one",
) -> MoodleFinalGradeEvidence:
    """Create representative untrusted Moodle evidence."""

    return MoodleFinalGradeEvidence(
        external_event_id=external_event_id,
        course_offering_id=uuid7(),
        student_person_id=uuid7(),
        grade_value="87.5",
        observed_at=NOW - timedelta(minutes=1),
        source_version="moodle-5",
    )


def _payload(evidence: MoodleFinalGradeEvidence) -> bytes:
    """Serialize evidence as the documented grade-event payload."""

    return json.dumps(
        {
            "external_event_id": evidence.external_event_id,
            "course_offering_id": str(evidence.course_offering_id),
            "student_person_id": str(evidence.student_person_id),
            "grade_value": evidence.grade_value,
            "observed_at": evidence.observed_at.isoformat(),
            "source_version": evidence.source_version,
        }
    ).encode("utf-8")


def _signed(
    body: bytes, *, secret: str = SIGNING_SECRET, at: datetime = NOW
) -> tuple[str, str]:
    """Return the timestamp and signature headers a Moodle-side sender computes."""

    timestamp = str(int(at.timestamp()))
    return timestamp, compute_grade_event_signature(
        secret=secret,
        timestamp=timestamp,
        body=body,
    )


async def _configured(
    service: MoodleIntegrationService,
    organization_id: UUID,
) -> TenantActorContext:
    """Configure Moodle and the signing secret for one tenant."""

    actor = _actor(organization_id)
    await service.configure(
        actor=actor,
        base_url="https://moodle.example.edu",
        token="secret-token",
    )
    await service.configure_grade_event_secret(actor=actor, secret=SIGNING_SECRET)
    return actor


async def test_configuration_encrypts_token_and_safe_status_omits_it() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(repository, audit=audit)
    organization_id = uuid7()
    actor = _actor(organization_id)

    status = await service.configure(
        actor=actor,
        base_url="https://moodle.example.edu",
        token="secret-token",
    )

    assert repository.encrypted_tokens[organization_id] != "secret-token"
    assert not hasattr(status, "token")
    assert status.grade_events_configured is False
    assert [event[0] for event in audit.events] == [
        "integrations.moodle.configuration_update_requested",
        "integrations.moodle.configuration.updated",
    ]
    assert [event[4] for event in audit.events] == ["intent_recorded", "succeeded"]


async def test_configuration_aborts_when_audit_intent_fails() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    service = _service(repository, audit=RecordingMoodleAuditSink(fail=True))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.configure(
            actor=_actor(uuid7()),
            base_url="https://moodle.example.edu",
            token="secret-token",
        )

    assert repository.configurations == {}


async def test_grade_event_secret_requires_configuration_and_permission() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(repository, audit=audit)
    organization_id = uuid7()
    actor = _actor(organization_id)

    with pytest.raises(ValidationError, match="Configure the Moodle integration"):
        await service.configure_grade_event_secret(actor=actor, secret=SIGNING_SECRET)
    await service.configure(
        actor=actor,
        base_url="https://moodle.example.edu",
        token="secret-token",
    )
    with pytest.raises(ValidationError, match="at least 32"):
        await service.configure_grade_event_secret(actor=actor, secret="too-short")
    with pytest.raises(AuthorizationError):
        await service.configure_grade_event_secret(
            actor=_actor(organization_id, frozenset({"integrations.read"})),
            secret=SIGNING_SECRET,
        )

    status = await service.configure_grade_event_secret(
        actor=actor,
        secret=SIGNING_SECRET,
    )

    assert status.grade_events_configured is True
    assert repository.encrypted_event_secrets[organization_id] != SIGNING_SECRET
    assert audit.events[-2][0] == (
        "integrations.moodle.grade_event_secret_update_requested"
    )
    assert audit.events[-1][0] == "integrations.moodle.grade_event_secret.updated"


async def test_duplicate_grade_evidence_reaches_grading_policy_once() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    receiver = RecordingGradeReceiver()
    service = _service(repository, receiver=receiver)
    organization_id = uuid7()
    evidence = _evidence()

    first = await service.receive_final_grade_evidence(
        organization_id=organization_id,
        evidence=evidence,
        correlation_id="test-correlation",
    )
    duplicate = await service.receive_final_grade_evidence(
        organization_id=organization_id,
        evidence=evidence,
        correlation_id="test-correlation",
    )

    assert first.duplicate is False
    assert first.status is GradeEvidenceStatus.ACCEPTED
    assert duplicate.duplicate is True
    assert duplicate.status is GradeEvidenceStatus.ACCEPTED
    assert receiver.received == [evidence]


async def test_review_required_disposition_keeps_evidence_pending() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(
        repository,
        receiver=RecordingGradeReceiver(GradeEvidenceDisposition.REVIEW_REQUIRED),
        audit=audit,
    )
    organization_id = uuid7()

    receipt = await service.receive_final_grade_evidence(
        organization_id=organization_id,
        evidence=_evidence(),
        correlation_id="test-correlation",
    )

    stored = await repository.get_grade_evidence_by_event(
        organization_id=organization_id,
        external_event_id="moodle-event-one",
    )
    assert receipt.status is GradeEvidenceStatus.PENDING
    assert stored is not None
    assert stored.status is GradeEvidenceStatus.PENDING
    assert stored.reason_code == "review_required"
    assert audit.evidence_events[-1].action == (
        "integrations.moodle.grade_evidence.received"
    )
    assert audit.evidence_events[-1].outcome == "pending"
    assert audit.evidence_events[-1].actor_subject_id is None


async def test_receiver_failure_marks_evidence_rejected_with_safe_code() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    service = _service(repository, receiver=RecordingGradeReceiver(fail=True))
    organization_id = uuid7()

    with pytest.raises(RuntimeError, match="grading policy unavailable"):
        await service.receive_final_grade_evidence(
            organization_id=organization_id,
            evidence=_evidence(),
            correlation_id="test-correlation",
        )

    stored = await repository.get_grade_evidence_by_event(
        organization_id=organization_id,
        external_event_id="moodle-event-one",
    )
    assert stored is not None
    assert stored.status is GradeEvidenceStatus.REJECTED
    assert stored.reason_code is not None
    assert stored.reason_code.startswith("moodle_error_")
    assert "unavailable" not in stored.reason_code


async def test_signed_grade_event_is_stored_once_and_replay_reports_duplicate() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(
        repository,
        receiver=RecordingGradeReceiver(GradeEvidenceDisposition.REVIEW_REQUIRED),
        audit=audit,
    )
    organization_id = uuid7()
    await _configured(service, organization_id)
    body = _payload(_evidence())
    timestamp, signature = _signed(body)

    receipt = await service.ingest_signed_grade_event(
        organization_id=organization_id,
        body=body,
        timestamp=timestamp,
        signature=signature,
        correlation_id="test-correlation",
    )
    replay = await service.ingest_signed_grade_event(
        organization_id=organization_id,
        body=body,
        timestamp=timestamp,
        signature=signature,
        correlation_id="test-correlation",
    )

    assert receipt.duplicate is False
    assert receipt.status is GradeEvidenceStatus.PENDING
    assert replay.duplicate is True
    assert replay.status is GradeEvidenceStatus.PENDING
    assert len(repository.evidence) == 1


async def test_signed_grade_event_fails_closed_on_bad_signature_or_secret() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(repository, audit=audit)
    organization_id = uuid7()
    body = _payload(_evidence())
    timestamp, signature = _signed(body)

    with pytest.raises(GradeEventSignatureError, match="not enabled"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=body,
            timestamp=timestamp,
            signature=signature,
            correlation_id="test-correlation",
        )
    await _configured(service, organization_id)
    _, wrong_signature = _signed(body, secret="another-tenant-secret-with-32-chars!!")
    with pytest.raises(GradeEventSignatureError, match="invalid"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=body,
            timestamp=timestamp,
            signature=wrong_signature,
            correlation_id="test-correlation",
        )
    stale_timestamp, stale_signature = _signed(body, at=NOW - timedelta(minutes=6))
    with pytest.raises(GradeEventSignatureError, match="window"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=body,
            timestamp=stale_timestamp,
            signature=stale_signature,
            correlation_id="test-correlation",
        )
    tampered = body.replace(b"87.5", b"99.9")
    with pytest.raises(GradeEventSignatureError, match="invalid"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=tampered,
            timestamp=timestamp,
            signature=signature,
            correlation_id="test-correlation",
        )

    assert repository.evidence == {}
    rejected = [
        event
        for event in audit.evidence_events
        if event.action == "integrations.moodle.grade_event_rejected"
    ]
    assert len(rejected) == 4
    assert {event.outcome for event in rejected} == {"signature_invalid"}
    assert all(event.reference == "unauthenticated" for event in rejected)


async def test_signed_grade_event_rejects_malformed_or_oversized_payload() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(repository, audit=audit)
    organization_id = uuid7()
    await _configured(service, organization_id)

    not_json = b"{not json"
    timestamp, signature = _signed(not_json)
    with pytest.raises(GradeEventRejectedError, match="not JSON"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=not_json,
            timestamp=timestamp,
            signature=signature,
            correlation_id="test-correlation",
        )
    unsupported = json.dumps({"external_event_id": "x", "surprise": 1}).encode()
    timestamp, signature = _signed(unsupported)
    with pytest.raises(GradeEventRejectedError, match="unsupported keys"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=unsupported,
            timestamp=timestamp,
            signature=signature,
            correlation_id="test-correlation",
        )
    oversized = b"{" + b" " * 20_000 + b"}"
    timestamp, signature = _signed(oversized)
    with pytest.raises(GradeEventRejectedError, match="too large"):
        await service.ingest_signed_grade_event(
            organization_id=organization_id,
            body=oversized,
            timestamp=timestamp,
            signature=signature,
            correlation_id="test-correlation",
        )

    assert repository.evidence == {}
    assert [
        event.outcome
        for event in audit.evidence_events
        if event.action == "integrations.moodle.grade_event_rejected"
    ] == ["payload_invalid"]


async def test_evidence_listing_requires_permission_and_bounds() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    service = _service(
        repository,
        receiver=RecordingGradeReceiver(GradeEvidenceDisposition.REVIEW_REQUIRED),
    )
    organization_id = uuid7()
    other_organization_id = uuid7()
    for index in range(3):
        await service.receive_final_grade_evidence(
            organization_id=organization_id,
            evidence=_evidence(external_event_id=f"event-{index}"),
            correlation_id="test-correlation",
        )
    await service.receive_final_grade_evidence(
        organization_id=other_organization_id,
        evidence=_evidence(external_event_id="foreign"),
        correlation_id="test-correlation",
    )
    actor = _actor(organization_id)

    listed = await service.list_grade_evidence(
        actor=actor,
        status=GradeEvidenceStatus.PENDING,
        course_offering_id=None,
        limit=2,
        offset=0,
    )

    assert len(listed) == 2
    assert all(record.organization_id == organization_id for record in listed)
    with pytest.raises(ValidationError):
        await service.list_grade_evidence(
            actor=actor,
            status=None,
            course_offering_id=None,
            limit=101,
            offset=0,
        )
    with pytest.raises(AuthorizationError):
        await service.list_grade_evidence(
            actor=_actor(organization_id, frozenset({"integrations.read"})),
            status=None,
            course_offering_id=None,
            limit=10,
            offset=0,
        )
    with pytest.raises(NotFoundError):
        await service.get_grade_evidence(actor=actor, evidence_id=uuid7())
    foreign = next(
        record
        for record in repository.evidence.values()
        if record.organization_id == other_organization_id
    )
    with pytest.raises(NotFoundError):
        await service.get_grade_evidence(actor=actor, evidence_id=foreign.id)
    assert (
        await service.pending_grade_evidence(
            organization_id=organization_id,
            evidence_id=foreign.id,
        )
        is None
    )


async def test_evidence_resolution_happens_exactly_once_with_audit() -> None:
    repository = InMemoryMoodleIntegrationRepository()
    audit = RecordingMoodleAuditSink()
    service = _service(
        repository,
        receiver=RecordingGradeReceiver(GradeEvidenceDisposition.REVIEW_REQUIRED),
        audit=audit,
    )
    organization_id = uuid7()
    await service.receive_final_grade_evidence(
        organization_id=organization_id,
        evidence=_evidence(),
        correlation_id="test-correlation",
    )
    stored = next(iter(repository.evidence.values()))
    grade_id = uuid7()
    reviewer = uuid7()

    pending = await service.pending_grade_evidence(
        organization_id=organization_id,
        evidence_id=stored.id,
    )
    accepted = await service.record_grade_evidence_acceptance(
        organization_id=organization_id,
        evidence_id=stored.id,
        final_grade_id=grade_id,
        actor_subject_id=reviewer,
        correlation_id="test-correlation",
    )

    assert pending is not None
    assert accepted.status is GradeEvidenceStatus.ACCEPTED
    assert accepted.accepted_final_grade_id == grade_id
    assert accepted.resolved_by == reviewer
    assert accepted.resolved_at == NOW
    assert (
        await service.pending_grade_evidence(
            organization_id=organization_id,
            evidence_id=stored.id,
        )
        is None
    )
    with pytest.raises(ConflictError):
        await service.record_grade_evidence_rejection(
            organization_id=organization_id,
            evidence_id=stored.id,
            reason_code="rejected_by_reviewer",
            actor_subject_id=reviewer,
            correlation_id="test-correlation",
        )
    with pytest.raises(NotFoundError):
        await service.record_grade_evidence_acceptance(
            organization_id=uuid7(),
            evidence_id=stored.id,
            final_grade_id=grade_id,
            actor_subject_id=reviewer,
            correlation_id="test-correlation",
        )
    assert audit.evidence_events[-1].action == (
        "integrations.moodle.grade_evidence.accepted"
    )
    assert audit.evidence_events[-1].actor_subject_id == reviewer
