"""Labor Estimate model."""

from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class LaborEstimate(Base, TimestampMixin):
    __tablename__ = "labor_estimates"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    takeoff_item_id = Column(Integer, ForeignKey("takeoff_items.id"), nullable=False)
    csi_code = Column(String(20), nullable=False)
    work_type = Column(String(100), nullable=True)
    crew_type = Column(String(100), nullable=True)
    productivity_rate = Column(Float, nullable=False)  # units per hour
    productivity_unit = Column(String(50), nullable=True)
    quantity = Column(Float, nullable=False)
    labor_hours = Column(Float, nullable=False)
    crew_size = Column(Integer, default=1)
    crew_days = Column(Float, nullable=True)
    hourly_rate = Column(Float, default=75.0)  # loaded labor rate
    total_labor_cost = Column(Float, nullable=False)

    project = relationship("Project", back_populates="labor_estimates")
    takeoff_item = relationship("TakeoffItem", back_populates="labor_estimates")
