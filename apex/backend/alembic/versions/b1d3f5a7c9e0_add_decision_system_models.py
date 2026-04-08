"""add decision system models

Revision ID: b1d3f5a7c9e0
Revises: a8c0d2e4f6b7
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "b1d3f5a7c9e0"
down_revision = "a8c0d2e4f6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # comparable_projects
    # ------------------------------------------------------------------
    op.create_table(
        "comparable_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client", sa.String(255), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("completed_date", sa.DateTime, nullable=True),
        sa.Column("final_contract_value", sa.Float, nullable=True),
        sa.Column("project_type", sa.String(100), nullable=True),
        sa.Column("market_sector", sa.String(100), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("delivery_method", sa.String(50), nullable=True),
        sa.Column("contract_type", sa.String(50), nullable=True),
        sa.Column("size_sf", sa.Float, nullable=True),
        sa.Column("scope_types", sa.Text, nullable=True),
        sa.Column("complexity_level", sa.String(20), nullable=True),
        sa.Column("data_quality_score", sa.Float, nullable=True, server_default="0.5"),
        sa.Column("source_system", sa.String(100), nullable=True),
    )

    # ------------------------------------------------------------------
    # canonical_activities
    # ------------------------------------------------------------------
    op.create_table(
        "canonical_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("division_code", sa.String(20), nullable=False),
        sa.Column("division_name", sa.String(255), nullable=True),
        sa.Column("expected_unit", sa.String(20), nullable=True),
        sa.Column("scope_family", sa.String(100), nullable=True),
        sa.Column("typical_cost_bucket", sa.String(50), nullable=True),
        sa.Column("common_dependencies", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # ------------------------------------------------------------------
    # activity_aliases
    # ------------------------------------------------------------------
    op.create_table(
        "activity_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_activity_id", sa.String(36),
                  sa.ForeignKey("canonical_activities.id"), nullable=False),
        sa.Column("alias", sa.String(500), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="1.0"),
    )

    # ------------------------------------------------------------------
    # historical_rate_observations
    # ------------------------------------------------------------------
    op.create_table(
        "historical_rate_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("comparable_project_id", sa.String(36),
                  sa.ForeignKey("comparable_projects.id"), nullable=False),
        sa.Column("canonical_activity_id", sa.String(36),
                  sa.ForeignKey("canonical_activities.id"), nullable=True),
        sa.Column("raw_activity_name", sa.String(500), nullable=False),
        sa.Column("division_code", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_cost", sa.Float, nullable=True),
        sa.Column("total_cost", sa.Float, nullable=True),
        sa.Column("labor_cost", sa.Float, nullable=True),
        sa.Column("material_cost", sa.Float, nullable=True),
        sa.Column("equipment_cost", sa.Float, nullable=True),
        sa.Column("sub_cost", sa.Float, nullable=True),
        sa.Column("production_rate", sa.Float, nullable=True),
        sa.Column("production_rate_unit", sa.String(50), nullable=True),
        sa.Column("data_quality_score", sa.Float, nullable=True, server_default="0.5"),
        sa.Column("source_row", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    # ------------------------------------------------------------------
    # decision_estimate_lines
    # ------------------------------------------------------------------
    op.create_table(
        "decision_estimate_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_run_id", sa.String(100), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("division_code", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("recommended_unit_cost", sa.Float, nullable=True),
        sa.Column("recommended_total_cost", sa.Float, nullable=True),
        sa.Column("pricing_basis", sa.String(50), nullable=True, server_default="no_data"),
        sa.Column("benchmark_sample_size", sa.Integer, nullable=True),
        sa.Column("benchmark_p25", sa.Float, nullable=True),
        sa.Column("benchmark_p50", sa.Float, nullable=True),
        sa.Column("benchmark_p75", sa.Float, nullable=True),
        sa.Column("benchmark_p90", sa.Float, nullable=True),
        sa.Column("benchmark_mean", sa.Float, nullable=True),
        sa.Column("benchmark_std_dev", sa.Float, nullable=True),
        sa.Column("benchmark_context_similarity", sa.Float, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("confidence_level", sa.String(20), nullable=True, server_default="very_low"),
        sa.Column("missing_quantity", sa.Boolean, nullable=True, server_default="0"),
        sa.Column("needs_review", sa.Boolean, nullable=True, server_default="1"),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    # ------------------------------------------------------------------
    # estimator_overrides
    # ------------------------------------------------------------------
    op.create_table(
        "estimator_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("estimate_line_id", sa.String(36),
                  sa.ForeignKey("decision_estimate_lines.id"), nullable=False),
        sa.Column("original_value", sa.Float, nullable=False),
        sa.Column("overridden_value", sa.Float, nullable=False),
        sa.Column("override_type", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(50), nullable=True),
        sa.Column("reason_text", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    # ------------------------------------------------------------------
    # cost_breakdown_buckets
    # ------------------------------------------------------------------
    op.create_table(
        "cost_breakdown_buckets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("bucket_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Float, nullable=True, server_default="0.0"),
        sa.Column("method", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # ------------------------------------------------------------------
    # decision_risk_items
    # ------------------------------------------------------------------
    op.create_table(
        "decision_risk_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("probability", sa.Float, nullable=True, server_default="0.5"),
        sa.Column("impact_cost", sa.Float, nullable=True, server_default="0.0"),
        sa.Column("impact_time_days", sa.Integer, nullable=True),
        sa.Column("severity", sa.String(20), nullable=True, server_default="medium"),
        sa.Column("mitigation", sa.Text, nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
    )

    # ------------------------------------------------------------------
    # escalation_inputs
    # ------------------------------------------------------------------
    op.create_table(
        "escalation_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("escalation_rate", sa.Float, nullable=True, server_default="0.03"),
        sa.Column("escalation_amount", sa.Float, nullable=True),
    )

    # ------------------------------------------------------------------
    # bid_outcomes
    # ------------------------------------------------------------------
    op.create_table(
        "bid_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("final_bid_submitted", sa.Float, nullable=True),
        sa.Column("winning_bid_value", sa.Float, nullable=True),
        sa.Column("delta_to_winner", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=True),
    )

    # ------------------------------------------------------------------
    # field_actuals
    # ------------------------------------------------------------------
    op.create_table(
        "field_actuals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("comparable_project_id", sa.String(36),
                  sa.ForeignKey("comparable_projects.id"), nullable=False),
        sa.Column("canonical_activity_name", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("actual_unit_cost", sa.Float, nullable=True),
        sa.Column("actual_total_cost", sa.Float, nullable=True),
        sa.Column("actual_production_rate", sa.Float, nullable=True),
        sa.Column("variance_to_estimate", sa.Float, nullable=True),
        sa.Column("cost_code", sa.String(50), nullable=True),
        sa.Column("data_quality_score", sa.Float, nullable=True, server_default="0.5"),
    )

    # ------------------------------------------------------------------
    # Add context columns to existing projects table (batch for SQLite)
    # ------------------------------------------------------------------
    new_project_cols = [
        ("market_sector",    sa.String(100)),
        ("region",           sa.String(100)),
        ("delivery_method",  sa.String(50)),
        ("contract_type",    sa.String(50)),
        ("complexity_level", sa.String(20)),
        ("schedule_pressure",sa.String(20)),
        ("size_sf",          sa.Float),
        ("scope_types",      sa.Text),
    ]
    with op.batch_alter_table("projects") as batch_op:
        for col_name, col_type in new_project_cols:
            try:
                batch_op.add_column(sa.Column(col_name, col_type, nullable=True))
            except Exception:
                pass  # column already exists


def downgrade() -> None:
    op.drop_table("field_actuals")
    op.drop_table("bid_outcomes")
    op.drop_table("escalation_inputs")
    op.drop_table("decision_risk_items")
    op.drop_table("cost_breakdown_buckets")
    op.drop_table("estimator_overrides")
    op.drop_table("decision_estimate_lines")
    op.drop_table("historical_rate_observations")
    op.drop_table("activity_aliases")
    op.drop_table("canonical_activities")
    op.drop_table("comparable_projects")

    remove_cols = [
        "market_sector", "region", "delivery_method", "contract_type",
        "complexity_level", "schedule_pressure", "size_sf", "scope_types",
    ]
    with op.batch_alter_table("projects") as batch_op:
        for col_name in remove_cols:
            try:
                batch_op.drop_column(col_name)
            except Exception:
                pass
