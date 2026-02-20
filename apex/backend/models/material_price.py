"""Material Price model."""

from sqlalchemy import Column, Integer, String, Float, Text
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class MaterialPrice(Base, TimestampMixin):
    __tablename__ = "material_prices"

    id = Column(Integer, primary_key=True, index=True)
    csi_code = Column(String(20), nullable=False, index=True)
    description = Column(Text, nullable=False)
    unit_cost = Column(Float, nullable=False)
    unit_of_measure = Column(String(50), nullable=False)
    supplier = Column(String(255), nullable=True)
    region = Column(String(100), nullable=True)
    effective_date = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)  # rs_means, vendor_quote, historical
