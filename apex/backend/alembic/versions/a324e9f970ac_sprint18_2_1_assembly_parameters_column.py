"""sprint18_2_1_assembly_parameters_column

Revision ID: a324e9f970ac
Revises: 8ae8a8fdc4c6
Create Date: 2026-04-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a324e9f970ac"
down_revision: str | Sequence[str] | None = "8ae8a8fdc4c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("spec_sections", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assembly_parameters_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("spec_sections", schema=None) as batch_op:
        batch_op.drop_column("assembly_parameters_json")
