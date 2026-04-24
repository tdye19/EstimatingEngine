"""HF-25 regression tests — confidence-driven risk level.

Sprint 18.x risk_level was driven by detected-problem severity (risk_score
factors), entirely decoupled from confidence (data coverage). Project 21
exposed the failure mode: 4.2% confidence + few visible problems → MODERATE
risk by old logic, but should be CRITICAL because we don't have enough
data to bid safely.

HF-25 fix: level is now a function of confidence via
_confidence_to_risk_level, with stable uppercase output ("LOW", "MODERATE",
"HIGH", "CRITICAL"). The risk_score factor math is preserved for a
future Intelligence Report breakdown surface.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents.agent_6_assembly import (
    _confidence_to_risk_level,
    run_assembly_agent,
)
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.models.project import Project

# ---------------------------------------------------------------------------
# Pure-function threshold + boundary tests
# ---------------------------------------------------------------------------


def test_confidence_75_returns_low():
    """Boundary: exactly 75.0 lands in LOW."""
    assert _confidence_to_risk_level(75.0) == "LOW"


def test_confidence_just_below_75_returns_moderate():
    """Boundary: 74.9 falls below LOW threshold → MODERATE."""
    assert _confidence_to_risk_level(74.9) == "MODERATE"


def test_confidence_50_boundary():
    """Two boundary checks for MODERATE → HIGH transition."""
    assert _confidence_to_risk_level(50.0) == "MODERATE"
    assert _confidence_to_risk_level(49.9) == "HIGH"


def test_confidence_25_boundary():
    """Two boundary checks for HIGH → CRITICAL transition."""
    assert _confidence_to_risk_level(25.0) == "HIGH"
    assert _confidence_to_risk_level(24.9) == "CRITICAL"


def test_confidence_zero_returns_critical():
    """Floor: 0 confidence → CRITICAL."""
    assert _confidence_to_risk_level(0.0) == "CRITICAL"


def test_confidence_100_returns_low():
    """Ceiling: 100 confidence → LOW."""
    assert _confidence_to_risk_level(100.0) == "LOW"


# ---------------------------------------------------------------------------
# Integration — Agent 6 end-to-end produces uppercase CRITICAL when data is thin
# ---------------------------------------------------------------------------


def test_agent_6_critical_when_confidence_under_25_integration(db_session: Session):
    """Project 21's failure-mode reproduction: a project with effectively
    no data should land at CRITICAL, not MODERATE."""
    suffix = uuid.uuid4().hex[:8]
    project = Project(
        name=f"HF25 critical {suffix}",
        project_number=f"HF25-CRIT-{suffix}",
        project_type="commercial",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # No takeoff items, no work categories, no spec sections — so every
    # rate-intel / field-cal / pb-coverage signal is empty. Confidence
    # collapses to ~0% and risk_level must be CRITICAL.
    result = run_assembly_agent(db_session, project.id, use_llm=False)

    report = (
        db_session.query(IntelligenceReportModel)
        .filter_by(id=result["report_id"])
        .one()
    )
    assert report.confidence_score is not None
    assert report.confidence_score < 25, (
        f"test setup expected sub-25 confidence, got {report.confidence_score}"
    )
    assert report.overall_risk_level == "CRITICAL", (
        f"expected CRITICAL at confidence={report.confidence_score}, "
        f"got {report.overall_risk_level!r}"
    )


# ---------------------------------------------------------------------------
# Output-case invariant — pins uppercase contract so a refactor can't
# silently lowercase the strings (the case change touched 2 separate sites
# in agent_6_assembly.py; this guard catches future drift)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "confidence_pct,expected",
    [
        (0.0, "CRITICAL"),
        (25.0, "HIGH"),
        (50.0, "MODERATE"),
        (75.0, "LOW"),
    ],
)
def test_risk_level_output_is_uppercase(confidence_pct: float, expected: str):
    """Every returned tier name is upper-case. Pins the API contract so a
    future refactor can't silently lowercase the output."""
    level = _confidence_to_risk_level(confidence_pct)
    assert level == expected
    assert level == level.upper()
    assert level in {"LOW", "MODERATE", "HIGH", "CRITICAL"}
