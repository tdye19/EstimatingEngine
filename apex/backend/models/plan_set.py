"""Plan set, sheet, and region models for plan ingestion pipeline."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class PlanSet(Base, TimestampMixin):
    """One uploaded PDF drawing set tied to a project."""

    __tablename__ = "plan_sets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_label = Column(String(100), nullable=True)
    upload_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_filename = Column(String(500), nullable=True)
    sheet_count = Column(Integer, default=0)
    status = Column(String(50), default="queued", nullable=False)

    project = relationship("Project", back_populates="plan_sets")
    document = relationship("Document")
    sheets = relationship("PlanSheet", back_populates="plan_set", cascade="all, delete-orphan")


class PlanSheet(Base, TimestampMixin):
    """A single drawing sheet parsed from a PlanSet PDF."""

    __tablename__ = "plan_sheets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_set_id = Column(Integer, ForeignKey("plan_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_number = Column(String(50), nullable=True)
    sheet_name = Column(String(500), nullable=True)
    discipline = Column(String(10), nullable=True)
    page_index = Column(Integer, nullable=False)
    preview_image_url = Column(String(1000), nullable=True)
    width_px = Column(Integer, nullable=True)
    height_px = Column(Integer, nullable=True)
    detected_scale = Column(String(50), nullable=True)
    confirmed_scale = Column(String(50), nullable=True)
    ocr_text_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    plan_set = relationship("PlanSet", back_populates="sheets")
    project = relationship("Project")
    regions = relationship("SheetRegion", back_populates="sheet", cascade="all, delete-orphan")
    takeoff_layers = relationship("TakeoffLayer", back_populates="plan_sheet")


class SheetRegion(Base):
    """A bounding-box region on a plan sheet, optionally labelled."""

    __tablename__ = "sheet_regions"

    id = Column(Integer, primary_key=True, index=True)
    plan_sheet_id = Column(Integer, ForeignKey("plan_sheets.id", ondelete="CASCADE"), nullable=False, index=True)
    region_type = Column(String(50), nullable=True)
    bbox_json = Column(Text, nullable=True)
    label = Column(String(500), nullable=True)
    source_method = Column(String(50), nullable=True)
    review_status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    sheet = relationship("PlanSheet", back_populates="regions")
