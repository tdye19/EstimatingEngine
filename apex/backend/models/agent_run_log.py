"""Agent Run Log model."""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON, DateTime
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

    project = relationship("Project", back_populates="agent_run_logs")
