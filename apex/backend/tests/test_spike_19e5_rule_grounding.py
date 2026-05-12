"""Unit tests for spike_19e5_rule_grounding pure functions.

Covers:
- load_rule_library: returns 25 rules with correct IDs and grounding fields
- classify_finding: valid_cite / hallucinated / no_cite on synthetic findings
- compute_metrics: correct aggregation
"""

import pytest

from apex.backend.scripts.spike_19e5_rule_grounding import (
    classify_finding,
    compute_metrics,
    load_rule_library,
)


# ---------------------------------------------------------------------------
# load_rule_library
# ---------------------------------------------------------------------------


class TestLoadRuleLibrary:
    def test_returns_25_rules(self):
        grounding, valid_ids = load_rule_library()
        assert len(grounding) == 25

    def test_valid_id_set_has_25_entries(self):
        _, valid_ids = load_rule_library()
        assert len(valid_ids) == 25

    def test_15_cgr_rules(self):
        _, valid_ids = load_rule_library()
        cgr = {rid for rid in valid_ids if rid.startswith("CGR-")}
        assert len(cgr) == 15

    def test_10_civ_rules(self):
        _, valid_ids = load_rule_library()
        civ = {rid for rid in valid_ids if rid.startswith("CIV-")}
        assert len(civ) == 10

    def test_known_boundary_ids_present(self):
        _, valid_ids = load_rule_library()
        assert "CGR-001" in valid_ids
        assert "CGR-015" in valid_ids
        assert "CIV-001" in valid_ids
        assert "CIV-010" in valid_ids

    def test_grounding_items_have_required_fields(self):
        grounding, _ = load_rule_library()
        for item in grounding:
            assert "rule_id" in item
            assert "category" in item
            assert "trigger_summary" in item
            assert "typical_responsibility" in item

    def test_no_phantom_ids(self):
        _, valid_ids = load_rule_library()
        assert "CGR-000" not in valid_ids
        assert "CGR-016" not in valid_ids
        assert "CIV-000" not in valid_ids
        assert "CIV-011" not in valid_ids


# ---------------------------------------------------------------------------
# classify_finding
# ---------------------------------------------------------------------------


