"""add_sub_bid_tables

Revision ID: 230fce14e46f
Revises: 05f8b317e2cd
Create Date: 2026-04-10 19:40:38.202404

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "230fce14e46f"
down_revision: str | Sequence[str] | None = "05f8b317e2cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sub_bid_packages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("trade", sa.String(200), nullable=False),
        sa.Column("csi_division", sa.String(10), nullable=True),
        sa.Column("base_scope_items", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("is_deleted", sa.Boolean, default=False, nullable=False),
    )

    op.create_table(
        "sub_bids",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("package_id", sa.Integer, sa.ForeignKey("sub_bid_packages.id"), nullable=False, index=True),
        sa.Column("subcontractor_name", sa.String(300), nullable=False),
        sa.Column("total_bid_amount", sa.Float, nullable=True),
        sa.Column("analysis_json", sa.JSON, nullable=True),
        sa.Column("normalized", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("is_deleted", sa.Boolean, default=False, nullable=False),
    )

    op.create_table(
        "sub_bid_line_items",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("bid_id", sa.Integer, sa.ForeignKey("sub_bids.id"), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("unit_cost", sa.Float, nullable=True),
        sa.Column("total_cost", sa.Float, nullable=True),
        sa.Column("csi_code", sa.String(20), nullable=True),
        sa.Column("matched_scope_item", sa.String(300), nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("is_outlier", sa.Boolean, default=False),
        sa.Column("is_suspiciously_low", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("is_deleted", sa.Boolean, default=False, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sub_bid_line_items")
    op.drop_table("sub_bids")
    op.drop_table("sub_bid_packages")
