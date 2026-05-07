"""retire runtime ALTER for project context columns

Revision ID: 3a69638ff6bd
Revises: d1e3f5a7b9c2
Create Date: 2026-05-07 17:45:46.832541

Converts the ensure_project_context_columns() runtime ALTER TABLE safety net
into a proper Alembic migration.  upgrade() is idempotent — production DBs
that already have these columns (added at app startup by the retired function)
skip the ADD COLUMN statements silently.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3a69638ff6bd"
down_revision: Union[str, Sequence[str], None] = "d1e3f5a7b9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns formerly added by ensure_project_context_columns():
# (column_name, SQLAlchemy type)
_COLUMNS = [
    ("project_type", sa.String(100)),
    ("market_sector", sa.String(100)),
    ("region", sa.String(100)),
    ("delivery_method", sa.String(50)),
    ("contract_type", sa.String(50)),
    ("complexity_level", sa.String(20)),
    ("schedule_pressure", sa.String(20)),
    ("size_sf", sa.Float()),
    ("scope_types", sa.Text()),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("projects")}

    with op.batch_alter_table("projects", schema=None) as batch_op:
        for col_name, col_type in _COLUMNS:
            if col_name not in existing:
                batch_op.add_column(sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        for col_name, _ in reversed(_COLUMNS):
            batch_op.drop_column(col_name)