class TestClassifyFinding:
    def setup_method(self):
        _, self.valid_ids = load_rule_library()

    def test_missing_rule_id_field_is_no_cite(self):
        assert classify_finding({"description": "some gap"}, self.valid_ids) == "no_cite"

    def test_none_rule_id_is_no_cite(self):
        assert classify_finding({"rule_id": None}, self.valid_ids) == "no_cite"

    def test_empty_string_rule_id_is_no_cite(self):
        assert classify_finding({"rule_id": ""}, self.valid_ids) == "no_cite"

    def test_valid_cgr_id_is_valid_cite(self):
        assert classify_finding({"rule_id": "CGR-001"}, self.valid_ids) == "valid_cite"

    def test_valid_civ_id_is_valid_cite(self):
        assert classify_finding({"rule_id": "CIV-010"}, self.valid_ids) == "valid_cite"

    def test_all_cgr_ids_are_valid_cite(self):
        for i in range(1, 16):
            rid = f"CGR-{i:03d}"
            result = classify_finding({"rule_id": rid}, self.valid_ids)
            assert result == "valid_cite", f"Expected valid_cite for {rid}, got {result}"

    def test_all_civ_ids_are_valid_cite(self):
        for i in range(1, 11):
            rid = f"CIV-{i:03d}"
            result = classify_finding({"rule_id": rid}, self.valid_ids)
            assert result == "valid_cite", f"Expected valid_cite for {rid}, got {result}"

    def test_nonexistent_cgr_id_is_hallucinated(self):
        assert classify_finding({"rule_id": "CGR-099"}, self.valid_ids) == "hallucinated"

    def test_nonexistent_civ_id_is_hallucinated(self):
        assert classify_finding({"rule_id": "CIV-099"}, self.valid_ids) == "hallucinated"

    def test_fabricated_prefix_is_hallucinated(self):
        assert classify_finding({"rule_id": "VAPOR-001"}, self.valid_ids) == "hallucinated"
        assert classify_finding({"rule_id": "SCOPE-003"}, self.valid_ids) == "hallucinated"

    def test_cgr_000_is_hallucinated(self):
        assert classify_finding({"rule_id": "CGR-000"}, self.valid_ids) == "hallucinated"

    def test_cgr_016_is_hallucinated(self):
        assert classify_finding({"rule_id": "CGR-016"}, self.valid_ids) == "hallucinated"


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def setup_method(self):
        _, self.valid_ids = load_rule_library()

    def _make_findings(self, valid: int = 0, hallucinated: int = 0, no_cite: int = 0) -> list[dict]:
        findings = []
        for _ in range(valid):
            findings.append({"description": "gap", "rule_id": "CGR-001"})
        for _ in range(hallucinated):
            findings.append({"description": "gap", "rule_id": "FAKE-999"})
        for _ in range(no_cite):
            findings.append({"description": "gap"})
        return findings

    def test_empty_findings(self):
        metrics, classified = compute_metrics([], self.valid_ids)
        assert metrics["total_findings"] == 0
        assert metrics["valid_cite_count"] == 0
        assert metrics["valid_cite_rate_overall"] == 0.0
        assert metrics["valid_cite_rate_among_cited"] == 0.0
        assert metrics["hallucinated_rate"] == 0.0
        assert classified == []

    def test_all_no_cite(self):
        findings = self._make_findings(no_cite=5)
        metrics, classified = compute_metrics(findings, self.valid_ids)
        assert metrics["total_findings"] == 5
        assert metrics["valid_cite_count"] == 0
        assert metrics["no_cite_count"] == 5
        assert metrics["hallucinated_count"] == 0
        assert metrics["valid_cite_rate_among_cited"] == 0.0
        assert all(c["classification"] == "no_cite" for c in classified)

    def test_all_valid_cites(self):
        findings = self._make_findings(valid=10)
        metrics, classified = compute_metrics(findings, self.valid_ids)
        assert metrics["total_findings"] == 10
        assert metrics["valid_cite_count"] == 10
        assert metrics["valid_cite_rate_overall"] == 1.0
        assert metrics["valid_cite_rate_among_cited"] == 1.0
        assert metrics["hallucinated_rate"] == 0.0

    def test_all_hallucinated(self):
        findings = self._make_findings(hallucinated=4)
        metrics, _ = compute_metrics(findings, self.valid_ids)
        assert metrics["hallucinated_count"] == 4
        assert metrics["hallucinated_rate"] == 1.0
        assert metrics["valid_cite_rate_among_cited"] == 0.0

    def test_mixed_counts(self):
        # 8 valid, 1 hallucinated, 1 no_cite = 10 total; cited = 9
        findings = self._make_findings(valid=8, hallucinated=1, no_cite=1)
        metrics, _ = compute_metrics(findings, self.valid_ids)
        assert metrics["total_findings"] == 10
        assert metrics["valid_cite_count"] == 8
        assert metrics["hallucinated_count"] == 1
        assert metrics["no_cite_count"] == 1
        assert metrics["valid_cite_rate_among_cited"] == round(8 / 9, 4)
        assert metrics["hallucinated_rate"] == round(1 / 10, 4)

    def test_classified_length_matches_total(self):
        findings = self._make_findings(valid=3, hallucinated=2, no_cite=5)
        metrics, classified = compute_metrics(findings, self.valid_ids)
        assert len(classified) == metrics["total_findings"]

    def test_classified_items_have_expected_keys(self):
        findings = self._make_findings(valid=1, hallucinated=1, no_cite=1)
        _, classified = compute_metrics(findings, self.valid_ids)
        for item in classified:
            assert "description" in item
            assert "rule_id" in item
            assert "classification" in item
            assert "rule_trigger_summary" in item

    def test_valid_cite_includes_trigger_summary(self):
        findings = [{"description": "gap", "rule_id": "CGR-001"}]
        _, classified = compute_metrics(findings, self.valid_ids)
        assert classified[0]["rule_trigger_summary"] is not None
        assert len(classified[0]["rule_trigger_summary"]) > 0

    def test_hallucinated_has_no_trigger_summary(self):
        findings = [{"description": "gap", "rule_id": "FAKE-999"}]
        _, classified = compute_metrics(findings, self.valid_ids)
        assert classified[0]["rule_trigger_summary"] is None
