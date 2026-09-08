from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.http import install_error_handlers
from grading.application.ports import TermGradeWriteGuard
from grading.application.service import GRADING_CLOSED_TERM_REVISE
from grading.application.service import GRADING_FINAL_RECORD
from grading.application.service import GRADING_FINAL_REVISE
from grading.application.service import GRADING_SCALE_MANAGE
from grading.application.service import GRADING_TRANSCRIPT_READ
from grading.application.service import OfficialGradingService
from grading.domain.exceptions import GradingRuleError
from grading.domain.models import GradeTarget
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleTemplate
from grading.domain.models import build_scale_from_template
from grading.infrastructure.repository import InMemoryExternalGradeEvidenceDirectory
from grading.infrastructure.repository import InMemoryGradeTargetDirectory
from grading.infrastructure.repository import InMemoryGradingRepository
from grading.infrastructure.repository import InMemoryTermClosureDirectory
from grading.infrastructure.repository import InMemoryTermGradeWriteGuard
from grading.presentation.router import router
from identity.presentation.dependencies import require_actor


@dataclass(frozen=True, slots=True)
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@dataclass(frozen=True, slots=True)
class RecordedGradeAuditEvent:
    action: str
    organization_id: UUID
    actor_subject_id: UUID
    final_grade_id: UUID
    correlation_id: str
    after_term_closure: bool
    outcome: str


class RecordingGradingAuditSink:
    """Capture privacy-minimized official grading evidence."""

    def __init__(
        self,
        *,
        fail_on_actions: set[str] | None = None,
    ) -> None:
        self.events: list[RecordedGradeAuditEvent] = []
        self.external_events: list[tuple[str, UUID, str, str | None]] = []
        self.fail_on_actions = set(fail_on_actions or set())

    async def record_final_grade_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        final_grade_id: UUID,
        correlation_id: str,
        after_term_closure: bool,
        outcome: str,
    ) -> None:
        if action in self.fail_on_actions:
            raise RuntimeError("Grading audit is unavailable.")
        self.events.append(
            RecordedGradeAuditEvent(
                action=action,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                final_grade_id=final_grade_id,
                correlation_id=correlation_id,
                after_term_closure=after_term_closure,
                outcome=outcome,
            )
        )

    async def record_external_evidence_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        evidence_id: UUID,
        correlation_id: str,
        outcome: str,
        reason: str | None,
    ) -> None:
        del organization_id, actor_subject_id, correlation_id
        if action in self.fail_on_actions:
            raise RuntimeError("Grading audit is unavailable.")
        self.external_events.append((action, evidence_id, outcome, reason))


