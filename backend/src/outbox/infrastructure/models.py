"""Outbox-owned persistence representation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.time import utc_now
from shared.models import BaseModel
from shared.models import UUIDPrimaryKeyMixin


class OutboxEventModel(UUIDPrimaryKeyMixin, BaseModel):
    """Durable application event with lease, retry, and quarantine state."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_outbox_events_idempotency_key",
        ),
        Index(
            "ix_outbox_events_delivery",
            "status",
            "available_at",
        ),
        Index(
            "ix_outbox_events_organization_created_at",
            "organization_id",
            "created_at",
        ),
    )

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    actor_subject_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, str | int | bool | None]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


__all__ = ["OutboxEventModel"]
