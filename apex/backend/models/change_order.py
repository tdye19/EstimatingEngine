"""Change order model — track scope changes and their cost/schedule impact
after the initial estimate is issued."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class ChangeOrder(Base, TimestampMixin):
    __tablename__ = "change_orders"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    co_number = Column(String(50), nullable=False)  # e.g. CO-001
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    csi_code = Column(String(20), nullable=True)

    # addition | deletion | modification
    change_type = Column(String(50), default="addition")
    # pending | approved | rejected | on_hold
    status = Column(String(50), default="pending")

    requested_by = Column(String(255), nullable=True)
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    cost_impact = Column(Float, default=0.0)  # positive = cost increase
    schedule_impact_days = Column(Integer, default=0)  # positive = delay

    project = relationship("Project", back_populates="change_orders")
