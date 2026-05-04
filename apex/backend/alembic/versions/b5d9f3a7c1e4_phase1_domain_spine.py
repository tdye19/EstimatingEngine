"""phase1_domain_spine

Revision ID: b5d9f3a7c1e4
Revises: c2d7e4a8b1f9
Create Date: 2026-05-01

Phase 1 concrete domain spine:
- projects: add trade_focus, scope_type, client_name, archived_at
- scope_packages: new table
- plan_sets: new table
- plan_sheets: new table
- sheet_regions: new table
- plan_takeoff_layers: new table
- plan_takeoff_items: new table
- agent_run_logs: add provenance columns
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5d9f3a7c1e4"
down_revision: str | Sequence[str] | None = "c2d7e4a8b1f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── projects: new columns ────────────────────────────────────────
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("trade_focus", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("scope_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("client_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))

    # ── scope_packages ───────────────────────────────────────────────
    op.create_table(
        "scope_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("trade_focus", sa.String(length=50), nullable=True),
        sa.Column("csi_division", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("inclusions_json", sa.Text(), nullable=True),
        sa.Column("exclusions_json", sa.Text(), nullable=True),
        sa.Column("assumptions_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("scope_packages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_scope_packages_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_scope_packages_project_id"), ["project_id"], unique=False
        )

    # ── plan_sets ────────────────────────────────────────────────────
    op.create_table(
        "plan_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=True),
        sa.Column("upload_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(length=500), nullable=True),
        sa.Column("sheet_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plan_sets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plan_sets_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_sets_project_id"), ["project_id"], unique=False
        )

    # ── plan_sheets ──────────────────────────────────────────────────
    op.create_table(
        "plan_sheets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("plan_set_id", sa.Integer(), nullable=False),
        sa.Column("sheet_number", sa.String(length=50), nullable=True),
        sa.Column("sheet_name", sa.String(length=500), nullable=True),
        sa.Column("discipline", sa.String(length=10), nullable=True),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("preview_image_url", sa.String(length=1000), nullable=True),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("detected_scale", sa.String(length=50), nullable=True),
        sa.Column("confirmed_scale", sa.String(length=50), nullable=True),
        sa.Column("ocr_text_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["plan_set_id"], ["plan_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plan_sheets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plan_sheets_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_sheets_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_sheets_plan_set_id"), ["plan_set_id"], unique=False
        )

    # ── sheet_regions ────────────────────────────────────────────────
    op.create_table(
        "sheet_regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_sheet_id", sa.Integer(), nullable=False),
        sa.Column("region_type", sa.String(length=50), nullable=True),
        sa.Column("bbox_json", sa.Text(), nullable=True),
        sa.Column("label", sa.String(length=500), nullable=True),
        sa.Column("source_method", sa.String(length=50), nullable=True),
        sa.Column("review_status", sa.String(length=50), nullable=True, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_sheet_id"], ["plan_sheets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sheet_regions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sheet_regions_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_sheet_regions_plan_sheet_id"), ["plan_sheet_id"], unique=False
        )

    # ── plan_takeoff_layers ──────────────────────────────────────────
    op.create_table(
        "plan_takeoff_layers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("plan_sheet_id", sa.Integer(), nullable=True),
        sa.Column("scope_package_id", sa.Integer(), nullable=True),
        sa.Column("trade_focus", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("layer_type", sa.String(length=50), nullable=True),
        sa.Column("visibility_default", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_sheet_id"], ["plan_sheets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scope_package_id"], ["scope_packages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plan_takeoff_layers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_layers_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_layers_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_layers_plan_sheet_id"), ["plan_sheet_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_layers_scope_package_id"), ["scope_package_id"], unique=False
        )

    # ── plan_takeoff_items ───────────────────────────────────────────
    op.create_table(
        "plan_takeoff_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("plan_sheet_id", sa.Integer(), nullable=True),
        sa.Column("takeoff_layer_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_log_id", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(length=50), nullable=True),
        sa.Column("label", sa.String(length=500), nullable=True),
        sa.Column("measurement_type", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("geometry_geojson", sa.Text(), nullable=True),
        sa.Column("bbox_json", sa.Text(), nullable=True),
        sa.Column("source_method", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=50), nullable=False, server_default="unreviewed"),
        sa.Column("assumptions_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["agent_run_log_id"], ["agent_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_sheet_id"], ["plan_sheets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["takeoff_layer_id"], ["plan_takeoff_layers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plan_takeoff_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_items_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_items_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_items_plan_sheet_id"), ["plan_sheet_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_plan_takeoff_items_takeoff_layer_id"), ["takeoff_layer_id"], unique=False
        )

    # ── agent_run_logs: provenance columns ───────────────────────────
    with op.batch_alter_table("agent_run_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_set_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("plan_sheet_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("scope_package_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("input_bundle_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("model_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("model_params_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("confidence_summary", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("output_schema_version", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("parent_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_run_logs_plan_set_id", "plan_sets", ["plan_set_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_agent_run_logs_plan_sheet_id", "plan_sheets", ["plan_sheet_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_agent_run_logs_scope_package_id", "scope_packages", ["scope_package_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_agent_run_logs_parent_run_id", "agent_run_logs", ["parent_run_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_run_logs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_agent_run_logs_parent_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_agent_run_logs_scope_package_id", type_="foreignkey")
        batch_op.drop_constraint("fk_agent_run_logs_plan_sheet_id", type_="foreignkey")
        batch_op.drop_constraint("fk_agent_run_logs_plan_set_id", type_="foreignkey")
        batch_op.drop_column("parent_run_id")
        batch_op.drop_column("output_schema_version")
        batch_op.drop_column("confidence_summary")
        batch_op.drop_column("model_params_json")
        batch_op.drop_column("model_name")
        batch_op.drop_column("input_bundle_hash")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("scope_package_id")
        batch_op.drop_column("plan_sheet_id")
        batch_op.drop_column("plan_set_id")

    with op.batch_alter_table("plan_takeoff_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_items_takeoff_layer_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_items_plan_sheet_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_items_project_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_items_id"))
    op.drop_table("plan_takeoff_items")

    with op.batch_alter_table("plan_takeoff_layers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_layers_scope_package_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_layers_plan_sheet_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_layers_project_id"))
        batch_op.drop_index(batch_op.f("ix_plan_takeoff_layers_id"))
    op.drop_table("plan_takeoff_layers")

    with op.batch_alter_table("sheet_regions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sheet_regions_plan_sheet_id"))
        batch_op.drop_index(batch_op.f("ix_sheet_regions_id"))
    op.drop_table("sheet_regions")

    with op.batch_alter_table("plan_sheets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_sheets_plan_set_id"))
        batch_op.drop_index(batch_op.f("ix_plan_sheets_project_id"))
        batch_op.drop_index(batch_op.f("ix_plan_sheets_id"))
    op.drop_table("plan_sheets")

    with op.batch_alter_table("plan_sets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_sets_project_id"))
        batch_op.drop_index(batch_op.f("ix_plan_sets_id"))
    op.drop_table("plan_sets")

    with op.batch_alter_table("scope_packages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scope_packages_project_id"))
        batch_op.drop_index(batch_op.f("ix_scope_packages_id"))
    op.drop_table("scope_packages")

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("archived_at")
        batch_op.drop_column("client_name")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("trade_focus")