class ClosingOnEntryTermGradeWriteGuard:
    """Close the term at one guard entry to simulate the pre-lock race."""

    def __init__(
        self,
        *,
        terms: InMemoryTermClosureDirectory,
        close_on_entry: int,
    ) -> None:
        self._terms = terms
        self._close_on_entry = close_on_entry
        self._entries = 0

    @asynccontextmanager
    async def hold_grade_write(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> AsyncIterator[None]:
        self._entries += 1
        if self._entries == self._close_on_entry:
            self._terms.set_closed(
                organization_id=organization_id,
                term_id=term_id,
            )
        yield


@dataclass(frozen=True, slots=True)
class GradingFixture:
    organization_id: UUID
    student_enrollment_id: UUID
    term_id: UUID
    first_target: GradeTarget
    second_target: GradeTarget
    scale: GradingScale
    repository: InMemoryGradingRepository
    terms: InMemoryTermClosureDirectory
    audit: RecordingGradingAuditSink
    service: OfficialGradingService


def _context(
    *,
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="grading-test",
        permissions=permissions,
    )


async def _fixture(
    *,
    audit: RecordingGradingAuditSink | None = None,
    term_write_guard_factory: (
        Callable[[InMemoryTermClosureDirectory], TermGradeWriteGuard] | None
    ) = None,
) -> GradingFixture:
    organization_id = uuid4()
    student_enrollment_id = uuid4()
    term_id = uuid4()
    first_target = GradeTarget(
        organization_id=organization_id,
        student_academic_enrollment_id=student_enrollment_id,
        course_enrollment_id=uuid4(),
        course_offering_id=uuid4(),
        term_id=term_id,
        course_id=uuid4(),
        credits=Decimal("3"),
    )
    second_target = GradeTarget(
        organization_id=organization_id,
        student_academic_enrollment_id=student_enrollment_id,
        course_enrollment_id=uuid4(),
        course_offering_id=uuid4(),
        term_id=term_id,
        course_id=uuid4(),
        credits=Decimal("4"),
    )
    repository = InMemoryGradingRepository()
    terms = InMemoryTermClosureDirectory()
    audit = audit or RecordingGradingAuditSink()
    service = OfficialGradingService(
        repository=repository,
        targets=InMemoryGradeTargetDirectory((first_target, second_target)),
        terms=terms,
        term_writes=(
            term_write_guard_factory(terms)
            if term_write_guard_factory is not None
            else InMemoryTermGradeWriteGuard()
        ),
        clock=FakeClock(datetime(2026, 8, 5, 10, tzinfo=UTC)),
        audit=audit,
        evidence=InMemoryExternalGradeEvidenceDirectory(),
    )
    scale = build_scale_from_template(
        scale_id=uuid4(),
        organization_id=organization_id,
        name="Official percentage",
        template=GradingScaleTemplate.PERCENTAGE,
    )
    await service.configure_scale(
        context=_context(
            organization_id=organization_id,
            permissions=frozenset({GRADING_SCALE_MANAGE}),
        ),
        scale=scale,
    )
    return GradingFixture(
        organization_id=organization_id,
        student_enrollment_id=student_enrollment_id,
        term_id=term_id,
        first_target=first_target,
        second_target=second_target,
        scale=scale,
        repository=repository,
        terms=terms,
        audit=audit,
        service=service,
    )


async def test_final_grade_revision_preserves_complete_previous_state() -> None:
    fixture = await _fixture()
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    original = await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )

    revised = await fixture.service.revise_final_grade(
        context=actor,
        final_grade_id=original.id,
        raw_score=Decimal("95"),
        explanation="Corrected the approved final calculation.",
    )

    history = await fixture.repository.list_grade_revisions(
        organization_id=fixture.organization_id,
        final_grade_id=original.id,
    )
    assert revised.symbol == "A"
    assert revised.revision_number == 1
    assert revised.gpa_contribution == Decimal("12")
    assert len(history) == 1
    assert history[0].previous_raw_score == Decimal("75")
    assert history[0].previous_symbol == "C"
    assert history[0].replacement_symbol == "A"
    assert history[0].explanation.startswith("Corrected")
    assert [event.action for event in fixture.audit.events] == [
        "grading.final_grade.record_requested",
        "grading.final_grade.recorded",
        "grading.final_grade.revision_requested",
        "grading.final_grade.revised",
    ]
    assert [event.outcome for event in fixture.audit.events] == [
        "intent_recorded",
        "succeeded",
        "intent_recorded",
        "succeeded",
    ]
    assert fixture.audit.events[-1].final_grade_id == original.id
    assert fixture.audit.events[-1].after_term_closure is False


