"""Official acceptance and rejection of external (Moodle) grade evidence."""

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
from grading.application.service import GRADING_CLOSED_TERM_REVISE
from grading.application.service import GRADING_FINAL_RECORD
from grading.application.service import GRADING_FINAL_REVISE
from grading.application.service import GRADING_SCALE_MANAGE
from grading.application.service import OfficialGradingService
from grading.domain.exceptions import GradingRuleError
from grading.domain.models import ExternalGradeEvidence
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
from identity.presentation.dependencies import require_csrf

NOW = datetime(2026, 8, 5, 10, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class RecordingAuditSink:
    """Capture grade and evidence audit actions in order."""

    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []
        self.reasons: list[str | None] = []

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
        del organization_id, actor_subject_id, final_grade_id, correlation_id
        del after_term_closure
        self.actions.append((action, outcome))

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
        del organization_id, actor_subject_id, evidence_id, correlation_id
        self.actions.append((action, outcome))
        self.reasons.append(reason)


@dataclass(frozen=True, slots=True)
class EvidenceFixture:
    organization_id: UUID
    term_id: UUID
    person_id: UUID
    target: GradeTarget
    scale: GradingScale
    evidence: ExternalGradeEvidence
    repository: InMemoryGradingRepository
    targets: InMemoryGradeTargetDirectory
    terms: InMemoryTermClosureDirectory
    directory: InMemoryExternalGradeEvidenceDirectory
    audit: RecordingAuditSink
    service: OfficialGradingService


def _context(
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="evidence-test",
        permissions=permissions,
    )


async def _fixture(*, grade_value: str = "87.5") -> EvidenceFixture:
    organization_id = uuid4()
    term_id = uuid4()
    person_id = uuid4()
    target = GradeTarget(
        organization_id=organization_id,
        student_academic_enrollment_id=uuid4(),
        course_enrollment_id=uuid4(),
        course_offering_id=uuid4(),
        term_id=term_id,
        course_id=uuid4(),
        credits=Decimal("3"),
    )
    targets = InMemoryGradeTargetDirectory()
    targets.add_participant(target, student_person_id=person_id)
    repository = InMemoryGradingRepository()
    terms = InMemoryTermClosureDirectory()
    directory = InMemoryExternalGradeEvidenceDirectory()
    audit = RecordingAuditSink()
    service = OfficialGradingService(
        repository=repository,
        targets=targets,
        terms=terms,
        term_writes=InMemoryTermGradeWriteGuard(),
        clock=FakeClock(NOW),
        audit=audit,
        evidence=directory,
    )
    scale = build_scale_from_template(
        scale_id=uuid4(),
        organization_id=organization_id,
        name="Official percentage",
        template=GradingScaleTemplate.PERCENTAGE,
    )
    await service.configure_scale(
        context=_context(organization_id, frozenset({GRADING_SCALE_MANAGE})),
        scale=scale,
    )
    evidence = ExternalGradeEvidence(
        evidence_id=uuid4(),
        external_event_id="moodle:grade:1",
        course_offering_id=target.course_offering_id,
        student_person_id=person_id,
        grade_value=grade_value,
        observed_at=NOW,
        source_version="moodle-5",
    )
    directory.add(organization_id=organization_id, evidence=evidence)
    return EvidenceFixture(
        organization_id=organization_id,
        term_id=term_id,
        person_id=person_id,
        target=target,
        scale=scale,
        evidence=evidence,
        repository=repository,
        targets=targets,
        terms=terms,
        directory=directory,
        audit=audit,
        service=service,
    )


async def test_acceptance_records_initial_grade_and_resolves_evidence() -> None:
    fixture = await _fixture()
    recorder = _context(fixture.organization_id, frozenset({GRADING_FINAL_RECORD}))

    grade = await fixture.service.accept_external_evidence(
        context=recorder,
        evidence_id=fixture.evidence.evidence_id,
        grading_scale_id=fixture.scale.id,
    )

    assert grade.course_enrollment_id == fixture.target.course_enrollment_id
    assert grade.raw_score == Decimal("87.5")
    assert grade.symbol == "B"
    assert grade.credits_earned == Decimal("3")
    assert grade.revision_number == 0
    assert grade.recorded_by == recorder.subject_id
    assert fixture.directory.acceptances == [
        (
            fixture.organization_id,
            fixture.evidence.evidence_id,
            grade.id,
            recorder.subject_id,
        )
    ]
    assert [action for action, _ in fixture.audit.actions] == [
        "grading.external_evidence.acceptance_requested",
        "grading.final_grade.record_requested",
        "grading.final_grade.recorded",
        "grading.external_evidence.accepted",
    ]
    with pytest.raises(NotFoundError):
        await fixture.service.accept_external_evidence(
            context=recorder,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.accept_external_evidence(
            context=_context(fixture.organization_id, frozenset()),
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
        )


async def test_acceptance_revises_existing_grade_only_with_explanation() -> None:
    fixture = await _fixture()
    recorder = _context(fixture.organization_id, frozenset({GRADING_FINAL_RECORD}))
    original = await fixture.service.record_final_grade(
        context=recorder,
        course_enrollment_id=fixture.target.course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("60"),
    )
    reviser = _context(
        fixture.organization_id,
        frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.accept_external_evidence(
            context=recorder,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
            explanation="Moodle total supersedes the provisional mark.",
        )
    with pytest.raises(GradingRuleError, match="requires an explanation"):
        await fixture.service.accept_external_evidence(
            context=reviser,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
        )
    revised = await fixture.service.accept_external_evidence(
        context=reviser,
        evidence_id=fixture.evidence.evidence_id,
        grading_scale_id=fixture.scale.id,
        explanation="Moodle total supersedes the provisional mark.",
    )

    assert revised.id == original.id
    assert revised.revision_number == 1
    assert revised.symbol == "B"
    history = await fixture.repository.list_grade_revisions(
        organization_id=fixture.organization_id,
        final_grade_id=original.id,
    )
    assert len(history) == 1
    assert history[0].previous_symbol == "D"
    assert fixture.directory.acceptances[-1][2] == original.id


async def test_acceptance_rejects_unmatched_or_non_numeric_evidence() -> None:
    non_numeric = await _fixture(grade_value="excellent")
    recorder = _context(non_numeric.organization_id, frozenset({GRADING_FINAL_RECORD}))

    with pytest.raises(GradingRuleError, match="numeric"):
        await non_numeric.service.accept_external_evidence(
            context=recorder,
            evidence_id=non_numeric.evidence.evidence_id,
            grading_scale_id=non_numeric.scale.id,
        )
    unmatched = ExternalGradeEvidence(
        evidence_id=uuid4(),
        external_event_id="moodle:grade:2",
        course_offering_id=non_numeric.target.course_offering_id,
        student_person_id=uuid4(),
        grade_value="90",
        observed_at=NOW,
        source_version="moodle-5",
    )
    non_numeric.directory.add(
        organization_id=non_numeric.organization_id,
        evidence=unmatched,
    )
    with pytest.raises(GradingRuleError, match="does not match"):
        await non_numeric.service.accept_external_evidence(
            context=recorder,
            evidence_id=unmatched.evidence_id,
            grading_scale_id=non_numeric.scale.id,
        )

    assert non_numeric.directory.acceptances == []
    assert non_numeric.audit.actions == []
    assert (
        await non_numeric.directory.get_pending_evidence(
            organization_id=non_numeric.organization_id,
            evidence_id=unmatched.evidence_id,
        )
        is not None
    )


async def test_acceptance_after_closure_requires_explanation_and_permission() -> None:
    fixture = await _fixture()
    fixture.terms.set_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    recorder = _context(fixture.organization_id, frozenset({GRADING_FINAL_RECORD}))

    with pytest.raises(GradingRuleError, match="post-closure"):
        await fixture.service.accept_external_evidence(
            context=recorder,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.accept_external_evidence(
            context=recorder,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
            explanation="Late Moodle total accepted by the registrar.",
        )
    grade = await fixture.service.accept_external_evidence(
        context=_context(
            fixture.organization_id,
            frozenset({GRADING_FINAL_RECORD, GRADING_CLOSED_TERM_REVISE}),
        ),
        evidence_id=fixture.evidence.evidence_id,
        grading_scale_id=fixture.scale.id,
        explanation="Late Moodle total accepted by the registrar.",
    )

    assert grade.recorded_after_term_closure is True
    assert grade.recording_explanation == "Late Moodle total accepted by the registrar."
    assert len(fixture.directory.acceptances) == 1


async def test_rejection_requires_reason_and_resolves_evidence_once() -> None:
    fixture = await _fixture()
    reviewer = _context(fixture.organization_id, frozenset({GRADING_FINAL_RECORD}))

    with pytest.raises(GradingRuleError, match="reason"):
        await fixture.service.reject_external_evidence(
            context=reviewer,
            evidence_id=fixture.evidence.evidence_id,
            reason="   ",
        )
    await fixture.service.reject_external_evidence(
        context=reviewer,
        evidence_id=fixture.evidence.evidence_id,
        reason="Student withdrew before the Moodle total was final.",
    )

    assert fixture.directory.rejections == [
        (
            fixture.organization_id,
            fixture.evidence.evidence_id,
            "rejected_by_reviewer",
            reviewer.subject_id,
        )
    ]
    assert [action for action, _ in fixture.audit.actions] == [
        "grading.external_evidence.rejection_requested",
        "grading.external_evidence.rejected",
    ]
    assert fixture.audit.reasons == [
        "Student withdrew before the Moodle total was final.",
        "Student withdrew before the Moodle total was final.",
    ]
    with pytest.raises(NotFoundError):
        await fixture.service.reject_external_evidence(
            context=reviewer,
            evidence_id=fixture.evidence.evidence_id,
            reason="Already handled.",
        )
    with pytest.raises(NotFoundError):
        await fixture.service.accept_external_evidence(
            context=reviewer,
            evidence_id=fixture.evidence.evidence_id,
            grading_scale_id=fixture.scale.id,
        )


def _application(
    service: OfficialGradingService,
    context: TenantActorContext,
) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.state.official_grading_service = service
    app.include_router(router)

    async def actor() -> TenantActorContext:
        return context

    async def csrf() -> None:
        return None

    app.dependency_overrides[require_actor] = actor
    app.dependency_overrides[require_csrf] = csrf
    return app


async def test_http_routes_accept_and_reject_external_evidence() -> None:
    accepted = await _fixture()
    rejected = await _fixture()
    accept_app = _application(
        accepted.service,
        _context(accepted.organization_id, frozenset({GRADING_FINAL_RECORD})),
    )
    reject_app = _application(
        rejected.service,
        _context(rejected.organization_id, frozenset({GRADING_FINAL_RECORD})),
    )
    unauthorized_app = _application(
        rejected.service,
        _context(rejected.organization_id, frozenset()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=accept_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/grading/external-evidence/{accepted.evidence.evidence_id}/accept",
            json={"grading_scale_id": str(accepted.scale.id)},
        )
        missing = await client.post(
            f"/api/v1/grading/external-evidence/{uuid4()}/accept",
            json={"grading_scale_id": str(accepted.scale.id)},
        )
    async with AsyncClient(
        transport=ASGITransport(app=unauthorized_app),
        base_url="http://test",
    ) as client:
        forbidden = await client.post(
            f"/api/v1/grading/external-evidence/{rejected.evidence.evidence_id}/reject",
            json={"reason": "Not an official result."},
        )
    async with AsyncClient(
        transport=ASGITransport(app=reject_app),
        base_url="http://test",
    ) as client:
        rejection = await client.post(
            f"/api/v1/grading/external-evidence/{rejected.evidence.evidence_id}/reject",
            json={"reason": "Not an official result."},
        )

    assert response.status_code == 200
    assert response.json()["symbol"] == "B"
    assert response.json()["course_enrollment_id"] == str(
        accepted.target.course_enrollment_id
    )
    assert missing.status_code == 404
    assert forbidden.status_code == 403
    assert rejection.status_code == 200
    assert rejection.json() == {
        "evidence_id": str(rejected.evidence.evidence_id),
        "status": "rejected",
    }
