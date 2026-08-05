"""Typed SQLAlchemy base and stable technical column mixins."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import MetaData
from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.identifiers import new_uuid7
from core.time import utc_now

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseModel(DeclarativeBase):
    """Base for module-owned SQLAlchemy persistence models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Provide a UUIDv7 primary key for persistent entities."""

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
        nullable=False,
    )


class TimestampMixin:
    """Provide timezone-aware creation and update timestamps."""

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


__all__ = [
    "BaseModel",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
