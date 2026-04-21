"""Intelligence Report model — aggregated findings from all upstream agents (Agent 6 v2)."""

from sqlalchemy import (
    Column,
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


class IntelligenceReportModel(Base):
    __tablename__ = "intelligence_reports"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    version = Column(Integer, default=1)
    generated_at = Column(DateTime, default=func.now())

    # Takeoff summary
    takeoff_item_count = Column(Integer, default=0)
    takeoff_total_labor = Column(Float)
    takeoff_total_material = Column(Float)

    # Intelligence summaries (stored as JSON)
    rate_intelligence_json = Column(Text)  # JSON of RateIntelligenceSummary
    field_calibration_json = Column(Text)  # JSON of FieldCalibrationSummary
    scope_risk_json = Column(Text)  # JSON of ScopeRiskSummary
    comparable_projects_json = Column(Text)  # JSON of ComparableProjectSummary

    # Spec intel
    spec_sections_parsed = Column(Integer, default=0)
    material_specs_extracted = Column(Integer, default=0)

    # Overall assessment
    overall_risk_level = Column(String, default="unknown")
    confidence_score = Column(Float)
    executive_narrative = Column(Text)
    narrative_method = Column(String, default="template")

    # PB coverage
    pb_projects_loaded = Column(Integer, default=0)
    pb_activities_available = Column(Integer, default=0)

    # Tokens
    narrative_tokens_used = Column(Integer, default=0)

    # Relationships
    project = relationship("Project", back_populates="intelligence_reports")

    __table_args__ = (
        Index("ix_ir_project_id", "project_id"),
        Index("ix_ir_project_version", "project_id", "version"),
    )
