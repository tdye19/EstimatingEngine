"""Tests for SpecSection.assembly_parameters_json column (Sprint 18.2.1)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


def _build_scaffold(db_session: Session, *, test_tag: str) -> tuple[Project, Document]:
    """Create a Project + Document satisfying every NOT NULL column.

    project_number is UUID-suffixed to survive conftest's shared in-memory
    StaticPool (commits persist across tests in the session).
    """
    suffix = uuid.uuid4().hex[:8]
    project = Project(
        name=f"Test {test_tag}",
        project_number=f"TEST-18.2.1-{test_tag}-{suffix}",
        project_type="commercial",
    )
    db_session.add(project)
    db_session.flush()

    doc = Document(
        project_id=project.id,
        filename=f"{test_tag}.pdf",
        file_path=f"/fake/{test_tag}.pdf",
        file_type="pdf",
        classification="spec",
        raw_text="test",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()

    return project, doc


def test_spec_section_stores_assembly_parameters_json(db_session: Session):
    project, doc = _build_scaffold(db_session, test_tag="A")

    section = SpecSection(
        project_id=project.id,
        document_id=doc.id,
        division_number="03",
        section_number="03 30 00",
        title="Cast-in-Place Concrete",
        assembly_parameters_json={
            "parameters": {
                "f_c_psi": {
                    "value": 4000,
                    "source_text": "minimum compressive strength of 4,000 psi at 28 days",
                    "confidence": 0.92,
                },
                "rebar_grade": {
                    "value": "Grade 60",
                    "source_text": "ASTM A615 Grade 60",
                    "confidence": 0.95,
                },
            },
            "extracted_at": "2026-04-20T18:30:00",
            "extraction_method": "llm",
        },
    )
    db_session.add(section)
    db_session.commit()

    retrieved = db_session.query(SpecSection).filter_by(id=section.id).first()
    assert retrieved.assembly_parameters_json is not None
    params = retrieved.assembly_parameters_json["parameters"]
    assert params["f_c_psi"]["value"] == 4000
    assert params["f_c_psi"]["confidence"] == 0.92
    assert params["rebar_grade"]["value"] == "Grade 60"
    assert retrieved.assembly_parameters_json["extraction_method"] == "llm"


def test_spec_section_assembly_parameters_nullable(db_session: Session):
    """Existing rows without parameters must round-trip as None."""
    project, doc = _build_scaffold(db_session, test_tag="B")

    section = SpecSection(
        project_id=project.id,
        document_id=doc.id,
        division_number="05",
        section_number="05 12 00",
        title="Structural Steel",
        # No assembly_parameters_json set
    )
    db_session.add(section)
    db_session.commit()

    retrieved = db_session.query(SpecSection).filter_by(id=section.id).first()
    assert retrieved.assembly_parameters_json is None
