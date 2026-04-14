"""sprint8_full_schema_with_estimate_library

Adds the 7 tables that were absent from the sprint-7 migration:
  - equipment_rates
  - audit_logs
  - bid_comparisons
  - bid_comparison_items
  - change_orders
  - estimate_library
  - estimate_library_tags

This migration is purely additive and safe to run on:
  * a fresh database (after the sprint-7 migration has run), or
  * an existing database that was migrated through sprint 7.

Revision ID: c9f4a8d2e1b3
Revises: 37e85ea73069
Create Date: 2026-03-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f4a8d2e1b3"
down_revision: str | Sequence[str] | None = "37e85ea73069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add all tables introduced / missed before sprint 8."""

    # ------------------------------------------------------------------
    # equipment_rates  (no FK dependencies)
    # ------------------------------------------------------------------
    op.create_table(
        "equipment_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("division_number", sa.String(length=10), nullable=False),
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("equipment_pct", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("equipment_rates", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_equipment_rates_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_rates_division_number"), ["division_number"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_rates_csi_code"), ["csi_code"], unique=False)

    # ------------------------------------------------------------------
    # audit_logs  (FK → users)
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_id"), ["id"], unique=False)

    # ------------------------------------------------------------------
    # bid_comparisons  (FK → projects)
    # ------------------------------------------------------------------
    op.create_table(
        "bid_comparisons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("bid_date", sa.String(length=50), nullable=True),
        sa.Column("total_bid_amount", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bid_comparisons", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bid_comparisons_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_bid_comparisons_project_id"), ["project_id"], unique=False)

    # ------------------------------------------------------------------
    # bid_comparison_items  (FK → bid_comparisons)
    # ------------------------------------------------------------------
    op.create_table(
        "bid_comparison_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("comparison_id", sa.Integer(), nullable=False),
        sa.Column("division_number", sa.String(length=10), nullable=False),
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["comparison_id"], ["bid_comparisons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bid_comparison_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bid_comparison_items_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_bid_comparison_items_comparison_id"), ["comparison_id"], unique=False)

    # ------------------------------------------------------------------
    # change_orders  (FK → projects)
    # ------------------------------------------------------------------
    op.create_table(
        "change_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("co_number", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("change_type", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_impact", sa.Float(), nullable=True),
        sa.Column("schedule_impact_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("change_orders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_change_orders_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_change_orders_project_id"), ["project_id"], unique=False)

    # ------------------------------------------------------------------
    # estimate_library  (FK → projects, estimates, users, organizations)
    # ------------------------------------------------------------------
    op.create_table(
        "estimate_library",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("estimate_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_type", sa.String(length=100), nullable=True),
        sa.Column("building_type", sa.String(length=100), nullable=True),
        sa.Column("square_footage", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("cost_per_sqft", sa.Float(), nullable=True),
        sa.Column("location_city", sa.String(length=100), nullable=True),
        sa.Column("location_state", sa.String(length=2), nullable=True),
        sa.Column("location_zip", sa.String(length=10), nullable=True),
        sa.Column("bid_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("bid_result", sa.String(length=50), nullable=True),
        sa.Column("csi_divisions_json", sa.Text(), nullable=True),
        sa.Column("line_item_count", sa.Integer(), nullable=True),
        sa.Column("tags", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("original_file_path", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("estimate_library", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_estimate_library_id"), ["id"], unique=False)

    # ------------------------------------------------------------------
    # estimate_library_tags  (FK → estimate_library, cascade delete)
    # ------------------------------------------------------------------
    op.create_table(
        "estimate_library_tags",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["estimate_library.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "tag", name="uq_entry_tag"),
    )
    with op.batch_alter_table("estimate_library_tags", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_estimate_library_tags_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_estimate_library_tags_entry_id"), ["entry_id"], unique=False)


def downgrade() -> None:
    """Drop the sprint-8 tables in reverse dependency order."""

    with op.batch_alter_table("estimate_library_tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_estimate_library_tags_entry_id"))
        batch_op.drop_index(batch_op.f("ix_estimate_library_tags_id"))
    op.drop_table("estimate_library_tags")

    with op.batch_alter_table("estimate_library", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_estimate_library_id"))
    op.drop_table("estimate_library")

    with op.batch_alter_table("change_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_change_orders_project_id"))
        batch_op.drop_index(batch_op.f("ix_change_orders_id"))
    op.drop_table("change_orders")

    with op.batch_alter_table("bid_comparison_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bid_comparison_items_comparison_id"))
        batch_op.drop_index(batch_op.f("ix_bid_comparison_items_id"))
    op.drop_table("bid_comparison_items")

    with op.batch_alter_table("bid_comparisons", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bid_comparisons_project_id"))
        batch_op.drop_index(batch_op.f("ix_bid_comparisons_id"))
    op.drop_table("bid_comparisons")

    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_id"))
    op.drop_table("audit_logs")

    with op.batch_alter_table("equipment_rates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_equipment_rates_csi_code"))
        batch_op.drop_index(batch_op.f("ix_equipment_rates_division_number"))
        batch_op.drop_index(batch_op.f("ix_equipment_rates_id"))
    op.drop_table("equipment_rates")
