"""sprint18_4_2_proposal_form_json

Revision ID: c2d7e4a8b1f9
Revises: a3b8c1d5e9f2
Create Date: 2026-04-24

Adds nullable proposal_form_json TEXT column to intelligence_reports.

Sprint 18.4.2: Agent 6 now emits a ProposalForm JSON section (mirroring
the CCI Trade Contract Proposal Form structure) alongside the existing
*_json sections. The column is nullable — Agent 6 omits the proposal
when there are no WorkCategories or no TakeoffItemV2 rows for the project.

Down-revision is HF-22's a3b8c1d5e9f2 (gap_report_items.division_number
nullable). HF-24 added no migration; this is the next head.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d7e4a8b1f9"
down_revision: str | Sequence[str] | None = "a3b8c1d5e9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("intelligence_reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("proposal_form_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("intelligence_reports", schema=None) as batch_op:
        batch_op.drop_column("proposal_form_json")
