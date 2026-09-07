"""Tenant-scoped provisioning status and retry routes."""

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict

from core.context import ActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from provisioning.application.service import ProvisioningService
from provisioning.domain.jobs import ProvisioningJob


class ProvisioningJobResponse(BaseModel):
    """Privacy-safe provisioning status response."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    subject_type: str
    subject_id: UUID
    target: str
    status: str
    attempts: int
    created_at: str
    updated_at: str
    external_reference: str | None
    last_error_code: str | None


def create_provisioning_router(
    *,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
    csrf_dependency: Callable[..., Awaitable[None]],
) -> APIRouter:
    """Create provisioning routes with identity and CSRF dependencies injected."""

    router = APIRouter(prefix="/api/v1/operations/provisioning", tags=["operations"])

    @router.get("")
    async def list_jobs(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ProvisioningJobResponse]:
        """List provisioning work for the active organization."""

        tenant_actor = _tenant_actor(actor)
        service: ProvisioningService = request.app.state.provisioning_service
        jobs = await service.list_for_actor(
            actor=tenant_actor,
            limit=limit,
            offset=offset,
        )
        return [_response(job) for job in jobs]

    @router.post("/{job_id}/retry")
    async def retry_job(
        job_id: UUID,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> ProvisioningJobResponse:
        """Retry one failed job through its normal idempotent adapter."""

        tenant_actor = _tenant_actor(actor)
        if "provisioning.retry" not in tenant_actor.permissions:
            raise AuthorizationError
        service: ProvisioningService = request.app.state.provisioning_service
        job = await service.execute(
            organization_id=tenant_actor.organization_id,
            job_id=job_id,
            actor_subject_id=tenant_actor.subject_id,
            correlation_id=tenant_actor.correlation_id,
            worker_initiated=False,
        )
        return _response(job)

    return router


def _tenant_actor(actor: ActorContext) -> TenantActorContext:
    """Reject platform context on ordinary tenant provisioning routes."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _response(job: ProvisioningJob) -> ProvisioningJobResponse:
    """Serialize safe provisioning fields without provider payloads."""

    return ProvisioningJobResponse(
        id=job.id,
        subject_type=job.subject_type,
        subject_id=job.subject_id,
        target=job.target.value,
        status=job.status.value,
        attempts=job.attempts,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        external_reference=job.external_reference,
        last_error_code=job.last_error_code,
    )


__all__ = ["create_provisioning_router"]
