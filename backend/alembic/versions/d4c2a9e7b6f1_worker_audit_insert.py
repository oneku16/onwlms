"""allow tenant-bound worker audit appends

Revision ID: d4c2a9e7b6f1
Revises: a7d3e4f19b2c
Create Date: 2026-08-05 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4c2a9e7b6f1"
down_revision: str | Sequence[str] | None = "a7d3e4f19b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permit only tenant-matching audit inserts from the worker role."""

    tenant_match = (
        "organization_id IS NOT DISTINCT FROM "
        "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    )
    op.execute("GRANT INSERT ON TABLE audit_records TO ownsis_worker")
    op.execute(
        "CREATE POLICY worker_audit_insert ON audit_records FOR INSERT "
        f"TO ownsis_worker WITH CHECK ({tenant_match})"
    )


def downgrade() -> None:
    """Remove the narrowly scoped worker audit capability."""

    op.execute("DROP POLICY worker_audit_insert ON audit_records")
    op.execute("REVOKE INSERT ON TABLE audit_records FROM ownsis_worker")
