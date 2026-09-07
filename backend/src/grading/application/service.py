"""Official grading application services and authorization boundaries."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from grading.application.ports import GradeTargetDirectory
from grading.application.ports import GradingAuditSink
from grading.application.ports import GradingClock
from grading.application.ports import GradingRepository
from grading.application.ports import TermClosureDirectory
from grading.domain.exceptions import GradeRevisionConflictError
from grading.domain.exceptions import GradingRuleError
from grading.domain.models import FinalGrade
from grading.domain.models import GpaSummary
from grading.domain.models import GradeRevision
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleTemplate
from grading.domain.models import TranscriptRecord
from grading.domain.models import build_scale_from_template
from grading.domain.models import calculate_gpa_summary
from grading.domain.models import transcript_record

GRADING_SCALE_MANAGE = "grading.scale.manage"
GRADING_FINAL_RECORD = "grading.final_grade.record"
GRADING_FINAL_REVISE = "grading.final_grade.revise"
GRADING_CLOSED_TERM_REVISE = "grading.final_grade.revise_closed_term"
GRADING_TRANSCRIPT_READ = "grading.transcript.read"
MAX_GRADING_ADMIN_PAGE_SIZE = 100


class OfficialGradingService:
    """Manage authoritative final results without losing amendment history."""

    def __init__(
        self,
        *,
        repository: GradingRepository,
        targets: GradeTargetDirectory,
        terms: TermClosureDirectory,
        clock: GradingClock,
        audit: GradingAuditSink,
    ) -> None:
        self._repository = repository
        self._targets = targets
        self._terms = terms
        self._clock = clock
        self._audit = audit

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
    ) -> FinalGrade:
        """Create the official final result for one tenant course enrollment."""

        _authorize(context, GRADING_FINAL_RECORD)
        target = await self._targets.get_grade_target(
            organization_id=context.organization_id,
            course_enrollment_id=course_enrollment_id,
        )
        if target is None:
            raise NotFoundError("Course enrollment was not found for grading.")
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
        )
        await self._repository.create_final_grade(grade)
        await self._audit.record_final_grade_event(
            action="grading.final_grade.recorded",
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            final_grade_id=grade.id,
            correlation_id=context.correlation_id,
            after_term_closure=False,
        )
        return grade

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
        credits_earned = current.credits_attempted if outcome.passing else Decimal(0)
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
        )
        return revised

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
    "GRADING_CLOSED_TERM_REVISE",
    "GRADING_FINAL_RECORD",
    "GRADING_FINAL_REVISE",
    "GRADING_SCALE_MANAGE",
    "GRADING_TRANSCRIPT_READ",
    "MAX_GRADING_ADMIN_PAGE_SIZE",
    "OfficialGradingService",
]
