"""Recipient-scoped in-app notification routes."""

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
from notifications.application.service import NotificationService
from notifications.domain.messages import Notification
from notifications.domain.messages import NotificationChannel
from notifications.domain.messages import NotificationPreference


class NotificationResponse(BaseModel):
    """Safe rendered notification response for its addressed recipient."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    channel: str
    subject: str
    body: str
    status: str
    created_at: str
    read_at: str | None


class NotificationPreferenceBody(BaseModel):
    """Strict update payload for one recipient channel preference."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class NotificationPreferenceResponse(BaseModel):
    """Effective recipient preference without identity fields."""

    model_config = ConfigDict(extra="forbid")

    channel: NotificationChannel
    enabled: bool


def create_notifications_router(
    *,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
    csrf_dependency: Callable[..., Awaitable[None]],
) -> APIRouter:
    """Create notification routes with injected identity and CSRF checks."""

    router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

    @router.get("")
    async def list_notifications(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[NotificationResponse]:
        """List only messages addressed to the current active membership."""

        tenant_actor = _tenant_actor(actor)
        service: NotificationService = request.app.state.notification_service
        notifications = await service.list_for_recipient(
            actor=tenant_actor,
            limit=limit,
            offset=offset,
        )
        return [_response(notification) for notification in notifications]

    @router.post("/{notification_id}/read")
    async def mark_notification_read(
        notification_id: UUID,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> NotificationResponse:
        """Mark one notification read only for its verified recipient."""

        tenant_actor = _tenant_actor(actor)
        service: NotificationService = request.app.state.notification_service
        notification = await service.mark_read(
            actor=tenant_actor,
            notification_id=notification_id,
        )
        return _response(notification)

    @router.get("/preferences")
    async def list_notification_preferences(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> list[NotificationPreferenceResponse]:
        """List effective channel choices for the current active membership."""

        tenant_actor = _tenant_actor(actor)
        service: NotificationService = request.app.state.notification_service
        preferences = await service.list_preferences(
            actor=tenant_actor,
        )
        return [_preference_response(preference) for preference in preferences]

    @router.put("/preferences/{channel}")
    async def update_notification_preference(
        channel: NotificationChannel,
        body: NotificationPreferenceBody,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> NotificationPreferenceResponse:
        """Update one channel choice for the current active membership."""

        tenant_actor = _tenant_actor(actor)
        service: NotificationService = request.app.state.notification_service
        preference = await service.set_preference(
            actor=tenant_actor,
            channel=channel,
            enabled=body.enabled,
        )
        return _preference_response(preference)

    @router.post("/{notification_id}/retry")
    async def retry_notification_delivery(
        notification_id: UUID,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> NotificationResponse:
        """Retry one recipient-owned retryable external delivery."""

        tenant_actor = _tenant_actor(actor)
        service: NotificationService = request.app.state.notification_service
        notification = await service.retry_external_delivery(
            actor=tenant_actor,
            notification_id=notification_id,
        )
        return _response(notification)

    return router


def _tenant_actor(actor: ActorContext) -> TenantActorContext:
    """Reject platform context on recipient notification routes."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _response(notification: Notification) -> NotificationResponse:
    """Serialize addressed message fields without provider diagnostic state."""

    return NotificationResponse(
        id=notification.id,
        channel=notification.channel.value,
        subject=notification.subject,
        body=notification.body,
        status=notification.status.value,
        created_at=notification.created_at.isoformat(),
        read_at=notification.read_at.isoformat() if notification.read_at else None,
    )


def _preference_response(
    preference: NotificationPreference,
) -> NotificationPreferenceResponse:
    """Serialize an effective preference without recipient identifiers."""

    return NotificationPreferenceResponse(
        channel=preference.channel,
        enabled=preference.enabled,
    )


__all__ = ["create_notifications_router"]
