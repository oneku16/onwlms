"""SQLAlchemy 2 persistence models owned by the admissions module."""

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
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class AdmissionsTenantModelMixin:
    """Provide explicit tenant ownership for admissions persistence."""

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


class ApplicantProfileModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist admissions-owned applicant identity and sensitive contact data."""

    __tablename__ = "admissions_applicant_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_applicant_profiles_organization_id_id",
        ),
    )

    SAFE_SERIALIZE_FIELDS = ("id", "given_name", "family_name")

    given_name: Mapped[str] = mapped_column(String(128), nullable=False)
    family_name: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_phone: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApplicationModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one application and current lifecycle state."""

    __tablename__ = "admissions_applications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_applications_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "applicant_profile_id"],
            [
                "admissions_applicant_profiles.organization_id",
                "admissions_applicant_profiles.id",
            ],
            name="fk_admissions_applications_tenant_applicant_profile",
        ),
        CheckConstraint(
            "deposit_amount IS NULL OR deposit_amount > 0",
            name="positive_deposit",
        ),
    )

    applicant_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    intake_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    seat_category: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    application_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    deposit_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deposit_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    deposit_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    deposit_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deposit_external_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    deposit_status: Mapped[str] = mapped_column(String(32), nullable=False)


class ApplicationDocumentModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist bounded metadata for an externally stored applicant document."""

    __tablename__ = "admissions_application_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_application_documents_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_documents_tenant_application",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="positive_size",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class AdmissionsPolicyModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist review, deposit, and reservation policy for an intake."""

    __tablename__ = "admissions_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_policies_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "program_id",
            "intake_id",
            name="uq_admissions_policies_tenant_program_intake",
        ),
        CheckConstraint(
            "reservation_duration_seconds > 0",
            name="reservation_duration_positive",
        ),
        CheckConstraint(
            "deposit_amount IS NULL OR deposit_amount > 0",
            name="admissions_policy_positive_deposit",
        ),
    )

    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    intake_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    deposit_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deposit_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    deposit_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    reservation_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class AdmissionsPolicyStageModel(
    AdmissionsTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist ordered configured review stages relationally."""

    __tablename__ = "admissions_policy_stages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "policy_id",
            "stage",
            name="uq_admissions_policy_stages_tenant_policy_stage",
        ),
        UniqueConstraint(
            "organization_id",
            "policy_id",
            "position",
            name="uq_admissions_policy_stages_tenant_policy_position",
        ),
        ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["admissions_policies.organization_id", "admissions_policies.id"],
            name="fk_admissions_policy_stages_tenant_policy",
        ),
        CheckConstraint("position >= 0", name="admissions_policy_stage_position"),
    )

    policy_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AdmissionQuotaModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a categorized program-intake seat capacity."""

    __tablename__ = "admissions_quotas"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_quotas_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "program_id",
            "intake_id",
            "seat_category",
            name="uq_admissions_quotas_tenant_program_intake_category",
        ),
        CheckConstraint("capacity > 0", name="admissions_quota_positive_capacity"),
    )

    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    intake_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    seat_category: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class SeatReservationModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a seat allocation protected by repository-level locking."""

    __tablename__ = "admissions_seat_reservations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_seat_reservations_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "application_id",
            name="uq_admissions_seat_reservations_tenant_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "quota_id"],
            ["admissions_quotas.organization_id", "admissions_quotas.id"],
            name="fk_admissions_reservations_tenant_quota",
        ),
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_reservations_tenant_application",
        ),
        CheckConstraint(
            "reserved_at < expires_at",
            name="time_order",
        ),
    )

    quota_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ReviewRecordModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist immutable stage review history."""

    __tablename__ = "admissions_review_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_reviews_tenant_application",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class AdmissionDecisionModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist append-only official admissions decision history."""

    __tablename__ = "admissions_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_decisions_tenant_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reservation_id"],
            [
                "admissions_seat_reservations.organization_id",
                "admissions_seat_reservations.id",
            ],
            name="fk_admissions_decisions_tenant_reservation",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    reservation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class EnrollmentConversionModel(
    AdmissionsTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist idempotent accepted-to-enrolled workflow state."""

    __tablename__ = "admissions_enrollment_conversions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "application_id",
            name="uq_admissions_conversions_tenant_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_conversions_tenant_application",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    academic_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = [
    "AdmissionDecisionModel",
    "AdmissionQuotaModel",
    "AdmissionsPolicyModel",
    "AdmissionsPolicyStageModel",
    "ApplicantProfileModel",
    "ApplicationDocumentModel",
    "ApplicationModel",
    "EnrollmentConversionModel",
    "ReviewRecordModel",
    "SeatReservationModel",
]