async def test_closed_term_revision_requires_explanation_and_permission() -> None:
    fixture = await _fixture()
    recorder = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD}),
    )
    grade = await fixture.service.record_final_grade(
        context=recorder,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("80"),
    )
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    ordinary_reviser = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_REVISE}),
    )

    with pytest.raises(GradingRuleError, match="explanation"):
        await fixture.service.revise_final_grade(
            context=ordinary_reviser,
            final_grade_id=grade.id,
            raw_score=Decimal("90"),
            explanation="",
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.revise_final_grade(
            context=ordinary_reviser,
            final_grade_id=grade.id,
            raw_score=Decimal("90"),
            explanation="Approved correction after closure.",
        )

    closed_term_reviser = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_REVISE, GRADING_CLOSED_TERM_REVISE}),
    )
    await fixture.service.revise_final_grade(
        context=closed_term_reviser,
        final_grade_id=grade.id,
        raw_score=Decimal("90"),
        explanation="Registrar approved correction after closure.",
    )
    history = await fixture.repository.list_grade_revisions(
        organization_id=fixture.organization_id,
        final_grade_id=grade.id,
    )
    assert history[0].after_term_closure is True
    assert fixture.audit.events[-1].after_term_closure is True


async def test_closed_term_blocks_initial_grade_without_amendment_capability() -> None:
    fixture = await _fixture()
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    recorder = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD}),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.record_final_grade(
            context=recorder,
            course_enrollment_id=fixture.first_target.course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("80"),
            explanation="Registrar-approved late finalization.",
        )

    grades = await fixture.repository.list_student_final_grades(
        organization_id=fixture.organization_id,
        student_academic_enrollment_id=fixture.student_enrollment_id,
    )
    assert grades == ()
    assert fixture.audit.events == []


async def test_closed_term_initial_grade_requires_explanation() -> None:
    fixture = await _fixture()
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    recorder = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_CLOSED_TERM_REVISE}),
    )

    with pytest.raises(GradingRuleError, match="explanation"):
        await fixture.service.record_final_grade(
            context=recorder,
            course_enrollment_id=fixture.first_target.course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("80"),
        )

    assert fixture.audit.events == []


async def test_closed_term_initial_grade_with_amendment_capability() -> None:
    fixture = await _fixture()
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    recorder = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_CLOSED_TERM_REVISE}),
    )

    grade = await fixture.service.record_final_grade(
        context=recorder,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("80"),
        explanation="Registrar-approved late finalization.",
    )
    stored = await fixture.repository.get_final_grade(
        organization_id=fixture.organization_id,
        final_grade_id=grade.id,
    )
    history_reader = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_REVISE}),
    )
    history = await fixture.service.grade_history(
        context=history_reader,
        final_grade_id=grade.id,
    )

    assert grade.revision_number == 0
    assert grade.recorded_after_term_closure is True
    assert grade.recording_explanation == "Registrar-approved late finalization."
    assert stored == grade
    assert history.final_grade_id == grade.id
    assert history.recorded_by == recorder.subject_id
    assert history.recorded_after_term_closure is True
    assert history.recording_explanation == "Registrar-approved late finalization."
    assert history.revisions == ()
    assert [event.action for event in fixture.audit.events] == [
        "grading.final_grade.record_requested",
        "grading.final_grade.recorded",
    ]
    assert all(event.after_term_closure for event in fixture.audit.events)


