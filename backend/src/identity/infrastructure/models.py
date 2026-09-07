"""Identity-owned SQLAlchemy persistence representations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class OwnIDSubjectModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one global OwnID subject without tenant authorization state."""

    __tablename__ = "identity_subjects"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_identity_subjects_issuer_subject",
        ),
    )

    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        """Return a representation that excludes external identity claims."""

        return f"OwnIDSubjectModel(id={self.id!s})"


class PlatformAdministratorModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist platform privilege separately from every tenant membership."""

    __tablename__ = "platform_administrators"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            name="uq_platform_administrators_subject_id",
        ),
    )

    subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "identity_subjects.id",
            name="fk_platform_administrators_subject_id_identity_subjects",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PendingOIDCFlowModel(UUIDPrimaryKeyMixin, BaseModel):
    """Persist one single-use OIDC flow using only a hashed browser key."""

    __tablename__ = "identity_pending_oidc_flows"
    __table_args__ = (
        UniqueConstraint(
            "key_digest",
            name="uq_identity_pending_oidc_flows_key_digest",
        ),
        Index(
            "ix_identity_pending_oidc_flows_expires_at",
            "expires_at",
        ),
    )

    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_nonce: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_code_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    return_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a representation that excludes all flow secrets."""

        return f"PendingOIDCFlowModel(id={self.id!s})"


class IdentitySessionModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist a server session with hashed browser and encrypted provider tokens."""

    __tablename__ = "identity_sessions"
    __table_args__ = (
        UniqueConstraint(
            "key_digest",
            name="uq_identity_sessions_key_digest",
        ),
        Index(
            "ix_identity_sessions_subject_expires_at",
            "subject_id",
            "expires_at",
        ),
    )

    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "identity_subjects.id",
            name="fk_identity_sessions_subject_id_identity_subjects",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    csrf_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_id_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a representation that excludes browser and provider secrets."""

        return f"IdentitySessionModel(id={self.id!s})"


__all__ = [
    "IdentitySessionModel",
    "OwnIDSubjectModel",
    "PendingOIDCFlowModel",
    "PlatformAdministratorModel",
]
