"""add Moodle grade-evidence acceptance lineage and reconciliation runs

Revision ID: b7c4d2e9f1a3
Revises: f2c9a7d4e6b1
Create Date: 2026-09-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c4d2e9f1a3"
down_revision: str | Sequence[str] | None = "f2c9a7d4e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONFIGURATIONS = "moodle_configurations"
_EVIDENCE = "moodle_grade_evidence"
_RUNS = "moodle_grade_reconciliation_runs"


def upgrade() -> None:
    """Add signed-event secrets, evidence resolution lineage, and run state."""

    op.add_column(
        _CONFIGURATIONS,
        sa.Column("encrypted_event_secret", sa.Text(), nullable=True),
    )
    op.add_column(
        _EVIDENCE,
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column(_EVIDENCE, "received_at", server_default=None)
    op.add_column(
        _EVIDENCE,
        sa.Column("accepted_final_grade_id", sa.Uuid(), nullable=True),
    )
    op.add_column(_EVIDENCE, sa.Column("resolved_by", sa.Uuid(), nullable=True))
    op.add_column(
        _EVIDENCE,
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_moodle_grade_evidence_organization_received",
        _EVIDENCE,
        ["organization_id", "received_at"],
        unique=False,
    )

    op.create_table(
        _RUNS,
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offering_count", sa.Integer(), nullable=False),
        sa.Column("unmapped_offering_count", sa.Integer(), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("new_evidence_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("unmapped_user_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moodle_grade_reconciliation_runs")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_moodle_grade_reconciliation_runs_organization_id_id",
        ),
    )
    op.create_index(
        "ix_moodle_grade_reconciliation_runs_organization_started",
        _RUNS,
        ["organization_id", "started_at"],
        unique=False,
    )

    tenant_match = (
        "organization_id IS NOT DISTINCT FROM "
        "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    )
    op.execute(f"ALTER TABLE {_RUNS} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_RUNS} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_access ON {_RUNS} FOR ALL TO ownsis "
        f"USING ({tenant_match}) WITH CHECK ({tenant_match})"
    )
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {_RUNS} FROM ownsis_worker")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {_RUNS} TO ownsis")


def downgrade() -> None:
    """Refuse rollback that would discard evidence lineage and run history."""

    raise RuntimeError(
        "Moodle grade-evidence acceptance lineage cannot be downgraded safely. "
        "Apply a reviewed forward repair or restore a verified backup."
    )
