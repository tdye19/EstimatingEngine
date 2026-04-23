"""GapFinding — Agent 3.5 scope gap analysis output (Sprint 18.3.1, extended 18.4.1).

One row per finding produced by the scope gap analyzer. Findings are
*regenerated* on every Agent 3.5 run via delete-then-insert scoped to
a project; there is no versioning and no updated_at — use created_at
to distinguish runs.

finding_type:
    in_scope_not_estimated  — WorkCategory scope has no matching takeoff item
    estimated_out_of_scope  — takeoff item has no matching WorkCategory scope
    partial_coverage        — match exists but coverage is incomplete

match_tier (how the matcher identified the link):
    csi_exact            — exact CSI code match
    spec_section_fuzzy   — spec section reference overlap (substring / prefix)
    llm_semantic         — LLM-mediated semantic match

source:
    rule — produced by deterministic matcher
    llm  — produced by the LLM review pass

Line-item FK transition (Sprint 18.4.1):
    takeoff_item_id  — FK to TakeoffItemV2 populated by every NEW emission.
                       This is the live reference post-18.4.1 Part B.
    estimate_line_id — FK to EstimateLineItem, retained for backward compat
                       with rows written before the Part A input-source fix.
                       The scope matcher now leaves this NULL on new rows.
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
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


class GapFinding(Base):
    __tablename__ = "gap_findings"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    finding_type = Column(String(32), nullable=False)
    # "in_scope_not_estimated" | "estimated_out_of_scope" | "partial_coverage"

    work_category_id = Column(
        Integer,
        ForeignKey("work_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    estimate_line_id = Column(
        Integer,
        ForeignKey("estimate_line_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    takeoff_item_id = Column(
        Integer,
        ForeignKey("takeoff_items_v2.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    spec_section_ref = Column(String(32), nullable=True)
    # CSI code in display form, e.g. "03 30 00". Stored as opaque string —
    # not FK'd to spec_sections because findings may reference codes that
    # exist in scope docs but not in the parsed spec sections.

    match_tier = Column(String(32), nullable=False)
    # "csi_exact" | "spec_section_fuzzy" | "llm_semantic"

    confidence = Column(Float, nullable=False)  # 0.0–1.0
    rationale = Column(Text, nullable=False)

    source = Column(String(16), nullable=False)
    # "rule" | "llm"

    severity = Column(
        String(16),
        nullable=False,
        default="WARNING",
        server_default="WARNING",
    )
    # "ERROR" | "WARNING" | "INFO" — queryable by downstream consumers
    # (gap UI, Intelligence Report). Added in Sprint 18.3.1.1.

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project")
    work_category = relationship("WorkCategory")
    estimate_line = relationship("EstimateLineItem")
    takeoff_item = relationship("TakeoffItemV2")

    __table_args__ = (
        Index(
            "ix_gap_findings_project_finding_type",
            "project_id",
            "finding_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<GapFinding(id={self.id}, project_id={self.project_id}, "
            f"type={self.finding_type}, tier={self.match_tier}, "
            f"confidence={self.confidence:.2f})>"
        )
