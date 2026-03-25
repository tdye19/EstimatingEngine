"""Chunked upload session model."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from apex.backend.db.database import Base


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    upload_id = Column(String(36), primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(255), nullable=True)
    total_chunks = Column(Integer, nullable=False)
    next_chunk = Column(Integer, nullable=False, default=0)
    temp_dir = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
