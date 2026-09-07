"""Moodle authority, credential safety, and duplicate-event behavior."""

from uuid import UUID
from uuid import uuid7

import pytest
from cryptography.fernet import Fernet

from core.context import TenantActorContext
from core.field_encryption import FieldCipher
from core.time import utc_now
from integrations.application.ports import MoodleGateway
from integrations.application.service import MoodleIntegrationService
from integrations.domain.moodle import IntegrationStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence


class InMemoryMoodleRepository:
    """Store protected tenant configuration and duplicate keys in memory."""

    def __init__(self) -> None:
        self.configurations: dict[UUID, tuple[MoodleConfiguration, str]] = {}
        self.events: dict[tuple[UUID, str], bool | None] = {}
        self.mappings: dict[tuple[UUID, str, UUID], str] = {}

    async def configure(
        self,
        *,
        organization_id: UUID,
        base_url: str,
        encrypted_token: str,
    ) -> MoodleConfiguration:
        """Store protected configuration."""

        configuration = MoodleConfiguration(
            organization_id=organization_id,
            base_url=base_url,
            status=IntegrationStatus.CONFIGURED,
            last_success_at=None,
            last_error_code=None,
        )
        self.configurations[organization_id] = (configuration, encrypted_token)
        return configuration

    async def get_configuration(
        self,
        organization_id: UUID,
    ) -> MoodleConfiguration | None:
        """Return safe configuration."""

        value = self.configurations.get(organization_id)
        return value[0] if value else None

    async def get_encrypted_token(self, organization_id: UUID) -> str | None:
        """Return protected credential."""

        value = self.configurations.get(organization_id)
        return value[1] if value else None

    async def put_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        external_id: str,
    ) -> None:
        """Store one mapping."""

        self.mappings[(organization_id, entity_type, entity_id)] = external_id

    async def get_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> str | None:
        """Resolve one mapping."""

        return self.mappings.get((organization_id, entity_type, entity_id))

    async def accept_grade_event_once(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
    ) -> bool:
        """Accept one external event key."""

        key = (organization_id, evidence.external_event_id)
        if key in self.events:
            return False
        self.events[key] = None
        return True

    async def mark_grade_event_outcome(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
        accepted: bool,
        reason_code: str | None,
    ) -> None:
        """Record the official-domain outcome."""

        del reason_code
        self.events[(organization_id, external_event_id)] = accepted

    async def record_success(self, organization_id: UUID) -> None:
        """Record success for protocol completeness."""

        del organization_id

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        error_code: str,
    ) -> None:
        """Record failure for protocol completeness."""

        del organization_id, error_code


class UnusedGatewayFactory:
    """Fail if a test unexpectedly invokes Moodle HTTP behavior."""

    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleGateway:
        """Reject unexpected construction."""

        del organization_id
        raise AssertionError("gateway should not be used")


class RecordingGradeReceiver:
    """Record evidence submitted to the authoritative grading boundary."""

    def __init__(self) -> None:
        self.received: list[MoodleFinalGradeEvidence] = []

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> bool:
        """Accept evidence without treating Moodle as direct authority."""

        del organization_id, correlation_id
        self.received.append(evidence)
        return True


class RecordingMoodleAuditSink:
    """Capture configuration evidence without configuration values."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, UUID, UUID, str, str]] = []

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


def _actor(organization_id: UUID) -> TenantActorContext:
    """Create an authorized integration administrator."""

    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="test-correlation",
        permissions=frozenset({"integrations.configure", "integrations.read"}),
    )


async def test_configuration_encrypts_token_and_safe_status_omits_it() -> None:
    repository = InMemoryMoodleRepository()
    audit = RecordingMoodleAuditSink()
    key = Fernet.generate_key().decode("ascii")
    service = MoodleIntegrationService(
        repository=repository,
        gateway_factory=UnusedGatewayFactory(),
        grade_receiver=RecordingGradeReceiver(),
        cipher=FieldCipher(key),
        audit=audit,
    )
    organization_id = uuid7()
    actor = _actor(organization_id)

    status = await service.configure(
        actor=actor,
        base_url="https://moodle.example.edu",
        token="secret-token",
    )

    stored = repository.configurations[organization_id][1]
    assert stored != "secret-token"
    assert not hasattr(status, "token")
    assert [event[0] for event in audit.events] == [
        "integrations.moodle.configuration_update_requested",
        "integrations.moodle.configuration.updated",
    ]
    assert [event[4] for event in audit.events] == [
        "intent_recorded",
        "succeeded",
    ]


async def test_configuration_aborts_when_audit_intent_fails() -> None:
    repository = InMemoryMoodleRepository()
    service = MoodleIntegrationService(
        repository=repository,
        gateway_factory=UnusedGatewayFactory(),
        grade_receiver=RecordingGradeReceiver(),
        cipher=FieldCipher(Fernet.generate_key().decode("ascii")),
        audit=RecordingMoodleAuditSink(fail=True),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.configure(
            actor=_actor(uuid7()),
            base_url="https://moodle.example.edu",
            token="secret-token",
        )

    assert repository.configurations == {}


async def test_duplicate_grade_evidence_reaches_grading_policy_once() -> None:
    repository = InMemoryMoodleRepository()
    receiver = RecordingGradeReceiver()
    service = MoodleIntegrationService(
        repository=repository,
        gateway_factory=UnusedGatewayFactory(),
        grade_receiver=receiver,
        cipher=FieldCipher(Fernet.generate_key().decode("ascii")),
        audit=RecordingMoodleAuditSink(),
    )
    organization_id = uuid7()
    evidence = MoodleFinalGradeEvidence(
        external_event_id="moodle-event-one",
        course_offering_id=uuid7(),
        student_person_id=uuid7(),
        grade_value="87.5",
        observed_at=utc_now(),
        source_version="moodle-5",
    )

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

    assert first is True
    assert duplicate is False
    assert receiver.received == [evidence]
