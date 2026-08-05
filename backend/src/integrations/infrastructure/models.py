"""Integration-owned tenant configuration, mappings, and evidence."""

from datetime import datetime
from uuid import UUID

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


class MoodleConfigurationModel(UUIDPrimaryKeyMixin, BaseModel):
    """Tenant Moodle activation state with encrypted credentials."""

    __tablename__ = "moodle_configurations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            name="uq_moodle_configurations_organization_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="configured",
        nullable=False,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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


class MoodleMappingModel(UUIDPrimaryKeyMixin, BaseModel):
    """Tenant-scoped opaque identifier mapping at the anti-corruption boundary."""

    __tablename__ = "moodle_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            name="uq_moodle_mappings_organization_entity",
        ),
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "external_id",
            name="uq_moodle_mappings_organization_external",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)


class MoodleGradeEvidenceModel(UUIDPrimaryKeyMixin, BaseModel):
    """Duplicate-safe external grade evidence and policy outcome."""

    __tablename__ = "moodle_grade_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_event_id",
            name="uq_moodle_grade_evidence_organization_event",
        ),
        Index(
            "ix_moodle_grade_evidence_organization_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    student_person_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    grade_value: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


__all__ = [
    "MoodleConfigurationModel",
    "MoodleGradeEvidenceModel",
    "MoodleMappingModel",
]
