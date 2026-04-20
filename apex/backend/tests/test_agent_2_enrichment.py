"""Tests for Agent 2's Division 03 enrichment phase (Sprint 18.2.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch

from apex.backend.agents import agent_2_spec_parser as a2
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


@pytest.fixture
def project_with_sections(db_session: Session):
    """Project with 3 sections: 2 Div 03, 1 Div 05."""
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Enrichment Test {suffix}",
        project_number=f"ENR-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    doc = Document(
        project_id=p.id,
        filename="specs.pdf",
        file_path="/fake",
        file_type="pdf",
        classification="spec",
        raw_text="full spec text",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()

    # HF-20: fixtures populate work_description (v2 LLM parser reality),
    # NOT raw_text. Enrichment reads work_description first.
    sections = [
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="03",
            section_number="03 30 00",
            title="Cast-in-Place Concrete",
            work_description="Concrete minimum 4000 psi. Grade 60 rebar.",
        ),
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="03",
            section_number="03 20 00",
            title="Concrete Reinforcing",
            work_description="ASTM A615 Grade 60 deformed bars.",
        ),
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="05",
            section_number="05 12 00",
            title="Structural Steel",
            work_description="A992 steel wide flange.",
        ),
    ]
    db_session.add_all(sections)
    db_session.commit()
    return p


def test_enrichment_targets_only_division_03(db_session, project_with_sections):
    result = a2._enrich_division_03_parameters(
        db_session,
        project_with_sections.id,
        use_llm=False,
    )
    assert result["division_03_count"] == 2
    assert result["enriched"] == 2

    div_05 = (
        db_session.query(SpecSection)
        .filter_by(
            section_number="05 12 00",
            project_id=project_with_sections.id,
        )
        .first()
    )
    assert div_05.assembly_parameters_json is None

    div_03_sections = (
        db_session.query(SpecSection)
        .filter_by(
            division_number="03", project_id=project_with_sections.id
        )
        .all()
    )
    assert all(s.assembly_parameters_json is not None for s in div_03_sections)

    # Persisted shape matches spec_section.py docstring (no warnings, no
    # source_text_length in the stored payload)
    sample = div_03_sections[0].assembly_parameters_json
    assert set(sample.keys()) == {
        "parameters",
        "extracted_at",
        "extraction_method",
    }


def test_extractor_failure_does_not_crash_enrichment(
    db_session, project_with_sections
):
    call_count = {"n": 0}

    def flaky_extract(text, csi_code=None, use_llm=True):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated extractor failure")
        return {
            "parameters": {},
            "extracted_at": "2026-04-20T00:00:00",
            "extraction_method": "regex",
            "warnings": [],
            "source_text_length": len(text or ""),
        }

    with patch.object(a2, "extract_assembly_parameters", side_effect=flaky_extract):
        result = a2._enrich_division_03_parameters(
            db_session, project_with_sections.id, use_llm=False
        )

    assert result["division_03_count"] == 2
    assert result["enriched"] == 1
    assert any("simulated extractor failure" in w for w in result["warnings"])


def test_no_division_03_short_circuits(db_session):
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"No Div 03 {suffix}",
        project_number=f"NOD-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    doc = Document(
        project_id=p.id,
        filename="specs.pdf",
        file_path="/fake",
        file_type="pdf",
        classification="spec",
        raw_text="text",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()

    db_session.add(
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="09",
            section_number="09 29 00",
            title="Gypsum Board",
            work_description='5/8" Type X gypsum board.',
        )
    )
    db_session.commit()

    result = a2._enrich_division_03_parameters(db_session, p.id, use_llm=False)
    assert result["division_03_count"] == 0
    assert result["enriched"] == 0
    assert result["extraction_methods"] == {}
    assert result["warnings"] == []


def test_empty_section_text_produces_warning(db_session, project_with_sections):
    """Both work_description AND raw_text empty -> skip with warning."""
    target = (
        db_session.query(SpecSection)
        .filter_by(
            section_number="03 30 00",
            project_id=project_with_sections.id,
        )
        .first()
    )
    # HF-20: must zero BOTH columns — enrichment falls back to raw_text if
    # work_description is empty.
    target.work_description = ""
    target.raw_text = ""
    db_session.commit()

    result = a2._enrich_division_03_parameters(
        db_session, project_with_sections.id, use_llm=False
    )

    assert result["division_03_count"] == 2
    assert result["enriched"] == 1  # only the non-empty one
    assert any(
        "empty work_description and raw_text" in w
        for w in result["warnings"]
    )


def test_enrichment_reads_work_description_not_raw_text(
    db_session, project_with_sections
):
    """HF-20 regression: work_description is the production source column.

    Before HF-20, enrichment read raw_text only. The v2 LLM parser leaves
    raw_text empty and populates work_description instead — so every
    real-world Division 03 section was silently skipped. This test pins
    the fix by setting raw_text explicitly empty.
    """
    sections = (
        db_session.query(SpecSection)
        .filter_by(
            project_id=project_with_sections.id, division_number="03"
        )
        .all()
    )
    for s in sections:
        s.work_description = "Concrete minimum 4000 psi. Grade 60 rebar."
        s.raw_text = ""  # explicitly empty — mirrors v2 LLM parser output
    db_session.commit()

    result = a2._enrich_division_03_parameters(
        db_session, project_with_sections.id, use_llm=False
    )

    assert result["enriched"] == result["division_03_count"]
    assert result["enriched"] > 0
    for s in (
        db_session.query(SpecSection)
        .filter_by(
            project_id=project_with_sections.id, division_number="03"
        )
        .all()
    ):
        assert s.assembly_parameters_json is not None
        params = s.assembly_parameters_json.get("parameters", {})
        assert "f_c_psi" in params
        assert params["f_c_psi"]["value"] == 4000