async def test_record_rechecks_term_after_entering_write_guard() -> None:
    fixture = await _fixture(
        term_write_guard_factory=lambda terms: ClosingOnEntryTermGradeWriteGuard(
            terms=terms,
            close_on_entry=1,
        )
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.record_final_grade(
            context=_context(
                organization_id=fixture.organization_id,
                permissions=frozenset({GRADING_FINAL_RECORD}),
            ),
            course_enrollment_id=fixture.first_target.course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("80"),
            explanation="The term closed while this grade was being recorded.",
        )

    assert fixture.audit.events == []
    assert (
        await fixture.repository.list_student_final_grades(
            organization_id=fixture.organization_id,
            student_academic_enrollment_id=fixture.student_enrollment_id,
        )
        == ()
    )


async def test_ordinary_revision_rechecks_closed_term_inside_write_guard() -> None:
    fixture = await _fixture(
        term_write_guard_factory=lambda terms: ClosingOnEntryTermGradeWriteGuard(
            terms=terms,
            close_on_entry=2,
        )
    )
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    original = await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.revise_final_grade(
            context=actor,
            final_grade_id=original.id,
            raw_score=Decimal("95"),
            explanation="Ordinary correction raced with closure.",
        )

    assert (
        await fixture.repository.get_final_grade(
            organization_id=fixture.organization_id,
            final_grade_id=original.id,
        )
        == original
    )
    assert (
        await fixture.repository.list_grade_revisions(
            organization_id=fixture.organization_id,
            final_grade_id=original.id,
        )
        == ()
    )
    assert [event.action for event in fixture.audit.events] == [
        "grading.final_grade.record_requested",
        "grading.final_grade.recorded",
    ]


async def test_record_audit_failure_prevents_final_grade_creation() -> None:
    audit = RecordingGradingAuditSink(
        fail_on_actions={"grading.final_grade.record_requested"}
    )
    fixture = await _fixture(audit=audit)
    recorder = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD}),
    )

    with pytest.raises(RuntimeError, match="audit is unavailable"):
        await fixture.service.record_final_grade(
            context=recorder,
            course_enrollment_id=fixture.first_target.course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("80"),
        )

    grades = await fixture.repository.list_student_final_grades(
        organization_id=fixture.organization_id,
        student_academic_enrollment_id=fixture.student_enrollment_id,
    )
    assert grades == ()
    assert fixture.audit.events == []


async def test_revision_audit_failure_preserves_grade_and_empty_history() -> None:
    fixture = await _fixture()
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    original = await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )
    fixture.audit.fail_on_actions.add("grading.final_grade.revision_requested")

    with pytest.raises(RuntimeError, match="audit is unavailable"):
        await fixture.service.revise_final_grade(
            context=actor,
            final_grade_id=original.id,
            raw_score=Decimal("95"),
            explanation="Attempted correction.",
        )

    current = await fixture.repository.get_final_grade(
        organization_id=fixture.organization_id,
        final_grade_id=original.id,
    )
    history = await fixture.repository.list_grade_revisions(
        organization_id=fixture.organization_id,
        final_grade_id=original.id,
    )
    assert current == original
    assert history == ()
    assert [event.action for event in fixture.audit.events] == [
        "grading.final_grade.record_requested",
        "grading.final_grade.recorded",
    ]


async def test_revision_history_requires_revise_permission_and_exact_tenant() -> None:
    fixture = await _fixture()
    reviser = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    original = await fixture.service.record_final_grade(
        context=reviser,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )
    await fixture.service.revise_final_grade(
        context=reviser,
        final_grade_id=original.id,
        raw_score=Decimal("85"),
        explanation="Approved correction.",
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.revision_history(
            context=_context(
                organization_id=fixture.organization_id,
                permissions=frozenset({GRADING_TRANSCRIPT_READ}),
            ),
            final_grade_id=original.id,
        )
    with pytest.raises(NotFoundError):
        await fixture.service.revision_history(
            context=_context(
                organization_id=uuid4(),
                permissions=frozenset({GRADING_FINAL_REVISE}),
            ),
            final_grade_id=original.id,
        )

    history = await fixture.service.revision_history(
        context=reviser,
        final_grade_id=original.id,
    )
    assert len(history) == 1
    assert history[0].explanation == "Approved correction."


async def test_gpa_uses_stored_grade_contributions_and_attempted_credits() -> None:
    fixture = await _fixture()
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_TRANSCRIPT_READ}),
    )
    await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("95"),
    )
    await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.second_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("40"),
    )

    summary = await fixture.service.gpa_summary(
        context=actor,
        student_academic_enrollment_id=fixture.student_enrollment_id,
    )
    transcript = await fixture.service.transcript(
        context=actor,
        student_academic_enrollment_id=fixture.student_enrollment_id,
    )
    assert summary.credits_attempted == Decimal("7")
    assert summary.credits_earned == Decimal("3")
    assert summary.quality_points == Decimal("12")
    assert summary.gpa == Decimal("12") / Decimal("7")
    assert len(transcript) == 2


