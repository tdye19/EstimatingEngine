"""add_export_profiles

Revision ID: c8e2f1a4b7d0
Revises: b5d9f3a7c1e4
Create Date: 2026-05-04

Adds export_profiles table for per-organization export branding and defaults.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2f1a4b7d0"
down_revision: str | Sequence[str] | None = "b5d9f3a7c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column("header_text", sa.String(length=500), nullable=True),
        sa.Column("default_sections_json", sa.Text(), nullable=True),
        sa.Column("include_assumptions", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("include_exclusions", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("group_by", sa.String(length=50), nullable=False, server_default="trade"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index("ix_export_profiles_id", "export_profiles", ["id"])
    op.create_index("ix_export_profiles_organization_id", "export_profiles", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_export_profiles_organization_id", table_name="export_profiles")
    op.drop_index("ix_export_profiles_id", table_name="export_profiles")
    op.drop_table("export_profiles")
