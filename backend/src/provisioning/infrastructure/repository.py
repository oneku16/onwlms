"""PostgreSQL provisioning job persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.errors import ConflictError
from core.errors import NotFoundError
from provisioning.domain.jobs import ProvisioningJob
from provisioning.domain.jobs import ProvisioningStatus
from provisioning.domain.jobs import ProvisioningTarget
from provisioning.infrastructure.models import ProvisioningJobModel
from shared.database import Database


class SQLAlchemyProvisioningRepository:
    """Persist provisioning state under explicit tenant transactions."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def ensure_jobs(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        targets: tuple[ProvisioningTarget, ...],
    ) -> list[ProvisioningJob]:
        """Create destination jobs with tenant-aware uniqueness protection."""

        for target in targets:
            key = f"{subject_type}:{subject_id}:{target.value}"
            try:
                async with self._database.session(
                    organization_id=organization_id,
                ) as session:
                    session.add(
                        ProvisioningJobModel(
                            organization_id=organization_id,
                            subject_type=subject_type,
                            subject_id=subject_id,
                            target=target.value,
                            idempotency_key=key,
                        )
                    )
            except IntegrityError:
                continue
        return await self._list_for_subject(
            organization_id=organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )

    async def get(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob | None:
        """Read one tenant-scoped job."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ProvisioningJobModel).where(
                    ProvisioningJobModel.id == job_id,
                    ProvisioningJobModel.organization_id == organization_id,
                )
            )
            return self._to_domain(model) if model else None

    async def recover_stale_processing(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        abandoned_before: datetime,
    ) -> list[ProvisioningJob]:
        """Return abandoned processing jobs to retry before event resumption."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = list(
                await session.scalars(
                    select(ProvisioningJobModel)
                    .where(
                        ProvisioningJobModel.organization_id == organization_id,
                        ProvisioningJobModel.subject_type == subject_type,
                        ProvisioningJobModel.subject_id == subject_id,
                    )
                    .with_for_update()
                )
            )
            for model in rows:
                if (
                    model.status == ProvisioningStatus.PROCESSING.value
                    and model.updated_at <= abandoned_before
                ):
                    model.status = ProvisioningStatus.RETRY.value
                    model.last_error_code = "processing_lease_expired"
            await session.flush()
            return [self._to_domain(model) for model in rows]

    async def mark_processing(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob:
        """Claim a pending or retry job with a row lock."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ProvisioningJobModel)
                .where(
                    ProvisioningJobModel.id == job_id,
                    ProvisioningJobModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError
            if model.status not in {
                ProvisioningStatus.PENDING.value,
                ProvisioningStatus.RETRY.value,
            }:
                raise ConflictError("Provisioning job cannot be retried")
            model.status = ProvisioningStatus.PROCESSING.value
            model.attempts += 1
            await session.flush()
            return self._to_domain(model)

    async def mark_succeeded(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        external_reference: str | None,
    ) -> None:
        """Record successful completion under tenant scope."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ProvisioningJobModel)
                .where(
                    ProvisioningJobModel.id == job_id,
                    ProvisioningJobModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError
            model.status = ProvisioningStatus.SUCCEEDED.value
            model.external_reference = external_reference
            model.last_error_code = None

    async def mark_failed(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Record a safe failure with explicit retry state."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ProvisioningJobModel)
                .where(
                    ProvisioningJobModel.id == job_id,
                    ProvisioningJobModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError
            model.status = (
                ProvisioningStatus.RETRY.value
                if retryable
                else ProvisioningStatus.FAILED.value
            )
            model.last_error_code = error_code[:120]

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ProvisioningJob]:
        """Return one tenant's latest provisioning work."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = await session.scalars(
                select(ProvisioningJobModel)
                .where(ProvisioningJobModel.organization_id == organization_id)
                .order_by(ProvisioningJobModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._to_domain(model) for model in rows]

    async def _list_for_subject(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
    ) -> list[ProvisioningJob]:
        """Return the complete destination set for one activated subject."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = await session.scalars(
                select(ProvisioningJobModel)
                .where(
                    ProvisioningJobModel.organization_id == organization_id,
                    ProvisioningJobModel.subject_type == subject_type,
                    ProvisioningJobModel.subject_id == subject_id,
                )
                .order_by(ProvisioningJobModel.target)
            )
            return [self._to_domain(model) for model in rows]

    @staticmethod
    def _to_domain(model: ProvisioningJobModel) -> ProvisioningJob:
        """Translate mutable persistence state into an immutable job value."""

        return ProvisioningJob(
            id=model.id,
            organization_id=model.organization_id,
            subject_type=model.subject_type,
            subject_id=model.subject_id,
            target=ProvisioningTarget(model.target),
            status=ProvisioningStatus(model.status),
            idempotency_key=model.idempotency_key,
            attempts=model.attempts,
            created_at=model.created_at,
            updated_at=model.updated_at,
            external_reference=model.external_reference,
            last_error_code=model.last_error_code,
        )


__all__ = ["SQLAlchemyProvisioningRepository"]
