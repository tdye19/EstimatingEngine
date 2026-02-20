"""Spec Section model for parsed CSI MasterFormat divisions."""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class SpecSection(Base, TimestampMixin):
    __tablename__ = "spec_sections"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    division_number = Column(String(10), nullable=False)  # e.g., "03", "09"
    section_number = Column(String(20), nullable=False)  # e.g., "03 30 00"
    title = Column(String(500), nullable=False)
    work_description = Column(Text, nullable=True)
    materials_referenced = Column(JSON, nullable=True)  # list of materials
    execution_requirements = Column(Text, nullable=True)
    submittal_requirements = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)  # extracted keyword tags
    raw_text = Column(Text, nullable=True)

    project = relationship("Project", back_populates="spec_sections")
    document = relationship("Document", back_populates="spec_sections")
    takeoff_items = relationship("TakeoffItem", back_populates="spec_section")
