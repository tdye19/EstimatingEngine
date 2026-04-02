"""sprint15_field_actuals: Create field_actuals_projects + field_actuals_line_items tables

Revision ID: f7b9d1e3a5c6
Revises: e6a8c2d4f0b3
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = "f7b9d1e3a5c6"
down_revision = "e6a8c2d4f0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_actuals_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source_file", sa.String()),
        sa.Column("file_hash", sa.String(32), unique=True),
        sa.Column("project_type", sa.String()),
        sa.Column("completion_date", sa.Date()),
        sa.Column("region", sa.String()),
        sa.Column("notes", sa.Text()),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "field_actuals_line_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("field_actuals_projects.id"), nullable=False),
        sa.Column("wbs_area", sa.String()),
        sa.Column("activity", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float()),
        sa.Column("unit", sa.String()),
        sa.Column("crew_trade", sa.String()),
        sa.Column("actual_production_rate", sa.Float()),
        sa.Column("actual_labor_hours", sa.Float()),
        sa.Column("actual_labor_cost", sa.Float()),
        sa.Column("actual_material_cost", sa.Float()),
        sa.Column("csi_code", sa.String()),
    )

    op.create_index("ix_fa_li_project_id", "field_actuals_line_items", ["project_id"])
    op.create_index("ix_fa_li_activity", "field_actuals_line_items", ["activity"])
    op.create_index("ix_fa_li_csi_code", "field_actuals_line_items", ["csi_code"])
    op.create_index("ix_fa_li_activity_unit", "field_actuals_line_items", ["activity", "unit"])


def downgrade() -> None:
    op.drop_index("ix_fa_li_activity_unit", table_name="field_actuals_line_items")
    op.drop_index("ix_fa_li_csi_code", table_name="field_actuals_line_items")
    op.drop_index("ix_fa_li_activity", table_name="field_actuals_line_items")
    op.drop_index("ix_fa_li_project_id", table_name="field_actuals_line_items")
    op.drop_table("field_actuals_line_items")
    op.drop_table("field_actuals_projects")
