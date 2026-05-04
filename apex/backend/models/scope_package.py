"""ScopePackage — bid scope definition attached to a Project."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class ScopePackage(Base, TimestampMixin):
    __tablename__ = "scope_packages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=True)
    trade_focus = Column(String(50), nullable=True)
    csi_division = Column(String(10), nullable=True)
    status = Column(String(50), default="active", nullable=False)
    inclusions_json = Column(Text, nullable=True)
    exclusions_json = Column(Text, nullable=True)
    assumptions_json = Column(Text, nullable=True)

    project = relationship("Project", back_populates="scope_packages")
    plan_takeoff_layers = relationship(
        "TakeoffLayer", back_populates="scope_package", cascade="all, delete-orphan"
    )
