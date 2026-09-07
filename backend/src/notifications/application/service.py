"""Preference-aware notification creation and delivery orchestration."""

import hashlib
from collections.abc import Sequence
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from core.time import utc_now
from notifications.application.ports import NotificationChannelAdapter
from notifications.application.ports import NotificationRecipientResolver
from notifications.application.ports import NotificationRepository
from notifications.domain.messages import DeliveryStatus
from notifications.domain.messages import Notification
from notifications.domain.messages import NotificationChannel
from notifications.domain.messages import NotificationPreference
from notifications.domain.templates import render_template

NOTIFICATIONS_READ_OWN = "notifications.read_own"
NOTIFICATIONS_PREFERENCES_MANAGE_OWN = "notifications.preferences.manage_own"
NOTIFICATIONS_DELIVERY_RETRY_OWN = "notifications.delivery.retry_own"


class NotificationService:
    """Create in-app messages and safely invoke configured external channels."""

    def __init__(
        self,
        *,
        repository: NotificationRepository,
        adapters: Sequence[NotificationChannelAdapter],
        recipients: NotificationRecipientResolver,
    ) -> None:
        self._repository = repository
        self._adapters = {adapter.channel: adapter for adapter in adapters}
        self._recipients = recipients

    async def create(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
        subject_template: str,
        body_template: str,
        variables: dict[str, str],
    ) -> Notification | None:
        """Create a rendered message when the recipient enables its channel."""

        if not await self._repository.channel_enabled(
            organization_id=organization_id,
            recipient_person_id=recipient_person_id,
            channel=channel,
        ):
            return None
        notification = Notification(
            id=new_uuid7(),
            organization_id=organization_id,
            recipient_person_id=recipient_person_id,
            channel=channel,
            subject=render_template(subject_template, variables),
            body=render_template(body_template, variables),
            status=DeliveryStatus.PENDING,
            created_at=utc_now(),
        )
        await self._repository.create(notification)
        if channel is NotificationChannel.IN_APP:
            await self._repository.record_delivery(
                organization_id=organization_id,
                notification_id=notification.id,
                provider_reference=None,
            )
            return notification
        await self._deliver(notification)
        return notification

    async def list_for_recipient(
        self,
        *,
        actor: TenantActorContext,
        limit: int,
        offset: int,
    ) -> list[Notification]:
        """List messages only for the verified tenant recipient."""

        _authorize(actor, NOTIFICATIONS_READ_OWN)
        recipient_person_id = await self._recipients.resolve_person_id(actor=actor)
        return await self._repository.list_for_recipient(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            limit=limit,
            offset=offset,
        )

    async def mark_read(
        self,
        *,
        actor: TenantActorContext,
        notification_id: UUID,
    ) -> Notification:
        """Mark one addressed message read without identifier-only authorization."""

        _authorize(actor, NOTIFICATIONS_READ_OWN)
        recipient_person_id = await self._recipients.resolve_person_id(actor=actor)
        return await self._repository.mark_read(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            notification_id=notification_id,
        )

    async def list_preferences(
        self,
        *,
        actor: TenantActorContext,
    ) -> tuple[NotificationPreference, ...]:
        """Return all effective preferences for the verified tenant recipient."""

        _authorize(actor, NOTIFICATIONS_READ_OWN)
        recipient_person_id = await self._recipients.resolve_person_id(actor=actor)
        stored = await self._repository.list_preferences(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
        )
        stored_by_channel = {preference.channel: preference for preference in stored}
        return tuple(
            stored_by_channel.get(channel)
            or NotificationPreference(
                organization_id=actor.organization_id,
                recipient_person_id=recipient_person_id,
                channel=channel,
                enabled=channel is NotificationChannel.IN_APP,
            )
            for channel in NotificationChannel
        )

    async def set_preference(
        self,
        *,
        actor: TenantActorContext,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationPreference:
        """Update one preference for the verified tenant recipient."""

        _authorize(actor, NOTIFICATIONS_PREFERENCES_MANAGE_OWN)
        recipient_person_id = await self._recipients.resolve_person_id(actor=actor)
        return await self._repository.set_channel_enabled(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            channel=channel,
            enabled=enabled,
        )

    async def retry_external_delivery(
        self,
        *,
        actor: TenantActorContext,
        notification_id: UUID,
    ) -> Notification:
        """Retry one retryable external message owned by the verified recipient."""

        _authorize(actor, NOTIFICATIONS_DELIVERY_RETRY_OWN)
        recipient_person_id = await self._recipients.resolve_person_id(actor=actor)
        notification = await self._repository.get_for_recipient(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            notification_id=notification_id,
        )
        if notification is None:
            raise NotFoundError("Notification was not found.")
        if (
            notification.channel is NotificationChannel.IN_APP
            or notification.status is not DeliveryStatus.RETRY
        ):
            raise ConflictError("Notification is not eligible for external retry.")
        if not await self._repository.channel_enabled(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            channel=notification.channel,
        ):
            raise ConflictError("Notification channel is disabled.")
        await self._deliver(notification)
        completed = await self._repository.get_for_recipient(
            organization_id=actor.organization_id,
            recipient_person_id=recipient_person_id,
            notification_id=notification_id,
        )
        if completed is None:
            raise ConflictError("Delivered notification could not be reloaded.")
        return completed

    async def _deliver(
        self,
        notification: Notification,
    ) -> None:
        """Invoke one configured external channel and record its safe outcome."""

        adapter = self._adapters.get(notification.channel)
        if adapter is None:
            await self._repository.record_failure(
                organization_id=notification.organization_id,
                notification_id=notification.id,
                error_code="channel_not_configured",
                retryable=False,
            )
            raise ConflictError("Notification channel is not configured")
        try:
            reference = await adapter.send(
                organization_id=notification.organization_id,
                recipient_person_id=notification.recipient_person_id,
                subject=notification.subject,
                body=notification.body,
                idempotency_key=str(notification.id),
            )
        except Exception as exc:
            digest = hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest()[:12]
            await self._repository.record_failure(
                organization_id=notification.organization_id,
                notification_id=notification.id,
                error_code=f"delivery_error_{digest}",
                retryable=True,
            )
            raise ConflictError("Notification delivery failed safely") from exc
        await self._repository.record_delivery(
            organization_id=notification.organization_id,
            notification_id=notification.id,
            provider_reference=reference,
        )


def _authorize(actor: TenantActorContext, permission: str) -> None:
    """Fail closed unless the tenant actor owns the requested capability."""

    if permission not in actor.permissions:
        raise AuthorizationError("Required notification permission is missing.")


__all__ = [
    "NOTIFICATIONS_DELIVERY_RETRY_OWN",
    "NOTIFICATIONS_PREFERENCES_MANAGE_OWN",
    "NOTIFICATIONS_READ_OWN",
    "NotificationService",
]
