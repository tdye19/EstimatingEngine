"""Tests for Spec 19E.6.3 — Rule Fact Validator.

Covers:
  - Valid rule_id → all 5 rule_* fields populated
  - Invalid rule_id → stripped, recorded in stripped_rule_ids
  - No rule_id → pass-through unchanged
  - Mixed batch → correct counts
  - Doctrine #1 hard test (no dollar fabrication)
  - Empty list → zero counts
  - Agent 3 integration: mocked LLM with 3 finding types
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apex.backend.agents.pipeline_contracts import GapFinding
from apex.backend.agents.tools.domain_gap_rules import get_canonical_facts
from apex.backend.agents.tools.rule_validator import validate_and_attach_rule_facts


def _make(rule_id=None, description="Test gap finding", **kwargs) -> GapFinding:
    return GapFinding(
        title="Test finding",
        gap_type="missing",
        severity="critical",
        description=description,
        rule_id=rule_id,
        **kwargs,
    )


class TestValidateAndAttachRuleFacts:
    def test_valid_rule_id_populates_all_five_fields(self):
        result = validate_and_attach_rule_facts([_make(rule_id="CGR-001")])
        assert result.valid_cite_count == 1
        assert result.stripped_cite_count == 0
        assert result.no_cite_count == 0
        f = result.findings[0]
        assert f.rule_id == "CGR-001"
        # rule_standard_ref may be None (not all rules have one)
        assert f.rule_severity is not None
        assert f.rule_cost_range_text is not None
        assert f.rule_typical_responsibility is not None
        assert f.rule_rfi_template is not None

    def test_valid_civil_rule_id(self):
        result = validate_and_attach_rule_facts([_make(rule_id="CIV-001")])
        assert result.valid_cite_count == 1
        f = result.findings[0]
        assert f.rule_id == "CIV-001"
        assert f.rule_severity is not None

    def test_invalid_rule_id_stripped(self):
        result = validate_and_attach_rule_facts([_make(rule_id="FAKE-999")])
        assert result.stripped_cite_count == 1
        assert result.valid_cite_count == 0
        assert "FAKE-999" in result.stripped_rule_ids
        f = result.findings[0]
        assert f.rule_id is None
        assert f.rule_severity is None
        assert f.rule_cost_range_text is None
        assert f.rule_typical_responsibility is None
        assert f.rule_rfi_template is None

    def test_no_rule_id_pass_through(self):
        result = validate_and_attach_rule_facts([_make(rule_id=None)])
        assert result.no_cite_count == 1
        assert result.valid_cite_count == 0
        assert result.stripped_cite_count == 0
        f = result.findings[0]
        assert f.rule_id is None
        assert f.rule_severity is None

    def test_mixed_batch_correct_counts(self):
        findings = [
            _make(rule_id="CGR-001"),   # valid
            _make(rule_id="FAKE-999"),   # invalid
            _make(rule_id=None),         # no cite
        ]
        result = validate_and_attach_rule_facts(findings)
        assert result.valid_cite_count == 1
        assert result.stripped_cite_count == 1
        assert result.no_cite_count == 1
        assert len(result.findings) == 3

    def test_doctrine_1_no_dollar_fabrication(self):
        """Validator preserves LLM description narratives; rule_* values come only from library."""
        finding = _make(rule_id="CGR-001", description="This will cost $100,000 for sure")
        result = validate_and_attach_rule_facts([finding])
        f = result.findings[0]

        # LLM description narrative is preserved unchanged
        assert "$100,000 for sure" in f.description

        # rule_cost_range_text is exactly the library canonical value, not the LLM text
        facts = get_canonical_facts("CGR-001")
        assert f.rule_cost_range_text == facts["cost_range_text"]

        # The invented dollar amount was NOT written into rule_cost_range_text
        assert f.rule_cost_range_text != "This will cost $100,000 for sure"

    def test_empty_list(self):
        result = validate_and_attach_rule_facts([])
        assert result.valid_cite_count == 0
        assert result.stripped_cite_count == 0
        assert result.no_cite_count == 0
        assert result.stripped_rule_ids == []
        assert result.findings == []

    def test_multiple_stripped_ids_all_recorded(self):
        findings = [_make(rule_id="BAD-1"), _make(rule_id="BAD-2")]
        result = validate_and_attach_rule_facts(findings)
        assert result.stripped_cite_count == 2
        assert set(result.stripped_rule_ids) == {"BAD-1", "BAD-2"}

    def test_validator_preserves_non_rule_fields(self):
        finding = _make(
            rule_id="CGR-001",
            recommendation="Add to scope",
            risk_score=9.0,
        )
        result = validate_and_attach_rule_facts([finding])
        f = result.findings[0]
        assert f.recommendation == "Add to scope"
        assert f.risk_score == 9.0


class TestAgentIntegration:
    """End-to-end: Agent 3 with mocked LLM returning valid cite, invalid cite, and no-cite."""

    def test_e2e_three_finding_types(self, db_session):
        from apex.backend.agents import agent_3_gap_analysis as a3
        from apex.backend.models.document import Document
        from apex.backend.models.gap_report import GapReportItem
        from apex.backend.models.project import Project
        from apex.backend.models.spec_section import SpecSection

        suffix = uuid.uuid4().hex[:8]
        p = Project(
            name=f"RV E2E {suffix}",
            project_number=f"RVE-{suffix}",
            project_type="commercial",
        )
        db_session.add(p)
        db_session.flush()

        doc = Document(
            project_id=p.id,
            filename="s.pdf",
            file_path="/f/s.pdf",
            file_type="pdf",
            classification="spec",
            processing_status="completed",
        )
        db_session.add(doc)
        db_session.flush()

        db_session.add(
            SpecSection(
                project_id=p.id,
                document_id=doc.id,
                division_number="03",
                section_number="03 30 00",
                title="Concrete",
            )
        )
        db_session.commit()

        llm_response = json.dumps([
            {
                "description": "Missing vapor barrier under SOG",
                "severity": "critical",
                "affected_csi_division": "03",
                "recommendation": "Add to scope",
                "gap_type": "missing_division",
                "rule_id": "CGR-001",   # valid
            },
            {
                "description": "Some gap with invalid rule reference",
                "severity": "medium",
                "affected_csi_division": "05",
                "recommendation": "Review scope",
                "gap_type": "missing_division",
                "rule_id": "FAKE-999",  # invalid — validator must strip
            },
            {
                "description": "No applicable rule for this finding",
                "severity": "low",
                "affected_csi_division": "22",
                "recommendation": "Confirm plumbing",
                "gap_type": "missing_division",
                # no rule_id
            },
        ])

        mock_resp = MagicMock()
        mock_resp.content = llm_response
        mock_resp.provider = "test"
        mock_resp.model = "test-model"
        mock_resp.input_tokens = 100
        mock_resp.output_tokens = 50
        mock_resp.cache_creation_input_tokens = 0
        mock_resp.cache_read_input_tokens = 0
        mock_resp.duration_ms = 100.0

        mock_provider = MagicMock()
        mock_provider.provider_name = "test"
        mock_provider.model_name = "test-model"
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.complete = AsyncMock(return_value=mock_resp)

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=mock_provider),
            patch("apex.backend.agents.agent_3_gap_analysis._retrieve_spec_context_for_gaps", return_value=""),
            patch("apex.backend.agents.agent_3_gap_analysis.log_token_usage"),
        ):
            result = a3.run_gap_analysis_agent(db_session, p.id)

        assert "total_gaps" in result
        assert "report_id" in result

        items = (
            db_session.query(GapReportItem)
            .filter(GapReportItem.gap_report_id == result["report_id"])
            .all()
        )

        # Valid cite: rule_id preserved in description block
        valid_items = [i for i in items if i.description and "[Rule ID: CGR-001]" in i.description]
        assert len(valid_items) == 1, "Expected exactly one finding with [Rule ID: CGR-001]"

        # Invalid cite: FAKE-999 must NOT appear anywhere (stripped by validator)
        bogus_items = [i for i in items if i.description and "FAKE-999" in i.description]
        assert len(bogus_items) == 0, "FAKE-999 should have been stripped by validator"
