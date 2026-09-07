"""Authorization-aware audit recording and inspection."""

from uuid import UUID

from audit.application.ports import AuditRepository
from audit.domain.records import AuditRecord
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError


class AuditService:
    """Expose append and tenant-safe audit query capabilities."""

    def __init__(
        self,
        repository: AuditRepository,
    ) -> None:
        self._repository = repository

    async def record(
        self,
        record: AuditRecord,
    ) -> None:
        """Append pre-classified evidence from an owning application capability."""

        await self._repository.append(record)

    async def list_for_actor(
        self,
        *,
        actor: PlatformActorContext | TenantActorContext,
        limit: int,
        offset: int,
        organization_id: UUID | None = None,
    ) -> list[AuditRecord]:
        """List evidence only within the actor's separately authorized scope."""

        if isinstance(actor, PlatformActorContext):
            if "audit.platform.read" not in actor.permissions:
                raise AuthorizationError
            if organization_id is None:
                return await self._repository.list_platform(
                    limit=limit,
                    offset=offset,
                )
            if "audit.tenant.support.read" not in actor.permissions:
                raise AuthorizationError
            return await self._repository.list_for_organization(
                organization_id=organization_id,
                limit=limit,
                offset=offset,
            )
        if "audit.read" not in actor.permissions:
            raise AuthorizationError
        if organization_id is not None and organization_id != actor.organization_id:
            raise AuthorizationError
        return await self._repository.list_for_organization(
            organization_id=actor.organization_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["AuditService"]
