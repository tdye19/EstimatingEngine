"""19C.2 — add bytes_received to upload_sessions

Revision ID: b3d7f2a9c1e5
Revises: a9f3c5b1d7e2
Create Date: 2026-05-12

Spec 19C.2: track cumulative uploaded bytes per session so the chunk
endpoint can reject uploads that exceed the client-declared total_size.
Nullable with default 0; existing sessions treat all prior bytes as 0.

upgrade() is idempotent — Sprint 19B pattern.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d7f2a9c1e5"
down_revision: Union[str, Sequence[str], None] = "a9f3c5b1d7e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("upload_sessions")}

    with op.batch_alter_table("upload_sessions", schema=None) as batch_op:
        if "bytes_received" not in existing:
            batch_op.add_column(
                sa.Column("bytes_received", sa.Integer(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    with op.batch_alter_table("upload_sessions", schema=None) as batch_op:
        batch_op.drop_column("bytes_received")
