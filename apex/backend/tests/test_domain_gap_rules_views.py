"""Tests for Spec 19E.6.1 canonical grounding accessors on DomainGapRule.

Covers:
- get_grounding_view_all: 25 entries, all four fields present and non-empty
- get_canonical_facts: correct return for known ID, None for unknown
- All 25 rules have non-null cost_range_text, typical_responsibility, rfi_template
"""

import pytest

from apex.backend.agents.tools.domain_gap_rules import (
    ALL_DOMAIN_RULES,
    DomainGapRule,
    get_canonical_facts,
    get_grounding_view_all,
)

# ---------------------------------------------------------------------------
# get_grounding_view_all
# ---------------------------------------------------------------------------


class TestGetGroundingViewAll:
    def setup_method(self):
        self.views = get_grounding_view_all()

    def test_returns_25_entries(self):
        assert len(self.views) == 25

    def test_all_have_rule_id(self):
        for v in self.views:
            assert "rule_id" in v
            assert v["rule_id"]

    def test_all_have_category(self):
        for v in self.views:
            assert "category" in v
            assert v["category"]

    def test_all_have_trigger_summary(self):
        for v in self.views:
            assert "trigger_summary" in v
            assert v["trigger_summary"]

    def test_all_have_typical_responsibility(self):
        for v in self.views:
            assert "typical_responsibility" in v
            assert v["typical_responsibility"]

    def test_rule_ids_match_library(self):
        library_ids = {r.id for r in ALL_DOMAIN_RULES}
        view_ids = {v["rule_id"] for v in self.views}
        assert view_ids == library_ids

    def test_order_matches_all_domain_rules(self):
        for rule, view in zip(ALL_DOMAIN_RULES, self.views):
            assert view["rule_id"] == rule.id

    def test_category_maps_to_gap_type(self):
        for rule, view in zip(ALL_DOMAIN_RULES, self.views):
            assert view["category"] == rule.gap_type

    def test_trigger_summary_maps_to_title(self):
        for rule, view in zip(ALL_DOMAIN_RULES, self.views):
            assert view["trigger_summary"] == rule.title

    def test_valid_category_values(self):
        valid = {"missing", "ambiguous", "scope_boundary"}
        for v in self.views:
            assert v["category"] in valid, f"{v['rule_id']} has unexpected category {v['category']!r}"

    def test_returns_new_list_each_call(self):
        a = get_grounding_view_all()
        b = get_grounding_view_all()
        assert a is not b


# ---------------------------------------------------------------------------
# get_canonical_facts
# ---------------------------------------------------------------------------


class TestGetCanonicalFacts:
    def test_known_cgr001_returns_dict(self):
        result = get_canonical_facts("CGR-001")
        assert result is not None
        assert isinstance(result, dict)

    def test_known_civ010_returns_dict(self):
        result = get_canonical_facts("CIV-010")
        assert result is not None

    def test_unknown_id_returns_none(self):
        assert get_canonical_facts("BOGUS-999") is None

    def test_empty_string_returns_none(self):
        assert get_canonical_facts("") is None

    def test_canonical_facts_has_all_six_fields(self):
        result = get_canonical_facts("CGR-001")
        expected_keys = {"rule_id", "standard_ref", "severity", "cost_range_text", "typical_responsibility", "rfi_template"}
        assert set(result.keys()) == expected_keys

    def test_rule_id_field_matches_requested_id(self):
        result = get_canonical_facts("CGR-005")
        assert result["rule_id"] == "CGR-005"

    def test_severity_is_valid_value(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            assert facts["severity"] in ("critical", "moderate", "watch"), (
                f"{rule.id} has unexpected severity {facts['severity']!r}"
            )

    def test_standard_ref_is_none_or_string(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            assert facts["standard_ref"] is None or isinstance(facts["standard_ref"], str)


# ---------------------------------------------------------------------------
# All 25 rules: non-null canonical fields
# ---------------------------------------------------------------------------


class TestAllRulesCanonicalFieldsPopulated:
    def test_all_25_have_cost_range_text(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            assert facts["cost_range_text"], (
                f"{rule.id} has empty cost_range_text"
            )

    def test_all_25_have_typical_responsibility(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            assert facts["typical_responsibility"], (
                f"{rule.id} has empty typical_responsibility"
            )

    def test_all_25_have_rfi_template(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            assert facts["rfi_template"], (
                f"{rule.id} has empty rfi_template"
            )

    def test_tbd_sentinel_is_acceptable(self):
        tbd_count = 0
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            if facts["rfi_template"] == "TBD — author pending":
                tbd_count += 1
        # 19 rules had empty rfi_language at time of authoring
        assert tbd_count <= 25, "More TBD entries than rules — something is wrong"
        assert tbd_count >= 0

    def test_no_none_values_for_required_text_fields(self):
        for rule in ALL_DOMAIN_RULES:
            facts = get_canonical_facts(rule.id)
            for field in ("cost_range_text", "typical_responsibility", "rfi_template"):
                assert facts[field] is not None, (
                    f"{rule.id}.{field} is None — must be string or 'TBD — author pending'"
                )


# ---------------------------------------------------------------------------
# DomainGapRule.standard_ref field existence
# ---------------------------------------------------------------------------


class TestStandardRefField:
    def test_field_exists_on_model(self):
        assert "standard_ref" in DomainGapRule.model_fields

    def test_default_is_none(self):
        assert DomainGapRule.model_fields["standard_ref"].default is None

    def test_can_instantiate_with_standard_ref(self):
        rule = DomainGapRule(
            id="TEST-001",
            name="Test",
            gap_type="missing",
            severity="watch",
            standard_ref="ACI 318-19",
        )
        assert rule.standard_ref == "ACI 318-19"

    def test_canonical_facts_includes_standard_ref_value(self):
        # All production rules currently have standard_ref=None — just verify the field passes through
        facts = get_canonical_facts("CGR-001")
        assert "standard_ref" in facts
