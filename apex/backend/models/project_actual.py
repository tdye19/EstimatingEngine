"""Project Actual model for field production data."""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class ProjectActual(Base, TimestampMixin):
    __tablename__ = "project_actuals"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    csi_code = Column(String(20), nullable=False)
    description = Column(Text, nullable=True)
    estimated_quantity = Column(Float, nullable=True)
    actual_quantity = Column(Float, nullable=True)
    estimated_labor_hours = Column(Float, nullable=True)
    actual_labor_hours = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)
    variance_hours = Column(Float, nullable=True)
    variance_cost = Column(Float, nullable=True)
    variance_pct = Column(Float, nullable=True)
    crew_type = Column(String(100), nullable=True)
    work_type = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    project = relationship("Project", back_populates="project_actuals")
