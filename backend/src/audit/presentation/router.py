"""Thin, explicitly serialized audit query routes."""

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

from audit.application.service import AuditService
from audit.domain.records import AuditRecord
from core.context import ActorContext


class AuditRecordResponse(BaseModel):
    """Safe audit response that cannot include arbitrary protected payloads."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID | None
    actor_subject_id: UUID | None
    action: str
    entity_type: str
    entity_id: str
    occurred_at: str
    source: str
    outcome: str
    correlation_id: str
    reason: str | None
    metadata: dict[str, str | int | bool] | None


def create_audit_router(
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
) -> APIRouter:
    """Create the audit router with an injected trusted actor resolver."""

    router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

    @router.get("")
    async def list_audit_records(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        organization_id: UUID | None = None,
    ) -> list[AuditRecordResponse]:
        """List authorized audit evidence under platform or tenant scope."""

        service: AuditService = request.app.state.audit_service
        records = await service.list_for_actor(
            actor=actor,
            limit=limit,
            offset=offset,
            organization_id=organization_id,
        )
        return [_response(record) for record in records]

    return router


def _response(record: AuditRecord) -> AuditRecordResponse:
    """Serialize only the audit contract's explicitly safe fields."""

    return AuditRecordResponse(
        id=record.id,
        organization_id=record.organization_id,
        actor_subject_id=record.actor_subject_id,
        action=record.action,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        occurred_at=record.occurred_at.isoformat(),
        source=record.source.value,
        outcome=record.outcome,
        correlation_id=record.correlation_id,
        reason=record.reason,
        metadata=record.metadata,
    )


__all__ = ["create_audit_router"]
