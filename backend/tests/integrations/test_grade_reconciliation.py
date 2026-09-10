"""Selected-term reconciliation observes mapped Moodle totals as evidence."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from uuid import UUID
from uuid import uuid7

import pytest
from cryptography.fernet import Fernet

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ExternalServiceError
from core.errors import NotFoundError
from core.errors import ValidationError
from core.field_encryption import FieldCipher
from integrations.application.ports import MoodleGateway
from integrations.application.reconciliation_service import GRADE_EVIDENCE_RECONCILE
from integrations.application.reconciliation_service import MAX_RECONCILIATION_OFFERINGS
from integrations.application.reconciliation_service import (
    MoodleGradeReconciliationService,
)
from integrations.application.service import GRADE_EVIDENCE_READ
from integrations.application.service import MoodleIntegrationService
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import IntegrationStatus
from integrations.domain.moodle import MoodleCourseGradeObservation
from integrations.domain.moodle import MoodleDeadlineEvidence
from integrations.domain.moodle import ReconciliationRunStatus
from integrations.infrastructure.grade_receiver import (
    ReviewRequiredGradeEvidenceReceiver,
)
from integrations.infrastructure.memory import InMemoryMoodleIntegrationRepository
from integrations.infrastructure.memory import InMemoryMoodleReconciliationRunRepository

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class FakeMoodleGateway:
    """Serve course totals per external course without other Moodle behavior."""

    def __init__(
        self,
        grades: dict[str, list[MoodleCourseGradeObservation]],
        *,
        fail: bool = False,
    ) -> None:
        self._grades = grades
        self._fail = fail
        self.requested: list[str] = []

    async def ensure_user(
        self,
        *,
        external_username: str,
        display_name: str,
        email: str | None,
        idempotency_key: str,
    ) -> str:
        raise AssertionError("reconciliation must not provision users")

    async def ensure_course(
        self,
        *,
        course_code: str,
        course_title: str,
        idempotency_key: str,
    ) -> str:
        raise AssertionError("reconciliation must not create courses")

    async def set_enrollment(
        self,
        *,
        external_user_id: str,
        external_course_id: str,
        role: str,
        active: bool,
        idempotency_key: str,
    ) -> None:
        raise AssertionError("reconciliation must not change enrollments")

    async def list_deadlines(
        self,
        *,
        external_user_id: str,
    ) -> list[MoodleDeadlineEvidence]:
        raise AssertionError("reconciliation must not read deadlines")

    async def list_course_grades(
        self,
        *,
        external_course_id: str,
    ) -> list[MoodleCourseGradeObservation]:
        self.requested.append(external_course_id)
        if self._fail:
            raise ExternalServiceError("Moodle request failed")
        return list(self._grades.get(external_course_id, []))


class FakeGatewayFactory:
    def __init__(self, gateway: FakeMoodleGateway) -> None:
        self._gateway = gateway

    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleGateway:
        del organization_id
        return self._gateway


class FakeTermOfferings:
    def __init__(self, offerings: dict[tuple[UUID, UUID], frozenset[UUID]]) -> None:
        self._offerings = offerings

    async def list_course_offering_ids(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> frozenset[UUID] | None:
        return self._offerings.get((organization_id, term_id))


class RecordingAuditSink:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    async def record_moodle_configuration_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del organization_id, actor_subject_id, correlation_id
        self.actions.append((action, outcome))

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
        del organization_id, actor_subject_id, evidence_reference, correlation_id
        self.actions.append((action, outcome))

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
        del organization_id, actor_subject_id, run_id, correlation_id
        self.actions.append((action, outcome))


@dataclass(frozen=True, slots=True)
class ReconciliationFixture:
    organization_id: UUID
    term_id: UUID
    mapped_offering_id: UUID
    unmapped_offering_id: UUID
    mapped_person_id: UUID
    repository: InMemoryMoodleIntegrationRepository
    runs: InMemoryMoodleReconciliationRunRepository
    gateway: FakeMoodleGateway
    audit: RecordingAuditSink
    service: MoodleGradeReconciliationService


def _observation(user_id: str, grade: str) -> MoodleCourseGradeObservation:
    return MoodleCourseGradeObservation(
        external_user_id=user_id,
        grade_item_id="900",
        grade_raw=grade,
        graded_at=NOW,
        observed_at=NOW,
        source_version="moodle-webservice-v1",
    )


def _actor(
    organization_id: UUID,
    permissions: frozenset[str] | None = None,
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="reconcile-test",
        permissions=permissions
        or frozenset({GRADE_EVIDENCE_RECONCILE, GRADE_EVIDENCE_READ}),
    )


async def _fixture(
    *,
    gateway_fails: bool = False,
    offering_count: int = 2,
) -> ReconciliationFixture:
    organization_id = uuid7()
    term_id = uuid7()
    mapped_offering_id = uuid7()
    unmapped_offering_id = uuid7()
    mapped_person_id = uuid7()
    repository = InMemoryMoodleIntegrationRepository()
    await repository.configure(
        organization_id=organization_id,
        base_url="https://moodle.example.edu",
        encrypted_token="protected",
    )
    await repository.put_mapping(
        organization_id=organization_id,
        entity_type="course_offering",
        entity_id=mapped_offering_id,
        external_id="course-11",
    )
    await repository.put_mapping(
        organization_id=organization_id,
        entity_type="person",
        entity_id=mapped_person_id,
        external_id="user-7",
    )
    gateway = FakeMoodleGateway(
        {"course-11": [_observation("user-7", "87.5"), _observation("user-8", "40")]},
        fail=gateway_fails,
    )
    audit = RecordingAuditSink()
    clock = FixedClock(NOW)
    intake = MoodleIntegrationService(
        repository=repository,
        gateway_factory=FakeGatewayFactory(gateway),
        grade_receiver=ReviewRequiredGradeEvidenceReceiver(),
        cipher=FieldCipher(Fernet.generate_key().decode("ascii")),
        audit=audit,
        clock=clock,
    )
    offering_ids = {mapped_offering_id, unmapped_offering_id}
    while len(offering_ids) < offering_count:
        offering_ids.add(uuid7())
    runs = InMemoryMoodleReconciliationRunRepository()
    service = MoodleGradeReconciliationService(
        repository=repository,
        runs=runs,
        intake=intake,
        gateway_factory=FakeGatewayFactory(gateway),
        offerings=FakeTermOfferings(
            {(organization_id, term_id): frozenset(offering_ids)}
        ),
        clock=clock,
        audit=audit,
    )
    return ReconciliationFixture(
        organization_id=organization_id,
        term_id=term_id,
        mapped_offering_id=mapped_offering_id,
        unmapped_offering_id=unmapped_offering_id,
        mapped_person_id=mapped_person_id,
        repository=repository,
        runs=runs,
        gateway=gateway,
        audit=audit,
        service=service,
    )


async def test_reconciliation_observes_mapped_offerings_and_counts_the_rest() -> None:
    fixture = await _fixture()

    run = await fixture.service.reconcile_term(
        actor=_actor(fixture.organization_id),
        term_id=fixture.term_id,
    )

    assert run.status is ReconciliationRunStatus.SUCCEEDED
    assert run.offering_count == 2
    assert run.unmapped_offering_count == 1
    assert run.observed_count == 2
    assert run.new_evidence_count == 1
    assert run.duplicate_count == 0
    assert run.unmapped_user_count == 1
    assert run.finished_at == NOW
    assert fixture.gateway.requested == ["course-11"]
    stored = list(fixture.repository.evidence.values())
    assert len(stored) == 1
    assert stored[0].course_offering_id == fixture.mapped_offering_id
    assert stored[0].student_person_id == fixture.mapped_person_id
    assert stored[0].grade_value == "87.5"
    assert stored[0].status is GradeEvidenceStatus.PENDING
    assert stored[0].reason_code == "review_required"
    assert stored[0].external_event_id.startswith("reconciliation:course-11:user-7:")
    configuration = fixture.repository.configurations[fixture.organization_id]
    assert configuration.status is IntegrationStatus.HEALTHY
    assert (
        await fixture.runs.get_run(
            organization_id=fixture.organization_id,
            run_id=run.id,
        )
        == run
    )
    assert [action for action, _ in fixture.audit.actions] == [
        "integrations.moodle.grade_reconciliation_requested",
        "integrations.moodle.grade_evidence.received",
        "integrations.moodle.grade_reconciliation.succeeded",
    ]


async def test_reconciliation_rerun_reports_duplicates() -> None:
    fixture = await _fixture()
    actor = _actor(fixture.organization_id)
    await fixture.service.reconcile_term(actor=actor, term_id=fixture.term_id)

    rerun = await fixture.service.reconcile_term(actor=actor, term_id=fixture.term_id)

    assert rerun.new_evidence_count == 0
    assert rerun.duplicate_count == 1
    assert len(fixture.repository.evidence) == 1
    listed = await fixture.service.list_runs(actor=actor, limit=10, offset=0)
    assert next(run.id for run in listed) == rerun.id
    assert len(listed) == 2


async def test_reconciliation_failure_marks_run_and_integration_failed() -> None:
    fixture = await _fixture(gateway_fails=True)
    actor = _actor(fixture.organization_id)

    with pytest.raises(ExternalServiceError):
        await fixture.service.reconcile_term(actor=actor, term_id=fixture.term_id)

    (run,) = fixture.runs.runs.values()
    assert run.status is ReconciliationRunStatus.FAILED
    assert run.error_code is not None
    assert run.error_code.startswith("moodle_error_")
    assert run.finished_at == NOW
    configuration = fixture.repository.configurations[fixture.organization_id]
    assert configuration.status is IntegrationStatus.DEGRADED
    assert fixture.audit.actions[-1] == (
        "integrations.moodle.grade_reconciliation.failed",
        "failed",
    )
    assert fixture.repository.evidence == {}


async def test_reconciliation_requires_permission_known_term_and_bounded_size() -> None:
    fixture = await _fixture()
    reader = _actor(fixture.organization_id, frozenset({GRADE_EVIDENCE_READ}))

    with pytest.raises(AuthorizationError):
        await fixture.service.reconcile_term(actor=reader, term_id=fixture.term_id)
    with pytest.raises(NotFoundError):
        await fixture.service.reconcile_term(
            actor=_actor(fixture.organization_id),
            term_id=uuid7(),
        )
    with pytest.raises(NotFoundError):
        await fixture.service.reconcile_term(
            actor=_actor(uuid7()),
            term_id=fixture.term_id,
        )
    oversized = await _fixture(offering_count=MAX_RECONCILIATION_OFFERINGS + 1)
    with pytest.raises(ValidationError, match="bounded"):
        await oversized.service.reconcile_term(
            actor=_actor(oversized.organization_id),
            term_id=oversized.term_id,
        )
    assert fixture.runs.runs == {}
    assert oversized.runs.runs == {}


async def test_run_reads_require_read_permission_and_stay_tenant_scoped() -> None:
    fixture = await _fixture()
    actor = _actor(fixture.organization_id)
    run = await fixture.service.reconcile_term(actor=actor, term_id=fixture.term_id)

    with pytest.raises(AuthorizationError):
        await fixture.service.list_runs(
            actor=_actor(
                fixture.organization_id, frozenset({GRADE_EVIDENCE_RECONCILE})
            ),
            limit=10,
            offset=0,
        )
    with pytest.raises(NotFoundError):
        await fixture.service.get_run(actor=_actor(uuid7()), run_id=run.id)
    with pytest.raises(ValidationError):
        await fixture.service.list_runs(actor=actor, limit=0, offset=0)
    assert await fixture.service.get_run(actor=actor, run_id=run.id) == run
