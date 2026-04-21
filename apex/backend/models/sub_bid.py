"""Subcontractor bid comparison models."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class SubBidPackage(Base, TimestampMixin):
    __tablename__ = "sub_bid_packages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    trade = Column(String(200), nullable=False)
    csi_division = Column(String(10), nullable=True)
    base_scope_items = Column(JSON, nullable=True)

    bids = relationship("SubBid", back_populates="package", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="sub_bid_packages")


class SubBid(Base, TimestampMixin):
    __tablename__ = "sub_bids"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("sub_bid_packages.id"), nullable=False, index=True)
    subcontractor_name = Column(String(300), nullable=False)
    total_bid_amount = Column(Float, nullable=True)
    analysis_json = Column(JSON, nullable=True)
    normalized = Column(Boolean, default=False)

    package = relationship("SubBidPackage", back_populates="bids")
    line_items = relationship("SubBidLineItem", back_populates="bid", cascade="all, delete-orphan")


class SubBidLineItem(Base, TimestampMixin):
    __tablename__ = "sub_bid_line_items"

    id = Column(Integer, primary_key=True, index=True)
    bid_id = Column(Integer, ForeignKey("sub_bids.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    quantity = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    unit_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    csi_code = Column(String(20), nullable=True)
    matched_scope_item = Column(String(300), nullable=True)
    match_confidence = Column(Float, nullable=True)
    is_outlier = Column(Boolean, default=False)
    is_suspiciously_low = Column(Boolean, default=False)

    bid = relationship("SubBid", back_populates="line_items")
