"""Estimate and EstimateLineItem models."""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class Estimate(Base, TimestampMixin):
    __tablename__ = "estimates"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    version = Column(Integer, default=1)
    status = Column(String(50), default="draft")  # draft, reviewed, submitted, awarded
    total_direct_cost = Column(Float, default=0.0)
    total_labor_cost = Column(Float, default=0.0)
    total_material_cost = Column(Float, default=0.0)
    total_subcontractor_cost = Column(Float, default=0.0)
    gc_markup_pct = Column(Float, default=0.0)
    gc_markup_amount = Column(Float, default=0.0)
    overhead_pct = Column(Float, default=10.0)
    overhead_amount = Column(Float, default=0.0)
    profit_pct = Column(Float, default=8.0)
    profit_amount = Column(Float, default=0.0)
    contingency_pct = Column(Float, default=5.0)
    contingency_amount = Column(Float, default=0.0)
    total_bid_amount = Column(Float, default=0.0)
    exclusions = Column(JSON, nullable=True)
    assumptions = Column(JSON, nullable=True)
    alternates = Column(JSON, nullable=True)
    bid_bond_required = Column(Integer, default=0)
    summary_json = Column(JSON, nullable=True)
    executive_summary = Column(Text, nullable=True)
    variance_report_json = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="estimates")
    line_items = relationship("EstimateLineItem", back_populates="estimate", cascade="all, delete-orphan")
    token_usage_records = relationship("TokenUsage", back_populates="estimate", foreign_keys="TokenUsage.estimate_id")


class EstimateLineItem(Base, TimestampMixin):
    __tablename__ = "estimate_line_items"

    id = Column(Integer, primary_key=True, index=True)
    estimate_id = Column(Integer, ForeignKey("estimates.id"), nullable=False, index=True)
    division_number = Column(String(10), nullable=False)
    csi_code = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, nullable=False)
    unit_of_measure = Column(String(50), nullable=False)
    labor_cost = Column(Float, default=0.0)
    material_cost = Column(Float, default=0.0)
    equipment_cost = Column(Float, default=0.0)
    subcontractor_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)

    estimate = relationship("Estimate", back_populates="line_items")
