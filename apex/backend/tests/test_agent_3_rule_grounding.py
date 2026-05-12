"""Tests for Spec 19E.6.2 — Agent 3 rule grounding integration.

Covers:
  - LLMGapItem contract accepts rule_id (valid, absent, and bogus)
  - _build_user_prompt includes rule grounding header and all 25 rule IDs
"""

from __future__ import annotations

import json

import pytest

from apex.backend.agents.agent_3_gap_analysis import LLMGapItem, _build_user_prompt
from apex.backend.agents.tools.domain_gap_rules import ALL_DOMAIN_RULES

_MINIMAL_SECTIONS = [
    {"division_number": "03", "section_number": "03 30 00", "title": "Cast-in-Place Concrete"}
]


class TestLLMGapItemContract:
    def test_accepts_valid_rule_id(self):
        item = LLMGapItem.model_validate(
            {
                "description": "Missing vapor barrier under SOG",
                "severity": "critical",
                "affected_csi_division": "03",
                "recommendation": "Add to concrete scope",
                "gap_type": "missing_division",
                "rule_id": "CGR-001",
            }
        )
        assert item.rule_id == "CGR-001"

    def test_accepts_no_rule_id(self):
        item = LLMGapItem.model_validate(
            {
                "description": "No Division 22 Plumbing in spec",
                "severity": "medium",
                "affected_csi_division": "22",
                "recommendation": "Confirm plumbing scope",
                "gap_type": "missing_division",
            }
        )
        assert item.rule_id is None

    def test_accepts_bogus_rule_id(self):
        """LLMGapItem accepts any string as rule_id — validation is Spec 19E.6.3's job."""
        item = LLMGapItem.model_validate(
            {
                "description": "Some gap",
                "severity": "low",
                "affected_csi_division": "05",
                "recommendation": "Review scope",
                "gap_type": "implied_scope",
                "rule_id": "FAKE-999",
            }
        )
        assert item.rule_id == "FAKE-999"


class TestPromptAssembly:
    def test_grounding_header_present(self):
        prompt = _build_user_prompt(_MINIMAL_SECTIONS)
        assert "DOMAIN RULES (for citation only" in prompt

    def test_all_25_rule_ids_in_prompt(self):
        prompt = _build_user_prompt(_MINIMAL_SECTIONS)
        for rule in ALL_DOMAIN_RULES:
            assert rule.id in prompt, f"Rule {rule.id} missing from assembled prompt"

    def test_25_rules_total(self):
        assert len(ALL_DOMAIN_RULES) == 25

    def test_grounding_is_valid_json_embedded(self):
        prompt = _build_user_prompt(_MINIMAL_SECTIONS)
        # Extract the JSON portion after the header line
        header = "DOMAIN RULES (for citation only — do NOT draft cost ranges or responsibility text):\n"
        assert header in prompt
        after_header = prompt[prompt.index(header) + len(header):]
        json_end = after_header.index("\n\n")
        grounding_json = after_header[:json_end]
        parsed = json.loads(grounding_json)
        assert isinstance(parsed, list)
        assert len(parsed) == 25

    def test_spec_context_prefix_preserved(self):
        prompt = _build_user_prompt(_MINIMAL_SECTIONS, spec_context="SPEC REF: some text")
        assert prompt.startswith("SPEC REF: some text")
