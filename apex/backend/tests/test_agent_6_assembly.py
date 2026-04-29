"""Agent 6 assembly tests — Sprint 18.3.3 GapFinding consumer.

Covers:
- _aggregate_gap_findings empty vs populated rollups.
- top_gap_findings ordering: ERROR → WARNING → INFO, confidence DESC within tier.
- Graceful degradation when the project has no findings (no exception, empty rollup).
- End-to-end through run_assembly_agent (template narrative path, no LLM):
  the "SCOPE MATCHER FINDINGS:" paragraph is present iff findings exist.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents.agent_6_assembly import (
    _aggregate_gap_findings,
    run_assembly_agent,
)
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.models.project import Project
from apex.backend.models.work_category import WorkCategory


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def _scaffold_project(db: Session, tag: str) -> Project:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Agent6 {tag}",
        project_number=f"A6-{tag}-{suffix}",
        project_type="commercial",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _scaffold_work_category(db: Session, project: Project, wc_number: str) -> WorkCategory:
    wc = WorkCategory(
        project_id=project.id,
        wc_number=wc_number,
        title=f"Category {wc_number}",
        work_included_items=[],
        specific_notes=[],
        related_work_by_others=[],
        add_alternates=[],
        allowances=[],
        unit_prices=[],
        referenced_spec_sections=[],
    )
    db.add(wc)
    db.commit()
    db.refresh(wc)
    return wc


def _add_finding(
    db: Session,
    *,
    project_id: int,
    finding_type: str,
    severity: str,
    confidence: float,
    match_tier: str = "csi_exact",
    source: str = "rule",
    rationale: str | None = None,
    work_category_id: int | None = None,
    spec_section_ref: str | None = None,
) -> GapFinding:
    f = GapFinding(
        project_id=project_id,
        finding_type=finding_type,
        match_tier=match_tier,
        confidence=confidence,
        rationale=rationale or f"{finding_type} @ {confidence:.2f}",
        source=source,
        severity=severity,
        work_category_id=work_category_id,
        spec_section_ref=spec_section_ref,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ---------------------------------------------------------------------------
# _aggregate_gap_findings — empty
# ---------------------------------------------------------------------------


def test_gap_findings_aggregator_empty(db_session: Session):
    project = _scaffold_project(db_session, "empty")

    result = _aggregate_gap_findings(db_session, project.id)

    assert result == {
        "in_scope_not_estimated": 0,
        "estimated_out_of_scope": 0,
        "partial_coverage": 0,
        "severity_error": 0,
        "severity_warning": 0,
        "severity_info": 0,
        "top_gap_findings": [],
    }


# ---------------------------------------------------------------------------
# _aggregate_gap_findings — populated
# ---------------------------------------------------------------------------


def test_gap_findings_aggregator_populated(db_session: Session):
    project = _scaffold_project(db_session, "pop")
    wc_a = _scaffold_work_category(db_session, project, "05")
    wc_b = _scaffold_work_category(db_session, project, "09")

    # Seed 5 findings: mix finding_types, severities, and confidences so ordering
    # is non-trivially determined.
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        severity="ERROR",
        confidence=0.70,
        work_category_id=wc_a.id,
        spec_section_ref="03 30 00",
    )
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        severity="ERROR",
        confidence=0.90,
        work_category_id=wc_a.id,
        spec_section_ref="03 31 00",
    )
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="estimated_out_of_scope",
        severity="WARNING",
        confidence=0.95,
        work_category_id=wc_b.id,
    )
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        severity="WARNING",
        confidence=0.40,
    )
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        severity="INFO",
        confidence=0.99,
        match_tier="llm_semantic",
        source="llm",
    )

    result = _aggregate_gap_findings(db_session, project.id)

    # finding_type counts
    assert result["in_scope_not_estimated"] == 2
    assert result["estimated_out_of_scope"] == 1
    assert result["partial_coverage"] == 2

    # severity counts
    assert result["severity_error"] == 2
    assert result["severity_warning"] == 2
    assert result["severity_info"] == 1

    # top_gap_findings: ERROR first (confidence DESC), then WARNING (confidence DESC), then INFO.
    top = result["top_gap_findings"]
    assert len(top) == 5

    severities_in_order = [t["severity"] for t in top]
    assert severities_in_order == ["ERROR", "ERROR", "WARNING", "WARNING", "INFO"]

    # Within ERROR tier: 0.90 before 0.70.
    assert top[0]["confidence"] == pytest.approx(0.90)
    assert top[1]["confidence"] == pytest.approx(0.70)
    # Within WARNING tier: 0.95 before 0.40.
    assert top[2]["confidence"] == pytest.approx(0.95)
    assert top[3]["confidence"] == pytest.approx(0.40)
    # INFO tier last.
    assert top[4]["confidence"] == pytest.approx(0.99)

    # Top entry carries expected keys sourced from the GapFinding model
    # (via relationships for work_category_number/_title).
    first = top[0]
    assert first["finding_type"] == "in_scope_not_estimated"
    assert first["severity"] == "ERROR"
    assert first["work_category_number"] == "05"
    assert first["work_category_title"] == "Category 05"
    assert first["spec_section_ref"] in {"03 30 00", "03 31 00"}
    assert isinstance(first["rationale"], str)


# ---------------------------------------------------------------------------
# Graceful degradation — project has no findings (replaces the void
# "estimate_run_id unresolvable" scenario per Sprint 18.3.3 Amendment 1).
# ---------------------------------------------------------------------------


def test_gap_findings_aggregator_handles_nonexistent_project(db_session: Session):
    # No project, no findings — the helper must still return an empty rollup
    # without raising.
    unused_project_id = 987_654_321

    result = _aggregate_gap_findings(db_session, unused_project_id)

    assert result["in_scope_not_estimated"] == 0
    assert result["estimated_out_of_scope"] == 0
    assert result["partial_coverage"] == 0
    assert result["severity_error"] == 0
    assert result["severity_warning"] == 0
    assert result["severity_info"] == 0
    assert result["top_gap_findings"] == []


# ---------------------------------------------------------------------------
# End-to-end — run_assembly_agent template path, narrative inclusion/omission.
# ---------------------------------------------------------------------------


def test_intelligence_report_includes_gap_findings_in_narrative(db_session: Session):
    project = _scaffold_project(db_session, "narr-on")
    wc = _scaffold_work_category(db_session, project, "05")
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        severity="ERROR",
        confidence=0.88,
        work_category_id=wc.id,
        spec_section_ref="05 50 00",
        rationale="WC 05 references 05 50 00 but no estimate line covers it",
    )
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        severity="WARNING",
        confidence=0.55,
    )

    result = run_assembly_agent(db_session, project.id, use_llm=False)

    assert result["narrative_method"] == "template"

    report = (
        db_session.query(IntelligenceReportModel)
        .filter_by(id=result["report_id"])
        .one()
    )
    narrative = report.executive_narrative or ""
    assert "SCOPE MATCHER FINDINGS:" in narrative
    assert "1 in-scope-not-estimated" in narrative
    assert "1 partial-coverage" in narrative
    assert "1 errors" in narrative
    assert "1 warnings" in narrative


def test_intelligence_report_omits_gap_findings_paragraph_when_empty(db_session: Session):
    project = _scaffold_project(db_session, "narr-off")

    result = run_assembly_agent(db_session, project.id, use_llm=False)

    assert result["narrative_method"] == "template"

    report = (
        db_session.query(IntelligenceReportModel)
        .filter_by(id=result["report_id"])
        .one()
    )
    narrative = report.executive_narrative or ""
    assert "SCOPE MATCHER FINDINGS" not in narrative


# ---------------------------------------------------------------------------
# Driver-bucket narrative — LLM path
# ---------------------------------------------------------------------------


def test_driver_bucket_narrative_llm_path(db_session: Session, mock_llm_response):
    """LLM path: driver-bucket headings appear; SCOPE MATCHER FINDINGS appended exactly once."""
    from unittest.mock import AsyncMock, MagicMock, patch

    project = _scaffold_project(db_session, "llm-bucket")
    wc = _scaffold_work_category(db_session, project, "03")

    # Scope matcher finding — routes to Quantity Growth bucket + triggers deterministic append
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        severity="ERROR",
        confidence=0.88,
        work_category_id=wc.id,
        spec_section_ref="03 30 00",
    )
    # Productivity signal — rate deviation finding via a second scope finding
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        severity="WARNING",
        confidence=0.60,
        rationale="Production rate for concrete placement not validated against field actuals",
    )

    # Simulated LLM output: bucket-organized narrative WITHOUT the deterministic marker
    fake_llm_narrative = (
        "Risk Overview: HIGH risk, 30% confidence. Review all flagged items before submission.\n\n"
        "## Quantity Growth\n"
        "One in-scope-not-estimated gap was identified for Division 03 concrete work. "
        "The finding at spec section 03 30 00 indicates potential quantity growth risk "
        "if scope is awarded without coverage.\n"
        "- [ERROR] in-scope-not-estimated for WC 03 (confidence 0.88): "
        "03 30 00 referenced in specs but not covered by an estimate line\n\n"
        "## Productivity\n"
        "One partial-coverage finding flags a production rate that has not been validated "
        "against field actuals for concrete placement. This introduces labor hour uncertainty.\n"
        "- [WARNING] partial-coverage (confidence 0.60): "
        "Production rate for concrete placement not validated against field actuals\n\n"
        "## Material Escalation\n"
        "No material escalation signals identified for this estimate.\n\n"
        "Recommendation: Hold for revision. Address the Division 03 scope gap before submission."
    )

    mock_resp = mock_llm_response(content=fake_llm_narrative)
    mock_provider = MagicMock()
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_provider.complete = AsyncMock(return_value=mock_resp)
    mock_provider.provider_name = "test"
    mock_provider.model_name = "test-model"

    with patch("apex.backend.services.llm_provider.get_llm_provider", return_value=mock_provider):
        result = run_assembly_agent(db_session, project.id, use_llm=True)

    assert result["narrative_method"] == "llm"

    report = db_session.query(IntelligenceReportModel).filter_by(id=result["report_id"]).one()
    narrative = report.executive_narrative or ""

    # Driver-bucket section headings must be present
    assert "Quantity Growth" in narrative
    assert "Productivity" in narrative
    assert "Material Escalation" in narrative

    # Deterministic marker appended exactly once (not in LLM output → appended by guard)
    assert narrative.count("SCOPE MATCHER FINDINGS:") == 1

    # proposal_form_json unaffected — no WorkCategories/TakeoffItemV2 in this fixture
    assert report.proposal_form_json is None
