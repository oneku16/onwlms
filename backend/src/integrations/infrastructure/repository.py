"""PostgreSQL integration configuration, mapping, evidence, and run adapters."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import ConflictError
from core.errors import NotFoundError
from core.time import utc_now
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import IntegrationStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeEvidenceRecord
from integrations.domain.moodle import MoodleGradeReconciliationRun
from integrations.domain.moodle import ReconciliationRunStatus
from integrations.infrastructure.models import MoodleConfigurationModel
from integrations.infrastructure.models import MoodleGradeEvidenceModel
from integrations.infrastructure.models import MoodleGradeReconciliationRunModel
from integrations.infrastructure.models import MoodleMappingModel
from shared.database import Database


class SQLAlchemyMoodleIntegrationRepository:
    """Persist each organization's integration state under tenant context."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def configure(
        self,
        *,
        organization_id: UUID,
        base_url: str,
        encrypted_token: str,
    ) -> MoodleConfiguration:
        """Create or rotate tenant configuration with a row lock."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleConfigurationModel)
                .where(MoodleConfigurationModel.organization_id == organization_id)
                .with_for_update()
            )
            if model is None:
                model = MoodleConfigurationModel(
                    organization_id=organization_id,
                    base_url=base_url,
                    encrypted_token=encrypted_token,
                    status=IntegrationStatus.CONFIGURED.value,
                )
                session.add(model)
            else:
                model.base_url = base_url
                model.encrypted_token = encrypted_token
                model.status = IntegrationStatus.CONFIGURED.value
                model.last_error_code = None
            await session.flush()
            return self._configuration(model)

    async def get_configuration(
        self,
        organization_id: UUID,
    ) -> MoodleConfiguration | None:
        """Return safe configuration metadata under tenant scope."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleConfigurationModel).where(
                    MoodleConfigurationModel.organization_id == organization_id
                )
            )
            return self._configuration(model) if model else None

    async def get_encrypted_token(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return protected token material only within infrastructure use."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            value: object = await session.scalar(
                select(MoodleConfigurationModel.encrypted_token).where(
                    MoodleConfigurationModel.organization_id == organization_id
                )
            )
            return value if isinstance(value, str) else None

    async def set_grade_event_secret(
        self,
        *,
        organization_id: UUID,
        encrypted_secret: str,
    ) -> MoodleConfiguration:
        """Store the protected signing secret on the locked configuration row."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await self._get_configuration_locked(session, organization_id)
            model.encrypted_event_secret = encrypted_secret
            await session.flush()
            return self._configuration(model)

    async def get_encrypted_grade_event_secret(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return the protected signing secret for tenant-bound verification."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            value: object = await session.scalar(
                select(MoodleConfigurationModel.encrypted_event_secret).where(
                    MoodleConfigurationModel.organization_id == organization_id
                )
            )
            return value if isinstance(value, str) else None

    async def put_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        external_id: str,
    ) -> None:
        """Insert a tenant mapping while preserving database uniqueness."""

        try:
            async with self._database.session(
                organization_id=organization_id,
            ) as session:
                session.add(
                    MoodleMappingModel(
                        organization_id=organization_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        external_id=external_id,
                    )
                )
        except IntegrityError:
            existing = await self.get_mapping(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            if existing != external_id:
                raise

    async def get_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> str | None:
        """Resolve a mapping within exactly one tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            value: object = await session.scalar(
                select(MoodleMappingModel.external_id).where(
                    MoodleMappingModel.organization_id == organization_id,
                    MoodleMappingModel.entity_type == entity_type,
                    MoodleMappingModel.entity_id == entity_id,
                )
            )
            return value if isinstance(value, str) else None

    async def get_entity_id(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        external_id: str,
    ) -> UUID | None:
        """Resolve a Moodle identifier back to one tenant entity."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            value: object = await session.scalar(
                select(MoodleMappingModel.entity_id).where(
                    MoodleMappingModel.organization_id == organization_id,
                    MoodleMappingModel.entity_type == entity_type,
                    MoodleMappingModel.external_id == external_id,
                )
            )
            return value if isinstance(value, UUID) else None

    async def accept_grade_event_once(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
    ) -> bool:
        """Persist external evidence once using a tenant-aware unique key."""

        try:
            async with self._database.session(
                organization_id=organization_id,
            ) as session:
                session.add(
                    MoodleGradeEvidenceModel(
                        organization_id=organization_id,
                        external_event_id=evidence.external_event_id,
                        course_offering_id=evidence.course_offering_id,
                        student_person_id=evidence.student_person_id,
                        grade_value=evidence.grade_value,
                        observed_at=evidence.observed_at,
                        source_version=evidence.source_version,
                    )
                )
        except IntegrityError:
            return False
        return True

    async def mark_grade_event_outcome(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
        status: GradeEvidenceStatus,
        reason_code: str | None,
    ) -> None:
        """Record how official grading policy dispositioned intake."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeEvidenceModel)
                .where(
                    MoodleGradeEvidenceModel.organization_id == organization_id,
                    MoodleGradeEvidenceModel.external_event_id == external_event_id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError
            model.status = status.value
            model.reason_code = reason_code

    async def get_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return one evidence record from exactly one tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeEvidenceModel).where(
                    MoodleGradeEvidenceModel.organization_id == organization_id,
                    MoodleGradeEvidenceModel.id == evidence_id,
                )
            )
            return self._evidence(model) if model is not None else None

    async def get_grade_evidence_by_event(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return stored evidence for one tenant external event key."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeEvidenceModel).where(
                    MoodleGradeEvidenceModel.organization_id == organization_id,
                    MoodleGradeEvidenceModel.external_event_id == external_event_id,
                )
            )
            return self._evidence(model) if model is not None else None

    async def list_grade_evidence(
        self,
        *,
        organization_id: UUID,
        status: GradeEvidenceStatus | None,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeEvidenceRecord, ...]:
        """Return a newest-first stable page of tenant evidence."""

        query = select(MoodleGradeEvidenceModel).where(
            MoodleGradeEvidenceModel.organization_id == organization_id
        )
        if status is not None:
            query = query.where(MoodleGradeEvidenceModel.status == status.value)
        if course_offering_id is not None:
            query = query.where(
                MoodleGradeEvidenceModel.course_offering_id == course_offering_id
            )
        query = (
            query.order_by(
                MoodleGradeEvidenceModel.received_at.desc(),
                MoodleGradeEvidenceModel.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = (await session.scalars(query)).all()
            return tuple(self._evidence(model) for model in models)

    async def resolve_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        status: GradeEvidenceStatus,
        reason_code: str | None,
        final_grade_id: UUID | None,
        resolved_by: UUID,
        resolved_at: datetime,
    ) -> MoodleGradeEvidenceRecord:
        """Resolve pending evidence exactly once under a tenant row lock."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeEvidenceModel)
                .where(
                    MoodleGradeEvidenceModel.organization_id == organization_id,
                    MoodleGradeEvidenceModel.id == evidence_id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError("Moodle grade evidence was not found.")
            if model.status != GradeEvidenceStatus.PENDING.value:
                raise ConflictError("Moodle grade evidence was already resolved.")
            model.status = status.value
            model.reason_code = reason_code
            model.accepted_final_grade_id = final_grade_id
            model.resolved_by = resolved_by
            model.resolved_at = resolved_at
            await session.flush()
            return self._evidence(model)

    async def record_success(
        self,
        organization_id: UUID,
    ) -> None:
        """Record successful communication and clear stale failure state."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await self._get_configuration_locked(session, organization_id)
            model.status = IntegrationStatus.HEALTHY.value
            model.last_success_at = utc_now()
            model.last_error_code = None

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        error_code: str,
    ) -> None:
        """Record a safe degraded state without provider response content."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await self._get_configuration_locked(session, organization_id)
            model.status = IntegrationStatus.DEGRADED.value
            model.last_error_code = error_code[:120]

    @staticmethod
    async def _get_configuration_locked(
        session: AsyncSession,
        organization_id: UUID,
    ) -> MoodleConfigurationModel:
        """Load configuration under a caller-owned transaction."""

        model = await session.scalar(
            select(MoodleConfigurationModel)
            .where(MoodleConfigurationModel.organization_id == organization_id)
            .with_for_update()
        )
        if model is None:
            raise NotFoundError
        return model

    @staticmethod
    def _configuration(model: MoodleConfigurationModel) -> MoodleConfiguration:
        """Translate configuration without serializing its credentials."""

        return MoodleConfiguration(
            organization_id=model.organization_id,
            base_url=model.base_url,
            status=IntegrationStatus(model.status),
            last_success_at=model.last_success_at,
            last_error_code=model.last_error_code,
            grade_events_configured=model.encrypted_event_secret is not None,
        )

    @staticmethod
    def _evidence(model: MoodleGradeEvidenceModel) -> MoodleGradeEvidenceRecord:
        """Translate one stored evidence row into the domain record."""

        return MoodleGradeEvidenceRecord(
            id=model.id,
            organization_id=model.organization_id,
            external_event_id=model.external_event_id,
            course_offering_id=model.course_offering_id,
            student_person_id=model.student_person_id,
            grade_value=model.grade_value,
            observed_at=model.observed_at,
            source_version=model.source_version,
            status=GradeEvidenceStatus(model.status),
            reason_code=model.reason_code,
            received_at=model.received_at,
            accepted_final_grade_id=model.accepted_final_grade_id,
            resolved_by=model.resolved_by,
            resolved_at=model.resolved_at,
        )


class SQLAlchemyMoodleReconciliationRunRepository:
    """Persist selected-term reconciliation runs under tenant context."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def create_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist one newly started tenant run."""

        async with self._database.session(
            organization_id=run.organization_id,
        ) as session:
            session.add(
                MoodleGradeReconciliationRunModel(
                    id=run.id,
                    organization_id=run.organization_id,
                    term_id=run.term_id,
                    requested_by=run.requested_by,
                    status=run.status.value,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    offering_count=run.offering_count,
                    unmapped_offering_count=run.unmapped_offering_count,
                    observed_count=run.observed_count,
                    new_evidence_count=run.new_evidence_count,
                    duplicate_count=run.duplicate_count,
                    unmapped_user_count=run.unmapped_user_count,
                    error_code=run.error_code,
                )
            )

    async def complete_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist the terminal outcome of one locked tenant run."""

        async with self._database.session(
            organization_id=run.organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeReconciliationRunModel)
                .where(
                    MoodleGradeReconciliationRunModel.organization_id
                    == run.organization_id,
                    MoodleGradeReconciliationRunModel.id == run.id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError("Reconciliation run was not found.")
            model.status = run.status.value
            model.finished_at = run.finished_at
            model.offering_count = run.offering_count
            model.unmapped_offering_count = run.unmapped_offering_count
            model.observed_count = run.observed_count
            model.new_evidence_count = run.new_evidence_count
            model.duplicate_count = run.duplicate_count
            model.unmapped_user_count = run.unmapped_user_count
            model.error_code = run.error_code

    async def get_run(
        self,
        *,
        organization_id: UUID,
        run_id: UUID,
    ) -> MoodleGradeReconciliationRun | None:
        """Return one run from exactly one tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MoodleGradeReconciliationRunModel).where(
                    MoodleGradeReconciliationRunModel.organization_id
                    == organization_id,
                    MoodleGradeReconciliationRunModel.id == run_id,
                )
            )
            return self._run(model) if model is not None else None

    async def list_runs(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeReconciliationRun, ...]:
        """Return a newest-first stable page of tenant runs."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = (
                await session.scalars(
                    select(MoodleGradeReconciliationRunModel)
                    .where(
                        MoodleGradeReconciliationRunModel.organization_id
                        == organization_id
                    )
                    .order_by(
                        MoodleGradeReconciliationRunModel.started_at.desc(),
                        MoodleGradeReconciliationRunModel.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return tuple(self._run(model) for model in models)

    @staticmethod
    def _run(
        model: MoodleGradeReconciliationRunModel,
    ) -> MoodleGradeReconciliationRun:
        """Translate one stored run row into the domain record."""

        return MoodleGradeReconciliationRun(
            id=model.id,
            organization_id=model.organization_id,
            term_id=model.term_id,
            requested_by=model.requested_by,
            status=ReconciliationRunStatus(model.status),
            started_at=model.started_at,
            finished_at=model.finished_at,
            offering_count=model.offering_count,
            unmapped_offering_count=model.unmapped_offering_count,
            observed_count=model.observed_count,
            new_evidence_count=model.new_evidence_count,
            duplicate_count=model.duplicate_count,
            unmapped_user_count=model.unmapped_user_count,
            error_code=model.error_code,
        )


__all__ = [
    "SQLAlchemyMoodleIntegrationRepository",
    "SQLAlchemyMoodleReconciliationRunRepository",
]
