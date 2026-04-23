"""Tests for Agent 3.5 — Scope Matcher (Sprint 18.3.2, rewritten in 18.4.1 Part A).

Covers:
  Tier 1 (CSI exact / division prefix) — 2 tests
  Tier 2 (fuzzy string above/below threshold) — 2 tests
  Tier 3 (LLM high/low confidence) — 2 tests
  Finding emission (unmatched, uncovered inclusion, exclusion conflict) — 3 tests
  Fresh-pipeline regression guard — 1 test
  Orchestration (upstream-failure skip log) — 1 test
  API (empty response + severity filter) — 2 tests
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.work_category import WorkCategory
from apex.backend.services import scope_matcher as sm
from apex.backend.services.agent_orchestrator import AGENT_DEFINITIONS, AgentOrchestrator

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_takeoff(db, project_id: int, **kw) -> TakeoffItemV2:
    """Build a TakeoffItemV2 row. `activity` is NOT NULL on the model;
    `csi_code` is nullable. row_number is NOT NULL — defaults to 1, but tests
    creating multiple rows in the same project should pass distinct values."""
    defaults = {
        "project_id": project_id,
        "row_number": 1,
        "activity": "Cast-in-place concrete",
        "csi_code": "03 30 00",
        "quantity": 100.0,
        "unit": "CY",
    }
    defaults.update(kw)
    ti = TakeoffItemV2(**defaults)
    db.add(ti)
    db.commit()
    db.refresh(ti)
    return ti


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
        """Takeoff CSI 03 30 00 matches WC with referenced_spec_sections=['033000']."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="03 30 00", activity="3000 PSI slab on grade",
        )
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
        """WC with multiple referenced divisions — takeoff item in one of them matches
        via the division prefix (non-exact, confidence 0.9)."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="03 31 00", activity="Reinforced concrete walls",
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
        """Takeoff activity closely matches WC title+inclusion union."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="XX XX XX",  # unparseable — tier 1 skips
            activity="cast in place concrete foundation walls",
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
        """Activity with no meaningful overlap to WC content → Tier 2 declines."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="XX XX XX",
            activity="landscape irrigation sleeves",
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
# Tier 2.5 — Activity-title fuzzy match (Sprint 18.4.1 Part D)
# ---------------------------------------------------------------------------


class TestTier25ActivityTitleFuzzy:
    def test_tier_2_5_activity_title_fuzzy_fires(self, db_session, test_project):
        """Activity name overlaps a WC inclusion line closely enough to
        clear the 0.55 threshold. Record cites the matched inclusion."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code=None,  # no CSI → Tier 1 skips
            activity="Senior Project Manager",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="00", title="General Conditions",
            referenced_spec_sections=[],  # force Tier 2 to miss on haystack
            work_included_items=[
                "Provide senior project manager oversight on site",
                "Daily safety coordination",
            ],
        )

        rec = sm._tier2_5_activity_title_fuzzy_match(li, [wc])
        assert rec is not None
        assert rec.tier == "activity_title_fuzzy"
        assert rec.source == "rule"
        assert rec.confidence >= sm.ACTIVITY_TITLE_FUZZY_THRESHOLD
        assert rec.work_category_id == wc.id
        # Rationale cites the matched inclusion text
        assert "senior project manager oversight" in rec.rationale.lower()

    def test_tier_2_5_skipped_if_tier_1_matched(self, db_session, test_project):
        """When Tier 1 CSI matches, later tiers must not overwrite the
        match — first-match-wins across tiers. End-to-end check via the
        full match loop: attribution tier should be csi_exact, not
        activity_title_fuzzy."""
        from apex.backend.agents.agent_3_5_scope_matcher import run_scope_matcher_agent
        from apex.backend.models.line_item_wc_attribution import LineItemWCAttribution

        ti = _make_takeoff(
            db_session, test_project.id,
            csi_code="03 30 00",  # triggers Tier 1
            activity="cast in place concrete foundation",
        )
        _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Structural Concrete",
            referenced_spec_sections=["033000"],  # Tier 1 hit
            work_included_items=[
                # This inclusion would easily clear Tier 2.5 on its own,
                # proving that if Tier 2.5 ever ran it would emit a match.
                "cast in place concrete foundation walls and footings",
            ],
        )

        run_scope_matcher_agent(db_session, test_project.id)

        row = (
            db_session.query(LineItemWCAttribution)
            .filter(
                LineItemWCAttribution.project_id == test_project.id,
                LineItemWCAttribution.takeoff_item_id == ti.id,
            )
            .one()
        )
        # Tier 1 set the tier; Tier 2.5 must not have overwritten it.
        assert row.match_tier == "csi_exact"
        assert row.confidence == 1.0

    def test_tier_2_5_threshold_respected(self, db_session, test_project):
        """Activity with no meaningful overlap to inclusions (ratio < 0.55)
        returns None — Tier 2.5 declines so Tier 3 / unmatched can handle it."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code=None,
            activity="xyzzy plugh frotz",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Structural Concrete",
            referenced_spec_sections=[],
            work_included_items=[
                "cast in place concrete",
                "slab on grade",
                "walls and footings",
            ],
        )

        rec = sm._tier2_5_activity_title_fuzzy_match(li, [wc])
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
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="XX XX XX", activity="exotic custom work",
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
            findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)

        # No partial_coverage, no out_of_scope for li; only in_scope_not_estimated
        # for the wc's inclusion (because wc.id IS in matched_wc_ids when li matches).
        # Matched WC is excluded from in_scope_not_estimated emission.
        assert not any(f.finding_type == "estimated_out_of_scope" for f in findings)
        assert not any(f.finding_type == "partial_coverage" for f in findings)
        assert not any(f.finding_type == "in_scope_not_estimated" for f in findings)

    def test_llm_low_confidence_creates_partial_coverage_info(self, db_session, test_project):
        """LLM returns 0.6 confidence — matcher records match BUT emits a
        partial_coverage finding with severity=INFO for estimator review."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="XX XX XX", activity="ambiguous wall feature",
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
            findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)

        partials = [f for f in findings if f.finding_type == "partial_coverage"]
        assert len(partials) == 1
        assert partials[0].severity == "INFO"
        assert partials[0].match_tier == "llm_semantic"
        assert partials[0].confidence == 0.6
        # Post-18.4.1 Part B: takeoff_item_id is the live FK; estimate_line_id
        # stays NULL on new rows (retained for legacy consumers only).
        assert partials[0].estimate_line_id is None
        assert partials[0].takeoff_item_id == li.id
        assert partials[0].work_category_id == wc.id


