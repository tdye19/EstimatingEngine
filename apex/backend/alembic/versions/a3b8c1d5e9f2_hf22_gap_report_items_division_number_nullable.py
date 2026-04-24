"""hf22_gap_report_items_division_number_nullable

Revision ID: a3b8c1d5e9f2
Revises: f8c5b2a9e3d1
Create Date: 2026-04-24

HF-22: relax gap_report_items.division_number to NULL.

Cross-cutting rule-based gap findings (e.g. SCOPE_CROSS_REFERENCES detecting
"takeoff includes concrete but missing associated reinforcement") don't map
to a single CSI division. The NOT NULL constraint forced Agent 3 to insert
None and crash with IntegrityError, leaving the SQLAlchemy session in
rolled-back state and hanging the entire pipeline at status="running".

Note for downgrade: this migration cannot be reversed cleanly once any
NULL rows have been written. Backfill or DELETE the NULL rows first if a
downgrade is required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b8c1d5e9f2"
down_revision: str | Sequence[str] | None = "f8c5b2a9e3d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gap_report_items", schema=None) as batch_op:
        batch_op.alter_column(
            "division_number",
            existing_type=sa.String(length=10),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("gap_report_items", schema=None) as batch_op:
        batch_op.alter_column(
            "division_number",
            existing_type=sa.String(length=10),
            nullable=False,
        )
