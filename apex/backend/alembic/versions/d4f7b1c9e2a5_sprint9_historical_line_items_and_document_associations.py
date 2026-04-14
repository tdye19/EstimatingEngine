"""sprint9_historical_line_items_and_document_associations

Creates 3 tables introduced in Sprint 9:
  - historical_line_items
  - document_groups
  - document_associations

Revision ID: d4f7b1c9e2a5
Revises: c9f4a8d2e1b3
Create Date: 2026-03-26 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f7b1c9e2a5"
down_revision = "c9f4a8d2e1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # historical_line_items
    # ------------------------------------------------------------------
    op.create_table(
        "historical_line_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Parent links
        sa.Column("library_entry_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        # Provenance
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        # CSI classification
        sa.Column("csi_code", sa.String(length=20), nullable=True),
        sa.Column("csi_division", sa.Integer(), nullable=True),
        sa.Column("csi_division_name", sa.String(length=100), nullable=True),
        # Trade
        sa.Column("trade", sa.String(length=100), nullable=True),
        # Line item content
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=50), nullable=True),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=False),
        # Cost breakdown
        sa.Column("labor_cost", sa.Float(), nullable=True),
        sa.Column("material_cost", sa.Float(), nullable=True),
        sa.Column("equipment_cost", sa.Float(), nullable=True),
        sa.Column("subcontractor_cost", sa.Float(), nullable=True),
        # Labor / productivity
        sa.Column("labor_hours", sa.Float(), nullable=True),
        sa.Column("labor_rate", sa.Float(), nullable=True),
        sa.Column("productivity_rate", sa.Float(), nullable=True),
        sa.Column("productivity_unit", sa.String(length=50), nullable=True),
        sa.Column("is_subcontracted", sa.Boolean(), nullable=False),
        # Denormalized fields for fast querying
        sa.Column("project_type", sa.String(length=100), nullable=True),
        sa.Column("building_type", sa.String(length=100), nullable=True),
        sa.Column("location_state", sa.String(length=2), nullable=True),
        sa.Column("bid_date", sa.Date(), nullable=True),
        sa.Column("bid_result", sa.String(length=50), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # Constraints
        sa.ForeignKeyConstraint(["library_entry_id"], ["estimate_library.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_historical_line_items_library_entry_id"),
        "historical_line_items",
        ["library_entry_id"],
    )
    op.create_index(
        op.f("ix_historical_line_items_csi_code"),
        "historical_line_items",
        ["csi_code"],
    )
    op.create_index(
        op.f("ix_historical_line_items_csi_division"),
        "historical_line_items",
        ["csi_division"],
    )
    op.create_index(
        op.f("ix_historical_line_items_trade"),
        "historical_line_items",
        ["trade"],
    )
    op.create_index(
        op.f("ix_historical_line_items_project_type"),
        "historical_line_items",
        ["project_type"],
    )
    # Composite index defined in __table_args__
    op.create_index(
        "ix_hli_csi_project_state",
        "historical_line_items",
        ["csi_code", "project_type", "location_state"],
    )

    # ------------------------------------------------------------------
    # document_groups
    # ------------------------------------------------------------------
    op.create_table(
        "document_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("library_entry_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["library_entry_id"], ["estimate_library.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_groups_id"),
        "document_groups",
        ["id"],
    )

    # ------------------------------------------------------------------
    # document_associations
    # ------------------------------------------------------------------
    op.create_table(
        "document_associations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("library_entry_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("document_role", sa.String(length=50), nullable=False),
        sa.Column("document_order", sa.Integer(), nullable=True),
        sa.Column("spec_sections_affected", sa.Text(), nullable=True),
        sa.Column("related_csi_divisions", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("parsed", sa.Boolean(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(), nullable=True),
        sa.Column("parse_errors", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["document_groups.id"]),
        sa.ForeignKeyConstraint(["library_entry_id"], ["estimate_library.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_associations_id"),
        "document_associations",
        ["id"],
    )


def downgrade() -> None:
    # Drop in reverse FK order: associations → groups → line_items
    op.drop_index(op.f("ix_document_associations_id"), table_name="document_associations")
    op.drop_table("document_associations")

    op.drop_index(op.f("ix_document_groups_id"), table_name="document_groups")
    op.drop_table("document_groups")

    op.drop_index("ix_hli_csi_project_state", table_name="historical_line_items")
    op.drop_index(op.f("ix_historical_line_items_project_type"), table_name="historical_line_items")
    op.drop_index(op.f("ix_historical_line_items_trade"), table_name="historical_line_items")
    op.drop_index(op.f("ix_historical_line_items_csi_division"), table_name="historical_line_items")
    op.drop_index(op.f("ix_historical_line_items_csi_code"), table_name="historical_line_items")
    op.drop_index(op.f("ix_historical_line_items_library_entry_id"), table_name="historical_line_items")
    op.drop_table("historical_line_items")
