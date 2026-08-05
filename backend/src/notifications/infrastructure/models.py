"""Notification-owned SQLAlchemy representations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.time import utc_now
from shared.models import BaseModel
from shared.models import UUIDPrimaryKeyMixin


class NotificationModel(UUIDPrimaryKeyMixin, BaseModel):
    """Tenant-owned rendered notification and safe delivery state."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_created_at",
            "organization_id",
            "recipient_person_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    recipient_person_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class NotificationPreferenceModel(UUIDPrimaryKeyMixin, BaseModel):
    """Recipient preference for one tenant-specific notification channel."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "person_id",
            "channel",
            name="uq_notification_preferences_organization_person_channel",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["NotificationModel", "NotificationPreferenceModel"]
