"""sprint18_4_1_gap_finding_takeoff_item_id

Revision ID: e7b4a9d2c5f8
Revises: d3a7b9c2e1f4
Create Date: 2026-04-23

Adds takeoff_item_id column to gap_findings for Sprint 18.4.1 Part B.

Background: Sprint 18.3.2's scope matcher was structurally wired to
EstimateLineItem, but Agent 6 creates EstimateLineItems AFTER Agent 3.5
runs in the pipeline [1,2,4,3,35,5,6] — so GapFinding.estimate_line_id
was always null/orphaned in practice. Part A of 18.4.1 repointed the
matcher at TakeoffItemV2 (populated by Agent 4, upstream of Agent 3.5);
this migration adds the new FK so new GapFinding rows can reference the
takeoff item that produced them.

estimate_line_id is retained for backward compatibility with any rows
that were written before Part A landed (and for downstream consumers
that still join against the legacy column).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b4a9d2c5f8"
down_revision: str | Sequence[str] | None = "d3a7b9c2e1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("takeoff_item_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_gap_findings_takeoff_item_id",
            "takeoff_items_v2",
            ["takeoff_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_gap_findings_takeoff_item_id"),
            ["takeoff_item_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gap_findings_takeoff_item_id"))
        batch_op.drop_constraint(
            "fk_gap_findings_takeoff_item_id", type_="foreignkey"
        )
        batch_op.drop_column("takeoff_item_id")
