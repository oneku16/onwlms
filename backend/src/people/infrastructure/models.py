"""People-owned SQLAlchemy persistence representations."""

from datetime import date
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class PersonModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist sensitive person state inside one organization boundary."""

    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_people_id_organization_id",
        ),
        UniqueConstraint(
            "organization_id",
            "national_identifier_digest",
            name="uq_people_organization_national_identifier_digest",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_people_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    given_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family_name: Mapped[str] = mapped_column(String(120), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted_national_identifier: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    national_identifier_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        """Return a representation without names, PIN, birth date, or contacts."""

        return f"PersonModel(id={self.id!s}, organization_id={self.organization_id!s})"


class ContactMethodModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist an encrypted person contact method with safe channel metadata."""

    __tablename__ = "person_contact_methods"
    __table_args__ = (
        ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_person_contact_methods_person_organization_people",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_capable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a representation without contact values."""

        return f"ContactMethodModel(id={self.id!s}, kind={self.kind!r})"


class MembershipModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one identity's tenant relationship independently of platform roles."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_organization_memberships_id_organization_id",
        ),
        UniqueConstraint(
            "organization_id",
            "identity_subject_id",
            name="uq_organization_memberships_organization_identity_subject",
        ),
        ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_organization_memberships_person_organization_people",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_organization_memberships_organization_id_organizations",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    identity_subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "identity_subjects.id",
            name="fk_org_memberships_identity_subject",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    person_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)


class MembershipRoleModel(BaseModel):
    """Persist one built-in role in a membership's multi-role set."""

    __tablename__ = "organization_membership_roles"
    __table_args__ = (
        PrimaryKeyConstraint(
            "membership_id",
            "role",
            name="pk_organization_membership_roles",
        ),
        ForeignKeyConstraint(
            ["membership_id", "organization_id"],
            ["organization_memberships.id", "organization_memberships.organization_id"],
            name="fk_membership_roles_membership_org",
            ondelete="CASCADE",
        ),
    )

    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class PersonProfileModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one simultaneous student, staff, teacher, or guardian profile."""

    __tablename__ = "person_profiles"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_person_profiles_id_organization_id",
        ),
        UniqueConstraint(
            "organization_id",
            "person_id",
            "kind",
            name="uq_person_profiles_organization_person_kind",
        ),
        ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_person_profiles_person_organization_people",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    encrypted_reference_number: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    def __repr__(self) -> str:
        """Return a representation without the sensitive reference number."""

        return f"PersonProfileModel(id={self.id!s}, kind={self.kind!r})"


class AcceptedStudentRegistrationModel(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    BaseModel,
):
    """Bind one external conversion key to module-owned People identifiers."""

    __tablename__ = "people_accepted_student_registrations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "conversion_id",
            name="uq_people_accepted_students_tenant_conversion",
        ),
        UniqueConstraint(
            "organization_id",
            "student_profile_id",
            name="uq_people_accepted_students_tenant_profile",
        ),
        ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_people_accepted_students_person_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["student_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_people_accepted_students_profile_org",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    conversion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    student_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    command_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class GuardianRelationshipModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist a same-tenant guardian-to-student profile relationship."""

    __tablename__ = "guardian_student_relationships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "guardian_profile_id",
            "student_profile_id",
            name="uq_guardian_student_relationships_profiles",
        ),
        ForeignKeyConstraint(
            ["guardian_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_guardian_relationships_guardian_profile_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["student_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_guardian_relationships_student_profile_org",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    guardian_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    student_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    relationship_label: Mapped[str] = mapped_column(String(80), nullable=False)


__all__ = [
    "AcceptedStudentRegistrationModel",
    "ContactMethodModel",
    "GuardianRelationshipModel",
    "MembershipModel",
    "MembershipRoleModel",
    "PersonModel",
    "PersonProfileModel",
]
