"""Audit-owned SQLAlchemy persistence representation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.time import utc_now
from shared.models import BaseModel
from shared.models import UUIDPrimaryKeyMixin


class AuditRecordModel(UUIDPrimaryKeyMixin, BaseModel):
    """Append-only database representation of privacy-minimized audit evidence."""

    __tablename__ = "audit_records"
    __table_args__ = (
        Index(
            "ix_audit_records_organization_occurred_at",
            "organization_id",
            "occurred_at",
        ),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    actor_subject_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    safe_metadata: Mapped[dict[str, str | int | bool] | None] = mapped_column(
        JSONB,
        nullable=True,
    )


__all__ = ["AuditRecordModel"]
