"""WorkCategory — authoritative bid-scope boundary for a project.

A WorkCategory represents a single bidding package's scope as defined in
a Work Scopes document (e.g., KCCU_Volume_2_Work_Scopes). One project has
many WorkCategories. WorkCategories are THE authoritative scope for bidding
— they supersede any scope implied by the project specs.

Populated by Agent 2B (Work Scope Parser, Spec 18.1.2).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class WorkCategory(Base):
    __tablename__ = "work_categories"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    wc_number = Column(String(16), nullable=False)
    # String — supports non-numeric values like "28A". Not an ordered sequence.

    title = Column(String(512), nullable=False)
    # Short description, e.g., "Earthwork and Site Utilities"

    # Parsed structured content
    work_included_items = Column(JSON, nullable=False, default=list)
    # List[str] — each string is a single inclusion line from "Work Included".
    # Empty list if section missing. Populated by Agent 2B.

    work_category_notes = Column(Text, nullable=True)
    # Prose content from "Work Category Notes" section. May be null.

    specific_notes = Column(JSON, nullable=False, default=list)
    # List[str] — items from "Specific Notes and Details" section.

    # Bid-risk content (flagged critical per handoff doc)
    related_work_by_others = Column(JSON, nullable=False, default=list)
    # List[str] — exclusion boundaries. What is NOT in this bid category.

    add_alternates = Column(JSON, nullable=False, default=list)
    # List[dict] — each: {"description": str, "price_type": "add"|"deduct"|"unknown"}

    allowances = Column(JSON, nullable=False, default=list)
    # List[dict] — each: {"description": str, "amount_dollars": float|None}

    unit_prices = Column(JSON, nullable=False, default=list)
    # List[dict] — each: {"description": str, "unit": str, "rate": float|None}

    # Cross-references
    referenced_spec_sections = Column(JSON, nullable=False, default=list)
    # List[str] — CSI section codes referenced, e.g., ["311000", "312000"].
    # Normalized to 6-digit string format (no spaces, no dots).

    # Source tracking
    source_document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_page_start = Column(Integer, nullable=True)
    source_page_end = Column(Integer, nullable=True)

    # Parse metadata
    parse_method = Column(String(32), nullable=True)
    # "llm" | "regex" | "manual"

    parse_confidence = Column(Float, nullable=True)
    # 0.0–1.0. Null if parse_method is "manual".

    # Standard timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="work_categories")
    source_document = relationship("Document", foreign_keys=[source_document_id])

    __table_args__ = (
        UniqueConstraint("project_id", "wc_number", name="uq_workcategory_project_wcnumber"),
        Index("ix_workcategory_project_wcnumber", "project_id", "wc_number"),
    )

    def __repr__(self) -> str:
        return f"<WorkCategory(id={self.id}, project_id={self.project_id}, wc={self.wc_number}, title={self.title!r})>"
