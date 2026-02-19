"""Document model."""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, xlsx
    classification = Column(String(50), nullable=True)  # spec, drawing, addendum, rfi
    file_size_bytes = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    processing_status = Column(String(50), default="pending")  # pending, processing, completed, error

    project = relationship("Project", back_populates="documents")
    spec_sections = relationship("SpecSection", back_populates="document", cascade="all, delete-orphan")
