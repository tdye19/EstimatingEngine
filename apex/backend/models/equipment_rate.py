"""Equipment Rate model."""

from sqlalchemy import Column, Float, Integer, String, Text

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class EquipmentRate(Base, TimestampMixin):
    __tablename__ = "equipment_rates"

    id = Column(Integer, primary_key=True, index=True)
    division_number = Column(String(10), nullable=False, index=True)
    csi_code = Column(String(20), nullable=True, index=True)
    equipment_pct = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    region = Column(String(100), nullable=True)
