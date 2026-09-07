"""PostgreSQL adapter for official grading and immutable revisions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.errors import ConflictError
from core.identifiers import new_uuid7
from grading.domain.exceptions import GradeRevisionConflictError
from grading.domain.models import FinalGrade
from grading.domain.models import GradeBand
from grading.domain.models import GradeRevision
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleKind
from grading.infrastructure.models import FinalGradeModel
from grading.infrastructure.models import GradeBandModel
from grading.infrastructure.models import GradeRevisionModel
from grading.infrastructure.models import GradingScaleModel
from shared.database import Database


class SQLAlchemyGradingRepository:
    """Persist tenant-owned grading aggregates with database concurrency guards."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def save_scale(self, scale: GradingScale) -> None:
        """Publish one immutable scale and its normalized threshold bands."""

        try:
            async with self._database.session(
                organization_id=scale.organization_id,
            ) as session:
                existing = await session.scalar(
                    select(GradingScaleModel).where(
                        GradingScaleModel.organization_id == scale.organization_id,
                        GradingScaleModel.id == scale.id,
                    )
                )
                if existing is not None:
                    stored = await self._scale_from_model(
                        organization_id=scale.organization_id,
                        model=existing,
                        database_session=session,
                    )
                    if stored != scale:
                        raise ConflictError("Published grading scales are immutable.")
                    return
                scale_model = GradingScaleModel(
                    id=scale.id,
                    organization_id=scale.organization_id,
                    name=scale.name,
                    kind=scale.kind.value,
                    minimum_score=scale.minimum_score,
                    maximum_score=scale.maximum_score,
                )
                session.add(scale_model)
                # The normalized bands do not use an ORM relationship, so make
                # the aggregate parent durable in this transaction before its
                # foreign-key children are flushed.
                await session.flush((scale_model,))
                for band in scale.bands:
                    session.add(
                        GradeBandModel(
                            id=new_uuid7(),
                            organization_id=scale.organization_id,
                            scale_id=scale.id,
                            minimum_score=band.minimum_score,
                            symbol=band.symbol,
                            passing=band.passing,
                            grade_points=band.grade_points,
                        )
                    )
        except IntegrityError as exc:
            raise ConflictError(
                "A grading scale with this name or definition already exists."
            ) from exc

    async def get_scale(
        self,
        *,
        organization_id: UUID,
        scale_id: UUID,
    ) -> GradingScale | None:
        """Return one complete scale only when its tenant owner matches."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(GradingScaleModel).where(
                    GradingScaleModel.organization_id == organization_id,
                    GradingScaleModel.id == scale_id,
                )
            )
            if model is None:
                return None
            return await self._scale_from_model(
                organization_id=organization_id,
                model=model,
                database_session=session,
            )

    async def list_scales(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[GradingScale, ...]:
        """Return a bounded stable grading-scale page for one tenant."""

        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(GradingScaleModel)
                        .where(GradingScaleModel.organization_id == organization_id)
                        .order_by(GradingScaleModel.name, GradingScaleModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
            return tuple(
                [
                    await self._scale_from_model(
                        organization_id=organization_id,
                        model=model,
                        database_session=session,
                    )
                    for model in models
                ]
            )

    async def create_final_grade(self, grade: FinalGrade) -> None:
        """Create the sole official grade for one course enrollment."""

        try:
            async with self._database.session(
                organization_id=grade.organization_id,
            ) as session:
                session.add(self._grade_to_model(grade))
        except IntegrityError as exc:
            raise ConflictError(
                "An official final grade already exists for this enrollment."
            ) from exc

    async def get_final_grade(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> FinalGrade | None:
        """Return current official grade state only from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(FinalGradeModel).where(
                    FinalGradeModel.organization_id == organization_id,
                    FinalGradeModel.id == final_grade_id,
                )
            )
            return self._grade_from_model(model) if model is not None else None

    async def revise_final_grade(
        self,
        *,
        grade: FinalGrade,
        expected_revision_number: int,
        revision: GradeRevision,
    ) -> None:
        """Append history and compare-and-swap current grade in one transaction."""

        try:
            async with self._database.session(
                organization_id=grade.organization_id,
            ) as session:
                model = await session.scalar(
                    select(FinalGradeModel)
                    .where(
                        FinalGradeModel.organization_id == grade.organization_id,
                        FinalGradeModel.id == grade.id,
                    )
                    .with_for_update()
                )
                if model is None or model.revision_number != expected_revision_number:
                    raise GradeRevisionConflictError(
                        "Final grade changed during the requested revision."
                    )
                if revision.revision_number != expected_revision_number + 1:
                    raise GradeRevisionConflictError(
                        "Grade revision sequence is not contiguous."
                    )
                if (
                    model.recorded_by != grade.recorded_by
                    or model.recorded_at != grade.recorded_at
                    or model.recorded_after_term_closure
                    != grade.recorded_after_term_closure
                    or model.recording_explanation != grade.recording_explanation
                ):
                    raise GradeRevisionConflictError(
                        "Initial grade recording evidence is immutable."
                    )
                session.add(self._revision_to_model(revision))
                self._apply_grade(model=model, grade=grade)
        except IntegrityError as exc:
            raise GradeRevisionConflictError(
                "Grade revision changed during the requested update."
            ) from exc

    async def list_student_final_grades(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[FinalGrade, ...]:
        """Return stable ordered current grades for one student enrollment."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(FinalGradeModel).where(
                            FinalGradeModel.organization_id == organization_id,
                            FinalGradeModel.student_academic_enrollment_id
                            == student_academic_enrollment_id,
                        )
                    )
                ).all()
            )
        return tuple(
            sorted(
                (self._grade_from_model(model) for model in models),
                key=lambda value: (str(value.term_id), str(value.course_id)),
            )
        )

    async def list_grade_revisions(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> tuple[GradeRevision, ...]:
        """Return contiguous immutable history for one tenant grade."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(GradeRevisionModel).where(
                            GradeRevisionModel.organization_id == organization_id,
                            GradeRevisionModel.final_grade_id == final_grade_id,
                        )
                    )
                ).all()
            )
        return tuple(
            sorted(
                (self._revision_from_model(model) for model in models),
                key=lambda value: value.revision_number,
            )
        )

    @staticmethod
    async def _scale_from_model(
        *,
        organization_id: UUID,
        model: GradingScaleModel,
        database_session: object,
    ) -> GradingScale:
        """Load a scale aggregate from its row and normalized bands."""

        from sqlalchemy.ext.asyncio import AsyncSession

        session = database_session
        if not isinstance(session, AsyncSession):
            raise TypeError("An asynchronous SQLAlchemy session is required.")
        bands = tuple(
            (
                await session.scalars(
                    select(GradeBandModel).where(
                        GradeBandModel.organization_id == organization_id,
                        GradeBandModel.scale_id == model.id,
                    )
                )
            ).all()
        )
        return GradingScale(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            kind=GradingScaleKind(model.kind),
            minimum_score=model.minimum_score,
            maximum_score=model.maximum_score,
            bands=tuple(
                GradeBand(
                    minimum_score=band.minimum_score,
                    symbol=band.symbol,
                    passing=band.passing,
                    grade_points=band.grade_points,
                )
                for band in sorted(bands, key=lambda value: value.minimum_score)
            ),
        )

    @staticmethod
    def _grade_to_model(grade: FinalGrade) -> FinalGradeModel:
        """Translate one current official grade into its persistence row."""

        model = FinalGradeModel(
            id=grade.id,
            organization_id=grade.organization_id,
            recorded_by=grade.recorded_by,
            recorded_at=grade.recorded_at,
            recorded_after_term_closure=grade.recorded_after_term_closure,
            recording_explanation=grade.recording_explanation,
        )
        SQLAlchemyGradingRepository._apply_grade(model=model, grade=grade)
        return model

    @staticmethod
    def _apply_grade(*, model: FinalGradeModel, grade: FinalGrade) -> None:
        """Apply complete current grade state without mutating history rows."""

        model.student_academic_enrollment_id = grade.student_academic_enrollment_id
        model.course_enrollment_id = grade.course_enrollment_id
        model.course_offering_id = grade.course_offering_id
        model.course_id = grade.course_id
        model.term_id = grade.term_id
        model.grading_scale_id = grade.grading_scale_id
        model.raw_score = grade.raw_score
        model.symbol = grade.symbol
        model.credits_attempted = grade.credits_attempted
        model.credits_earned = grade.credits_earned
        model.grade_points = grade.grade_points
        model.gpa_contribution = grade.gpa_contribution
        model.revision_number = grade.revision_number
        model.grade_updated_at = grade.updated_at

    @staticmethod
    def _grade_from_model(model: FinalGradeModel) -> FinalGrade:
        """Translate a stored current grade into a validated domain aggregate."""

        return FinalGrade(
            id=model.id,
            organization_id=model.organization_id,
            student_academic_enrollment_id=model.student_academic_enrollment_id,
            course_enrollment_id=model.course_enrollment_id,
            course_offering_id=model.course_offering_id,
            course_id=model.course_id,
            term_id=model.term_id,
            grading_scale_id=model.grading_scale_id,
            raw_score=model.raw_score,
            symbol=model.symbol,
            credits_attempted=model.credits_attempted,
            credits_earned=model.credits_earned,
            grade_points=model.grade_points,
            gpa_contribution=model.gpa_contribution,
            revision_number=model.revision_number,
            recorded_by=model.recorded_by,
            recorded_at=model.recorded_at,
            updated_at=model.grade_updated_at,
            recorded_after_term_closure=model.recorded_after_term_closure,
            recording_explanation=model.recording_explanation,
        )

    @staticmethod
    def _revision_to_model(revision: GradeRevision) -> GradeRevisionModel:
        """Translate an immutable revision into its append-only persistence row."""

        return GradeRevisionModel(
            id=revision.id,
            organization_id=revision.organization_id,
            final_grade_id=revision.final_grade_id,
            revision_number=revision.revision_number,
            previous_raw_score=revision.previous_raw_score,
            previous_symbol=revision.previous_symbol,
            previous_credits_earned=revision.previous_credits_earned,
            previous_grade_points=revision.previous_grade_points,
            previous_gpa_contribution=revision.previous_gpa_contribution,
            replacement_raw_score=revision.replacement_raw_score,
            replacement_symbol=revision.replacement_symbol,
            replacement_credits_earned=revision.replacement_credits_earned,
            replacement_grade_points=revision.replacement_grade_points,
            replacement_gpa_contribution=revision.replacement_gpa_contribution,
            explanation=revision.explanation,
            revised_by=revision.revised_by,
            revised_at=revision.revised_at,
            after_term_closure=revision.after_term_closure,
        )

    @staticmethod
    def _revision_from_model(model: GradeRevisionModel) -> GradeRevision:
        """Translate one append-only history row into its domain value."""

        return GradeRevision(
            id=model.id,
            organization_id=model.organization_id,
            final_grade_id=model.final_grade_id,
            revision_number=model.revision_number,
            previous_raw_score=model.previous_raw_score,
            previous_symbol=model.previous_symbol,
            previous_credits_earned=model.previous_credits_earned,
            previous_grade_points=model.previous_grade_points,
            previous_gpa_contribution=model.previous_gpa_contribution,
            replacement_raw_score=model.replacement_raw_score,
            replacement_symbol=model.replacement_symbol,
            replacement_credits_earned=model.replacement_credits_earned,
            replacement_grade_points=model.replacement_grade_points,
            replacement_gpa_contribution=model.replacement_gpa_contribution,
            explanation=model.explanation,
            revised_by=model.revised_by,
            revised_at=model.revised_at,
            after_term_closure=model.after_term_closure,
        )


__all__ = ["SQLAlchemyGradingRepository"]
