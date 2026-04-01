"""SQLAlchemy model for Estimation History (bid intelligence) data."""

from sqlalchemy import (
    Column, Date, DateTime, Float, Integer, String, Text, func,
)

from apex.backend.db.database import Base


class BIEstimate(Base):
    __tablename__ = "bi_estimates"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Classification
    status = Column(String(30), index=True)            # Awarded / Closed / Open
    region = Column(String(100), index=True)
    market_sector = Column(String(100), index=True)
    month = Column(Integer)

    # Identifiers
    job_number = Column(String(50))
    estimate_number = Column(String(50), unique=True)
    name = Column(String(500), nullable=False)

    # Dates
    bid_date = Column(Date)
    sales_date = Column(Date)

    # Financials
    bid_amount = Column(Float)
    location = Column(String(255))
    trade = Column(String(100))
    estimator = Column(String(100), index=True)
    contract_amount = Column(Float)
    contract_fee = Column(Float)
    contract_hours = Column(Float)
    comments = Column(Text)

    # Volume / area
    conc_vol_cy = Column(Float)
    building_sf = Column(Float)

    # Labor hours
    production_mh = Column(Float)
    installation_mh = Column(Float)
    gc_mh = Column(Float)
    total_mh = Column(Float)

    # Cost / schedule
    fee = Column(Float)
    duration_weeks = Column(Float)
    total_gc_labor = Column(Float)
    staff_labor_hours = Column(Float)
    total_gcs = Column(Float)
    gc_pct = Column(Float)
    customer = Column(String(255))
    final_hours = Column(Float)

    # WIP
    wip_est_cost = Column(Float)
    wip_est_fee = Column(Float)
    wip_est_contract = Column(Float)
    wip_fee_pct = Column(Float)

    # Contract
    contract_status = Column(String(50))
    job_start_date = Column(Date)
    job_end_date = Column(Date)
    weeks = Column(Float)
    equipment_value = Column(Float)

    # Bid outcome
    delivery_method = Column(String(100))
    num_bidders = Column(Integer)
    opportunity_source = Column(String(100))
    go_no_go_score = Column(String(20))
    loss_reason = Column(String(255))
    competitor_who_won = Column(String(255))
    our_rank = Column(Integer)
    bid_delta_pct = Column(Float)

    ingested_at = Column(DateTime, default=func.now())

    # Computed properties — deterministic Python, not stored
    @property
    def cost_per_cy(self) -> float | None:
        if self.bid_amount and self.conc_vol_cy and self.conc_vol_cy > 0:
            return round(self.bid_amount / self.conc_vol_cy, 2)
        return None

    @property
    def cost_per_sf(self) -> float | None:
        if self.bid_amount and self.building_sf and self.building_sf > 0:
            return round(self.bid_amount / self.building_sf, 2)
        return None
