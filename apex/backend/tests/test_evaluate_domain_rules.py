"""Unit tests for evaluate_domain_rules harness — pure function coverage only.

No live DB, no pipeline, no ORM. These tests exercise the three utility
functions that are the harness's core logic.
"""
from types import SimpleNamespace

import pytest

from apex.backend.scripts.evaluate_domain_rules import (
    compute_coverage_stats,
    extract_rule_id,
    filter_domain_rule_findings,
)


class TestExtractRuleId:
    def test_cgr_match(self):
        assert extract_rule_id("Some text\n\n[Rule ID: CGR-001]") == "CGR-001"

    def test_no_rule_id(self):
        assert extract_rule_id("Description without rule id") is None

    def test_civ_match(self):
        assert extract_rule_id("[Rule ID: CIV-007]") == "CIV-007"

    def test_lowercase_no_match(self):
        # "bogus" is all-lowercase — does not match [A-Z]+-\d+
        assert extract_rule_id("[Rule ID: bogus]") is None

    def test_none_input(self):
        assert extract_rule_id(None) is None

    def test_empty_string(self):
        assert extract_rule_id("") is None

    def test_tag_embedded_in_longer_text(self):
        desc = (
            "Concrete scope missing cold-weather protection procedures. "
            "Verify Division 01 vs 03 responsibility.\n\n[Rule ID: CGR-009]"
        )
        assert extract_rule_id(desc) == "CGR-009"

    def test_whitespace_between_colon_and_id(self):
        assert extract_rule_id("[Rule ID:  CGR-015]") == "CGR-015"


class TestFilterDomainRuleFindings:
    def _items(self, descriptions):
        return [SimpleNamespace(description=d) for d in descriptions]

    def test_keeps_only_rule_id_items(self):
        items = self._items([
            "Some gap [Rule ID: CGR-001]",
            "Generic checklist gap — no rule id here",
            None,
            "[Rule ID: CIV-003] earthwork gap text",
        ])
        result = filter_domain_rule_findings(items)
        assert len(result) == 2
        assert all("[Rule ID:" in i.description for i in result)

    def test_empty_list(self):
        assert filter_domain_rule_findings([]) == []

    def test_none_description_excluded(self):
        assert filter_domain_rule_findings(self._items([None, ""])) == []

    def test_all_items_have_rule_id(self):
        items = self._items(["[Rule ID: CGR-001] a", "[Rule ID: CIV-002] b"])
        assert len(filter_domain_rule_findings(items)) == 2

    def test_no_items_have_rule_id(self):
        items = self._items(["generic gap", "spec vs takeoff gap"])
        assert filter_domain_rule_findings(items) == []


class TestCoverageStats:
    def _rules(self, ids):
        return [SimpleNamespace(id=i) for i in ids]

    def test_basic_stats(self):
        rules = self._rules(["CGR-001", "CGR-002", "CGR-003"])
        findings = {"CGR-001": ["f1", "f2"], "CGR-003": ["f3"]}
        stats = compute_coverage_stats(findings, rules)
        assert stats["total_rules"] == 3
        assert stats["rules_fired"] == 2
        assert stats["rules_not_fired"] == 1
        assert stats["total_findings"] == 3

    def test_no_findings(self):
        rules = self._rules(["CGR-001", "CGR-002"])
        stats = compute_coverage_stats({}, rules)
        assert stats["rules_fired"] == 0
        assert stats["rules_not_fired"] == 2
        assert stats["total_findings"] == 0

    def test_all_rules_fired(self):
        rules = self._rules(["CGR-001", "CIV-001"])
        findings = {"CGR-001": ["f1"], "CIV-001": ["f2", "f3"]}
        stats = compute_coverage_stats(findings, rules)
        assert stats["rules_fired"] == 2
        assert stats["rules_not_fired"] == 0
        assert stats["total_findings"] == 3

    def test_distribution_counts(self):
        rules = self._rules(["CGR-001", "CGR-002"])
        findings = {"CGR-001": ["a", "b", "c"]}
        stats = compute_coverage_stats(findings, rules)
        assert stats["findings_per_rule_distribution"]["CGR-001"] == 3

    def test_empty_registry(self):
        stats = compute_coverage_stats({}, [])
        assert stats["total_rules"] == 0
        assert stats["rules_fired"] == 0
        assert stats["rules_not_fired"] == 0
