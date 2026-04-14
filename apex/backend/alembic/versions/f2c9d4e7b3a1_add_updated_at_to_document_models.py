"""add_updated_at_to_document_models

Add nullable updated_at columns to document_groups and document_associations.

Revision ID: f2c9d4e7b3a1
Revises: d4f7b1c9e2a5
Create Date: 2026-03-28 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2c9d4e7b3a1"
down_revision = "d4f7b1c9e2a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_groups", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("document_associations", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_associations", "updated_at")
    op.drop_column("document_groups", "updated_at")
