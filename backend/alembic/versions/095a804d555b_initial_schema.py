"""initial schema

Revision ID: 095a804d555b
Revises:
Create Date: 2026-08-05 14:53:27.042569
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "095a804d555b"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Keep this classification explicit in the immutable migration. A new table with
# organization_id must be introduced by a later migration with its own RLS policy.
TENANT_TABLES = (
    "academic_calendar_events",
    "academic_cohorts",
    "academic_course_enrollments",
    "academic_course_offering_meetings",
    "academic_course_offerings",
    "academic_course_selection_approvals",
    "academic_course_selection_override_violations",
    "academic_course_selection_overrides",
    "academic_course_selection_policies",
    "academic_course_selection_request_offerings",
    "academic_course_selection_requests",
    "academic_courses",
    "academic_curriculum_courses",
    "academic_curriculum_prerequisites",
    "academic_departments",
    "academic_faculties",
    "academic_program_curricula",
    "academic_programs",
    "academic_rooms",
    "academic_student_enrollments",
    "academic_teacher_assignments",
    "academic_terms",
    "academic_years",
    "admissions_applicant_profiles",
    "admissions_application_documents",
    "admissions_applications",
    "admissions_decisions",
    "admissions_enrollment_conversions",
    "admissions_policies",
    "admissions_policy_stages",
    "admissions_quotas",
    "admissions_review_records",
    "admissions_seat_reservations",
    "audit_records",
    "grading_final_grades",
    "grading_grade_revisions",
    "grading_scale_bands",
    "grading_scales",
    "guardian_student_relationships",
    "moodle_configurations",
    "moodle_grade_evidence",
    "moodle_mappings",
    "notification_preferences",
    "notifications",
    "organization_campuses",
    "organization_entitlement_overrides",
    "organization_membership_roles",
    "organization_memberships",
    "organization_subscriptions",
    "outbox_events",
    "people",
    "person_contact_methods",
    "person_profiles",
    "provisioning_jobs",
    "scheduling_session_groups",
    "scheduling_session_teachers",
    "scheduling_sessions",
)

GLOBAL_TABLES = (
    "entitlement_features",
    "entitlement_plan_features",
    "entitlement_plans",
    "identity_pending_oidc_flows",
    "identity_sessions",
    "identity_subjects",
    "organizations",
    "platform_administrators",
)

IMMUTABLE_TABLES = (
    "academic_course_selection_approvals",
    "academic_course_selection_override_violations",
    "academic_course_selection_overrides",
    "admissions_application_documents",
    "admissions_decisions",
    "admissions_review_records",
    "audit_records",
    "grading_grade_revisions",
    "grading_scale_bands",
    "grading_scales",
)

RUNTIME_MUTABLE_TENANT_TABLES = tuple(
    table
    for table in TENANT_TABLES
    if table not in IMMUTABLE_TABLES
    and table not in {"outbox_events", "provisioning_jobs"}
)

RUNTIME_DELETE_TABLES = (
    "academic_curriculum_courses",
    "academic_curriculum_prerequisites",
    "admissions_policy_stages",
    "organization_membership_roles",
    "scheduling_session_groups",
    "scheduling_session_teachers",
    "scheduling_sessions",
)


def _table_list(tables: Sequence[str]) -> str:
    """Render a reviewed collection of static SQL identifiers."""

    return ", ".join(tables)


def _require_runtime_roles() -> None:
    """Fail before grants when infrastructure did not provision runtime roles."""

    op.execute(
        """
        DO $ownsis_roles$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ownsis') THEN
                RAISE EXCEPTION
                    'Required NOBYPASSRLS role ownsis is not provisioned'
                    USING ERRCODE = '42704';
            END IF;
            IF NOT EXISTS (
                SELECT FROM pg_roles WHERE rolname = 'ownsis_worker'
            ) THEN
                RAISE EXCEPTION
                    'Required NOBYPASSRLS role ownsis_worker is not provisioned'
                    USING ERRCODE = '42704';
            END IF;
            IF EXISTS (
                SELECT
                FROM pg_roles
                WHERE rolname IN ('ownsis', 'ownsis_worker')
                  AND (rolsuper OR rolbypassrls)
            ) THEN
                RAISE EXCEPTION
                    'OwnSIS runtime roles must be NOSUPERUSER NOBYPASSRLS'
                    USING ERRCODE = '42501';
            END IF;
        END
        $ownsis_roles$;
        """
    )


def _install_row_level_security() -> None:
    """Force tenant isolation and grant only the two deliberate discovery paths."""

    tenant_match = (
        "organization_id IS NOT DISTINCT FROM "
        "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_access ON {table} FOR ALL TO ownsis "
            f"USING ({tenant_match}) WITH CHECK ({tenant_match})"
        )

    subject_match = (
        "identity_subject_id = "
        "NULLIF(current_setting('app.identity_subject_id', true), '')::uuid"
    )
    op.execute(
        "CREATE POLICY subject_discovery ON organization_memberships "
        f"FOR SELECT TO ownsis USING ({subject_match})"
    )
    op.execute(
        "CREATE POLICY subject_discovery ON organization_membership_roles "
        "FOR SELECT TO ownsis USING (EXISTS ("
        "SELECT 1 FROM organization_memberships AS membership "
        "WHERE membership.id = organization_membership_roles.membership_id "
        "AND membership.organization_id = "
        "organization_membership_roles.organization_id "
        "AND membership.identity_subject_id = "
        "NULLIF(current_setting('app.identity_subject_id', true), '')::uuid))"
    )

    op.execute(
        "CREATE POLICY worker_claim ON outbox_events FOR SELECT "
        "TO ownsis_worker USING (true)"
    )
    op.execute(
        "CREATE POLICY worker_update ON outbox_events FOR UPDATE "
        "TO ownsis_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY worker_tenant_access ON provisioning_jobs FOR ALL "
        f"TO ownsis_worker USING ({tenant_match}) WITH CHECK ({tenant_match})"
    )


def _install_immutable_history_guards() -> None:
    """Reject destructive mutation even by an accidentally over-granted role."""

    op.execute(
        """
        CREATE FUNCTION ownsis_reject_immutable_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $immutable$
        BEGIN
            RAISE EXCEPTION 'immutable history cannot be updated or deleted'
                USING ERRCODE = '55000';
        END;
        $immutable$;
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER reject_immutable_mutation "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION ownsis_reject_immutable_mutation()"
        )
    op.execute("REVOKE ALL ON FUNCTION ownsis_reject_immutable_mutation() FROM PUBLIC")


