"""Gap Report model for scope gap analysis."""

from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class GapReport(Base, TimestampMixin):
    __tablename__ = "gap_reports"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    overall_score = Column(Float, nullable=True)
    total_gaps = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    moderate_count = Column(Integer, default=0)
    watch_count = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="gap_reports")
    items = relationship("GapReportItem", back_populates="gap_report", cascade="all, delete-orphan")


class GapReportItem(Base, TimestampMixin):
    __tablename__ = "gap_report_items"

    id = Column(Integer, primary_key=True, index=True)
    gap_report_id = Column(Integer, ForeignKey("gap_reports.id"), nullable=False, index=True)
    division_number = Column(String(10), nullable=False)
    section_number = Column(String(20), nullable=True)
    title = Column(String(500), nullable=False)
    gap_type = Column(String(50), nullable=False)  # missing, ambiguous, conflicting
    severity = Column(String(20), nullable=False)  # critical, moderate, watch
    description = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    risk_score = Column(Float, nullable=True)

    gap_report = relationship("GapReport", back_populates="items")
