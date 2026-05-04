"""TakeoffLayer and PlanTakeoffItem — canvas-geometry takeoff records."""

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class TakeoffLayer(Base, TimestampMixin):
    """A named measurement layer on a plan sheet."""

    __tablename__ = "plan_takeoff_layers"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_sheet_id = Column(Integer, ForeignKey("plan_sheets.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_package_id = Column(Integer, ForeignKey("scope_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    trade_focus = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    layer_type = Column(String(50), nullable=True)
    visibility_default = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="plan_takeoff_layers")
    plan_sheet = relationship("PlanSheet", back_populates="takeoff_layers")
    scope_package = relationship("ScopePackage", back_populates="plan_takeoff_layers")
    items = relationship("PlanTakeoffItem", back_populates="layer", cascade="all, delete-orphan")


class PlanTakeoffItem(Base, TimestampMixin):
    """A single measured quantity on a plan sheet, with geometry and review state."""

    __tablename__ = "plan_takeoff_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_sheet_id = Column(Integer, ForeignKey("plan_sheets.id", ondelete="SET NULL"), nullable=True, index=True)
    takeoff_layer_id = Column(Integer, ForeignKey("plan_takeoff_layers.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_run_log_id = Column(Integer, ForeignKey("agent_run_logs.id", ondelete="SET NULL"), nullable=True)
    item_type = Column(String(50), nullable=True)
    label = Column(String(500), nullable=True)
    measurement_type = Column(String(50), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    geometry_geojson = Column(Text, nullable=True)
    bbox_json = Column(Text, nullable=True)
    source_method = Column(String(50), default="manual", nullable=False)
    confidence = Column(Float, nullable=True)
    review_status = Column(String(50), default="unreviewed", nullable=False)
    assumptions_json = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="plan_takeoff_items")
    layer = relationship("TakeoffLayer", back_populates="items")