def _grant_runtime_privileges() -> None:
    """Grant each process role only the operations used by its repositories."""

    op.execute("GRANT USAGE ON SCHEMA public TO ownsis, ownsis_worker")
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public "
        "FROM ownsis, ownsis_worker"
    )

    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE organizations TO ownsis")
    op.execute(
        "GRANT SELECT, INSERT ON TABLE entitlement_features, "
        "entitlement_plans, entitlement_plan_features TO ownsis"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE identity_subjects, "
        "platform_administrators TO ownsis"
    )
    op.execute(
        "GRANT SELECT, INSERT, DELETE ON TABLE identity_pending_oidc_flows TO ownsis"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE identity_sessions TO ownsis"
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE "
        f"{_table_list(RUNTIME_MUTABLE_TENANT_TABLES)} TO ownsis"
    )
    op.execute(f"GRANT DELETE ON TABLE {_table_list(RUNTIME_DELETE_TABLES)} TO ownsis")
    op.execute(
        f"GRANT SELECT, INSERT ON TABLE {_table_list(IMMUTABLE_TABLES)} TO ownsis"
    )
    op.execute("GRANT INSERT ON TABLE outbox_events TO ownsis")
    op.execute("GRANT SELECT, INSERT ON TABLE provisioning_jobs TO ownsis")
    op.execute(
        "GRANT UPDATE (status, attempts, external_reference, last_error_code, "
        "updated_at) ON TABLE provisioning_jobs TO ownsis"
    )

    op.execute("GRANT SELECT ON TABLE outbox_events TO ownsis_worker")
    op.execute(
        "GRANT UPDATE (status, attempts, available_at, locked_at, locked_by, "
        "processed_at, last_error_code) ON TABLE outbox_events TO ownsis_worker"
    )
    op.execute("GRANT SELECT, INSERT ON TABLE provisioning_jobs TO ownsis_worker")
    op.execute(
        "GRANT UPDATE (status, attempts, external_reference, last_error_code, "
        "updated_at) ON TABLE provisioning_jobs TO ownsis_worker"
    )


