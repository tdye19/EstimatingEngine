"""sprint18_4_1_line_item_wc_attribution

Revision ID: f8c5b2a9e3d1
Revises: e7b4a9d2c5f8
Create Date: 2026-04-23

Creates line_item_wc_attributions table for Sprint 18.4.1 Part C.

One row per TakeoffItemV2 per project after Agent 3.5 runs — either
attributed to a WorkCategory (match_tier in {csi_exact,
spec_section_fuzzy, activity_title_fuzzy, llm_semantic}) or to NULL
(match_tier="unmatched"). Regenerated via delete-then-insert per project
on every matcher run; mirrors GapFinding's contract.

Powers per-WC pricing roll-ups for the Proposal Form output.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c5b2a9e3d1"
down_revision: str | Sequence[str] | None = "e7b4a9d2c5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "line_item_wc_attributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("takeoff_item_id", sa.Integer(), nullable=False),
        sa.Column("work_category_id", sa.Integer(), nullable=True),
        sa.Column("match_tier", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["takeoff_item_id"], ["takeoff_items_v2.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["work_category_id"], ["work_categories.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "takeoff_item_id",
            name="uq_attribution_project_takeoff",
        ),
    )
    with op.batch_alter_table("line_item_wc_attributions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_line_item_wc_attributions_project_id"),
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_line_item_wc_attributions_takeoff_item_id"),
            ["takeoff_item_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_line_item_wc_attributions_work_category_id"),
            ["work_category_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("line_item_wc_attributions", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_line_item_wc_attributions_work_category_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_line_item_wc_attributions_takeoff_item_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_line_item_wc_attributions_project_id")
        )
    op.drop_table("line_item_wc_attributions")
