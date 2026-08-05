"""Organization-owned SQLAlchemy persistence representations."""

from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class OrganizationModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one tenant's lifecycle and non-secret organization configuration."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        UniqueConstraint(
            "custom_domain",
            name="uq_organizations_custom_domain",
        ),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(7), nullable=False)
    logo_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    logo_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    education_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    custom_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    custom_domain_status: Mapped[str | None] = mapped_column(
        String(24),
        nullable=True,
    )
    ownid_tenant_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ownid_client_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return a representation without branding or integration metadata."""

        return f"OrganizationModel(id={self.id!s})"


class CampusModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one campus inside exactly one organization boundary."""

    __tablename__ = "organization_campuses"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_organization_campuses_organization_code",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_organization_campuses_organization_id_organizations",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["CampusModel", "OrganizationModel"]
