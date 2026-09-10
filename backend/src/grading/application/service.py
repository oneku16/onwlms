"""Official grading application services and authorization boundaries."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from grading.application.ports import ExternalGradeEvidenceDirectory
from grading.application.ports import GradeTargetDirectory
from grading.application.ports import GradingAuditSink
from grading.application.ports import GradingClock
from grading.application.ports import GradingRepository
from grading.application.ports import TermClosureDirectory
from grading.application.ports import TermGradeWriteGuard
from grading.domain.exceptions import GradeRevisionConflictError
from grading.domain.exceptions import GradingRuleError
from grading.domain.models import FinalGrade
from grading.domain.models import FinalGradeHistory
from grading.domain.models import GpaSummary
from grading.domain.models import GradeRevision
from grading.domain.models import GradeTarget
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleTemplate
from grading.domain.models import TranscriptRecord
from grading.domain.models import build_scale_from_template
from grading.domain.models import calculate_gpa_summary
from grading.domain.models import parse_external_score
from grading.domain.models import transcript_record

GRADING_SCALE_MANAGE = "grading.scale.manage"
GRADING_FINAL_RECORD = "grading.final_grade.record"
GRADING_FINAL_REVISE = "grading.final_grade.revise"
GRADING_CLOSED_TERM_REVISE = "grading.final_grade.revise_closed_term"
GRADING_TRANSCRIPT_READ = "grading.transcript.read"
MAX_GRADING_ADMIN_PAGE_SIZE = 100
EXTERNAL_EVIDENCE_REJECTED_REASON_CODE = "rejected_by_reviewer"


class OfficialGradingService:
    """Manage authoritative final results without losing amendment history."""

    def __init__(
        self,
        *,
        repository: GradingRepository,
        targets: GradeTargetDirectory,
        terms: TermClosureDirectory,
        term_writes: TermGradeWriteGuard,
        clock: GradingClock,
        audit: GradingAuditSink,
        evidence: ExternalGradeEvidenceDirectory,
    ) -> None:
        self._repository = repository
        self._targets = targets
        self._terms = terms
        self._term_writes = term_writes
        self._clock = clock
        self._audit = audit
        self._evidence = evidence

    async def configure_scale(
        self,
        *,
        context: TenantActorContext,
        scale: GradingScale,
    ) -> None:
        """Persist one tenant-owned official grading scale."""

        _authorize(context, GRADING_SCALE_MANAGE)
        _require_tenant(context, scale.organization_id)
        await self._repository.save_scale(scale)

    async def configure_template(
        self,
        *,
        context: TenantActorContext,
        name: str,
        template: GradingScaleTemplate,
    ) -> GradingScale:
        """Create and persist a tenant copy of a built-in scale template."""

        _authorize(context, GRADING_SCALE_MANAGE)
        scale = build_scale_from_template(
            scale_id=new_uuid7(),
            organization_id=context.organization_id,
            name=name,
            template=template,
        )
        await self._repository.save_scale(scale)
        return scale

    async def get_scale(
        self,
        *,
        context: TenantActorContext,
        scale_id: UUID,
    ) -> GradingScale:
        """Return one authorized tenant grading-scale definition."""

        _authorize(context, GRADING_SCALE_MANAGE)
        scale = await self._repository.get_scale(
            organization_id=context.organization_id,
            scale_id=scale_id,
        )
        if scale is None:
            raise NotFoundError("Grading scale was not found.")
        return scale

    async def list_scales(
        self,
        *,
        context: TenantActorContext,
        limit: int,
        offset: int,
    ) -> tuple[GradingScale, ...]:
        """Return an authorized bounded page of tenant grading scales."""

        _authorize(context, GRADING_SCALE_MANAGE)
        if limit < 1 or limit > MAX_GRADING_ADMIN_PAGE_SIZE or offset < 0:
            raise GradingRuleError(
                f"Grading page limit must be 1-{MAX_GRADING_ADMIN_PAGE_SIZE} "
                "and offset cannot be negative."
            )
        return await self._repository.list_scales(
            organization_id=context.organization_id,
            limit=limit,
            offset=offset,
        )

    async def record_final_grade(
        self,
        *,
        context: TenantActorContext,
        course_enrollment_id: UUID,
        grading_scale_id: UUID,
        raw_score: Decimal,
        explanation: str | None = None,
    ) -> FinalGrade:
        """Create the official final result for one tenant course enrollment."""

        _authorize(context, GRADING_FINAL_RECORD)
        target = await self._targets.get_grade_target(
            organization_id=context.organization_id,
            course_enrollment_id=course_enrollment_id,
        )
        if target is None:
            raise NotFoundError("Course enrollment was not found for grading.")
        return await self._record_final_grade(
            context=context,
            target=target,
            grading_scale_id=grading_scale_id,
            raw_score=raw_score,
            explanation=explanation,
        )

    async def revise_final_grade(
        self,
        *,
        context: TenantActorContext,
        final_grade_id: UUID,
        raw_score: Decimal,
        explanation: str,
        grading_scale_id: UUID | None = None,
        expected_revision_number: int | None = None,
    ) -> FinalGrade:
        """Amend an official grade while atomically preserving previous state."""

        _authorize(context, GRADING_FINAL_REVISE)
        if not explanation.strip():
            raise GradingRuleError("Grade revision explanation is required.")
        current = await self._repository.get_final_grade(
            organization_id=context.organization_id,
            final_grade_id=final_grade_id,
        )
        if current is None:
            raise NotFoundError("Final grade was not found.")
        if (
            expected_revision_number is not None
            and current.revision_number != expected_revision_number
        ):
            raise GradeRevisionConflictError(
                "Final grade revision does not match the requested version."
            )
        return await self._revise_final_grade(
            context=context,
            current=current,
            raw_score=raw_score,
            explanation=explanation,
            grading_scale_id=grading_scale_id,
        )

    async def accept_external_evidence(
        self,
        *,
        context: TenantActorContext,
        evidence_id: UUID,
        grading_scale_id: UUID,
        explanation: str | None = None,
    ) -> FinalGrade:
        """Turn pending external evidence into an official grade decision.

        Acceptance is an ordinary authorized grade mutation. It records an
        initial grade when the participation has none, or revises the current
        grade, under the same permission, closure, and explanation rules that
        govern manual recording. Evidence never writes a grade by itself.
        """

        _authorize(context, GRADING_FINAL_RECORD)
        evidence = await self._evidence.get_pending_evidence(
            organization_id=context.organization_id,
            evidence_id=evidence_id,
        )
        if evidence is None:
            raise NotFoundError("Pending external grade evidence was not found.")
        target = await self._targets.get_grade_target_for_participant(
            organization_id=context.organization_id,
            course_offering_id=evidence.course_offering_id,
            student_person_id=evidence.student_person_id,
        )
        if target is None:
            raise GradingRuleError(
                "External evidence does not match exactly one active official "
                "course enrollment."
            )
        raw_score = parse_external_score(evidence.grade_value)
        await self._audit.record_external_evidence_event(
            action="grading.external_evidence.acceptance_requested",
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            evidence_id=evidence_id,
            correlation_id=context.correlation_id,
            outcome="intent_recorded",
            reason=None,
        )
        current = await self._repository.get_final_grade_for_course_enrollment(
            organization_id=context.organization_id,
            course_enrollment_id=target.course_enrollment_id,
        )
        if current is None:
            grade = await self._record_final_grade(
                context=context,
                target=target,
                grading_scale_id=grading_scale_id,
                raw_score=raw_score,
                explanation=explanation,
            )
        else:
            _authorize(context, GRADING_FINAL_REVISE)
            if explanation is None or not explanation.strip():
                raise GradingRuleError(
                    "Revising an existing official grade from external evidence "
                    "requires an explanation."
                )
            grade = await self._revise_final_grade(
                context=context,
                current=current,
                raw_score=raw_score,
                explanation=explanation,
                grading_scale_id=grading_scale_id,
            )
        await self._evidence.record_acceptance(
            organization_id=context.organization_id,
            evidence_id=evidence_id,
            final_grade_id=grade.id,
            actor_subject_id=context.subject_id,
            correlation_id=context.correlation_id,
        )
        await self._audit.record_external_evidence_event(
            action="grading.external_evidence.accepted",
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            evidence_id=evidence_id,
            correlation_id=context.correlation_id,
            outcome="succeeded",
            reason=None,
        )
        return grade

    async def reject_external_evidence(
        self,
        *,
        context: TenantActorContext,
        evidence_id: UUID,
        reason: str,
    ) -> None:
        """Decline pending external evidence with an audited explanation."""

        _authorize(context, GRADING_FINAL_RECORD)
        if not reason.strip():
            raise GradingRuleError("External evidence rejection reason is required.")
        evidence = await self._evidence.get_pending_evidence(
            organization_id=context.organization_id,
            evidence_id=evidence_id,
        )
        if evidence is None:
            raise NotFoundError("Pending external grade evidence was not found.")
        await self._audit.record_external_evidence_event(
            action="grading.external_evidence.rejection_requested",
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            evidence_id=evidence_id,
            correlation_id=context.correlation_id,
            outcome="intent_recorded",
            reason=reason.strip(),
        )
        await self._evidence.record_rejection(
            organization_id=context.organization_id,
            evidence_id=evidence_id,
            reason_code=EXTERNAL_EVIDENCE_REJECTED_REASON_CODE,
            actor_subject_id=context.subject_id,
            correlation_id=context.correlation_id,
        )
        await self._audit.record_external_evidence_event(
            action="grading.external_evidence.rejected",
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            evidence_id=evidence_id,
            correlation_id=context.correlation_id,
            outcome="succeeded",
            reason=reason.strip(),
        )

    async def revision_history(
        self,
        *,
        context: TenantActorContext,
        final_grade_id: UUID,
    ) -> tuple[GradeRevision, ...]:
        """Return immutable history to actors authorized to amend the grade."""

        history = await self.grade_history(
            context=context,
            final_grade_id=final_grade_id,
        )
        return history.revisions

    async def grade_history(
        self,
        *,
        context: TenantActorContext,
        final_grade_id: UUID,
    ) -> FinalGradeHistory:
        """Return initial recording evidence and immutable amendment history."""

        _authorize(context, GRADING_FINAL_REVISE)
        grade = await self._repository.get_final_grade(
            organization_id=context.organization_id,
            final_grade_id=final_grade_id,
        )
        if grade is None:
            raise NotFoundError("Final grade was not found.")
        revisions = await self._repository.list_grade_revisions(
            organization_id=context.organization_id,
            final_grade_id=grade.id,
        )
        return FinalGradeHistory(
            final_grade_id=grade.id,
            recorded_by=grade.recorded_by,
            recorded_at=grade.recorded_at,
            recorded_after_term_closure=grade.recorded_after_term_closure,
            recording_explanation=grade.recording_explanation,
            revisions=revisions,
        )

    async def transcript(
        self,
        *,
        context: TenantActorContext,
        student_academic_enrollment_id: UUID,
    ) -> tuple[TranscriptRecord, ...]:
        """Return official transcript records for one tenant enrollment."""

        _authorize(context, GRADING_TRANSCRIPT_READ)
        grades = await self._repository.list_student_final_grades(
            organization_id=context.organization_id,
            student_academic_enrollment_id=student_academic_enrollment_id,
        )
        return tuple(transcript_record(grade) for grade in grades)

    async def gpa_summary(
        self,
        *,
        context: TenantActorContext,
        student_academic_enrollment_id: UUID,
    ) -> GpaSummary:
        """Return attempted credits, earned credits, and official GPA."""

        _authorize(context, GRADING_TRANSCRIPT_READ)
        grades = await self._repository.list_student_final_grades(
            organization_id=context.organization_id,
            student_academic_enrollment_id=student_academic_enrollment_id,
        )
        return calculate_gpa_summary(grades)

    async def _record_final_grade(
        self,
        *,
        context: TenantActorContext,
        target: GradeTarget,
        grading_scale_id: UUID,
        raw_score: Decimal,
        explanation: str | None,
    ) -> FinalGrade:
        """Create the official result for an already resolved grade target."""

        async with self._term_writes.hold_grade_write(
            organization_id=context.organization_id,
            term_id=target.term_id,
        ):
            after_term_closure = await self._terms.is_term_closed(
                organization_id=context.organization_id,
                term_id=target.term_id,
            )
            if after_term_closure:
                if explanation is None or not explanation.strip():
                    raise GradingRuleError(
                        "A post-closure final grade explanation is required."
                    )
                _authorize(context, GRADING_CLOSED_TERM_REVISE)
            recording_explanation = (
                explanation.strip()
                if after_term_closure and explanation is not None
                else None
            )
            scale = await self._repository.get_scale(
                organization_id=context.organization_id,
                scale_id=grading_scale_id,
            )
            if scale is None:
                raise NotFoundError("Grading scale was not found.")
            outcome = scale.resolve(raw_score)
            now = self._clock.now()
            grade = FinalGrade(
                id=new_uuid7(),
                organization_id=context.organization_id,
                student_academic_enrollment_id=target.student_academic_enrollment_id,
                course_enrollment_id=target.course_enrollment_id,
                course_offering_id=target.course_offering_id,
                course_id=target.course_id,
                term_id=target.term_id,
                grading_scale_id=scale.id,
                raw_score=raw_score,
                symbol=outcome.symbol,
                credits_attempted=target.credits,
                credits_earned=(target.credits if outcome.passing else Decimal(0)),
                grade_points=outcome.grade_points,
                gpa_contribution=(
                    outcome.grade_points * target.credits
                    if outcome.grade_points is not None
                    else None
                ),
                revision_number=0,
                recorded_by=context.subject_id,
                recorded_at=now,
                updated_at=now,
                recorded_after_term_closure=after_term_closure,
                recording_explanation=recording_explanation,
            )
            await self._audit.record_final_grade_event(
                action="grading.final_grade.record_requested",
                organization_id=context.organization_id,
                actor_subject_id=context.subject_id,
                final_grade_id=grade.id,
                correlation_id=context.correlation_id,
                after_term_closure=after_term_closure,
                outcome="intent_recorded",
            )
            await self._repository.create_final_grade(grade)
            await self._audit.record_final_grade_event(
                action="grading.final_grade.recorded",
                organization_id=context.organization_id,
                actor_subject_id=context.subject_id,
                final_grade_id=grade.id,
                correlation_id=context.correlation_id,
                after_term_closure=after_term_closure,
                outcome="succeeded",
            )
        return grade

    async def _revise_final_grade(
        self,
        *,
        context: TenantActorContext,
        current: FinalGrade,
        raw_score: Decimal,
        explanation: str,
        grading_scale_id: UUID | None,
    ) -> FinalGrade:
        """Amend an already loaded official grade under the term write guard."""

        async with self._term_writes.hold_grade_write(
            organization_id=context.organization_id,
            term_id=current.term_id,
        ):
            after_term_closure = await self._terms.is_term_closed(
                organization_id=context.organization_id,
                term_id=current.term_id,
            )
            if after_term_closure:
                _authorize(context, GRADING_CLOSED_TERM_REVISE)
            scale = await self._repository.get_scale(
                organization_id=context.organization_id,
                scale_id=grading_scale_id or current.grading_scale_id,
            )
            if scale is None:
                raise NotFoundError("Grading scale was not found.")
            outcome = scale.resolve(raw_score)
            revised_at = self._clock.now()
            next_revision_number = current.revision_number + 1
            credits_earned = (
                current.credits_attempted if outcome.passing else Decimal(0)
            )
            gpa_contribution = (
                outcome.grade_points * current.credits_attempted
                if outcome.grade_points is not None
                else None
            )
            revised = replace(
                current,
                grading_scale_id=scale.id,
                raw_score=raw_score,
                symbol=outcome.symbol,
                credits_earned=credits_earned,
                grade_points=outcome.grade_points,
                gpa_contribution=gpa_contribution,
                revision_number=next_revision_number,
                updated_at=revised_at,
            )
            revision = GradeRevision(
                id=new_uuid7(),
                organization_id=context.organization_id,
                final_grade_id=current.id,
                revision_number=next_revision_number,
                previous_raw_score=current.raw_score,
                previous_symbol=current.symbol,
                previous_credits_earned=current.credits_earned,
                previous_grade_points=current.grade_points,
                previous_gpa_contribution=current.gpa_contribution,
                replacement_raw_score=revised.raw_score,
                replacement_symbol=revised.symbol,
                replacement_credits_earned=revised.credits_earned,
                replacement_grade_points=revised.grade_points,
                replacement_gpa_contribution=revised.gpa_contribution,
                explanation=explanation,
                revised_by=context.subject_id,
                revised_at=revised_at,
                after_term_closure=after_term_closure,
            )
            await self._audit.record_final_grade_event(
                action="grading.final_grade.revision_requested",
                organization_id=context.organization_id,
                actor_subject_id=context.subject_id,
                final_grade_id=revised.id,
                correlation_id=context.correlation_id,
                after_term_closure=after_term_closure,
                outcome="intent_recorded",
            )
            await self._repository.revise_final_grade(
                grade=revised,
                expected_revision_number=current.revision_number,
                revision=revision,
            )
            await self._audit.record_final_grade_event(
                action="grading.final_grade.revised",
                organization_id=context.organization_id,
                actor_subject_id=context.subject_id,
                final_grade_id=revised.id,
                correlation_id=context.correlation_id,
                after_term_closure=after_term_closure,
                outcome="succeeded",
            )
        return revised


def _authorize(
    context: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the trusted actor has an official-grading permission."""

    if permission not in context.permissions:
        raise AuthorizationError("Required grading permission is missing.")


def _require_tenant(
    context: TenantActorContext,
    resource_organization_id: UUID,
) -> None:
    """Reject resource ownership mismatch without revealing another tenant."""

    if context.organization_id != resource_organization_id:
        raise NotFoundError("Grading resource was not found.")


__all__ = [
    "EXTERNAL_EVIDENCE_REJECTED_REASON_CODE",
    "GRADING_CLOSED_TERM_REVISE",
    "GRADING_FINAL_RECORD",
    "GRADING_FINAL_REVISE",
    "GRADING_SCALE_MANAGE",
    "GRADING_TRANSCRIPT_READ",
    "MAX_GRADING_ADMIN_PAGE_SIZE",
    "OfficialGradingService",
]
