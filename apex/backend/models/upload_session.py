"""Chunked upload session model."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

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
    bytes_received = Column(Integer, nullable=False, default=0)
    temp_dir = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    project = relationship("Project", back_populates="upload_sessions")
