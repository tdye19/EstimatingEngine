"""SQLAlchemy models for Productivity Brain data."""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class PBProject(Base):
    __tablename__ = "pb_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    source_file = Column(String(500), nullable=False)
    file_hash = Column(String(32), nullable=False, unique=True)
    format_type = Column(String(30))  # '26col_civil', '21col_estimate', 'averaged_rates'
    project_count = Column(Integer, default=1)
    total_line_items = Column(Integer, default=0)
    ingested_at = Column(DateTime, default=func.now())

    line_items = relationship(
        "PBLineItem",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class PBLineItem(Base):
    __tablename__ = "pb_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("pb_projects.id"), nullable=False, index=True)
    wbs_area = Column(String(255))
    activity = Column(String(500), nullable=False, index=True)
    quantity = Column(Float)
    unit = Column(String(50))
    crew_trade = Column(String(200))
    production_rate = Column(Float)  # Unit/MH
    labor_hours = Column(Float)
    labor_cost_per_unit = Column(Float)
    material_cost_per_unit = Column(Float)
    equipment_cost = Column(Float)
    sub_cost = Column(Float)
    total_cost = Column(Float)
    csi_code = Column(String(20), index=True)
    source_project = Column(String(255))  # For averaged files: which sub-project

    project = relationship("PBProject", back_populates="line_items")

    __table_args__ = (Index("ix_pb_li_activity_unit", "activity", "unit"),)
