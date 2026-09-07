from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
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
from grading.infrastructure.repository import InMemoryGradeTargetDirectory
from grading.infrastructure.repository import InMemoryGradingRepository
from grading.infrastructure.repository import InMemoryTermClosureDirectory


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


class RecordingGradingAuditSink:
    """Capture privacy-minimized official grading evidence."""

    def __init__(self) -> None:
        self.events: list[RecordedGradeAuditEvent] = []

    async def record_final_grade_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        final_grade_id: UUID,
        correlation_id: str,
        after_term_closure: bool,
    ) -> None:
        self.events.append(
            RecordedGradeAuditEvent(
                action=action,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                final_grade_id=final_grade_id,
                correlation_id=correlation_id,
                after_term_closure=after_term_closure,
            )
        )


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


async def _fixture() -> GradingFixture:
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
    audit = RecordingGradingAuditSink()
    service = OfficialGradingService(
        repository=repository,
        targets=InMemoryGradeTargetDirectory((first_target, second_target)),
        terms=terms,
        clock=FakeClock(datetime(2026, 8, 5, 10, tzinfo=UTC)),
        audit=audit,
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
        "grading.final_grade.recorded",
        "grading.final_grade.revised",
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
