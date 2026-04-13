"""PB-INTEGRATE-1: Productivity Brain tables

Revision ID: b3d5f7a9c1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "b3d5f7a9c1e2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pb_projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_file", sa.String(length=500), nullable=False),
        sa.Column("file_hash", sa.String(length=32), nullable=False),
        sa.Column("format_type", sa.String(length=30), nullable=True),
        sa.Column("project_count", sa.Integer(), server_default="1", nullable=True),
        sa.Column("total_line_items", sa.Integer(), server_default="0", nullable=True),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash"),
    )

    op.create_table(
        "pb_line_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("wbs_area", sa.String(length=255), nullable=True),
        sa.Column("activity", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("crew_trade", sa.String(length=200), nullable=True),
        sa.Column("production_rate", sa.Float(), nullable=True),
        sa.Column("labor_hours", sa.Float(), nullable=True),
        sa.Column("labor_cost_per_unit", sa.Float(), nullable=True),
        sa.Column("material_cost_per_unit", sa.Float(), nullable=True),
        sa.Column("equipment_cost", sa.Float(), nullable=True),
        sa.Column("sub_cost", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=True),
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("source_project", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["pb_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Single-column indexes
    op.create_index("ix_pb_line_items_project_id", "pb_line_items", ["project_id"])
    op.create_index("ix_pb_line_items_activity", "pb_line_items", ["activity"])
    op.create_index("ix_pb_line_items_csi_code", "pb_line_items", ["csi_code"])

    # Composite index for Agent 4 rate matching
    op.create_index("ix_pb_li_activity_unit", "pb_line_items", ["activity", "unit"])


def downgrade() -> None:
    op.drop_index("ix_pb_li_activity_unit", table_name="pb_line_items")
    op.drop_index("ix_pb_line_items_csi_code", table_name="pb_line_items")
    op.drop_index("ix_pb_line_items_activity", table_name="pb_line_items")
    op.drop_index("ix_pb_line_items_project_id", table_name="pb_line_items")
    op.drop_table("pb_line_items")
    op.drop_table("pb_projects")
