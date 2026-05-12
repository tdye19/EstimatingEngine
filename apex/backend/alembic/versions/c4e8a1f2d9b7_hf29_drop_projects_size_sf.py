"""HF-29 — drop zombie size_sf column from projects

Revision ID: c4e8a1f2d9b7
Revises: b3d7f2a9c1e5
Create Date: 2026-05-12

Spec HF-29: size_sf was added to projects by migration 3a69638ff6bd as part
of the decision-system context columns, but was never added to the Project ORM
model.  The canonical project size field is Project.square_footage.  Code that
accessed project.size_sf via getattr always returned None.

This migration drops the zombie column.  ComparableProject.size_sf (on the
comparable_projects table) is a different column and is NOT touched here.

upgrade() and downgrade() are idempotent — Sprint 19B pattern.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1f2d9b7"
down_revision: Union[str, Sequence[str], None] = "b3d7f2a9c1e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("projects")}

    if "size_sf" in existing:
        with op.batch_alter_table("projects", schema=None) as batch_op:
            batch_op.drop_column("size_sf")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("projects")}

    if "size_sf" not in existing:
        with op.batch_alter_table("projects", schema=None) as batch_op:
            batch_op.add_column(sa.Column("size_sf", sa.Float(), nullable=True))
