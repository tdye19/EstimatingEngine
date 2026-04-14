"""AGENT2-V2: Add spec parameter columns to spec_sections

Revision ID: d5f7b9a1c3e4
Revises: c4e6a8d0f2b1
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f7b9a1c3e4"
down_revision = "c4e6a8d0f2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("spec_sections") as batch_op:
        batch_op.add_column(sa.Column("in_scope", sa.Boolean(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("material_specs", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("quality_requirements", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("referenced_standards", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("spec_sections") as batch_op:
        batch_op.drop_column("referenced_standards")
        batch_op.drop_column("quality_requirements")
        batch_op.drop_column("material_specs")
        batch_op.drop_column("in_scope")
