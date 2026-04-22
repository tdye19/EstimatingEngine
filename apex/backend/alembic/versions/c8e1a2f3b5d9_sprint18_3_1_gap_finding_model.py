"""sprint18_3_1_gap_finding_model

Revision ID: c8e1a2f3b5d9
Revises: b7d2c1e9f8a4
Create Date: 2026-04-21

Creates gap_findings table for Agent 3.5 scope gap analysis output.

finding_type, match_tier, source are stored as String columns matching
the Sprint 18.1 convention (see WorkCategory.parse_method). Pydantic's
Literal[...] types on GapFindingOut are the authoritative enum.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e1a2f3b5d9"
down_revision: str | Sequence[str] | None = "b7d2c1e9f8a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gap_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("finding_type", sa.String(length=32), nullable=False),
        sa.Column("work_category_id", sa.Integer(), nullable=True),
        sa.Column("estimate_line_id", sa.Integer(), nullable=True),
        sa.Column("spec_section_ref", sa.String(length=32), nullable=True),
        sa.Column("match_tier", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_category_id"], ["work_categories.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["estimate_line_id"], ["estimate_line_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_gap_findings_project_id"),
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_gap_findings_project_finding_type",
            ["project_id", "finding_type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("gap_findings", schema=None) as batch_op:
        batch_op.drop_index("ix_gap_findings_project_finding_type")
        batch_op.drop_index(batch_op.f("ix_gap_findings_project_id"))
    op.drop_table("gap_findings")
