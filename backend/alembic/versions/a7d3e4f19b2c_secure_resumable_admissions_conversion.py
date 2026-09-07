"""secure resumable admissions conversion

Revision ID: a7d3e4f19b2c
Revises: 095a804d555b
Create Date: 2026-08-05 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e4f19b2c"
down_revision: str | Sequence[str] | None = "095a804d555b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = (
    "academic_admissions_enrollment_registrations",
    "people_accepted_student_registrations",
)


def _require_safe_contact_transition() -> None:
    """Refuse to relabel plaintext applicant contacts as encrypted data."""

    op.execute(
        "LOCK TABLE admissions_applicant_profiles, "
        "admissions_enrollment_conversions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $secure_applicant_contacts$
        BEGIN
            IF EXISTS (SELECT 1 FROM admissions_applicant_profiles LIMIT 1) THEN
                RAISE EXCEPTION
                    'Applicant contacts require an approved export, encryption, '
                    'and forward migration before this revision can run'
                    USING ERRCODE = '55000';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM admissions_enrollment_conversions
                WHERE student_id IS NULL OR academic_enrollment_id IS NULL
                LIMIT 1
            ) THEN
                RAISE EXCEPTION
                    'Pending admissions conversions lack stable downstream IDs; '
                    'resolve them before this revision'
                    USING ERRCODE = '55000';
            END IF;
        END
        $secure_applicant_contacts$;
        """
    )


def _install_tenant_security() -> None:
    """Apply forced RLS and least-privilege grants to the new bindings."""

    tenant_match = (
        "organization_id IS NOT DISTINCT FROM "
        "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    )
    for table in _NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_access ON {table} FOR ALL TO ownsis "
            f"USING ({tenant_match}) WITH CHECK ({tenant_match})"
        )
        op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM ownsis_worker")
        op.execute(f"GRANT SELECT, INSERT ON TABLE {table} TO ownsis")


def upgrade() -> None:
    """Encrypt new applicant contact writes and add resumable bindings."""

    _require_safe_contact_transition()
    op.alter_column(
        "admissions_applicant_profiles",
        "email",
        new_column_name="encrypted_email",
        existing_type=sa.String(length=320),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "admissions_applicant_profiles",
        "phone",
        new_column_name="encrypted_phone",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "admissions_enrollment_conversions",
        "student_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "admissions_enrollment_conversions",
        "academic_enrollment_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.add_column(
        "admissions_enrollment_conversions",
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
    )

    op.create_table(
        "academic_admissions_enrollment_registrations",
        sa.Column("conversion_id", sa.Uuid(), nullable=False),
        sa.Column("academic_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("intake_term_id", sa.Uuid(), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_admissions_enrollments_tenant_enrollment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "intake_term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_admissions_enrollments_tenant_term",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_academic_admissions_enrollment_registrations"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "academic_enrollment_id",
            name="uq_academic_admissions_enrollments_tenant_enrollment",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "conversion_id",
            name="uq_academic_admissions_enrollments_tenant_conversion",
        ),
    )
    op.create_index(
        op.f("ix_academic_admissions_enrollment_registrations_organization_id"),
        "academic_admissions_enrollment_registrations",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "people_accepted_student_registrations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversion_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_people_accepted_students_person_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_people_accepted_students_profile_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_people_accepted_student_registrations"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "conversion_id",
            name="uq_people_accepted_students_tenant_conversion",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "student_profile_id",
            name="uq_people_accepted_students_tenant_profile",
        ),
    )
    op.create_index(
        op.f("ix_people_accepted_student_registrations_organization_id"),
        "people_accepted_student_registrations",
        ["organization_id"],
        unique=False,
    )
    _install_tenant_security()


def downgrade() -> None:
    """Refuse a downgrade that would relabel ciphertext as plaintext."""

    raise RuntimeError(
        "This security migration cannot be downgraded safely. Restore an "
        "approved pre-migration backup or apply a reviewed forward-recovery "
        "migration."
    )
