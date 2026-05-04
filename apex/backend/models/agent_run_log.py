"""Agent Run Log model."""

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class AgentRunLog(Base, TimestampMixin):
    __tablename__ = "agent_run_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    agent_name = Column(String(100), nullable=False)
    agent_number = Column(Integer, nullable=False)  # 1-7
    status = Column(String(50), default="queued")  # queued, running, completed, error
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    output_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    # Phase 1 provenance enrichment
    plan_set_id = Column(Integer, ForeignKey("plan_sets.id", ondelete="SET NULL"), nullable=True)
    plan_sheet_id = Column(Integer, ForeignKey("plan_sheets.id", ondelete="SET NULL"), nullable=True)
    scope_package_id = Column(Integer, ForeignKey("scope_packages.id", ondelete="SET NULL"), nullable=True)
    prompt_version = Column(String(100), nullable=True)
    input_bundle_hash = Column(String(64), nullable=True)
    model_name = Column(String(100), nullable=True)
    model_params_json = Column(JSON, nullable=True)
    confidence_summary = Column(JSON, nullable=True)
    output_schema_version = Column(String(50), nullable=True)
    parent_run_id = Column(Integer, ForeignKey("agent_run_logs.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="agent_run_logs")
