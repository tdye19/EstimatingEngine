"""sprint12_4_shadow_mode

Add shadow mode fields to projects table: mode, manual_estimate_total,
manual_estimate_notes.

Revision ID: a1b2c3d4e5f6
Revises: e5a2b7d3f1c8
Create Date: 2026-03-31 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "e4ae649389b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("mode", sa.String(20), nullable=False, server_default="shadow"))
        batch_op.add_column(sa.Column("manual_estimate_total", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("manual_estimate_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("manual_estimate_notes")
        batch_op.drop_column("manual_estimate_total")
        batch_op.drop_column("mode")
