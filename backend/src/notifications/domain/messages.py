"""Safe notification content and delivery state."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class NotificationChannel(StrEnum):
    """Supported in-product and replaceable external delivery channels."""

    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class DeliveryStatus(StrEnum):
    """Observable delivery outcome without exposing provider payloads."""

    PENDING = "pending"
    SENT = "sent"
    RETRY = "retry"
    FAILED = "failed"
    READ = "read"


@dataclass(frozen=True, slots=True)
class Notification:
    """Represent a tenant-branded message addressed to one person."""

    id: UUID
    organization_id: UUID
    recipient_person_id: UUID
    channel: NotificationChannel
    subject: str
    body: str
    status: DeliveryStatus
    created_at: datetime
    read_at: datetime | None = None
    provider_reference: str | None = None
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    """Represent one person's effective tenant-scoped channel choice."""

    organization_id: UUID
    recipient_person_id: UUID
    channel: NotificationChannel
    enabled: bool


__all__ = [
    "DeliveryStatus",
    "Notification",
    "NotificationChannel",
    "NotificationPreference",
]