def upgrade() -> None:
    """Apply this schema transition."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "academic_calendar_events",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instruction_allowed", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "starts_at < ends_at",
            name=op.f("ck_academic_calendar_events_academic_calendar_event_time_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_calendar_events")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_calendar_events_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_academic_calendar_events_organization_id"),
        "academic_calendar_events",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_faculties",
        sa.Column("campus_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_faculties")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_academic_faculties_organization_id_code"
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_faculties_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_faculties_organization_id"),
        "academic_faculties",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_rooms",
        sa.Column("campus_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("room_type", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "capacity > 0",
            name=op.f("ck_academic_rooms_academic_room_positive_capacity"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_rooms")),
        sa.UniqueConstraint(
            "organization_id",
            "campus_id",
            "code",
            name="uq_academic_rooms_tenant_campus_code",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_rooms_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_rooms_organization_id"),
        "academic_rooms",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_years",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "starts_on < ends_on",
            name=op.f("ck_academic_years_academic_year_date_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_years")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_years_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_academic_years_organization_id_name"
        ),
    )
    op.create_index(
        op.f("ix_academic_years_organization_id"),
        "academic_years",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_applicant_profiles",
        sa.Column("given_name", sa.String(length=128), nullable=False),
        sa.Column("family_name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_applicant_profiles")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_applicant_profiles_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_admissions_applicant_profiles_organization_id"),
        "admissions_applicant_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_policies",
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("intake_id", sa.Uuid(), nullable=False),
        sa.Column("deposit_required", sa.Boolean(), nullable=False),
        sa.Column("deposit_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("deposit_currency", sa.String(length=3), nullable=True),
        sa.Column("reservation_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "deposit_amount IS NULL OR deposit_amount > 0",
            name=op.f("ck_admissions_policies_admissions_policy_positive_deposit"),
        ),
        sa.CheckConstraint(
            "reservation_duration_seconds > 0",
            name=op.f("ck_admissions_policies_reservation_duration_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_policies")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_admissions_policies_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "program_id",
            "intake_id",
            name="uq_admissions_policies_tenant_program_intake",
        ),
    )
    op.create_index(
        op.f("ix_admissions_policies_organization_id"),
        "admissions_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_quotas",
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("intake_id", sa.Uuid(), nullable=False),
        sa.Column("seat_category", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "capacity > 0",
            name=op.f("ck_admissions_quotas_admissions_quota_positive_capacity"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_quotas")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_admissions_quotas_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "program_id",
            "intake_id",
            "seat_category",
            name="uq_admissions_quotas_tenant_program_intake_category",
        ),
    )
    op.create_index(
        op.f("ix_admissions_quotas_organization_id"),
        "admissions_quotas",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "audit_records",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_subject_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "safe_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_records")),
    )
    op.create_index(
        "ix_audit_records_organization_occurred_at",
        "audit_records",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "entitlement_features",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("base_included", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlement_features")),
        sa.UniqueConstraint("code", name="uq_entitlement_features_code"),
    )
    op.create_table(
        "entitlement_plans",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlement_plans")),
        sa.UniqueConstraint("code", name="uq_entitlement_plans_code"),
    )
    op.create_table(
        "grading_scales",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("minimum_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("maximum_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "minimum_score < maximum_score",
            name=op.f("ck_grading_scales_grading_scale_score_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_scales")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_grading_scales_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_grading_scales_organization_id_name"
        ),
    )
    op.create_index(
        op.f("ix_grading_scales_organization_id"),
        "grading_scales",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "identity_pending_oidc_flows",
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("state_digest", sa.String(length=64), nullable=False),
        sa.Column("encrypted_nonce", sa.Text(), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("return_path", sa.String(length=2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_pending_oidc_flows")),
        sa.UniqueConstraint(
            "key_digest", name="uq_identity_pending_oidc_flows_key_digest"
        ),
    )
    op.create_index(
        "ix_identity_pending_oidc_flows_expires_at",
        "identity_pending_oidc_flows",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "identity_subjects",
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_subjects")),
        sa.UniqueConstraint(
            "issuer", "subject", name="uq_identity_subjects_issuer_subject"
        ),
    )
    op.create_table(
        "moodle_configurations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moodle_configurations")),
        sa.UniqueConstraint(
            "organization_id", name="uq_moodle_configurations_organization_id"
        ),
    )
    op.create_table(
        "moodle_grade_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.String(length=200), nullable=False),
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("student_person_id", sa.Uuid(), nullable=False),
        sa.Column("grade_value", sa.String(length=80), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moodle_grade_evidence")),
        sa.UniqueConstraint(
            "organization_id",
            "external_event_id",
            name="uq_moodle_grade_evidence_organization_event",
        ),
    )
    op.create_index(
        "ix_moodle_grade_evidence_organization_status",
        "moodle_grade_evidence",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "moodle_mappings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moodle_mappings")),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            name="uq_moodle_mappings_organization_entity",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "external_id",
            name="uq_moodle_mappings_organization_external",
        ),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint(
            "organization_id",
            "person_id",
            "channel",
            name="uq_notification_preferences_organization_person_channel",
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider_reference", sa.String(length=200), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_recipient_created_at",
        "notifications",
        ["organization_id", "recipient_person_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "organizations",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("organization_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("primary_color", sa.String(length=7), nullable=False),
        sa.Column("secondary_color", sa.String(length=7), nullable=False),
        sa.Column("logo_file_name", sa.String(length=255), nullable=True),
        sa.Column("logo_content_type", sa.String(length=100), nullable=True),
        sa.Column("logo_size_bytes", sa.Integer(), nullable=True),
        sa.Column("logo_object_key", sa.String(length=1024), nullable=True),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("education_mode", sa.String(length=24), nullable=False),
        sa.Column("custom_domain", sa.String(length=253), nullable=True),
        sa.Column("custom_domain_status", sa.String(length=24), nullable=True),
        sa.Column("ownid_tenant_reference", sa.String(length=255), nullable=True),
        sa.Column("ownid_client_reference", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("custom_domain", name="uq_organizations_custom_domain"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "outbox_events",
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_subject_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
    )
    op.create_index(
        "ix_outbox_events_delivery",
        "outbox_events",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_organization_created_at",
        "outbox_events",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "provisioning_jobs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provisioning_jobs")),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_provisioning_jobs_organization_id_idempotency_key",
        ),
    )
    op.create_index(
        "ix_provisioning_jobs_organization_status",
        "provisioning_jobs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "scheduling_sessions",
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("required_room_type", sa.String(length=64), nullable=False),
        sa.Column("expected_attendance", sa.Integer(), nullable=False),
        sa.Column("recurrence_interval_weeks", sa.Integer(), nullable=True),
        sa.Column("recurrence_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "expected_attendance > 0",
            name=op.f("ck_scheduling_sessions_scheduling_session_positive_attendance"),
        ),
        sa.CheckConstraint(
            "recurrence_interval_weeks IS NULL OR recurrence_interval_weeks > 0",
            name=op.f("ck_scheduling_sessions_recurrence_interval_positive"),
        ),
        sa.CheckConstraint(
            "starts_at < ends_at",
            name=op.f("ck_scheduling_sessions_scheduling_session_time_order"),
        ),
        sa.CheckConstraint(
            "version >= 0",
            name=op.f("ck_scheduling_sessions_scheduling_session_version_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduling_sessions")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_scheduling_sessions_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_scheduling_sessions_organization_id"),
        "scheduling_sessions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_departments",
        sa.Column("faculty_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "faculty_id"],
            ["academic_faculties.organization_id", "academic_faculties.id"],
            name="fk_academic_departments_tenant_faculty",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_departments")),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_departments_organization_id_code",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_departments_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_departments_organization_id"),
        "academic_departments",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_terms",
        sa.Column("academic_year_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("enrollment_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "starts_on < ends_on",
            name=op.f("ck_academic_terms_academic_term_date_order"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_terms_tenant_academic_year",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_terms")),
        sa.UniqueConstraint(
            "organization_id",
            "academic_year_id",
            "name",
            name="uq_academic_terms_organization_year_name",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_terms_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_terms_organization_id"),
        "academic_terms",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_applications",
        sa.Column("applicant_profile_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("intake_id", sa.Uuid(), nullable=False),
        sa.Column("seat_category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("application_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deposit_required", sa.Boolean(), nullable=False),
        sa.Column("deposit_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("deposit_currency", sa.String(length=3), nullable=True),
        sa.Column("deposit_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deposit_external_reference", sa.String(length=255), nullable=True),
        sa.Column("deposit_status", sa.String(length=32), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "deposit_amount IS NULL OR deposit_amount > 0",
            name=op.f("ck_admissions_applications_positive_deposit"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "applicant_profile_id"],
            [
                "admissions_applicant_profiles.organization_id",
                "admissions_applicant_profiles.id",
            ],
            name="fk_admissions_applications_tenant_applicant_profile",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_applications")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_applications_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_admissions_applications_organization_id"),
        "admissions_applications",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_policy_stages",
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_admissions_policy_stages_admissions_policy_stage_position"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["admissions_policies.organization_id", "admissions_policies.id"],
            name="fk_admissions_policy_stages_tenant_policy",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_policy_stages")),
        sa.UniqueConstraint(
            "organization_id",
            "policy_id",
            "position",
            name="uq_admissions_policy_stages_tenant_policy_position",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "policy_id",
            "stage",
            name="uq_admissions_policy_stages_tenant_policy_stage",
        ),
    )
    op.create_index(
        op.f("ix_admissions_policy_stages_organization_id"),
        "admissions_policy_stages",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "entitlement_plan_features",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("feature_code", sa.String(length=80), nullable=False),
        sa.Column("usage_amount", sa.Integer(), nullable=True),
        sa.Column("usage_period", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["feature_code"],
            ["entitlement_features.code"],
            name="fk_entitlement_plan_features_feature_code_features",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["entitlement_plans.id"],
            name="fk_entitlement_plan_features_plan_id_plans",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "plan_id", "feature_code", name="pk_entitlement_plan_features"
        ),
    )
    op.create_table(
        "grading_final_grades",
        sa.Column("student_academic_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("course_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("grading_scale_id", sa.Uuid(), nullable=False),
        sa.Column("raw_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "credits_attempted", sa.Numeric(precision=8, scale=2), nullable=False
        ),
        sa.Column("credits_earned", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("grade_points", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("gpa_contribution", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grade_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "credits_attempted > 0",
            name=op.f("ck_grading_final_grades_attempted_credits_positive"),
        ),
        sa.CheckConstraint(
            "credits_earned >= 0 AND credits_earned <= credits_attempted",
            name=op.f(
                "ck_grading_final_grades_grading_final_grade_earned_credit_range"
            ),
        ),
        sa.CheckConstraint(
            "revision_number >= 0",
            name=op.f("ck_grading_final_grades_revision_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "grading_scale_id"],
            ["grading_scales.organization_id", "grading_scales.id"],
            name="fk_grading_final_grades_tenant_scale",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_final_grades")),
        sa.UniqueConstraint(
            "organization_id",
            "course_enrollment_id",
            name="uq_grading_final_grades_tenant_course_enrollment",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_grading_final_grades_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_grading_final_grades_organization_id"),
        "grading_final_grades",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grading_final_grades_student_academic_enrollment_id"),
        "grading_final_grades",
        ["student_academic_enrollment_id"],
        unique=False,
    )
    op.create_table(
        "grading_scale_bands",
        sa.Column("scale_id", sa.Uuid(), nullable=False),
        sa.Column("minimum_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("passing", sa.Boolean(), nullable=False),
        sa.Column("grade_points", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "grade_points IS NULL OR grade_points >= 0",
            name=op.f("ck_grading_scale_bands_grading_band_nonnegative_points"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "scale_id"],
            ["grading_scales.organization_id", "grading_scales.id"],
            name="fk_grading_bands_tenant_scale",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_scale_bands")),
        sa.UniqueConstraint(
            "organization_id",
            "scale_id",
            "minimum_score",
            name="uq_grading_bands_tenant_scale_threshold",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "scale_id",
            "symbol",
            name="uq_grading_bands_tenant_scale_symbol",
        ),
    )
    op.create_index(
        op.f("ix_grading_scale_bands_organization_id"),
        "grading_scale_bands",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "identity_sessions",
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("csrf_digest", sa.String(length=64), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_id_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("provider_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["identity_subjects.id"],
            name="fk_identity_sessions_subject_id_identity_subjects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_sessions")),
        sa.UniqueConstraint("key_digest", name="uq_identity_sessions_key_digest"),
    )
    op.create_index(
        "ix_identity_sessions_subject_expires_at",
        "identity_sessions",
        ["subject_id", "expires_at"],
        unique=False,
    )
    op.create_table(
        "organization_campuses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_campuses_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_campuses")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_organization_campuses_organization_code"
        ),
    )
    op.create_table(
        "organization_entitlement_overrides",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("feature_code", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("usage_amount", sa.Integer(), nullable=True),
        sa.Column("usage_period", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_code"],
            ["entitlement_features.code"],
            name="fk_organization_entitlement_overrides_feature_code_features",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_org_entitlement_overrides_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_organization_entitlement_overrides")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "feature_code",
            name="uq_organization_entitlement_overrides_organization_feature",
        ),
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_subscriptions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["entitlement_plans.id"],
            name="fk_organization_subscriptions_plan_id_plans",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_subscriptions")),
        sa.UniqueConstraint(
            "organization_id", name="uq_organization_subscriptions_organization_id"
        ),
    )
    op.create_table(
        "people",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("given_name", sa.String(length=120), nullable=False),
        sa.Column("family_name", sa.String(length=120), nullable=False),
        sa.Column("preferred_name", sa.String(length=120), nullable=True),
        sa.Column("encrypted_national_identifier", sa.Text(), nullable=True),
        sa.Column("national_identifier_digest", sa.String(length=64), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_people_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_people_id_organization_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "national_identifier_digest",
            name="uq_people_organization_national_identifier_digest",
        ),
    )
    op.create_table(
        "platform_administrators",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["identity_subjects.id"],
            name="fk_platform_administrators_subject_id_identity_subjects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_administrators")),
        sa.UniqueConstraint("subject_id", name="uq_platform_administrators_subject_id"),
    )
    op.create_table(
        "scheduling_session_groups",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["scheduling_sessions.organization_id", "scheduling_sessions.id"],
            name="fk_scheduling_session_groups_tenant_session",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduling_session_groups")),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            "group_id",
            name="uq_scheduling_session_groups_tenant_session_group",
        ),
    )
    op.create_index(
        op.f("ix_scheduling_session_groups_organization_id"),
        "scheduling_session_groups",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "scheduling_session_teachers",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["scheduling_sessions.organization_id", "scheduling_sessions.id"],
            name="fk_scheduling_session_teachers_tenant_session",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduling_session_teachers")),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            "teacher_id",
            name="uq_scheduling_session_teachers_tenant_session_teacher",
        ),
    )
    op.create_index(
        op.f("ix_scheduling_session_teachers_organization_id"),
        "scheduling_session_teachers",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_courses",
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("credits", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "credits > 0",
            name=op.f("ck_academic_courses_academic_course_positive_credits"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["academic_departments.organization_id", "academic_departments.id"],
            name="fk_academic_courses_tenant_department",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_courses")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_academic_courses_organization_id_code"
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_courses_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_courses_organization_id"),
        "academic_courses",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_programs",
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("education_mode", sa.String(length=32), nullable=False),
        sa.Column("credit_unit_label", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["academic_departments.organization_id", "academic_departments.id"],
            name="fk_academic_programs_tenant_department",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_programs")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_academic_programs_organization_id_code"
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_programs_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_programs_organization_id"),
        "academic_programs",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_application_documents",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=128), nullable=False),
        sa.Column("file_reference", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_admissions_application_documents_positive_size"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_documents_tenant_application",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_application_documents")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_application_documents_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_admissions_application_documents_organization_id"),
        "admissions_application_documents",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_enrollment_conversions",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=True),
        sa.Column("academic_enrollment_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_conversions_tenant_application",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_admissions_enrollment_conversions")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "application_id",
            name="uq_admissions_conversions_tenant_application",
        ),
    )
    op.create_index(
        op.f("ix_admissions_enrollment_conversions_organization_id"),
        "admissions_enrollment_conversions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_review_records",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation", sa.String(length=2000), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_reviews_tenant_application",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_review_records")),
    )
    op.create_index(
        op.f("ix_admissions_review_records_organization_id"),
        "admissions_review_records",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_seat_reservations",
        sa.Column("quota_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "reserved_at < expires_at",
            name=op.f("ck_admissions_seat_reservations_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_reservations_tenant_application",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "quota_id"],
            ["admissions_quotas.organization_id", "admissions_quotas.id"],
            name="fk_admissions_reservations_tenant_quota",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_seat_reservations")),
        sa.UniqueConstraint(
            "organization_id",
            "application_id",
            name="uq_admissions_seat_reservations_tenant_application",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_admissions_seat_reservations_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_admissions_seat_reservations_organization_id"),
        "admissions_seat_reservations",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "grading_grade_revisions",
        sa.Column("final_grade_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "previous_raw_score", sa.Numeric(precision=12, scale=4), nullable=False
        ),
        sa.Column("previous_symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "previous_credits_earned", sa.Numeric(precision=8, scale=2), nullable=False
        ),
        sa.Column(
            "previous_grade_points", sa.Numeric(precision=8, scale=4), nullable=True
        ),
        sa.Column(
            "previous_gpa_contribution",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column(
            "replacement_raw_score", sa.Numeric(precision=12, scale=4), nullable=False
        ),
        sa.Column("replacement_symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "replacement_credits_earned",
            sa.Numeric(precision=8, scale=2),
            nullable=False,
        ),
        sa.Column(
            "replacement_grade_points", sa.Numeric(precision=8, scale=4), nullable=True
        ),
        sa.Column(
            "replacement_gpa_contribution",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.Column("revised_by", sa.Uuid(), nullable=False),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("after_term_closure", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name=op.f("ck_grading_grade_revisions_grading_revision_positive_number"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "final_grade_id"],
            ["grading_final_grades.organization_id", "grading_final_grades.id"],
            name="fk_grading_revisions_tenant_final_grade",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_grade_revisions")),
        sa.UniqueConstraint(
            "organization_id",
            "final_grade_id",
            "revision_number",
            name="uq_grading_revisions_tenant_grade_revision",
        ),
    )
    op.create_index(
        op.f("ix_grading_grade_revisions_organization_id"),
        "grading_grade_revisions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "organization_memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("identity_subject_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_subject_id"],
            ["identity_subjects.id"],
            name="fk_org_memberships_identity_subject",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_memberships_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_organization_memberships_person_organization_people",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_memberships")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name="uq_organization_memberships_id_organization_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "identity_subject_id",
            name="uq_organization_memberships_organization_identity_subject",
        ),
    )
    op.create_table(
        "person_contact_methods",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("whatsapp_capable", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_person_contact_methods_person_organization_people",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_contact_methods")),
    )
    op.create_table(
        "person_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("encrypted_reference_number", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["people.id", "people.organization_id"],
            name="fk_person_profiles_person_organization_people",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_profiles")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_person_profiles_id_organization_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "person_id",
            "kind",
            name="uq_person_profiles_organization_person_kind",
        ),
    )
    op.create_table(
        "academic_cohorts",
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_cohorts_tenant_academic_year",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_cohorts_tenant_program",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_cohorts")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_academic_cohorts_organization_id_code"
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_academic_cohorts_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_academic_cohorts_organization_id"),
        "academic_cohorts",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_offerings",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("campus_id", sa.Uuid(), nullable=False),
        sa.Column("section_code", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "capacity > 0", name=op.f("ck_academic_course_offerings_positive_capacity")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_offerings_tenant_course",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_offerings_tenant_term",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_course_offerings")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_course_offerings_organization_id_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "term_id",
            "course_id",
            "section_code",
            name="uq_academic_offerings_tenant_term_course_section",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_offerings_organization_id"),
        "academic_course_offerings",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_policies",
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("education_mode", sa.String(length=32), nullable=False),
        sa.Column("maximum_credits", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "maximum_credits > 0",
            name=op.f("ck_academic_course_selection_policies_positive_max_credits"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_selection_policies_tenant_program",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_selection_policies_tenant_term",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_policies")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "program_id",
            "term_id",
            name="uq_academic_selection_policies_tenant_program_term",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_selection_policies_organization_id"),
        "academic_course_selection_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_program_curricula",
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_curricula_tenant_year",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_curricula_tenant_program",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_program_curricula")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_program_curricula_organization_id_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "program_id",
            "academic_year_id",
            name="uq_academic_curricula_tenant_program_year",
        ),
    )
    op.create_index(
        op.f("ix_academic_program_curricula_organization_id"),
        "academic_program_curricula",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "admissions_decisions",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admissions_applications.organization_id", "admissions_applications.id"],
            name="fk_admissions_decisions_tenant_application",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reservation_id"],
            [
                "admissions_seat_reservations.organization_id",
                "admissions_seat_reservations.id",
            ],
            name="fk_admissions_decisions_tenant_reservation",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admissions_decisions")),
    )
    op.create_index(
        op.f("ix_admissions_decisions_organization_id"),
        "admissions_decisions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "guardian_student_relationships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("guardian_profile_id", sa.Uuid(), nullable=False),
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_label", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["guardian_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_guardian_relationships_guardian_profile_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "organization_id"],
            ["person_profiles.id", "person_profiles.organization_id"],
            name="fk_guardian_relationships_student_profile_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guardian_student_relationships")),
        sa.UniqueConstraint(
            "organization_id",
            "guardian_profile_id",
            "student_profile_id",
            name="uq_guardian_student_relationships_profiles",
        ),
    )
    op.create_table(
        "organization_membership_roles",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id", "organization_id"],
            ["organization_memberships.id", "organization_memberships.organization_id"],
            name="fk_membership_roles_membership_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "membership_id", "role", name="pk_organization_membership_roles"
        ),
    )
    op.create_table(
        "academic_course_offering_meetings",
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "starts_at < ends_at",
            name=op.f("ck_academic_course_offering_meetings_time_order"),
        ),
        sa.CheckConstraint(
            "weekday >= 1 AND weekday <= 7",
            name=op.f("ck_academic_course_offering_meetings_weekday_range"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_offering_meetings_tenant_offering",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_offering_meetings")
        ),
    )
    op.create_index(
        op.f("ix_academic_course_offering_meetings_organization_id"),
        "academic_course_offering_meetings",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_curriculum_courses",
        sa.Column("curriculum_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("credits", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "credits > 0", name=op.f("ck_academic_curriculum_courses_positive_credits")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_curriculum_courses_tenant_course",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "curriculum_id"],
            [
                "academic_program_curricula.organization_id",
                "academic_program_curricula.id",
            ],
            name="fk_academic_curriculum_courses_tenant_curriculum",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_curriculum_courses")),
        sa.UniqueConstraint(
            "organization_id",
            "curriculum_id",
            "course_id",
            name="uq_academic_curriculum_courses_tenant_curriculum_course",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_curriculum_courses_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_academic_curriculum_courses_organization_id"),
        "academic_curriculum_courses",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_student_enrollments",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_student_enrollments_tenant_year",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "cohort_id"],
            ["academic_cohorts.organization_id", "academic_cohorts.id"],
            name="fk_academic_student_enrollments_tenant_cohort",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_student_enrollments_tenant_program",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_student_enrollments")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_student_enrollments_organization_id_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "student_id",
            "program_id",
            "academic_year_id",
            name="uq_academic_student_enrollment_tenant_student_program_year",
        ),
    )
    op.create_index(
        op.f("ix_academic_student_enrollments_organization_id"),
        "academic_student_enrollments",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_teacher_assignments",
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_teacher_assignments_tenant_offering",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_teacher_assignments")),
        sa.UniqueConstraint(
            "organization_id",
            "course_offering_id",
            "teacher_id",
            name="uq_academic_teacher_assignments_tenant_offering_teacher",
        ),
    )
    op.create_index(
        op.f("ix_academic_teacher_assignments_organization_id"),
        "academic_teacher_assignments",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_requests",
        sa.Column("student_academic_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_credits", sa.Numeric(precision=8, scale=2), nullable=False
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=1000), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "requested_credits > 0",
            name=op.f("ck_academic_course_selection_requests_positive_credits"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "student_academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_selection_requests_tenant_student_enrollment",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_selection_requests_tenant_term",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_requests")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_selection_requests_organization_id_id",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_selection_requests_organization_id"),
        "academic_course_selection_requests",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_curriculum_prerequisites",
        sa.Column("curriculum_course_id", sa.Uuid(), nullable=False),
        sa.Column("prerequisite_course_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "curriculum_course_id"],
            [
                "academic_curriculum_courses.organization_id",
                "academic_curriculum_courses.id",
            ],
            name="fk_academic_prerequisites_tenant_curriculum_course",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "prerequisite_course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_prerequisites_tenant_course",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_curriculum_prerequisites")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "curriculum_course_id",
            "prerequisite_course_id",
            name="uq_academic_prerequisites_tenant_item_prerequisite",
        ),
    )
    op.create_index(
        op.f("ix_academic_curriculum_prerequisites_organization_id"),
        "academic_curriculum_prerequisites",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_enrollments",
        sa.Column("student_academic_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("credits", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selection_request_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "credits > 0", name=op.f("ck_academic_course_enrollments_positive_credits")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_course_enrollments_tenant_offering",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "selection_request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_course_enrollments_tenant_selection_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "student_academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_course_enrollments_tenant_student_enrollment",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_course_enrollments")),
        sa.UniqueConstraint(
            "organization_id",
            "student_academic_enrollment_id",
            "course_offering_id",
            name="uq_academic_course_enrollments_tenant_student_offering",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_enrollments_organization_id"),
        "academic_course_enrollments",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_approvals",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_selection_approvals_tenant_request",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_approvals")
        ),
    )
    op.create_index(
        op.f("ix_academic_course_selection_approvals_organization_id"),
        "academic_course_selection_approvals",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_overrides",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("override_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_selection_overrides_tenant_request",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_overrides")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_selection_overrides_organization_id_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "request_id",
            name="uq_academic_selection_overrides_tenant_request",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_selection_overrides_organization_id"),
        "academic_course_selection_overrides",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_request_offerings",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("course_offering_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_request_offerings_tenant_offering",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_request_offerings_tenant_request",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_request_offerings")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "request_id",
            "course_offering_id",
            name="uq_academic_request_offerings_tenant_request_offering",
        ),
    )
    op.create_index(
        op.f("ix_academic_course_selection_request_offerings_organization_id"),
        "academic_course_selection_request_offerings",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "academic_course_selection_override_violations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("override_id", sa.Uuid(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("related_identifier", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "override_id"],
            [
                "academic_course_selection_overrides.organization_id",
                "academic_course_selection_overrides.id",
            ],
            name="fk_academic_override_violations_tenant_override",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_academic_course_selection_override_violations")
        ),
    )
    op.create_index(
        "ix_academic_override_violations_org",
        "academic_course_selection_override_violations",
        ["organization_id"],
        unique=False,
    )
    _require_runtime_roles()
    _install_row_level_security()
    _install_immutable_history_guards()
    _grant_runtime_privileges()
    # ### end Alembic commands ###


def downgrade() -> None:
    """Refuse an unsafe destructive reversal of the release baseline."""

    message = (
        "The initial OwnSIS schema cannot be downgraded safely; restore an "
        "approved backup into a replacement database instead."
    )
    raise RuntimeError(message)
