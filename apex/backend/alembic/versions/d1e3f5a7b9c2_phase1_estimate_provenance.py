"""phase1_estimate_provenance

Revision ID: d1e3f5a7b9c2
Revises: b5d9f3a7c1e4
Create Date: 2026-05-04

Add agent_run_log_id FK to estimate_line_items so every AI-generated
estimate row can be traced back to the run that produced it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e3f5a7b9c2"
down_revision: str | Sequence[str] | None = ("b5d9f3a7c1e4", "c8e2f1a4b7d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("estimate_line_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("agent_run_log_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_estimate_line_items_agent_run_log_id",
            "agent_run_logs",
            ["agent_run_log_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("estimate_line_items", schema=None) as batch_op:
        batch_op.drop_constraint("fk_estimate_line_items_agent_run_log_id", type_="foreignkey")
        batch_op.drop_column("agent_run_log_id")
