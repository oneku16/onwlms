"""PostgreSQL integration configuration, mapping, and evidence adapter."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.errors import NotFoundError
from core.time import utc_now
from integrations.domain.moodle import IntegrationStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.infrastructure.models import MoodleConfigurationModel
from integrations.infrastructure.models import MoodleGradeEvidenceModel
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
        accepted: bool,
        reason_code: str | None,
    ) -> None:
        """Record whether official grading policy accepted the evidence."""

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
            model.status = "accepted" if accepted else "rejected"
            model.reason_code = reason_code

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
        session: object,
        organization_id: UUID,
    ) -> MoodleConfigurationModel:
        """Load configuration under a caller-owned transaction."""

        from sqlalchemy.ext.asyncio import AsyncSession

        if not isinstance(session, AsyncSession):
            message = "session must be an AsyncSession"
            raise TypeError(message)
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
        """Translate configuration without serializing its credential."""

        return MoodleConfiguration(
            organization_id=model.organization_id,
            base_url=model.base_url,
            status=IntegrationStatus(model.status),
            last_success_at=model.last_success_at,
            last_error_code=model.last_error_code,
        )


__all__ = ["SQLAlchemyMoodleIntegrationRepository"]
