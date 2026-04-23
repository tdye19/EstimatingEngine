"""Timeout-guard tests for Agent 3 (Sprint 18.3.3.4).

Regression cover for the demo-blocker where Agent 3 hung in status='running'
for 30+ minutes because provider.complete() had no asyncio.wait_for cap.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents import agent_3_gap_analysis as a3
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


@pytest.fixture
def project_with_specs(db_session: Session):
    """Minimal project with a couple of spec sections so Agent 3 has work to do."""
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"A3 Timeout Test {suffix}",
        project_number=f"A3T-{suffix}",
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
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="22",
            section_number="22 00 00",
            title="Plumbing",
            work_description="Copper domestic water piping.",
        ),
    ]
    db_session.add_all(sections)
    db_session.commit()
    return p


class _HealthyProvider:
    """Fake provider whose health_check returns True so the LLM path is taken."""

    provider_name = "fake"
    model_name = "fake-model"

    async def health_check(self) -> bool:
        return True

    async def complete(self, **kwargs):
        raise NotImplementedError  # override per test


class _SlowCompleteProvider(_HealthyProvider):
    async def complete(self, **kwargs):
        # Sleep longer than the patched LLM_TIMEOUT_SECONDS so wait_for fires.
        await asyncio.sleep(2.0)
        raise AssertionError("should be cancelled by asyncio.wait_for before reaching here")


class _HangHealthProvider:
    """Health check hangs; complete() must never be reached."""

    provider_name = "fake"
    model_name = "fake-model"

    async def health_check(self) -> bool:
        await asyncio.sleep(30.0)
        return True

    async def complete(self, **kwargs):
        raise AssertionError("complete() must not be called when health check times out")


class _ExceptionCompleteProvider(_HealthyProvider):
    async def complete(self, **kwargs):
        raise ValueError("simulated API failure (e.g. JSON parse / auth)")


def test_llm_call_times_out_falls_back_to_rule_based(
    db_session, project_with_specs, monkeypatch
):
    """LLM call hangs past LLM_TIMEOUT_SECONDS → TimeoutError caught → rule-based path."""
    monkeypatch.setattr(a3, "LLM_TIMEOUT_SECONDS", 0.1)

    with patch(
        "apex.backend.services.llm_provider.get_llm_provider",
        return_value=_SlowCompleteProvider(),
    ):
        result = a3.run_gap_analysis_agent(db_session, project_with_specs.id)

    # Pipeline completes (no exception propagated) and lands in rule-based path.
    assert result is not None
    assert "total_gaps" in result
    assert "report_id" in result

    from apex.backend.models.gap_report import GapReport

    report = db_session.query(GapReport).filter(GapReport.id == result["report_id"]).one()
    assert (report.metadata_json or {}).get("analysis_method") == "rule_based"


def test_health_check_times_out_skips_llm(db_session, project_with_specs, monkeypatch):
    """Health check hangs → wait_for fires within HEALTH_CHECK_TIMEOUT_SECONDS → rule-based path."""
    monkeypatch.setattr(a3, "HEALTH_CHECK_TIMEOUT_SECONDS", 0.2)

    started = time.monotonic()
    with patch(
        "apex.backend.services.llm_provider.get_llm_provider",
        return_value=_HangHealthProvider(),
    ):
        result = a3.run_gap_analysis_agent(db_session, project_with_specs.id)
    elapsed = time.monotonic() - started

    # Must return via rule-based path, not hang for the full 30s mock sleep.
    assert elapsed < 5.0, f"health check timeout did not fire promptly (took {elapsed:.2f}s)"
    assert result is not None

    from apex.backend.models.gap_report import GapReport

    report = db_session.query(GapReport).filter(GapReport.id == result["report_id"]).one()
    assert (report.metadata_json or {}).get("analysis_method") == "rule_based"


def test_llm_call_exception_still_handled(db_session, project_with_specs):
    """Regression: non-timeout exceptions in complete() still hit the fallback branch."""
    with patch(
        "apex.backend.services.llm_provider.get_llm_provider",
        return_value=_ExceptionCompleteProvider(),
    ):
        result = a3.run_gap_analysis_agent(db_session, project_with_specs.id)

    assert result is not None
    assert "total_gaps" in result

    from apex.backend.models.gap_report import GapReport

    report = db_session.query(GapReport).filter(GapReport.id == result["report_id"]).one()
    assert (report.metadata_json or {}).get("analysis_method") == "rule_based"
