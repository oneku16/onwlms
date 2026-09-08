"""Integration-owned tenant configuration, mappings, evidence, and runs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from core.time import utc_now
from shared.models import BaseModel
from shared.models import TimestampMixin
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
    encrypted_event_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    def __repr__(self) -> str:
        """Return a representation without credential material."""

        return f"MoodleConfigurationModel(id={self.id!s}, status={self.status!r})"


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
    """Duplicate-safe external grade evidence and its official resolution."""

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
        Index(
            "ix_moodle_grade_evidence_organization_received",
            "organization_id",
            "received_at",
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
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    accepted_final_grade_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    resolved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class MoodleGradeReconciliationRunModel(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    BaseModel,
):
    """Operator-visible outcome of one selected-term grade reconciliation."""

    __tablename__ = "moodle_grade_reconciliation_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_moodle_grade_reconciliation_runs_organization_id_id",
        ),
        Index(
            "ix_moodle_grade_reconciliation_runs_organization_started",
            "organization_id",
            "started_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    offering_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_offering_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_user_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


__all__ = [
    "MoodleConfigurationModel",
    "MoodleGradeEvidenceModel",
    "MoodleGradeReconciliationRunModel",
    "MoodleMappingModel",
]
