"""sprint18_3_1_1_gap_finding_severity

Revision ID: d3a7b9c2e1f4
Revises: c8e1a2f3b5d9
Create Date: 2026-04-22

Adds severity column to gap_findings so downstream consumers (gap UI,
Intelligence Report) can filter/sort by severity without re-deriving it
from confidence + finding_type + match_tier. Introduced as a sub-migration
of Sprint 18.3.1 (GapFinding model) before Sprint 18.3.2 (Agent 3.5 matcher)
populates the table.

Values: "ERROR" | "WARNING" | "INFO". Server-default "WARNING" backfills
safely; the gap_findings table is empty at merge time (no rows have been
written yet — Agent 3.5 is the first writer).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a7b9c2e1f4"
down_revision: str | Sequence[str] | None = "c8e1a2f3b5d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "severity",
                sa.String(length=16),
                nullable=False,
                server_default="WARNING",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.drop_column("severity")
