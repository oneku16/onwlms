"""Provisioning-owned SQLAlchemy representation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.time import utc_now
from shared.models import BaseModel
from shared.models import UUIDPrimaryKeyMixin


class ProvisioningJobModel(UUIDPrimaryKeyMixin, BaseModel):
    """Tenant-owned provisioning attempt and outcome state."""

    __tablename__ = "provisioning_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_provisioning_jobs_organization_id_idempotency_key",
        ),
        Index(
            "ix_provisioning_jobs_organization_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


__all__ = ["ProvisioningJobModel"]
