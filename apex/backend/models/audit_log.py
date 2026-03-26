"""Audit log model for tracking data changes."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from apex.backend.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)  # "create", "update", "delete"
    resource_type = Column(String(100), nullable=False)  # "project", "estimate", "material_price", "user", "organization"
    resource_id = Column(Integer, nullable=False)
    details = Column(JSON, nullable=True)  # old/new values or contextual info
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
