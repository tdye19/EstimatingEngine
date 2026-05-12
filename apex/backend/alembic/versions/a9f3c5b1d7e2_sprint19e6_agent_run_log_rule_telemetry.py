"""sprint19e6 — add rule_telemetry column to agent_run_logs

Revision ID: a9f3c5b1d7e2
Revises: 3a69638ff6bd
Create Date: 2026-05-12

Spec 19E.6.4: persist ValidationResult telemetry from Agent 3 onto each
AgentRunLog row so Tucker can query citation quality without re-running the
pipeline.  Nullable JSON column; existing rows default to NULL.

upgrade() is idempotent — if the column was already added manually it
is skipped silently (Sprint 19B pattern).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9f3c5b1d7e2"
down_revision: Union[str, Sequence[str], None] = "3a69638ff6bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("agent_run_logs")}

    with op.batch_alter_table("agent_run_logs", schema=None) as batch_op:
        if "rule_telemetry" not in existing:
            batch_op.add_column(sa.Column("rule_telemetry", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_run_logs", schema=None) as batch_op:
        batch_op.drop_column("rule_telemetry")
