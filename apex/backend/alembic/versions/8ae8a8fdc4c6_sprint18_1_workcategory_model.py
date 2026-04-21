"""sprint18_1_workcategory_model

Revision ID: 8ae8a8fdc4c6
Revises: 230fce14e46f
Create Date: 2026-04-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8ae8a8fdc4c6"
down_revision: str | Sequence[str] | None = "230fce14e46f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("wc_number", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("work_included_items", sa.JSON(), nullable=False),
        sa.Column("work_category_notes", sa.Text(), nullable=True),
        sa.Column("specific_notes", sa.JSON(), nullable=False),
        sa.Column("related_work_by_others", sa.JSON(), nullable=False),
        sa.Column("add_alternates", sa.JSON(), nullable=False),
        sa.Column("allowances", sa.JSON(), nullable=False),
        sa.Column("unit_prices", sa.JSON(), nullable=False),
        sa.Column("referenced_spec_sections", sa.JSON(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("source_page_start", sa.Integer(), nullable=True),
        sa.Column("source_page_end", sa.Integer(), nullable=True),
        sa.Column("parse_method", sa.String(length=32), nullable=True),
        sa.Column("parse_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "wc_number", name="uq_workcategory_project_wcnumber"
        ),
    )
    with op.batch_alter_table("work_categories", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_work_categories_project_id"),
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_workcategory_project_wcnumber",
            ["project_id", "wc_number"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("work_categories", schema=None) as batch_op:
        batch_op.drop_index("ix_workcategory_project_wcnumber")
        batch_op.drop_index(batch_op.f("ix_work_categories_project_id"))

    op.drop_constraint(
        "uq_workcategory_project_wcnumber",
        "work_categories",
        type_="unique",
    )
    op.drop_table("work_categories")
