"""Provisioning orchestration with bounded retries and safe failures."""

import hashlib
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.time import utc_now
from provisioning.application.ports import ProvisioningAdapter
from provisioning.application.ports import ProvisioningAuditSink
from provisioning.application.ports import ProvisioningRepository
from provisioning.domain.jobs import ProvisioningJob
from provisioning.domain.jobs import ProvisioningStatus
from provisioning.domain.jobs import ProvisioningTarget


class ProvisioningService:
    """Create and execute idempotent destination-specific provisioning jobs."""

    def __init__(
        self,
        *,
        repository: ProvisioningRepository,
        adapters: Sequence[ProvisioningAdapter],
        max_attempts: int,
        audit: ProvisioningAuditSink,
        lease_seconds: int = 300,
    ) -> None:
        self._repository = repository
        self._adapters = {adapter.target: adapter for adapter in adapters}
        self._max_attempts = max_attempts
        self._audit = audit
        self._lease_seconds = lease_seconds

    async def create_activation_jobs(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
    ) -> list[ProvisioningJob]:
        """Create the approved default destination set exactly once."""

        await self._repository.ensure_jobs(
            organization_id=organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
            targets=tuple(ProvisioningTarget),
        )
        return await self._repository.recover_stale_processing(
            organization_id=organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
            abandoned_before=utc_now() - timedelta(seconds=self._lease_seconds),
        )

    async def execute(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        actor_subject_id: UUID | None = None,
        correlation_id: str | None = None,
        worker_initiated: bool = True,
    ) -> ProvisioningJob:
        """Execute one job under its immutable tenant and idempotency context."""

        job = await self._repository.mark_processing(
            organization_id=organization_id,
            job_id=job_id,
        )
        adapter = self._adapters.get(job.target)
        audit_correlation_id = correlation_id or f"provisioning:{job.id}"
        if adapter is None:
            await self._record_attempt(
                job=job,
                actor_subject_id=actor_subject_id,
                correlation_id=audit_correlation_id,
                outcome="terminal_failure",
                worker_initiated=worker_initiated,
            )
            await self._repository.mark_failed(
                organization_id=organization_id,
                job_id=job_id,
                error_code="adapter_not_configured",
                retryable=False,
            )
            raise ConflictError("Provisioning adapter is not configured")
        try:
            reference = await adapter.provision(
                organization_id=job.organization_id,
                subject_type=job.subject_type,
                subject_id=job.subject_id,
                idempotency_key=job.idempotency_key,
            )
        except Exception as exc:
            error_code = self._safe_error_code(exc)
            retryable = job.attempts < self._max_attempts
            await self._record_attempt(
                job=job,
                actor_subject_id=actor_subject_id,
                correlation_id=audit_correlation_id,
                outcome=("retryable_failure" if retryable else "terminal_failure"),
                worker_initiated=worker_initiated,
            )
            await self._repository.mark_failed(
                organization_id=organization_id,
                job_id=job_id,
                error_code=error_code,
                retryable=retryable,
            )
            raise ConflictError("Provisioning attempt failed safely") from exc
        await self._record_attempt(
            job=job,
            actor_subject_id=actor_subject_id,
            correlation_id=audit_correlation_id,
            outcome="succeeded",
            worker_initiated=worker_initiated,
        )
        await self._repository.mark_succeeded(
            organization_id=organization_id,
            job_id=job_id,
            external_reference=reference,
        )
        completed = await self._repository.get(
            organization_id=organization_id,
            job_id=job_id,
        )
        if completed is None:
            raise ConflictError("Completed provisioning job could not be reloaded")
        return completed

    async def _record_attempt(
        self,
        *,
        job: ProvisioningJob,
        actor_subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
        worker_initiated: bool,
    ) -> None:
        """Append outcome before final state so audit failure stays recoverable."""

        await self._audit.record_provisioning_attempt(
            organization_id=job.organization_id,
            actor_subject_id=actor_subject_id,
            job_id=job.id,
            target=job.target.value,
            attempt=job.attempts,
            outcome=outcome,
            correlation_id=correlation_id,
            worker_initiated=worker_initiated,
        )

    async def list_for_actor(
        self,
        *,
        actor: TenantActorContext,
        limit: int,
        offset: int,
    ) -> list[ProvisioningJob]:
        """List provisioning state only for authorized organization operators."""

        if "provisioning.read" not in actor.permissions:
            raise AuthorizationError
        return await self._repository.list_for_organization(
            organization_id=actor.organization_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def can_retry(job: ProvisioningJob) -> bool:
        """Return whether an observable job remains eligible for retry."""

        return job.status in {ProvisioningStatus.PENDING, ProvisioningStatus.RETRY}

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        """Map an exception class to a stable opaque operational code."""

        digest = hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest()[:12]
        return f"provisioning_error_{digest}"


__all__ = ["ProvisioningService"]
