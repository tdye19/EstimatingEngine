"""HistoricalLineItem model — normalized line-item storage across all historical bids."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class HistoricalLineItem(Base):
    """A single normalized line item from a historical bid, linked to an EstimateLibraryEntry."""

    __tablename__ = "historical_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Parent links
    library_entry_id = Column(
        Integer,
        ForeignKey("estimate_library.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    # Provenance
    source_file = Column(String(500), nullable=True)
    source_type = Column(String(50), nullable=False)  # "winest", "pipeline_agent4", "pipeline_agent5", "manual"

    # CSI classification
    csi_code = Column(String(20), nullable=True, index=True)
    csi_division = Column(Integer, nullable=True, index=True)
    csi_division_name = Column(String(100), nullable=True)

    # Trade
    trade = Column(String(100), nullable=True, index=True)

    # Line item content
    description = Column(Text, nullable=False)
    quantity = Column(Float, nullable=True)
    unit_of_measure = Column(String(50), nullable=True)
    unit_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=False)

    # Cost breakdown
    labor_cost = Column(Float, nullable=True)
    material_cost = Column(Float, nullable=True)
    equipment_cost = Column(Float, nullable=True)
    subcontractor_cost = Column(Float, nullable=True)

    # Labor / productivity
    labor_hours = Column(Float, nullable=True)
    labor_rate = Column(Float, nullable=True)
    productivity_rate = Column(Float, nullable=True)
    productivity_unit = Column(String(50), nullable=True)

    is_subcontracted = Column(Boolean, default=False, nullable=False)

    # Denormalized fields for fast querying
    project_type = Column(String(100), nullable=True, index=True)
    building_type = Column(String(100), nullable=True)
    location_state = Column(String(2), nullable=True)
    bid_date = Column(Date, nullable=True)
    bid_result = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    library_entry = relationship("EstimateLibraryEntry", back_populates="line_items")
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (Index("ix_hli_csi_project_state", "csi_code", "project_type", "location_state"),)
