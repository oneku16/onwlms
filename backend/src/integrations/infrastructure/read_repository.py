"""PostgreSQL projections of privacy-safe Moodle grade evidence status."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select

from integrations.application.read_models import GradeSynchronizationStatus
from integrations.infrastructure.models import MoodleGradeEvidenceModel
from shared.database import Database


class SQLAlchemyIntegrationEvidenceReadRepository:
    """Summarize evidence under tenant context without exposing grade payloads."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def grade_synchronization_status(
        self,
        *,
        organization_id: UUID,
        course_offering_ids: frozenset[UUID],
    ) -> tuple[GradeSynchronizationStatus, ...]:
        """Return one deterministic status for every requested tenant section."""

        if not course_offering_ids:
            return ()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(MoodleGradeEvidenceModel)
                        .where(
                            MoodleGradeEvidenceModel.organization_id == organization_id,
                            MoodleGradeEvidenceModel.course_offering_id.in_(
                                course_offering_ids
                            ),
                        )
                        .order_by(
                            MoodleGradeEvidenceModel.course_offering_id,
                            MoodleGradeEvidenceModel.observed_at,
                            MoodleGradeEvidenceModel.id,
                        )
                    )
                ).all()
            )
        by_section: defaultdict[UUID, list[MoodleGradeEvidenceModel]] = defaultdict(
            list
        )
        for model in models:
            by_section[model.course_offering_id].append(model)
        results: list[GradeSynchronizationStatus] = []
        for section_id in sorted(course_offering_ids, key=str):
            evidence = by_section[section_id]
            unresolved_count = sum(value.status != "accepted" for value in evidence)
            status = "not_observed"
            if evidence:
                status = "healthy" if unresolved_count == 0 else "attention_required"
            results.append(
                GradeSynchronizationStatus(
                    course_offering_id=section_id,
                    status=status,
                    last_observed_at=(
                        max(value.observed_at for value in evidence)
                        if evidence
                        else None
                    ),
                    unresolved_count=unresolved_count,
                )
            )
        return tuple(results)


__all__ = ["SQLAlchemyIntegrationEvidenceReadRepository"]
