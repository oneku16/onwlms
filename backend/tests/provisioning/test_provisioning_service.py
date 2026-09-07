"""Provisioning idempotency, partial failure, and retry behavior."""

from dataclasses import replace
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from uuid import uuid7

import pytest

from core.errors import ConflictError
from core.time import utc_now
from outbox.application.events import ApplicationEvent
from provisioning.application.handler import ActivationProvisioningHandler
from provisioning.application.service import ProvisioningService
from provisioning.domain.jobs import ProvisioningJob
from provisioning.domain.jobs import ProvisioningStatus
from provisioning.domain.jobs import ProvisioningTarget
from provisioning.infrastructure.adapters import RecordingProvisioningAdapter
from provisioning.infrastructure.adapters import UnavailableProvisioningAdapter


class RecordingProvisioningAuditSink:
    """Capture minimized attempt evidence for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.fail = False

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
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(
            {
                "organization_id": organization_id,
                "actor_subject_id": actor_subject_id,
                "job_id": job_id,
                "target": target,
                "attempt": attempt,
                "outcome": outcome,
                "correlation_id": correlation_id,
                "worker_initiated": worker_initiated,
            }
        )


class InMemoryProvisioningRepository:
    """Preserve unique destination jobs and observable state in memory."""

    def __init__(self) -> None:
        self.jobs: dict[UUID, ProvisioningJob] = {}

    async def ensure_jobs(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        targets: tuple[ProvisioningTarget, ...],
    ) -> list[ProvisioningJob]:
        """Create only missing target jobs."""

        for target in targets:
            key = f"{subject_type}:{subject_id}:{target.value}"
            if any(job.idempotency_key == key for job in self.jobs.values()):
                continue
            now = utc_now()
            job = ProvisioningJob(
                id=uuid7(),
                organization_id=organization_id,
                subject_type=subject_type,
                subject_id=subject_id,
                target=target,
                status=ProvisioningStatus.PENDING,
                idempotency_key=key,
                attempts=0,
                created_at=now,
                updated_at=now,
            )
            self.jobs[job.id] = job
        return list(self.jobs.values())

    async def get(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob | None:
        """Return a matching tenant job."""

        job = self.jobs.get(job_id)
        return job if job and job.organization_id == organization_id else None

    async def recover_stale_processing(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        abandoned_before: datetime,
    ) -> list[ProvisioningJob]:
        """Release matching abandoned jobs before an event is resumed."""

        recovered: list[ProvisioningJob] = []
        for job_id, job in self.jobs.items():
            if (
                job.organization_id == organization_id
                and job.subject_type == subject_type
                and job.subject_id == subject_id
                and job.status is ProvisioningStatus.PROCESSING
                and job.updated_at <= abandoned_before
            ):
                job = replace(job, status=ProvisioningStatus.RETRY)
                self.jobs[job_id] = job
            if (
                job.organization_id == organization_id
                and job.subject_type == subject_type
                and job.subject_id == subject_id
            ):
                recovered.append(job)
        return recovered

    async def mark_processing(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
    ) -> ProvisioningJob:
        """Transition a tenant job to processing."""

        job = self.jobs[job_id]
        assert job.organization_id == organization_id
        updated = replace(
            job,
            status=ProvisioningStatus.PROCESSING,
            attempts=job.attempts + 1,
            updated_at=utc_now(),
        )
        self.jobs[job_id] = updated
        return updated

    async def mark_succeeded(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        external_reference: str | None,
    ) -> None:
        """Transition a job to success."""

        job = self.jobs[job_id]
        assert job.organization_id == organization_id
        self.jobs[job_id] = replace(
            job,
            status=ProvisioningStatus.SUCCEEDED,
            external_reference=external_reference,
        )

    async def mark_failed(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Transition a job to retry or terminal failure."""

        job = self.jobs[job_id]
        assert job.organization_id == organization_id
        self.jobs[job_id] = replace(
            job,
            status=(
                ProvisioningStatus.RETRY if retryable else ProvisioningStatus.FAILED
            ),
            last_error_code=error_code,
        )

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ProvisioningJob]:
        """Return only the requested tenant's work."""

        jobs = [
            job for job in self.jobs.values() if job.organization_id == organization_id
        ]
        return jobs[offset : offset + limit]


async def test_activation_creates_each_destination_once() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    service = ProvisioningService(
        repository=repository,
        adapters=[],
        max_attempts=3,
        audit=audit,
    )
    organization_id = uuid7()
    subject_id = uuid7()

    first = await service.create_activation_jobs(
        organization_id=organization_id,
        subject_type="student",
        subject_id=subject_id,
    )
    second = await service.create_activation_jobs(
        organization_id=organization_id,
        subject_type="student",
        subject_id=subject_id,
    )

    assert len(first) == len(ProvisioningTarget)
    assert {job.id for job in first} == {job.id for job in second}


