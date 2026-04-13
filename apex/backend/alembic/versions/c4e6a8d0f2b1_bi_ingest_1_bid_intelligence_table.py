"""BI-INGEST-1: Bid Intelligence estimation history table

Revision ID: c4e6a8d0f2b1
Revises: b3d5f7a9c1e2
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e6a8d0f2b1"
down_revision = "b3d5f7a9c1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bi_estimates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Classification
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("market_sector", sa.String(length=100), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        # Identifiers
        sa.Column("job_number", sa.String(length=50), nullable=True),
        sa.Column("estimate_number", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        # Dates
        sa.Column("bid_date", sa.Date(), nullable=True),
        sa.Column("sales_date", sa.Date(), nullable=True),
        # Financials
        sa.Column("bid_amount", sa.Float(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("trade", sa.String(length=100), nullable=True),
        sa.Column("estimator", sa.String(length=100), nullable=True),
        sa.Column("contract_amount", sa.Float(), nullable=True),
        sa.Column("contract_fee", sa.Float(), nullable=True),
        sa.Column("contract_hours", sa.Float(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        # Volume / area
        sa.Column("conc_vol_cy", sa.Float(), nullable=True),
        sa.Column("building_sf", sa.Float(), nullable=True),
        # Labor hours
        sa.Column("production_mh", sa.Float(), nullable=True),
        sa.Column("installation_mh", sa.Float(), nullable=True),
        sa.Column("gc_mh", sa.Float(), nullable=True),
        sa.Column("total_mh", sa.Float(), nullable=True),
        # Cost / schedule
        sa.Column("fee", sa.Float(), nullable=True),
        sa.Column("duration_weeks", sa.Float(), nullable=True),
        sa.Column("total_gc_labor", sa.Float(), nullable=True),
        sa.Column("staff_labor_hours", sa.Float(), nullable=True),
        sa.Column("total_gcs", sa.Float(), nullable=True),
        sa.Column("gc_pct", sa.Float(), nullable=True),
        sa.Column("customer", sa.String(length=255), nullable=True),
        sa.Column("final_hours", sa.Float(), nullable=True),
        # WIP
        sa.Column("wip_est_cost", sa.Float(), nullable=True),
        sa.Column("wip_est_fee", sa.Float(), nullable=True),
        sa.Column("wip_est_contract", sa.Float(), nullable=True),
        sa.Column("wip_fee_pct", sa.Float(), nullable=True),
        # Contract
        sa.Column("contract_status", sa.String(length=50), nullable=True),
        sa.Column("job_start_date", sa.Date(), nullable=True),
        sa.Column("job_end_date", sa.Date(), nullable=True),
        sa.Column("weeks", sa.Float(), nullable=True),
        sa.Column("equipment_value", sa.Float(), nullable=True),
        # Bid outcome
        sa.Column("delivery_method", sa.String(length=100), nullable=True),
        sa.Column("num_bidders", sa.Integer(), nullable=True),
        sa.Column("opportunity_source", sa.String(length=100), nullable=True),
        sa.Column("go_no_go_score", sa.String(length=20), nullable=True),
        sa.Column("loss_reason", sa.String(length=255), nullable=True),
        sa.Column("competitor_who_won", sa.String(length=255), nullable=True),
        sa.Column("our_rank", sa.Integer(), nullable=True),
        sa.Column("bid_delta_pct", sa.Float(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estimate_number"),
    )

    op.create_index("ix_bi_estimates_status", "bi_estimates", ["status"])
    op.create_index("ix_bi_estimates_region", "bi_estimates", ["region"])
    op.create_index("ix_bi_estimates_market_sector", "bi_estimates", ["market_sector"])
    op.create_index("ix_bi_estimates_estimator", "bi_estimates", ["estimator"])


def downgrade() -> None:
    op.drop_index("ix_bi_estimates_estimator", table_name="bi_estimates")
    op.drop_index("ix_bi_estimates_market_sector", table_name="bi_estimates")
    op.drop_index("ix_bi_estimates_region", table_name="bi_estimates")
    op.drop_index("ix_bi_estimates_status", table_name="bi_estimates")
    op.drop_table("bi_estimates")
