"""Takeoff Item model for quantity takeoff."""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class TakeoffItem(Base, TimestampMixin):
    __tablename__ = "takeoff_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    spec_section_id = Column(Integer, ForeignKey("spec_sections.id"), nullable=True)
    csi_code = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, nullable=False)
    unit_of_measure = Column(String(50), nullable=False)
    drawing_reference = Column(String(255), nullable=True)
    confidence = Column(Float, default=0.8)
    notes = Column(Text, nullable=True)
    is_manual_override = Column(Integer, default=0)

    project = relationship("Project", back_populates="takeoff_items")
    spec_section = relationship("SpecSection", back_populates="takeoff_items")
    labor_estimates = relationship("LaborEstimate", back_populates="takeoff_item")
