"""Bid comparison models — upload competitor bids or historical actuals
and overlay them against the current estimate."""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class BidComparison(Base, TimestampMixin):
    """Header record for one comparison dataset (a competitor bid or historical actual)."""

    __tablename__ = "bid_comparisons"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    name = Column(String(255), nullable=False)           # e.g. "Competitor A", "2023 Awarded Bid"
    source_type = Column(String(50), default="competitor")  # competitor | historical | internal
    bid_date = Column(String(50), nullable=True)
    total_bid_amount = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    # JSON blob of any extra metadata (bidder, project size, etc.)
    metadata_json = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="bid_comparisons")
    items = relationship("BidComparisonItem", back_populates="comparison", cascade="all, delete-orphan")


class BidComparisonItem(Base, TimestampMixin):
    """Line-level data for a comparison — one row per CSI division or cost category."""

    __tablename__ = "bid_comparison_items"

    id = Column(Integer, primary_key=True, index=True)
    comparison_id = Column(Integer, ForeignKey("bid_comparisons.id"), nullable=False, index=True)

    division_number = Column(String(10), nullable=False)
    csi_code = Column(String(20), nullable=True)
    description = Column(String(500), nullable=True)
    amount = Column(Float, default=0.0)
    unit_cost = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    unit_of_measure = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)

    comparison = relationship("BidComparison", back_populates="items")
