"""LineItemWCAttribution — persistent takeoff-item → WorkCategory attribution
(Sprint 18.4.1 Part C).

Every TakeoffItemV2 in a project gets exactly one attribution row after
Agent 3.5 runs — either to a real WorkCategory (match_tier in csi_exact,
spec_section_fuzzy, activity_title_fuzzy, llm_semantic) or to NULL with
match_tier="unmatched".

Regenerated on every Agent 3.5 run via delete-then-insert scoped to a
project. Mirrors GapFinding's contract: no versioning, no updated_at —
use created_at to distinguish runs.

Powers per-WC pricing roll-ups (Sprint 18.4.x Proposal Form output) and
any consumer that needs a stable many-to-one attribution without
re-running the matcher.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class LineItemWCAttribution(Base):
    __tablename__ = "line_item_wc_attributions"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    takeoff_item_id = Column(
        Integer,
        ForeignKey("takeoff_items_v2.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_category_id = Column(
        Integer,
        ForeignKey("work_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    match_tier = Column(String(32), nullable=False)
    # "csi_exact" | "spec_section_fuzzy" | "activity_title_fuzzy"
    # | "llm_semantic" | "unmatched"

    confidence = Column(Float, nullable=False, default=0.0)  # 0.0–1.0
    rationale = Column(Text, nullable=True)

    source = Column(String(16), nullable=False, default="rule")
    # "rule" | "llm"

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project")
    takeoff_item = relationship("TakeoffItemV2")
    work_category = relationship("WorkCategory")

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "takeoff_item_id",
            name="uq_attribution_project_takeoff",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LineItemWCAttribution(id={self.id}, project_id={self.project_id}, "
            f"takeoff_item_id={self.takeoff_item_id}, wc_id={self.work_category_id}, "
            f"tier={self.match_tier}, confidence={self.confidence:.2f})>"
        )
