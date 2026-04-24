"""HF-24 regression tests — SCOPE MATCHER FINDINGS marker on the LLM path.

Sprint 18.3.3 added the literal "SCOPE MATCHER FINDINGS:" paragraph to
Agent 6's TEMPLATE narrative. Project 20 then proved that the LLM
narrative path doesn't preserve that token — the validator's A9 grep
fails because the LLM rephrases the data into its own prose.

HF-24 fix: after the LLM path produces a narrative, append the
deterministic marker paragraph (built by _build_scope_matcher_paragraph)
when findings exist AND the literal token isn't already in the LLM's
output. The "already in" guard prevents duplication if the LLM happens
to use the literal phrasing or if a future prompt change leaks it
through.

Each test mocks the LLM provider + _llm_generate_narrative so we exercise
the LLM path deterministically without a real API call.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents import agent_6_assembly as a6
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.models.project import Project
from apex.backend.models.work_category import WorkCategory

# ---------------------------------------------------------------------------
# Scaffolding (mirrors test_agent_6_assembly.py for consistency)
# ---------------------------------------------------------------------------


def _scaffold_project(db: Session, tag: str) -> Project:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"HF24 {tag}",
        project_number=f"HF24-{tag}-{suffix}",
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
    confidence: float = 1.0,
    work_category_id: int | None = None,
) -> GapFinding:
    f = GapFinding(
        project_id=project_id,
        finding_type=finding_type,
        match_tier="csi_exact",
        confidence=confidence,
        rationale=f"{finding_type} @ {severity}",
        source="rule",
        severity=severity,
        work_category_id=work_category_id,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ---------------------------------------------------------------------------
# LLM mock — minimal stub provider + patched narrative generator
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal LLM provider stub: passes the health check, exposes name fields."""

    provider_name = "stub"
    model_name = "stub-model"

    async def health_check(self) -> bool:
        return True


def _patch_llm(monkeypatch: pytest.MonkeyPatch, llm_text: str) -> None:
    """Force the LLM path to be taken with *llm_text* as the returned narrative.

    Patches both the provider factory and the async _llm_generate_narrative
    helper so the agent's LLM branch runs end-to-end without real network IO.
    Token counts are zero — the test only cares about the narrative string.
    """

    def _fake_get_llm_provider(*args: Any, **kwargs: Any) -> _StubProvider:
        return _StubProvider()

    async def _fake_llm_generate_narrative(*args: Any, **kwargs: Any) -> tuple:
        return (llm_text, 0, 0, 0, 0)

    # get_llm_provider is imported inline inside run_assembly_agent (`from
    # apex.backend.services.llm_provider import get_llm_provider`), so we
    # patch the source module — the inline import resolves through it.
    import apex.backend.services.llm_provider as _llm_mod

    monkeypatch.setattr(_llm_mod, "get_llm_provider", _fake_get_llm_provider)
    monkeypatch.setattr(a6, "_llm_generate_narrative", _fake_llm_generate_narrative)


def _read_narrative(db: Session, report_id: int) -> str:
    report = (
        db.query(IntelligenceReportModel).filter_by(id=report_id).one()
    )
    return report.executive_narrative or ""


# ---------------------------------------------------------------------------
# Test 1 — WARNING-only findings, LLM omits marker → marker appended
# ---------------------------------------------------------------------------


def test_scope_matcher_paragraph_appears_with_only_warnings(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """Project 20's failure mode: 1000+ findings, all severity=WARNING,
    LLM narrative omits the literal marker. HF-24 must append it."""
    project = _scaffold_project(db_session, "warn-only")
    wc = _scaffold_work_category(db_session, project, "30")
    for _ in range(3):
        _add_finding(
            db_session,
            project_id=project.id,
            finding_type="estimated_out_of_scope",
            severity="WARNING",
            work_category_id=wc.id,
        )

    _patch_llm(
        monkeypatch,
        llm_text=(
            "# BID INTELLIGENCE BRIEFING\n"
            "**Project:** test\n\n"
            "Some narrative body here without the literal marker token."
        ),
    )

    result = a6.run_assembly_agent(db_session, project.id, use_llm=True)

    assert result["narrative_method"] == "llm"
    narrative = _read_narrative(db_session, result["report_id"])
    assert "SCOPE MATCHER FINDINGS:" in narrative
    # Body content from the helper round-trips: counts and severity line.
    assert "3 estimated-out-of-scope" in narrative
    assert "3 warnings" in narrative


# ---------------------------------------------------------------------------
# Test 2 — only in_scope_not_estimated findings → marker appended
# ---------------------------------------------------------------------------


def test_scope_matcher_paragraph_appears_with_only_in_scope_not_estimated(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """Single-finding-type scenario sketched in the original spec.
    Confirms the gate (_has_gap_findings) doesn't require multiple types."""
    project = _scaffold_project(db_session, "isne-only")
    wc = _scaffold_work_category(db_session, project, "05")
    for _ in range(2):
        _add_finding(
            db_session,
            project_id=project.id,
            finding_type="in_scope_not_estimated",
            severity="WARNING",
            work_category_id=wc.id,
        )

    _patch_llm(monkeypatch, llm_text="LLM narrative without the marker.")

    result = a6.run_assembly_agent(db_session, project.id, use_llm=True)

    assert result["narrative_method"] == "llm"
    narrative = _read_narrative(db_session, result["report_id"])
    assert "SCOPE MATCHER FINDINGS:" in narrative
    assert "2 in-scope-not-estimated" in narrative
    assert "0 estimated-out-of-scope" in narrative


# ---------------------------------------------------------------------------
# Test 3 — zero findings → marker NOT appended (preserves no-op branch)
# ---------------------------------------------------------------------------


def test_scope_matcher_paragraph_omitted_when_zero_findings(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """No GapFindings exist. The marker MUST stay absent — appending it
    on an empty rollup would be a regression in the other direction."""
    project = _scaffold_project(db_session, "no-findings")

    _patch_llm(monkeypatch, llm_text="LLM narrative, no findings present.")

    result = a6.run_assembly_agent(db_session, project.id, use_llm=True)

    assert result["narrative_method"] == "llm"
    narrative = _read_narrative(db_session, result["report_id"])
    assert "SCOPE MATCHER FINDINGS" not in narrative


# ---------------------------------------------------------------------------
# Test 4 (Amendment 2) — LLM already includes marker → no duplication
# ---------------------------------------------------------------------------


def test_scope_matcher_paragraph_not_duplicated_when_llm_already_includes_it(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """If the LLM happens to use the literal "SCOPE MATCHER FINDINGS:"
    string, the idempotency guard must skip the append so the final
    narrative contains the marker exactly once."""
    project = _scaffold_project(db_session, "idem")
    wc = _scaffold_work_category(db_session, project, "09")
    _add_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        severity="WARNING",
        work_category_id=wc.id,
    )

    llm_text = (
        "# BID INTELLIGENCE BRIEFING\n"
        "Some body...\n\n"
        "SCOPE MATCHER FINDINGS: 0 in-scope-not-estimated, 0 estimated-out-of-scope, "
        "1 partial-coverage. Severity: 0 errors, 1 warnings, 0 info."
    )
    _patch_llm(monkeypatch, llm_text=llm_text)

    result = a6.run_assembly_agent(db_session, project.id, use_llm=True)

    assert result["narrative_method"] == "llm"
    narrative = _read_narrative(db_session, result["report_id"])
    assert narrative.count("SCOPE MATCHER FINDINGS:") == 1, (
        f"marker appeared {narrative.count('SCOPE MATCHER FINDINGS:')} times — "
        "idempotency guard failed"
    )
