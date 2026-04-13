"""Productivity History model."""

from sqlalchemy import Column, Float, Integer, String, Text

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class ProductivityHistory(Base, TimestampMixin):
    __tablename__ = "productivity_history"

    id = Column(Integer, primary_key=True, index=True)
    csi_code = Column(String(20), nullable=False, index=True)
    work_type = Column(String(100), nullable=False)
    crew_type = Column(String(100), nullable=True)
    productivity_rate = Column(Float, nullable=False)  # unit per hour
    unit_of_measure = Column(String(50), nullable=False)
    source_project = Column(String(255), nullable=True)
    source_project_id = Column(Integer, nullable=True)
    is_actual = Column(Integer, default=0)  # 0=estimated, 1=actual
    confidence_score = Column(Float, default=0.5)
    sample_count = Column(Integer, default=1)
    region = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
