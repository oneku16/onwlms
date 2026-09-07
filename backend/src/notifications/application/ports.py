"""Notification storage and external-channel ports."""

from typing import Protocol
from uuid import UUID

from core.context import TenantActorContext
from notifications.domain.messages import Notification
from notifications.domain.messages import NotificationChannel
from notifications.domain.messages import NotificationPreference


class NotificationRepository(Protocol):
    """Persist tenant-owned notification content and outcomes."""

    async def create(
        self,
        notification: Notification,
    ) -> None:
        """Persist one notification exactly once by identifier."""
        ...

    async def list_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Notification]:
        """Return one recipient's messages under one tenant."""
        ...

    async def mark_read(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification:
        """Mark only the addressed person's in-app message as read."""
        ...

    async def get_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Return one notification only for its tenant recipient."""
        ...

    async def record_delivery(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        provider_reference: str | None,
    ) -> None:
        """Record successful external delivery."""
        ...

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Record a privacy-safe external delivery failure."""
        ...

    async def channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
    ) -> bool:
        """Resolve the recipient's tenant-scoped channel preference."""
        ...

    async def list_preferences(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
    ) -> tuple[NotificationPreference, ...]:
        """Return explicitly stored tenant-recipient channel preferences."""
        ...

    async def set_channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationPreference:
        """Create or replace one tenant-recipient channel preference."""
        ...


class NotificationChannelAdapter(Protocol):
    """Deliver a message through one replaceable external channel."""

    @property
    def channel(self) -> NotificationChannel:
        """Return the one external channel implemented by this adapter."""
        ...

    async def send(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> str | None:
        """Send idempotently and return a safe provider reference."""
        ...


class NotificationRecipientResolver(Protocol):
    """Revalidate the person linked to one active tenant membership."""

    async def resolve_person_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        """Return the exact tenant person bound to the actor's membership."""
        ...


__all__ = [
    "NotificationChannelAdapter",
    "NotificationRecipientResolver",
    "NotificationRepository",
]
