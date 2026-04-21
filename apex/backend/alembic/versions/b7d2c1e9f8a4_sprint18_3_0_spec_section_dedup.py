"""sprint18_3_0_spec_section_dedup

Revision ID: b7d2c1e9f8a4
Revises: a324e9f970ac
Create Date: 2026-04-21

HF-21 — Cross-document SpecSection dedup. Cleans up existing duplicates
(longest work_description wins; lowest id tiebreaker) before adding the
unique constraint, so the constraint install cannot fail on populated DBs.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b7d2c1e9f8a4"
down_revision: str | Sequence[str] | None = "a324e9f970ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Window function picks the winner per (project_id, section_number) group:
# 1. non-null work_description ranks before NULL
# 2. longest work_description wins
# 3. lowest id is the final tiebreaker
# rn=1 row is kept; all others are deleted.
_DEDUP_SQL = """
DELETE FROM spec_sections
WHERE id NOT IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY project_id, section_number
                   ORDER BY
                       CASE WHEN work_description IS NULL THEN 1 ELSE 0 END,
                       LENGTH(COALESCE(work_description, '')) DESC,
                       id ASC
               ) AS rn
        FROM spec_sections
    ) ranked
    WHERE rn = 1
)
"""


def upgrade() -> None:
    # Step 1 — data cleanup. Must run BEFORE the constraint is added; otherwise
    # any project with duplicate (project_id, section_number) rows fails the
    # ALTER with IntegrityError.
    op.execute(_DEDUP_SQL)

    # Step 2 — install the unique constraint via batch_alter_table (SQLite path).
    with op.batch_alter_table("spec_sections", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_spec_section_project_csi",
            ["project_id", "section_number"],
        )


def downgrade() -> None:
    # Only the constraint is reversible; the deletions are not restored.
    with op.batch_alter_table("spec_sections", schema=None) as batch_op:
        batch_op.drop_constraint("uq_spec_section_project_csi", type_="unique")
