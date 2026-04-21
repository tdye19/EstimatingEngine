"""Spec Section model for parsed CSI MasterFormat divisions.

assembly_parameters_json structure (populated by Sprint 18.2.2 extractor):
{
  "parameters": {
    "f_c_psi":                   {"value": 4000, "source_text": "...", "confidence": 0.92},
    "cement_type":               {"value": "Type I/II", "source_text": "...", "confidence": 0.88},
    "aggregate_max_size_inches": {"value": 0.75, "source_text": "...", "confidence": 0.85},
    "slump_range_inches":        {"value": "3-5", "source_text": "...", "confidence": 0.90},
    "air_entrainment_pct":       {"value": "5-7", "source_text": "...", "confidence": 0.82},
    "rebar_grade":               {"value": "Grade 60", "source_text": "...", "confidence": 0.95},
    "finish_class":              {"value": "troweled smooth", "source_text": "...", "confidence": 0.78},
    "curing_method":             {"value": "moist cure 7 days", "source_text": "...", "confidence": 0.80}
  },
  "extracted_at": "2026-04-20T18:30:00.000000",
  "extraction_method": "llm" | "regex" | "llm_partial"
}

Each parameter entry has value + source_text (the spec excerpt that
justified the value — traceability) + confidence (0.0-1.0). Parameters not
found are absent from the dict (not None). Null at the column level means
"not extracted yet" — distinct from {} meaning "extracted, none found".
"""

from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class SpecSection(Base, TimestampMixin):
    __tablename__ = "spec_sections"
    __table_args__ = (
        # HF-21 (Sprint 18.3.0): one row per CSI code per project. Agent 2's
        # multi-chunk/multi-doc parse paths previously accumulated duplicates
        # across runs; upsert logic in the loader + this constraint are two
        # layers of the same guarantee.
        UniqueConstraint(
            "project_id", "section_number", name="uq_spec_section_project_csi"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    division_number = Column(String(10), nullable=False)  # e.g., "03", "09"
    section_number = Column(String(20), nullable=False)  # e.g., "03 30 00"
    title = Column(String(500), nullable=False)
    work_description = Column(Text, nullable=True)
    materials_referenced = Column(JSON, nullable=True)  # list of materials
    execution_requirements = Column(Text, nullable=True)
    submittal_requirements = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)  # extracted keyword tags
    raw_text = Column(Text, nullable=True)

    # v2 spec parameter fields (Agent 2 AGENT2-V2)
    in_scope = Column(Boolean, default=True, nullable=False, server_default="1")
    material_specs = Column(JSON, nullable=True)  # division-specific material parameters
    quality_requirements = Column(JSON, nullable=True)  # testing/inspection requirements
    referenced_standards = Column(JSON, nullable=True)  # ACI, ASTM, CRSI codes

    # Sprint 18.2 — assembly parameter extractor (see class docstring for shape)
    assembly_parameters_json = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="spec_sections")
    document = relationship("Document", back_populates="spec_sections")
    takeoff_items = relationship("TakeoffItem", back_populates="spec_section")
