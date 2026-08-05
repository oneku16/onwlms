"""SQLAlchemy 2 persistence models owned by official grading."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class GradingTenantModelMixin:
    """Provide explicit tenant ownership for official grading records."""

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


class GradingScaleModel(
    GradingTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist an immutable tenant-owned grading scale definition."""

    __tablename__ = "grading_scales"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_grading_scales_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_grading_scales_organization_id_name",
        ),
        CheckConstraint(
            "minimum_score < maximum_score",
            name="grading_scale_score_order",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    minimum_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    maximum_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)


class GradeBandModel(
    GradingTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one threshold and GPA mapping for a grading scale."""

    __tablename__ = "grading_scale_bands"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "scale_id",
            "minimum_score",
            name="uq_grading_bands_tenant_scale_threshold",
        ),
        UniqueConstraint(
            "organization_id",
            "scale_id",
            "symbol",
            name="uq_grading_bands_tenant_scale_symbol",
        ),
        ForeignKeyConstraint(
            ["organization_id", "scale_id"],
            ["grading_scales.organization_id", "grading_scales.id"],
            name="fk_grading_bands_tenant_scale",
        ),
        CheckConstraint(
            "grade_points IS NULL OR grade_points >= 0",
            name="grading_band_nonnegative_points",
        ),
    )

    scale_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    minimum_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    passing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grade_points: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
    )


class FinalGradeModel(
    GradingTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist current official final grade state for a course enrollment."""

    __tablename__ = "grading_final_grades"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_grading_final_grades_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "course_enrollment_id",
            name="uq_grading_final_grades_tenant_course_enrollment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "grading_scale_id"],
            ["grading_scales.organization_id", "grading_scales.id"],
            name="fk_grading_final_grades_tenant_scale",
        ),
        CheckConstraint(
            "credits_attempted > 0",
            name="attempted_credits_positive",
        ),
        CheckConstraint(
            "credits_earned >= 0 AND credits_earned <= credits_attempted",
            name="grading_final_grade_earned_credit_range",
        ),
        CheckConstraint(
            "revision_number >= 0",
            name="revision_nonnegative",
        ),
    )

    student_academic_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    course_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    course_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grading_scale_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    raw_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    credits_attempted: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    credits_earned: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    grade_points: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
    )
    gpa_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    grade_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class GradeRevisionModel(
    GradingTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist append-only before-and-after official grade history."""

    __tablename__ = "grading_grade_revisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "final_grade_id",
            "revision_number",
            name="uq_grading_revisions_tenant_grade_revision",
        ),
        ForeignKeyConstraint(
            ["organization_id", "final_grade_id"],
            ["grading_final_grades.organization_id", "grading_final_grades.id"],
            name="fk_grading_revisions_tenant_final_grade",
        ),
        CheckConstraint(
            "revision_number > 0",
            name="grading_revision_positive_number",
        ),
    )

    final_grade_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_raw_score: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )
    previous_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_credits_earned: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    previous_grade_points: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
    )
    previous_gpa_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )
    replacement_raw_score: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )
    replacement_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    replacement_credits_earned: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    replacement_grade_points: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
    )
    replacement_gpa_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )
    explanation: Mapped[str] = mapped_column(String(2000), nullable=False)
    revised_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    after_term_closure: Mapped[bool] = mapped_column(Boolean, nullable=False)


__all__ = [
    "FinalGradeModel",
    "GradeBandModel",
    "GradeRevisionModel",
    "GradingScaleModel",
]
