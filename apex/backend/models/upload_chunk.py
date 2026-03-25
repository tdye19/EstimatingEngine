"""Chunk storage for distributed-safe chunked uploads."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, ForeignKey
from apex.backend.db.database import Base


class UploadChunk(Base):
    __tablename__ = "upload_chunks"

    upload_id = Column(
        String(36),
        ForeignKey("upload_sessions.upload_id", ondelete="CASCADE"),
        primary_key=True,
    )
    chunk_number = Column(Integer, primary_key=True)
    chunk_data = Column(LargeBinary, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
