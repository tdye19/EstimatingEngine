"""sprint16_intelligence_report: Create intelligence_reports table

Revision ID: a8c0d2e4f6b7
Revises: f7b9d1e3a5c6
Create Date: 2026-04-02
"""

import sqlalchemy as sa
from alembic import op

revision = "a8c0d2e4f6b7"
down_revision = "f7b9d1e3a5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        # Takeoff summary
        sa.Column("takeoff_item_count", sa.Integer(), server_default="0"),
        sa.Column("takeoff_total_labor", sa.Float()),
        sa.Column("takeoff_total_material", sa.Float()),
        # Intelligence summaries (JSON)
        sa.Column("rate_intelligence_json", sa.Text()),
        sa.Column("field_calibration_json", sa.Text()),
        sa.Column("scope_risk_json", sa.Text()),
        sa.Column("comparable_projects_json", sa.Text()),
        # Spec intel
        sa.Column("spec_sections_parsed", sa.Integer(), server_default="0"),
        sa.Column("material_specs_extracted", sa.Integer(), server_default="0"),
        # Overall assessment
        sa.Column("overall_risk_level", sa.String(), server_default="unknown"),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("executive_narrative", sa.Text()),
        sa.Column("narrative_method", sa.String(), server_default="template"),
        # PB coverage
        sa.Column("pb_projects_loaded", sa.Integer(), server_default="0"),
        sa.Column("pb_activities_available", sa.Integer(), server_default="0"),
        # Tokens
        sa.Column("narrative_tokens_used", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_ir_project_id", "intelligence_reports", ["project_id"])
    op.create_index("ix_ir_project_version", "intelligence_reports", ["project_id", "version"])


def downgrade() -> None:
    op.drop_index("ix_ir_project_version", table_name="intelligence_reports")
    op.drop_index("ix_ir_project_id", table_name="intelligence_reports")
    op.drop_table("intelligence_reports")
