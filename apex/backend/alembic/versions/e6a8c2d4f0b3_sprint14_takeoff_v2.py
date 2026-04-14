"""sprint14_takeoff_v2: Create takeoff_items_v2 table for Agent 4 v2

Revision ID: e6a8c2d4f0b3
Revises: d5f7b9a1c3e4
Create Date: 2026-04-02
"""

import sqlalchemy as sa
from alembic import op

revision = "e6a8c2d4f0b3"
down_revision = "d5f7b9a1c3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "takeoff_items_v2",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("wbs_area", sa.String()),
        sa.Column("activity", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float()),
        sa.Column("unit", sa.String()),
        sa.Column("crew", sa.String()),
        sa.Column("production_rate", sa.Float()),
        sa.Column("labor_cost_per_unit", sa.Float()),
        sa.Column("material_cost_per_unit", sa.Float()),
        sa.Column("csi_code", sa.String()),
        # Rate recommendation fields (populated by Agent 4)
        sa.Column("historical_avg_rate", sa.Float()),
        sa.Column("historical_min_rate", sa.Float()),
        sa.Column("historical_max_rate", sa.Float()),
        sa.Column("sample_count", sa.Integer(), server_default="0"),
        sa.Column("confidence", sa.String(), server_default="none"),
        sa.Column("delta_pct", sa.Float()),
        sa.Column("flag", sa.String(), server_default="NO_DATA"),
        sa.Column("matching_projects", sa.Text()),  # JSON array of project names
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_takeoff_v2_project_activity",
        "takeoff_items_v2",
        ["project_id", "activity"],
    )


def downgrade() -> None:
    op.drop_index("ix_takeoff_v2_project_activity", table_name="takeoff_items_v2")
    op.drop_table("takeoff_items_v2")
