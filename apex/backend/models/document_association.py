"""DocumentGroup and DocumentAssociation models."""

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from apex.backend.db.database import Base


class DocumentGroup(Base):
    """A named collection of documents belonging to one bid package."""

    __tablename__ = "document_groups"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    library_entry_id = Column(Integer, ForeignKey("estimate_library.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    associations = relationship("DocumentAssociation", back_populates="group")


class DocumentAssociation(Base):
    """Links a document to a project/library entry and assigns it a role."""

    __tablename__ = "document_associations"

    VALID_ROLES = {
        "spec", "winest_bid", "rfi", "addendum", "schedule", "submittal",
        "manual", "plans", "blueprints", "as_built", "change_order",
        "bid_tab", "subcontractor_quote", "other",
    }

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    library_entry_id = Column(Integer, ForeignKey("estimate_library.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("document_groups.id"), nullable=True)

    document_role = Column(String(50), nullable=False)
    document_order = Column(Integer, nullable=True)
    spec_sections_affected = Column(Text, nullable=True)   # JSON array of section numbers
    related_csi_divisions = Column(String(200), nullable=True)  # comma-separated
    notes = Column(Text, nullable=True)

    parsed = Column(Boolean, default=False, nullable=False)
    parsed_at = Column(DateTime, nullable=True)
    parse_errors = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    document = relationship("Document")
    library_entry = relationship("EstimateLibraryEntry", back_populates="document_associations")
    group = relationship("DocumentGroup", back_populates="associations")
