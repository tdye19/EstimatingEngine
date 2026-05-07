"""Unit tests for Agent 3 domain-rules fallback observability (19E.3).

Regression cover: when run_domain_rules() returns zero findings, Agent 3 must
emit a WARNING log and set analysis_method = "rule_based_empty_fallback_to_checklist"
instead of silently logging at INFO and writing "rule_based".
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apex.backend.agents import agent_3_gap_analysis as a3
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


@pytest.fixture
def project_with_specs(db_session):
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"A3 Domain Rules Test {suffix}",
        project_number=f"A3D-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    doc = Document(
        project_id=p.id,
        filename="specs.pdf",
        file_path="/fake/specs.pdf",
        file_type="pdf",
        classification="spec",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()

    sections = [
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="03",
            section_number="03 30 00",
            title="Cast-in-Place Concrete",
            work_description="4000 psi concrete with Grade 60 rebar.",
        ),
    ]
    db_session.add_all(sections)
    db_session.commit()
    return p


def test_empty_domain_rules_logs_warning_and_sets_fallback_metadata(
    db_session, project_with_specs, caplog
):
    """run_domain_rules() → [] triggers WARNING log and fallback analysis_method."""
    import logging

    with patch.object(a3, "run_domain_rules", return_value=[]), patch(
        "apex.backend.services.llm_provider.get_llm_provider",
        return_value=None,
    ), caplog.at_level(logging.WARNING, logger="apex.agent.gap_analysis"):
        result = a3.run_gap_analysis_agent(db_session, project_with_specs.id)

    assert result is not None
    assert "report_id" in result

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "rule_based_empty_fallback_to_checklist" in msg or "0 findings" in msg
        for msg in warning_messages
    ), f"Expected WARNING about 0 domain-rule findings; got: {warning_messages}"

    from apex.backend.models.gap_report import GapReport

    report = db_session.query(GapReport).filter(GapReport.id == result["report_id"]).one()
    assert (report.metadata_json or {}).get("analysis_method") == "rule_based_empty_fallback_to_checklist"