async def test_pass_fail_template_does_not_distort_gpa() -> None:
    organization_id = uuid4()
    scale = build_scale_from_template(
        scale_id=uuid4(),
        organization_id=organization_id,
        name="Pass or fail",
        template=GradingScaleTemplate.PASS_FAIL,
    )

    passing = scale.resolve(Decimal(1))

    assert passing.symbol == "Pass"
    assert passing.passing is True
    assert passing.grade_points is None


async def test_cross_tenant_course_enrollment_is_not_gradeable() -> None:
    fixture = await _fixture()
    attacker = _context(
        organization_id=uuid4(),
        permissions=frozenset({GRADING_FINAL_RECORD}),
    )

    with pytest.raises(NotFoundError):
        await fixture.service.record_final_grade(
            context=attacker,
            course_enrollment_id=fixture.first_target.course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("95"),
        )


async def test_revision_history_api_is_typed_authorized_and_tenant_scoped() -> None:
    fixture = await _fixture()
    reviser = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    original = await fixture.service.record_final_grade(
        context=reviser,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )
    await fixture.service.revise_final_grade(
        context=reviser,
        final_grade_id=original.id,
        raw_score=Decimal("95"),
        explanation="Registrar-approved correction.",
    )
    current_actor = {"value": reviser}

    async def actor_dependency() -> TenantActorContext:
        return current_actor["value"]

    app = FastAPI()
    app.state.official_grading_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        authorized = await client.get(
            f"/api/v1/grading/final-grades/{original.id}/revisions"
        )
        current_actor["value"] = _context(
            organization_id=fixture.organization_id,
            permissions=frozenset({GRADING_TRANSCRIPT_READ}),
        )
        unauthorized = await client.get(
            f"/api/v1/grading/final-grades/{original.id}/revisions"
        )
        current_actor["value"] = _context(
            organization_id=uuid4(),
            permissions=frozenset({GRADING_FINAL_REVISE}),
        )
        cross_tenant = await client.get(
            f"/api/v1/grading/final-grades/{original.id}/revisions"
        )

    payload = authorized.json()
    assert authorized.status_code == 200
    assert len(payload) == 1
    assert payload[0]["final_grade_id"] == str(original.id)
    assert payload[0]["revision_number"] == 1
    assert payload[0]["explanation"] == "Registrar-approved correction."
    assert payload[0]["revised_by"] == str(reviser.subject_id)
    assert payload[0]["after_term_closure"] is False
    assert unauthorized.status_code == 403
    assert cross_tenant.status_code == 404
    operation = app.openapi()["paths"][
        "/api/v1/grading/final-grades/{final_grade_id}/revisions"
    ]["get"]
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "array"
    )


async def test_closed_initial_grade_history_api_exposes_recording_explanation() -> None:
    fixture = await _fixture()
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset(
            {
                GRADING_FINAL_RECORD,
                GRADING_FINAL_REVISE,
                GRADING_CLOSED_TERM_REVISE,
            }
        ),
    )
    grade = await fixture.service.record_final_grade(
        context=actor,
        course_enrollment_id=fixture.first_target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("80"),
        explanation="Registrar-approved late finalization.",
    )

    async def actor_dependency() -> TenantActorContext:
        return actor

    app = FastAPI()
    app.state.official_grading_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/grading/final-grades/{grade.id}/history")

    assert response.status_code == 200
    assert response.json() == {
        "final_grade_id": str(grade.id),
        "recorded_by": str(actor.subject_id),
        "recorded_at": grade.recorded_at.isoformat().replace("+00:00", "Z"),
        "recorded_after_term_closure": True,
        "recording_explanation": "Registrar-approved late finalization.",
        "revisions": [],
    }
    schema = app.openapi()["components"]["schemas"]["FinalGradeHistoryResponse"]
    assert {
        "recorded_after_term_closure",
        "recording_explanation",
        "revisions",
    }.issubset(schema["required"])