async def test_recording_adapter_reuses_idempotent_external_reference() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    adapters = [RecordingProvisioningAdapter(target) for target in ProvisioningTarget]
    service = ProvisioningService(
        repository=repository,
        adapters=adapters,
        max_attempts=3,
        audit=audit,
    )
    jobs = await repository.ensure_jobs(
        organization_id=uuid7(),
        subject_type="student",
        subject_id=uuid7(),
        targets=(ProvisioningTarget.OWNID,),
    )

    completed = await service.execute(
        organization_id=jobs[0].organization_id,
        job_id=jobs[0].id,
    )

    assert completed.status is ProvisioningStatus.SUCCEEDED
    assert completed.external_reference == "test-ownid-1"
    assert audit.events[0]["outcome"] == "succeeded"
    assert audit.events[0]["target"] == ProvisioningTarget.OWNID.value


async def test_unconfigured_provider_fails_without_false_success() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    service = ProvisioningService(
        repository=repository,
        adapters=[UnavailableProvisioningAdapter(ProvisioningTarget.MOODLE)],
        max_attempts=1,
        audit=audit,
    )
    jobs = await repository.ensure_jobs(
        organization_id=uuid7(),
        subject_type="student",
        subject_id=uuid7(),
        targets=(ProvisioningTarget.MOODLE,),
    )

    with pytest.raises(ConflictError, match="failed safely"):
        await service.execute(
            organization_id=jobs[0].organization_id,
            job_id=jobs[0].id,
        )

    failed = repository.jobs[jobs[0].id]
    assert failed.status is ProvisioningStatus.FAILED
    assert "unavailable" not in (failed.last_error_code or "")
    assert audit.events[0]["outcome"] == "terminal_failure"


async def test_audit_failure_keeps_successful_effect_recoverable() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    audit.fail = True
    service = ProvisioningService(
        repository=repository,
        adapters=[RecordingProvisioningAdapter(ProvisioningTarget.OWNID)],
        max_attempts=3,
        audit=audit,
    )
    jobs = await repository.ensure_jobs(
        organization_id=uuid7(),
        subject_type="student",
        subject_id=uuid7(),
        targets=(ProvisioningTarget.OWNID,),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.execute(
            organization_id=jobs[0].organization_id,
            job_id=jobs[0].id,
        )

    assert repository.jobs[jobs[0].id].status is ProvisioningStatus.PROCESSING


async def test_activation_handler_executes_each_destination_idempotently() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    adapters = [RecordingProvisioningAdapter(target) for target in ProvisioningTarget]
    service = ProvisioningService(
        repository=repository,
        adapters=adapters,
        max_attempts=3,
        audit=audit,
    )
    handler = ActivationProvisioningHandler(service)
    organization_id = uuid7()
    subject_id = uuid7()
    event = ApplicationEvent(
        id=uuid7(),
        event_type="person.activated.v1",
        contract_version=1,
        occurred_at=utc_now(),
        organization_id=organization_id,
        actor_subject_id=uuid7(),
        correlation_id="activation-test",
        idempotency_key=f"student:{subject_id}:activated",
        payload={"subject_type": "student", "subject_id": str(subject_id)},
    )

    await handler.handle(event)
    await handler.handle(event)

    assert len(repository.jobs) == len(ProvisioningTarget)
    assert all(
        job.status is ProvisioningStatus.SUCCEEDED for job in repository.jobs.values()
    )
    assert all(len(adapter.operations) == 1 for adapter in adapters)
    assert len(audit.events) == len(ProvisioningTarget)
    assert all(event["outcome"] == "succeeded" for event in audit.events)


async def test_activation_handler_recovers_abandoned_processing_job() -> None:
    repository = InMemoryProvisioningRepository()
    audit = RecordingProvisioningAuditSink()
    adapters = [RecordingProvisioningAdapter(target) for target in ProvisioningTarget]
    service = ProvisioningService(
        repository=repository,
        adapters=adapters,
        max_attempts=3,
        audit=audit,
        lease_seconds=300,
    )
    organization_id = uuid7()
    subject_id = uuid7()
    jobs = await repository.ensure_jobs(
        organization_id=organization_id,
        subject_type="student",
        subject_id=subject_id,
        targets=(ProvisioningTarget.OWNID,),
    )
    repository.jobs[jobs[0].id] = replace(
        jobs[0],
        status=ProvisioningStatus.PROCESSING,
        updated_at=utc_now() - timedelta(minutes=10),
    )
    handler = ActivationProvisioningHandler(service)
    event = ApplicationEvent(
        id=uuid7(),
        event_type="person.activated.v1",
        contract_version=1,
        occurred_at=utc_now(),
        organization_id=organization_id,
        actor_subject_id=uuid7(),
        correlation_id="stale-processing-test",
        idempotency_key=f"student:{subject_id}:activated",
        payload={"subject_type": "student", "subject_id": str(subject_id)},
    )

    await handler.handle(event)

    recovered = repository.jobs[jobs[0].id]
    assert recovered.status is ProvisioningStatus.SUCCEEDED
    assert recovered.attempts == 1
