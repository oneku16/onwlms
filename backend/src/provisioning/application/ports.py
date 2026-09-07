"""Replaceable provisioning and job-storage ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from provisioning.domain.jobs import ProvisioningJob
from provisioning.domain.jobs import ProvisioningTarget


class ProvisioningAdapter(Protocol):
    """Provision exactly one approved external destination."""

    @property
    def target(self) -> ProvisioningTarget:
        """Return the destination owned by this adapter."""
        ...

    async def provision(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        idempotency_key: str,
    ) -> str | None:
        """Apply an idempotent effect and return its safe external reference."""
        ...


class ProvisioningRepository(Protocol):
    """Persist observable provisioning work and attempt outcomes."""

    async def ensure_jobs(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        targets: tuple[ProvisioningTarget, ...],
    ) -> list[ProvisioningJob]:
        """Create missing jobs and return the complete destination set."""
        ...

    async def recover_stale_processing(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        abandoned_before: datetime,
    ) -> list[ProvisioningJob]:
        """Release abandoned processing leases and return the subject job set."""
        ...

    async def get(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob | None:
        """Return one tenant-scoped job."""
        ...

    async def mark_processing(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob:
        """Atomically claim a retryable job for an attempt."""
        ...

    async def mark_succeeded(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        external_reference: str | None,
    ) -> None:
        """Record successful completion."""
        ...

    async def mark_failed(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Record a privacy-safe retryable or terminal failure."""
        ...

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ProvisioningJob]:
        """Return one tenant's most recent provisioning work."""
        ...


class ProvisioningAuditSink(Protocol):
    """Append minimized outcome evidence for each provisioning attempt."""

    async def record_provisioning_attempt(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        job_id: UUID,
        target: str,
        attempt: int,
        outcome: str,
        correlation_id: str,
        worker_initiated: bool,
    ) -> None:
        """Record one completed attempt without provider data or errors."""
        ...


__all__ = [
    "ProvisioningAdapter",
    "ProvisioningAuditSink",
    "ProvisioningRepository",
]
