"""TakeoffItemV2 — rate-intelligence takeoff items (Agent 4 v2)."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class TakeoffItemV2(Base):
    __tablename__ = "takeoff_items_v2"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    row_number = Column(Integer, nullable=False)
    wbs_area = Column(String)
    activity = Column(String, nullable=False)
    quantity = Column(Float)
    unit = Column(String)
    crew = Column(String)
    production_rate = Column(Float)
    # HF-29: estimator's file rate (preferred) with PB historical avg as fallback.
    labor_cost_per_unit = Column(Float)
    material_cost_per_unit = Column(Float)
    csi_code = Column(String)

    # Rate recommendation fields (populated by Agent 4)
    historical_avg_rate = Column(Float)
    historical_min_rate = Column(Float)
    historical_max_rate = Column(Float)
    sample_count = Column(Integer, default=0)
    confidence = Column(String, default="none")
    delta_pct = Column(Float)
    flag = Column(String, default="NO_DATA")
    matching_projects = Column(Text)  # JSON array of project names

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    project = relationship("Project", back_populates="takeoff_items_v2")

    __table_args__ = (Index("ix_takeoff_v2_project_activity", "project_id", "activity"),)
