"""Tests for Agent 3.5 — Scope Matcher (Sprint 18.3.2).

Covers:
  Tier 1 (CSI exact / division prefix) — 2 tests
  Tier 2 (fuzzy string above/below threshold) — 2 tests
  Tier 3 (LLM high/low confidence) — 2 tests
  Finding emission (unmatched, uncovered inclusion, exclusion conflict) — 3 tests
  Orchestration (upstream-failure skip log) — 1 test
  API (empty response + severity filter) — 2 tests
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.work_category import WorkCategory
from apex.backend.services import scope_matcher as sm
from apex.backend.services.agent_orchestrator import AGENT_DEFINITIONS, AgentOrchestrator

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_estimate(db, project_id: int) -> Estimate:
    est = Estimate(project_id=project_id, version=1, status="draft")
    db.add(est)
    db.commit()
    db.refresh(est)
    return est


def _make_line(db, estimate_id: int, **kw) -> EstimateLineItem:
    defaults = {
        "estimate_id": estimate_id,
        "division_number": "03",
        "csi_code": "03 30 00",
        "description": "Cast-in-place concrete",
        "quantity": 100.0,
        "unit_of_measure": "CY",
        "total_cost": 10_000.0,
    }
    defaults.update(kw)
    li = EstimateLineItem(**defaults)
    db.add(li)
    db.commit()
    db.refresh(li)
    return li


def _make_wc(db, project_id: int, **kw) -> WorkCategory:
    defaults = {
        "project_id": project_id,
        "wc_number": "03",
        "title": "Structural Concrete",
        "work_included_items": [],
        "specific_notes": [],
        "related_work_by_others": [],
        "add_alternates": [],
        "allowances": [],
        "unit_prices": [],
        "referenced_spec_sections": [],
    }
    defaults.update(kw)
    wc = WorkCategory(**defaults)
    db.add(wc)
    db.commit()
    db.refresh(wc)
    return wc


# ---------------------------------------------------------------------------
# Tier 1 — CSI exact / division prefix
# ---------------------------------------------------------------------------


class TestTier1CSIMatch:
    def test_exact_6_digit_csi_match(self, db_session, test_project):
        """Line item CSI 03 30 00 matches WC with referenced_spec_sections=['033000']."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(db_session, est.id, csi_code="03 30 00", description="3000 PSI slab on grade")
        wc_concrete = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Concrete",
            referenced_spec_sections=["033000"],
            work_included_items=["Slab on grade"],
        )
        wc_metals = _make_wc(
            db_session, test_project.id,
            wc_number="05", title="Metals",
            referenced_spec_sections=["051200"],
            work_included_items=["Structural steel"],
        )

        rec = sm._tier1_csi_match(li, [wc_concrete, wc_metals])
        assert rec is not None
        assert rec.work_category_id == wc_concrete.id
        assert rec.tier == "csi_exact"
        assert rec.confidence == 1.0
        assert rec.spec_section_ref == "033000"

    def test_multi_division_wc_prefix_match(self, db_session, test_project):
        """WC with multiple referenced divisions — line item in one of them matches
        via the division prefix (non-exact, confidence 0.9)."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="03 31 00", description="Reinforced concrete walls",
        )
        wc_multi = _make_wc(
            db_session, test_project.id,
            wc_number="03A", title="Concrete & Masonry",
            referenced_spec_sections=["040500", "033000"],
            work_included_items=["Concrete walls", "Masonry"],
        )
        wc_other = _make_wc(
            db_session, test_project.id,
            wc_number="26", title="Electrical",
            referenced_spec_sections=["260500"],
            work_included_items=["Wiring"],
        )

        rec = sm._tier1_csi_match(li, [wc_multi, wc_other])
        assert rec is not None
        assert rec.work_category_id == wc_multi.id
        # Either 033000 exact (if it's picked first) or the division prefix match.
        assert rec.confidence >= 0.9


# ---------------------------------------------------------------------------
# Tier 2 — Fuzzy string match on title + work_included_items
# ---------------------------------------------------------------------------


class TestTier2FuzzyMatch:
    def test_fuzzy_above_threshold(self, db_session, test_project):
        """Line item description closely matches WC title+inclusion union."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="XX XX XX",  # unparseable — tier 1 skips
            description="cast in place concrete foundation walls",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="structural concrete",
            referenced_spec_sections=[],  # forces tier 2
            work_included_items=["cast in place concrete foundation walls and footings"],
        )

        rec = sm._tier2_fuzzy_match(li, [wc])
        assert rec is not None
        assert rec.tier == "spec_section_fuzzy"
        assert rec.confidence >= sm.FUZZY_THRESHOLD
        assert rec.work_category_id == wc.id

    def test_fuzzy_below_threshold_returns_none(self, db_session, test_project):
        """Description with no meaningful overlap to WC content → Tier 2 declines."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="XX XX XX",
            description="landscape irrigation sleeves",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="structural concrete",
            referenced_spec_sections=[],
            work_included_items=["slab on grade", "walls"],
        )

        rec = sm._tier2_fuzzy_match(li, [wc])
        assert rec is None


# ---------------------------------------------------------------------------
# Tier 3 — LLM semantic match
# ---------------------------------------------------------------------------


def _mock_llm_provider(content: str):
    """Build a provider whose complete() returns a stubbed LLMResponse-shaped object."""
    fake_resp = MagicMock()
    fake_resp.content = content
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=fake_resp)
    provider.health_check = AsyncMock(return_value=True)
    provider.provider_name = "mock"
    provider.model_name = "mock-model"
    return provider


class TestTier3LLMMatch:
    def test_llm_high_confidence_match_no_finding(self, db_session, test_project):
        """LLM returns 0.9 confidence → match recorded, no partial_coverage finding."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="XX XX XX", description="exotic custom work",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="99", title="Special Construction",
            referenced_spec_sections=[],
            work_included_items=["custom fabrication"],
        )
        provider = _mock_llm_provider(
            '[{"line_item_id": ' + str(li.id)
            + ', "work_category_id": ' + str(wc.id)
            + ', "confidence": 0.9, "reason": "matches custom fab scope"}]'
        )

        with patch(
            "apex.backend.services.llm_provider.get_llm_provider",
            return_value=provider,
        ):
            findings = sm.match_scope_to_takeoff(test_project.id, db_session)

        # No partial_coverage, no out_of_scope for li; only in_scope_not_estimated
        # for the wc's inclusion (because wc.id IS in matched_wc_ids when li matches).
        # Matched WC is excluded from in_scope_not_estimated emission.
        assert not any(f.finding_type == "estimated_out_of_scope" for f in findings)
        assert not any(f.finding_type == "partial_coverage" for f in findings)
        assert not any(f.finding_type == "in_scope_not_estimated" for f in findings)

    def test_llm_low_confidence_creates_partial_coverage_info(self, db_session, test_project):
        """LLM returns 0.6 confidence — matcher records match BUT emits a
        partial_coverage finding with severity=INFO for estimator review."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="XX XX XX", description="ambiguous wall feature",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="09", title="Finishes",
            referenced_spec_sections=[],
            work_included_items=["interior finishes"],
        )
        provider = _mock_llm_provider(
            '[{"line_item_id": ' + str(li.id)
            + ', "work_category_id": ' + str(wc.id)
            + ', "confidence": 0.6, "reason": "tentative — could be 09 or 10"}]'
        )

        with patch(
            "apex.backend.services.llm_provider.get_llm_provider",
            return_value=provider,
        ):
            findings = sm.match_scope_to_takeoff(test_project.id, db_session)

        partials = [f for f in findings if f.finding_type == "partial_coverage"]
        assert len(partials) == 1
        assert partials[0].severity == "INFO"
        assert partials[0].match_tier == "llm_semantic"
        assert partials[0].confidence == 0.6
        assert partials[0].estimate_line_id == li.id
        assert partials[0].work_category_id == wc.id


# ---------------------------------------------------------------------------
# Finding emission
# ---------------------------------------------------------------------------


class TestFindingEmission:
    def test_unmatched_after_all_tiers_emits_out_of_scope(self, db_session, test_project):
        """Line item that nothing matches → estimated_out_of_scope WARNING."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="32 90 00", description="landscape irrigation",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="structural concrete",
            referenced_spec_sections=["033000"],
            work_included_items=["slab on grade"],
        )
        # LLM says "no match" (wc_id=null)
        provider = _mock_llm_provider(
            '[{"line_item_id": ' + str(li.id)
            + ', "work_category_id": null, '
            + '"confidence": 0.0, "reason": "no WC fits"}]'
        )

        with patch(
            "apex.backend.services.llm_provider.get_llm_provider",
            return_value=provider,
        ):
            findings = sm.match_scope_to_takeoff(test_project.id, db_session)

        oos = [f for f in findings if f.finding_type == "estimated_out_of_scope"]
        assert len(oos) >= 1
        matched = [f for f in oos if f.estimate_line_id == li.id]
        assert len(matched) == 1
        assert matched[0].severity == "WARNING"
        assert matched[0].work_category_id is None
        assert "did not match any published WorkCategory" in matched[0].rationale
        # The unmatched WC should also surface as in_scope_not_estimated for its inclusion
        assert any(
            f.finding_type == "in_scope_not_estimated" and f.work_category_id == wc.id
            for f in findings
        )

    def test_wc_with_no_matches_emits_in_scope_finding_per_inclusion(
        self, db_session, test_project
    ):
        """WC with zero matched line items → one in_scope_not_estimated per inclusion."""
        est = _make_estimate(db_session, test_project.id)
        # No line items in this estimate.
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="26", title="Electrical",
            referenced_spec_sections=["260500"],
            work_included_items=["power distribution", "lighting", "grounding"],
        )

        findings = sm.match_scope_to_takeoff(test_project.id, db_session)
        in_scope = [
            f for f in findings
            if f.finding_type == "in_scope_not_estimated" and f.work_category_id == wc.id
        ]
        assert len(in_scope) == 3
        assert all(f.severity == "WARNING" for f in in_scope)
        assert all(f.source == "rule" for f in in_scope)
        # spec_section_ref populated from first referenced CSI
        assert all(f.spec_section_ref == "260500" for f in in_scope)
        # estimate_id exists to silence pyflakes (and to make sure setup ran)
        assert est.id is not None

    def test_explicit_exclusion_conflict_emits_error(self, db_session, test_project):
        """Line item matches WC scope but WC explicitly excludes that work →
        estimated_out_of_scope finding with severity=ERROR."""
        est = _make_estimate(db_session, test_project.id)
        li = _make_line(
            db_session, est.id,
            csi_code="03 30 00",
            description="concrete cutting and coring",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Structural Concrete",
            referenced_spec_sections=["033000"],
            work_included_items=["cast in place concrete"],
            related_work_by_others=["concrete cutting and coring"],
        )

        findings = sm.match_scope_to_takeoff(test_project.id, db_session)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 1
        assert errors[0].finding_type == "estimated_out_of_scope"
        assert errors[0].estimate_line_id == li.id
        assert errors[0].work_category_id == wc.id
        assert "explicitly excludes" in errors[0].rationale


