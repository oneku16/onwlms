"""add tenant teacher availability windows

Revision ID: e8f5c3a1b7d2
Revises: d4c2a9e7b6f1
Create Date: 2026-08-05 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f5c3a1b7d2"
down_revision: str | Sequence[str] | None = "d4c2a9e7b6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduling_teacher_availability_windows"


def upgrade() -> None:
    """Create Scheduling-owned windows with forced tenant isolation."""

    op.create_table(
        _TABLE,
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "starts_at < ends_at",
            name=op.f("ck_scheduling_teacher_availability_windows_time_order"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_scheduling_teacher_availability_windows"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "teacher_id",
            "starts_at",
            "ends_at",
            name="uq_scheduling_teacher_availability_exact_window",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_scheduling_teacher_availability_org_id",
        ),
    )
    op.create_index(
        op.f("ix_scheduling_teacher_availability_windows_organization_id"),
        _TABLE,
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_scheduling_teacher_availability_teacher_time",
        _TABLE,
        ["organization_id", "teacher_id", "starts_at", "ends_at"],
        unique=False,
    )

    tenant_match = (
        "organization_id IS NOT DISTINCT FROM "
        "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_access ON {_TABLE} FOR ALL TO ownsis "
        f"USING ({tenant_match}) WITH CHECK ({tenant_match})"
    )
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {_TABLE} FROM ownsis_worker")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON TABLE {_TABLE} TO ownsis")


def downgrade() -> None:
    """Refuse destructive rollback of authoritative availability data."""

    raise RuntimeError(
        "Teacher availability migration cannot be downgraded safely. "
        "Apply a reviewed forward repair or restore a verified backup."
    )
