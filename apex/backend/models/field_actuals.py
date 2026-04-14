"""Field Actuals models — what crews actually produced on completed projects."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class FieldActualsProject(Base):
    __tablename__ = "field_actuals_projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    source_file = Column(String)
    file_hash = Column(String(32), unique=True)  # MD5 dedup
    project_type = Column(String)  # "completed", "in_progress"
    completion_date = Column(Date)
    region = Column(String)
    notes = Column(Text)
    ingested_at = Column(DateTime, default=func.now())

    line_items = relationship(
        "FieldActualsLineItem",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class FieldActualsLineItem(Base):
    __tablename__ = "field_actuals_line_items"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("field_actuals_projects.id"), nullable=False, index=True)
    wbs_area = Column(String)
    activity = Column(String, nullable=False)
    quantity = Column(Float)
    unit = Column(String)
    crew_trade = Column(String)
    actual_production_rate = Column(Float)  # Unit/MH — what the crew actually did
    actual_labor_hours = Column(Float)
    actual_labor_cost = Column(Float)
    actual_material_cost = Column(Float)
    csi_code = Column(String)

    project = relationship("FieldActualsProject", back_populates="line_items")

    __table_args__ = (
        Index("ix_fa_li_activity", "activity"),
        Index("ix_fa_li_csi_code", "csi_code"),
        Index("ix_fa_li_activity_unit", "activity", "unit"),
    )
