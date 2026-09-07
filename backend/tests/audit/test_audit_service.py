"""Audit authorization and tenant-isolation behavior."""

from uuid import uuid7

import pytest

from audit.application.service import AuditService
from audit.domain.records import AuditRecord
from audit.domain.records import AuditSource
from audit.infrastructure.sinks import ApplicationAuditSink
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.time import utc_now


class InMemoryAuditRepository:
    """Keep test evidence in insertion order."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append(self, record: AuditRecord) -> None:
        """Append one record."""

        self.records.append(record)

    async def list_for_organization(
        self,
        *,
        organization_id: object,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Return only matching tenant records."""

        matching = [
            record
            for record in self.records
            if record.organization_id == organization_id
        ]
        return matching[offset : offset + limit]

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Return only global records."""

        matching = [record for record in self.records if record.organization_id is None]
        return matching[offset : offset + limit]


async def test_tenant_actor_cannot_query_another_organization() -> None:
    organization_a = uuid7()
    organization_b = uuid7()
    actor = TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_a,
        membership_id=uuid7(),
        correlation_id="test-correlation",
        permissions=frozenset({"audit.read"}),
    )
    service = AuditService(InMemoryAuditRepository())

    with pytest.raises(AuthorizationError):
        await service.list_for_actor(
            actor=actor,
            limit=20,
            offset=0,
            organization_id=organization_b,
        )


async def test_tenant_actor_reads_only_own_append_only_evidence() -> None:
    organization_id = uuid7()
    repository = InMemoryAuditRepository()
    record = AuditRecord(
        id=uuid7(),
        organization_id=organization_id,
        actor_subject_id=uuid7(),
        action="grade.final.revised",
        entity_type="final_grade",
        entity_id="grade-id",
        occurred_at=utc_now(),
        source=AuditSource.API,
        outcome="success",
        correlation_id="test-correlation",
        reason="Approved correction",
    )
    await repository.append(record)
    actor = TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="test-correlation",
        permissions=frozenset({"audit.read"}),
    )

    result = await AuditService(repository).list_for_actor(
        actor=actor,
        limit=20,
        offset=0,
    )

    assert result == [record]


async def test_application_sink_minimizes_governance_evidence() -> None:
    repository = InMemoryAuditRepository()
    sink = ApplicationAuditSink(AuditService(repository))
    organization_id = uuid7()
    actor_subject_id = uuid7()
    grade_id = uuid7()
    request_id = uuid7()
    term_id = uuid7()
    job_id = uuid7()
    scheduling_id = uuid7()

    await sink.record_final_grade_event(
        action="grading.final_grade.revision_requested",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        final_grade_id=grade_id,
        correlation_id="grade-correlation",
        after_term_closure=True,
        outcome="intent_recorded",
    )
    await sink.record_course_selection_event(
        action="academics.course_selection.rejection_requested",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        request_id=request_id,
        correlation_id="selection-correlation",
        outcome="intent_recorded",
    )
    await sink.record_term_closure_intent(
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        term_id=term_id,
        correlation_id="term-close-correlation",
        reason="Registrar approval",
    )
    await sink.record_moodle_configuration_event(
        action="integrations.moodle.configuration.updated",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        correlation_id="moodle-correlation",
        outcome="succeeded",
    )
    await sink.record_provisioning_attempt(
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        job_id=job_id,
        target="moodle",
        attempt=2,
        outcome="retryable_failure",
        correlation_id="provisioning-correlation",
        worker_initiated=True,
    )
    await sink.record_scheduling_event(
        action="scheduling.session.create.intent",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        target_id=scheduling_id,
        correlation_id="scheduling-correlation",
        outcome="intent_recorded",
    )

    grade, selection, closure_intent, moodle, provisioning, scheduling = (
        repository.records
    )
    assert grade.entity_id == str(grade_id)
    assert grade.action == "grading.final_grade.revision_requested"
    assert grade.outcome == "intent_recorded"
    assert grade.reason is None
    assert grade.metadata == {"after_term_closure": True}
    assert selection.entity_id == str(request_id)
    assert selection.action == "academics.course_selection.rejection_requested"
    assert selection.outcome == "intent_recorded"
    assert selection.reason is None
    assert selection.metadata is None
    assert closure_intent.organization_id == organization_id
    assert closure_intent.actor_subject_id == actor_subject_id
    assert closure_intent.action == "academics.term.closure_intent.authorized"
    assert closure_intent.entity_type == "academic_term"
    assert closure_intent.entity_id == str(term_id)
    assert closure_intent.correlation_id == "term-close-correlation"
    assert closure_intent.outcome == "intent_recorded"
    assert closure_intent.reason == "Registrar approval"
    assert closure_intent.metadata is None
    assert moodle.entity_id == str(organization_id)
    assert moodle.outcome == "succeeded"
    assert moodle.reason is None
    assert moodle.metadata is None
    assert provisioning.entity_id == str(job_id)
    assert provisioning.source is AuditSource.WORKER
    assert provisioning.metadata == {"target": "moodle", "attempt": 2}
    assert scheduling.entity_type == "scheduling_resource"
    assert scheduling.entity_id == str(scheduling_id)
    assert scheduling.action == "scheduling.session.create.intent"
    assert scheduling.outcome == "intent_recorded"
    assert scheduling.reason is None
    assert scheduling.metadata is None
