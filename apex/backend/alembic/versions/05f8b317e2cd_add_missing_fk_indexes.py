"""add_missing_fk_indexes

Revision ID: 05f8b317e2cd
Revises: 2e5ae275617d
Create Date: 2026-04-10 19:14:28.768988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05f8b317e2cd'
down_revision: Union[str, Sequence[str], None] = '2e5ae275617d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index_name, table_name, columns)
INDEXES = [
    # Decision system tables
    ("ix_historical_rate_observations_comparable_project_id", "historical_rate_observations", ["comparable_project_id"]),
    ("ix_historical_rate_observations_canonical_activity_id", "historical_rate_observations", ["canonical_activity_id"]),
    ("ix_historical_rate_observations_division_code", "historical_rate_observations", ["division_code"]),
    ("ix_estimate_runs_project_id", "estimate_runs", ["project_id"]),
    ("ix_estimate_runs_project_id_version", "estimate_runs", ["project_id", "version_number"]),
    ("ix_estimate_runs_run_status", "estimate_runs", ["run_status"]),
    ("ix_scope_items_estimate_run_id", "scope_items", ["estimate_run_id"]),
    ("ix_scope_items_canonical_activity_id", "scope_items", ["canonical_activity_id"]),
    ("ix_scope_items_scope_status", "scope_items", ["scope_status"]),
    ("ix_quantity_items_estimate_run_id", "quantity_items", ["estimate_run_id"]),
    ("ix_quantity_items_scope_item_id", "quantity_items", ["scope_item_id"]),
    ("ix_benchmark_results_estimate_run_id", "benchmark_results", ["estimate_run_id"]),
    ("ix_benchmark_results_scope_item_id", "benchmark_results", ["scope_item_id"]),
    ("ix_decision_estimate_lines_estimate_run_id", "decision_estimate_lines", ["estimate_run_id"]),
    ("ix_decision_estimate_lines_scope_item_id", "decision_estimate_lines", ["scope_item_id"]),
    ("ix_decision_estimate_lines_line_status", "decision_estimate_lines", ["line_status"]),
    ("ix_cost_breakdown_buckets_estimate_run_id", "cost_breakdown_buckets", ["estimate_run_id"]),
    ("ix_decision_risk_items_estimate_run_id", "decision_risk_items", ["estimate_run_id"]),
    ("ix_decision_risk_items_severity", "decision_risk_items", ["severity"]),
    ("ix_escalation_inputs_estimate_run_id", "escalation_inputs", ["estimate_run_id"]),
    ("ix_schedule_scenarios_estimate_run_id", "schedule_scenarios", ["estimate_run_id"]),
    ("ix_estimator_overrides_estimate_run_id", "estimator_overrides", ["estimate_run_id"]),
    ("ix_estimator_overrides_estimate_line_id", "estimator_overrides", ["estimate_line_id"]),
    ("ix_bid_outcomes_project_id", "bid_outcomes", ["project_id"]),
    ("ix_bid_outcomes_estimate_run_id", "bid_outcomes", ["estimate_run_id"]),
    ("ix_field_actuals_comparable_project_id", "field_actuals", ["comparable_project_id"]),
    ("ix_source_references_source_document_id", "source_references", ["source_document_id"]),
    ("ix_activity_aliases_canonical_activity_id", "activity_aliases", ["canonical_activity_id"]),
    ("ix_comparable_projects_type_region", "comparable_projects", ["project_type", "region"]),
    ("ix_comparable_projects_market_sector", "comparable_projects", ["market_sector"]),
    # Core tables
    ("ix_estimates_project_id", "estimates", ["project_id"]),
    ("ix_documents_project_id", "documents", ["project_id"]),
    ("ix_documents_processing_status", "documents", ["processing_status"]),
    ("ix_spec_sections_project_id", "spec_sections", ["project_id"]),
    ("ix_spec_sections_document_id", "spec_sections", ["document_id"]),
    ("ix_takeoff_items_project_id", "takeoff_items", ["project_id"]),
    ("ix_takeoff_items_spec_section_id", "takeoff_items", ["spec_section_id"]),
    ("ix_labor_estimates_project_id", "labor_estimates", ["project_id"]),
    ("ix_labor_estimates_takeoff_item_id", "labor_estimates", ["takeoff_item_id"]),
    ("ix_agent_run_logs_project_id", "agent_run_logs", ["project_id"]),
    ("ix_agent_run_logs_status", "agent_run_logs", ["status"]),
]


def upgrade() -> None:
    """Add indexes on all FK and high-cardinality filter columns."""
    for index_name, table_name, columns in INDEXES:
        try:
            op.create_index(index_name, table_name, columns)
        except Exception:
            # Index may already exist (SQLite) or table/column may differ
            pass


def downgrade() -> None:
    """Drop all indexes added in upgrade (reverse order)."""
    for index_name, table_name, _columns in reversed(INDEXES):
        try:
            op.drop_index(index_name, table_name=table_name)
        except Exception:
            pass
