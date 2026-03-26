"""Estimate Library models — searchable archive of completed estimates."""

import json
from datetime import date
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class EstimateLibraryEntry(Base, TimestampMixin):
    """A single archived estimate entry in the library."""

    __tablename__ = "estimate_library"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Optional links back to live project / estimate records
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    estimate_id = Column(Integer, ForeignKey("estimates.id"), nullable=True)

    # Core descriptive fields
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Classification
    project_type = Column(String(100), nullable=True)   # e.g. "Commercial Office TI"
    building_type = Column(String(100), nullable=True)  # e.g. "Wood Frame"

    # Size & cost
    square_footage = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=False)
    cost_per_sqft = Column(Float, nullable=True)  # auto-calculated

    # Location
    location_city = Column(String(100), nullable=True)
    location_state = Column(String(2), nullable=True)
    location_zip = Column(String(10), nullable=True)

    # Bid info
    bid_date = Column(Date, nullable=True)
    status = Column(String(50), default="completed", nullable=False)
    bid_result = Column(String(50), nullable=True)  # "won","lost","no_bid","pending"

    # Detail blobs
    csi_divisions_json = Column(Text, nullable=True)  # JSON string
    line_item_count = Column(Integer, nullable=True)

    # Search / tagging
    tags = Column(String(500), nullable=True)  # comma-separated fallback

    # Provenance
    source = Column(String(50), default="pipeline", nullable=False)
    original_file_path = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Ownership / org
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    # Template flag
    is_template = Column(Boolean, default=False, nullable=False)

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    estimate = relationship("Estimate", foreign_keys=[estimate_id])
    creator = relationship("User", foreign_keys=[created_by])
    organization = relationship("Organization", foreign_keys=[organization_id])
    library_tags = relationship(
        "EstimateLibraryTag",
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    line_items = relationship(
        "HistoricalLineItem",
        back_populates="library_entry",
        cascade="all, delete-orphan",
    )
    document_associations = relationship(
        "DocumentAssociation",
        back_populates="library_entry",
    )

    # ── helpers ────────────────────────────────────────────────────
    def recalculate_cost_per_sqft(self) -> None:
        if self.square_footage and self.square_footage > 0 and self.total_cost:
            self.cost_per_sqft = round(self.total_cost / self.square_footage, 4)
        else:
            self.cost_per_sqft = None

    def get_csi_divisions(self) -> dict:
        if not self.csi_divisions_json:
            return {}
        try:
            return json.loads(self.csi_divisions_json)
        except (ValueError, TypeError):
            return {}

    def set_csi_divisions(self, data: dict) -> None:
        self.csi_divisions_json = json.dumps(data)


class EstimateLibraryTag(Base):
    """Normalized tag rows for an EstimateLibraryEntry."""

    __tablename__ = "estimate_library_tags"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    entry_id = Column(
        Integer,
        ForeignKey("estimate_library.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag = Column(String(100), nullable=False)

    entry = relationship("EstimateLibraryEntry", back_populates="library_tags")

    __table_args__ = (UniqueConstraint("entry_id", "tag", name="uq_entry_tag"),)
