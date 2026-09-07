"""add immutable final-grade recording evidence

Revision ID: f2c9a7d4e6b1
Revises: e8f5c3a1b7d2
Create Date: 2026-08-07 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c9a7d4e6b1"
down_revision: str | Sequence[str] | None = "e8f5c3a1b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "grading_final_grades"
_CHECK = "ck_grading_final_grades_recording_explanation_matches_closure"


def upgrade() -> None:
    """Preserve whether and why an initial grade was recorded after closure."""

    op.add_column(
        _TABLE,
        sa.Column(
            "recorded_after_term_closure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "recording_explanation",
            sa.String(length=2000),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f(_CHECK),
        _TABLE,
        "(recorded_after_term_closure "
        "AND recording_explanation IS NOT NULL "
        "AND char_length(btrim(recording_explanation)) > 0) "
        "OR (NOT recorded_after_term_closure "
        "AND recording_explanation IS NULL)",
    )
    op.alter_column(
        _TABLE,
        "recorded_after_term_closure",
        server_default=None,
    )


def downgrade() -> None:
    """Refuse rollback that would discard official recording explanations."""

    raise RuntimeError(
        "Final-grade recording evidence cannot be downgraded safely. "
        "Apply a reviewed forward repair or restore a verified backup."
    )
