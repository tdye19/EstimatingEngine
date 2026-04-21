"""Tests for Sprint 17.2-v2 domain rules integration."""

from apex.backend.agents.tools.domain_gap_rules import (
    ALL_DOMAIN_RULES,
    CIVIL_GAP_RULES,
    CONCRETE_GAP_RULES,
    run_domain_rules,
)


def test_rule_count_is_25():
    assert len(ALL_DOMAIN_RULES) == 25
    assert len(CONCRETE_GAP_RULES) == 15
    assert len(CIVIL_GAP_RULES) == 10


def test_every_rule_has_cost_unit():
    for rule in ALL_DOMAIN_RULES:
        assert rule.cost_unit, f"Rule {rule.id} missing cost_unit"
        assert rule.cost_unit in {"SF", "CY", "LF", "SY", "each", "splice", "project"}


def test_cgr_010_does_not_fire_on_fly_ash_only():
    """Verify SCM false-positive fix — common modern mix shouldn't trigger."""
    sections = [{"section_number": "03 30 00", "division_number": "03"}]
    spec_text = "Concrete mix shall include fly ash and slag per sustainability requirements."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    assert not any(f["rule_id"] == "CGR-010" for f in findings), (
        "CGR-010 should not fire on generic SCM keywords after fix"
    )


def test_cgr_010_still_fires_on_high_strength():
    """Verify CGR-010 still fires on genuine specialty-mix triggers."""
    sections = [{"section_number": "03 30 00", "division_number": "03"}]
    spec_text = "10000 psi high-strength concrete mix required for columns."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    assert any(f["rule_id"] == "CGR-010" for f in findings), (
        "CGR-010 should still fire on high-strength keyword"
    )


def test_civ_001_cost_range_updated():
    """Verify CIV-001 high bound raised to 250000."""
    civ_001 = next((r for r in ALL_DOMAIN_RULES if r.id == "CIV-001"), None)
    assert civ_001 is not None
    assert civ_001.cost_impact_high == 250000


def test_vapor_barrier_fires_on_sog_no_vapor_scope():
    """CGR-001 — spec mentions vapor barrier but concrete scope excludes 03 15 05."""
    sections = [{"section_number": "03 31 09", "division_number": "03"}]
    spec_text = "Slab on grade with 15-mil vapor barrier per ASTM E1745."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    assert any(f["rule_id"] == "CGR-001" for f in findings)


def test_vapor_barrier_silent_when_scope_includes_it():
    """CGR-001 — should NOT fire when 03 15 05 is in scope."""
    sections = [
        {"section_number": "03 31 09", "division_number": "03"},
        {"section_number": "03 15 05", "division_number": "03"},
    ]
    spec_text = "Slab on grade with 15-mil vapor barrier."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    assert not any(f["rule_id"] == "CGR-001" for f in findings), (
        "CGR-001 should be silenced when 03 15 05 vapor barrier is in scope"
    )


def test_findings_include_cost_unit():
    """Every triggered finding must include cost_unit in output dict."""
    sections = [{"section_number": "03 31 09", "division_number": "03"}]
    spec_text = "Slab on grade with 15-mil vapor barrier."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    for f in findings:
        assert "cost_unit" in f, f"Finding missing cost_unit: {f}"
        assert f["cost_unit"] in {"SF", "CY", "LF", "SY", "each", "splice", "project"}


def test_findings_schema_compatible_with_gapreportitem():
    """Every finding has the fields GapReportItem needs."""
    sections = [{"section_number": "03 31 09", "division_number": "03"}]
    spec_text = "Slab on grade with 15-mil vapor barrier."
    findings = run_domain_rules(sections, spec_content_text=spec_text)
    assert len(findings) > 0
    for f in findings:
        assert f["division_number"]
        assert f["title"]
        assert f["gap_type"] in {"missing", "ambiguous", "conflicting", "scope_boundary"}
        assert f["severity"] in {"critical", "moderate", "watch"}


def test_zero_rules_on_empty_input():
    assert run_domain_rules([], "") == []
