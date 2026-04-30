"""Regression tests: Agent 3 truncation detection and retry path.

Covers the Railway prod failure where output_tokens=4096 caused JSON parse
errors and silent fallback to rule-based analysis for projects that had
Cast-in-Place Concrete and other Div 03 sections legitimately present.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents import agent_3_gap_analysis as a3
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.services.llm_provider import LLMResponse

# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

_COMPLETE_JSON = (
    '[{"description": "Division 22 Plumbing is absent from the specification", '
    '"severity": "critical", "affected_csi_division": "22", '
    '"recommendation": "Confirm plumbing scope with MEP sub", '
    '"gap_type": "missing_division"}]'
)

# Ends mid-string inside the second object — simulates hitting max_tokens
_TRUNCATED_JSON = (
    '[{"description": "Division 22 Plumbing is absent from the specification", '
    '"severity": "critical", "affected_csi_division": "22", '
    '"recommendation": "Confirm plumbing scope with MEP sub", '
    '"gap_type": "missing_division"}, '
    '{"description": "Division 23 HVAC not addressed — commercial building of this type '
    "typically requires full mechanical scope including AHUs, ductwork, and controls. "
    "Omission could result in significant change orders during construction. Verify with "
    "mechanical sub whether this division is covered under a separate prime contract or"
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _seed_project(db_session: Session) -> int:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Truncation Test {suffix}",
        project_number=f"TRN-{suffix}",
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

    db_session.add_all(
        [
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
                division_number="05",
                section_number="05 10 00",
                title="Structural Steel Framing",
            ),
        ]
    )
    db_session.commit()
    return p.id


def _make_response(content: str, max_tokens: int) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="fake-model",
        provider="fake",
        input_tokens=500,
        output_tokens=max_tokens,
        duration_ms=1000.0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


# ---------------------------------------------------------------------------
# Unit tests for the truncation detector
# ---------------------------------------------------------------------------


def test_is_truncated_returns_true_for_cut_off_string():
    assert a3._is_truncated(_TRUNCATED_JSON) is True


def test_is_truncated_returns_false_for_complete_json():
    assert a3._is_truncated(_COMPLETE_JSON) is False


def test_is_truncated_returns_true_when_no_closing_brace():
    assert a3._is_truncated('{"key": "value') is True


def test_is_truncated_handles_escaped_quotes():
    # Escaped quote inside a value must not count as a string boundary
    complete = '[{"description": "he said \\"hello\\"", "severity": "low", "affected_csi_division": "01", "recommendation": "none", "gap_type": "missing_division"}]'
    assert a3._is_truncated(complete) is False


# ---------------------------------------------------------------------------
# Integration test: retry path
# ---------------------------------------------------------------------------


class _RetryProvider:
    """Returns a truncated response on call 1, a complete response on call 2."""

    provider_name = "fake"
    model_name = "fake-model"
    calls: list[int]

    def __init__(self):
        self.calls = []

    async def health_check(self) -> bool:
        return True

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 16000,
    ) -> LLMResponse:
        self.calls.append(max_tokens)
        content = _TRUNCATED_JSON if len(self.calls) == 1 else _COMPLETE_JSON
        return _make_response(content, max_tokens)


def test_truncated_response_retries_and_uses_retry_result(db_session):
    """Agent 3 retries once with max_tokens=32000 on truncation and uses the
    complete retry response — does NOT fall back to rule-based analysis."""
    provider = _RetryProvider()
    project_id = _seed_project(db_session)

    with patch("apex.backend.services.llm_provider.get_llm_provider", return_value=provider):
        result = a3.run_gap_analysis_agent(db_session, project_id)

    assert result is not None
    assert len(provider.calls) == 2, f"expected 2 LLM calls, got {provider.calls}"
    assert provider.calls[0] == 16000, "initial call must use max_tokens=16000"
    assert provider.calls[1] == 32000, "retry call must use max_tokens=32000"

    from apex.backend.models.gap_report import GapReport, GapReportItem

    report = db_session.query(GapReport).filter(GapReport.id == result["report_id"]).one()
    assert (report.metadata_json or {}).get("analysis_method") == "llm", (
        "analysis_method should be 'llm' — rule-based fallback must not have fired"
    )

    items = db_session.query(GapReportItem).filter(GapReportItem.gap_report_id == report.id).all()
    assert len(items) >= 1
    assert any("22" in (i.division_number or "") for i in items), (
        "Gap report should contain the Div 22 item from the complete retry response"
    )