# ---------------------------------------------------------------------------
# Orchestration — upstream-failure skip
# ---------------------------------------------------------------------------


class TestOrchestratorSkip:
    def test_agent_35_skipped_when_upstream_failed(self, db_session, test_project):
        """Agent 3.5 is registered in AGENT_DEFINITIONS and can be logged as
        skipped via the same _log_skipped path the orchestrator uses after an
        upstream failure — this confirms the pipeline's stop-on-failure loop
        will cover Agent 3.5 since 35 is in pipeline_agents."""
        assert 35 in AGENT_DEFINITIONS
        assert AGENT_DEFINITIONS[35][0] == "Scope Matcher Agent"

        orch = AgentOrchestrator(db_session, test_project.id)
        orch._log_skipped("Scope Matcher Agent", 35, reason="Agent 3 failed")

        log = (
            db_session.query(AgentRunLog)
            .filter(
                AgentRunLog.project_id == test_project.id,
                AgentRunLog.agent_number == 35,
            )
            .one()
        )
        assert log.status == "skipped"
        assert "Agent 3 failed" in (log.output_summary or "")


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/gap-findings
# ---------------------------------------------------------------------------


class TestGapFindingsAPI:
    def test_empty_list_when_never_run(self, client, auth_headers, test_project):
        """Endpoint returns 200 with empty grouped findings when Agent 3.5
        has never populated the table for this project."""
        res = client.get(
            f"/api/projects/{test_project.id}/gap-findings",
            headers=auth_headers,
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["success"] is True
        assert payload["data"]["total"] == 0
        assert payload["data"]["findings"] == {
            "in_scope_not_estimated": [],
            "estimated_out_of_scope": [],
            "partial_coverage": [],
        }
        assert payload["data"]["severity_filter"] is None

    def test_severity_filter_returns_only_matching_subset(
        self, client, auth_headers, db_session, test_project
    ):
        """?severity=ERROR returns only ERROR-severity findings."""
        # Seed one ERROR, one WARNING, one INFO directly
        db_session.add_all(
            [
                GapFinding(
                    project_id=test_project.id,
                    finding_type="estimated_out_of_scope",
                    work_category_id=None,
                    estimate_line_id=None,
                    spec_section_ref=None,
                    match_tier="csi_exact",
                    confidence=1.0,
                    rationale="ERROR row",
                    source="rule",
                    severity="ERROR",
                ),
                GapFinding(
                    project_id=test_project.id,
                    finding_type="in_scope_not_estimated",
                    work_category_id=None,
                    estimate_line_id=None,
                    spec_section_ref=None,
                    match_tier="csi_exact",
                    confidence=1.0,
                    rationale="WARNING row",
                    source="rule",
                    severity="WARNING",
                ),
                GapFinding(
                    project_id=test_project.id,
                    finding_type="partial_coverage",
                    work_category_id=None,
                    estimate_line_id=None,
                    spec_section_ref=None,
                    match_tier="llm_semantic",
                    confidence=0.6,
                    rationale="INFO row",
                    source="llm",
                    severity="INFO",
                ),
            ]
        )
        db_session.commit()

        res = client.get(
            f"/api/projects/{test_project.id}/gap-findings?severity=ERROR",
            headers=auth_headers,
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["data"]["total"] == 1
        assert payload["data"]["severity_filter"] == "ERROR"
        # Flatten grouped view
        all_rows = [
            row
            for rows in payload["data"]["findings"].values()
            for row in rows
        ]
        assert len(all_rows) == 1
        assert all_rows[0]["severity"] == "ERROR"
        assert all_rows[0]["rationale"] == "ERROR row"
