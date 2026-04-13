"""sprint10_productivity_benchmark

Creates the productivity_benchmarks table introduced in Sprint 10.

Revision ID: e5a2b7d3f1c8
Revises: f2c9d4e7b3a1
Create Date: 2026-03-28 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5a2b7d3f1c8"
down_revision = "f2c9d4e7b3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "productivity_benchmarks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # CSI classification
        sa.Column("csi_division", sa.String(length=2), nullable=False),
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        # Segmentation dimensions
        sa.Column("project_type", sa.String(length=50), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        # Aggregated cost stats
        sa.Column("avg_unit_cost", sa.Float(), nullable=False),
        sa.Column("avg_labor_cost_per_unit", sa.Float(), nullable=True),
        sa.Column("avg_material_cost_per_unit", sa.Float(), nullable=True),
        sa.Column("avg_equipment_cost_per_unit", sa.Float(), nullable=True),
        sa.Column("avg_sub_cost_per_unit", sa.Float(), nullable=True),
        # Productivity rate
        sa.Column("avg_labor_hours_per_unit", sa.Float(), nullable=True),
        # Distribution
        sa.Column("min_unit_cost", sa.Float(), nullable=True),
        sa.Column("max_unit_cost", sa.Float(), nullable=True),
        sa.Column("std_dev", sa.Float(), nullable=True),
        # Data quality
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("last_computed_at", sa.DateTime(), nullable=False),
        sa.Column("source_project_ids", sa.Text(), nullable=True),
        # Org scope
        sa.Column("organization_id", sa.Integer(), nullable=False),
        # Soft-delete + timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Single-column indexes
    op.create_index(
        op.f("ix_productivity_benchmarks_csi_division"),
        "productivity_benchmarks",
        ["csi_division"],
    )
    op.create_index(
        op.f("ix_productivity_benchmarks_csi_code"),
        "productivity_benchmarks",
        ["csi_code"],
    )
    op.create_index(
        op.f("ix_productivity_benchmarks_project_type"),
        "productivity_benchmarks",
        ["project_type"],
    )
    op.create_index(
        op.f("ix_productivity_benchmarks_region"),
        "productivity_benchmarks",
        ["region"],
    )
    op.create_index(
        op.f("ix_productivity_benchmarks_organization_id"),
        "productivity_benchmarks",
        ["organization_id"],
    )

    # Composite indexes
    op.create_index(
        "ix_pb_division_type_region_org",
        "productivity_benchmarks",
        ["csi_division", "project_type", "region", "organization_id"],
    )
    op.create_index(
        "ix_pb_code_uom_org",
        "productivity_benchmarks",
        ["csi_code", "unit_of_measure", "organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pb_code_uom_org", table_name="productivity_benchmarks")
    op.drop_index("ix_pb_division_type_region_org", table_name="productivity_benchmarks")
    op.drop_index(op.f("ix_productivity_benchmarks_organization_id"), table_name="productivity_benchmarks")
    op.drop_index(op.f("ix_productivity_benchmarks_region"), table_name="productivity_benchmarks")
    op.drop_index(op.f("ix_productivity_benchmarks_project_type"), table_name="productivity_benchmarks")
    op.drop_index(op.f("ix_productivity_benchmarks_csi_code"), table_name="productivity_benchmarks")
    op.drop_index(op.f("ix_productivity_benchmarks_csi_division"), table_name="productivity_benchmarks")
    op.drop_table("productivity_benchmarks")