# ---------------------------------------------------------------------------
# Finding emission
# ---------------------------------------------------------------------------


class TestFindingEmission:
    def test_unmatched_after_all_tiers_emits_out_of_scope(self, db_session, test_project):
        """Takeoff item that nothing matches → estimated_out_of_scope WARNING."""
        li = _make_takeoff(
            db_session, test_project.id,
            csi_code="32 90 00", activity="landscape irrigation",
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
            findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)

        oos = [f for f in findings if f.finding_type == "estimated_out_of_scope"]
        # Exactly one takeoff item in this project → one out-of-scope finding.
        assert len(oos) == 1
        assert oos[0].severity == "WARNING"
        assert oos[0].work_category_id is None
        # Post-18.4.1 Part B: takeoff_item_id populated, estimate_line_id NULL.
        assert oos[0].estimate_line_id is None
        assert oos[0].takeoff_item_id == li.id
        assert "did not match any published WorkCategory" in oos[0].rationale
        # The unmatched WC should also surface as in_scope_not_estimated for its inclusion
        assert any(
            f.finding_type == "in_scope_not_estimated" and f.work_category_id == wc.id
            for f in findings
        )

    def test_wc_with_no_matches_emits_in_scope_finding_per_inclusion(
        self, db_session, test_project
    ):
        """WC with zero matched takeoff items → one in_scope_not_estimated per inclusion."""
        # No takeoff items at all — only a WC.
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="26", title="Electrical",
            referenced_spec_sections=["260500"],
            work_included_items=["power distribution", "lighting", "grounding"],
        )

        findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)
        in_scope = [
            f for f in findings
            if f.finding_type == "in_scope_not_estimated" and f.work_category_id == wc.id
        ]
        assert len(in_scope) == 3
        assert all(f.severity == "WARNING" for f in in_scope)
        assert all(f.source == "rule" for f in in_scope)
        # spec_section_ref populated from first referenced CSI
        assert all(f.spec_section_ref == "260500" for f in in_scope)

    def test_explicit_exclusion_conflict_emits_error(self, db_session, test_project):
        """Takeoff matches WC scope but WC explicitly excludes that work →
        estimated_out_of_scope finding with severity=ERROR."""
        ti = _make_takeoff(
            db_session, test_project.id,
            csi_code="03 30 00",
            activity="concrete cutting and coring",
        )
        wc = _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Structural Concrete",
            referenced_spec_sections=["033000"],
            work_included_items=["cast in place concrete"],
            related_work_by_others=["concrete cutting and coring"],
        )

        findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 1
        assert errors[0].finding_type == "estimated_out_of_scope"
        # Post-18.4.1 Part B: takeoff_item_id populated, estimate_line_id NULL.
        assert errors[0].estimate_line_id is None
        assert errors[0].takeoff_item_id == ti.id
        assert errors[0].work_category_id == wc.id
        assert "explicitly excludes" in errors[0].rationale


# ---------------------------------------------------------------------------
# Fresh-pipeline regression guard (Sprint 18.4.1 Part A)
# ---------------------------------------------------------------------------


class TestFreshPipelineRegression:
    def test_matcher_fires_on_fresh_pipeline(self, db_session, test_project):
        """Regression guard for the pre-18.4.1 bug: matcher used to read
        EstimateLineItem, but Agent 6 (which creates Estimates) runs AFTER
        Agent 3.5 in the pipeline — so on every fresh pipeline the matcher
        silently returned []. After Part A the matcher reads TakeoffItemV2
        directly and must emit findings when takeoff data is present and
        no Estimate exists."""
        # TakeoffItemV2 rows present. NO Estimate / EstimateLineItem rows.
        _make_takeoff(
            db_session, test_project.id,
            row_number=1, csi_code="03 30 00", activity="Cast-in-place concrete",
        )
        _make_takeoff(
            db_session, test_project.id,
            row_number=2, csi_code="99 99 99", activity="Widget that matches nothing",
        )
        _make_wc(
            db_session, test_project.id,
            wc_number="03", title="Structural Concrete",
            referenced_spec_sections=["033000"],
            work_included_items=["cast in place concrete"],
        )

        findings, _attributions = sm.match_scope_to_takeoff(test_project.id, db_session)

        # Must NOT be empty (that's exactly the pre-fix bug).
        assert len(findings) > 0, (
            "Matcher returned 0 findings on a fresh pipeline with takeoff "
            "data present — 18.4.1 Part A regression."
        )
        # Expect the widget row to surface as estimated_out_of_scope.
        assert any(f.finding_type == "estimated_out_of_scope" for f in findings)


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
