"""Unit tests for diagnose_agent2_coverage pure functions.

Covers:
- infer_agent2_method (timing-bucket logic)
- infer_agent2b_method (timing-bucket logic)
- count_patterns (regex pattern counting)
- build_hypotheses (decision-tree logic)
"""

import pytest

from apex.backend.scripts.diagnose_agent2_coverage import (
    build_hypotheses,
    count_patterns,
    infer_agent2_method,
    infer_agent2b_method,
)


# ---------------------------------------------------------------------------
# test_inferred_method_classification
# ---------------------------------------------------------------------------


class TestInferAgent2Method:
    def test_none_returns_unknown(self):
        assert infer_agent2_method(None) == "UNKNOWN"

    def test_zero_is_fallback_regex(self):
        assert infer_agent2_method(0) == "FALLBACK_REGEX_LIKELY"

    def test_below_2000_is_fallback_regex(self):
        assert infer_agent2_method(55.0) == "FALLBACK_REGEX_LIKELY"
        assert infer_agent2_method(1999.9) == "FALLBACK_REGEX_LIKELY"

    def test_boundary_2000_is_ambiguous(self):
        assert infer_agent2_method(2000) == "AMBIGUOUS"

    def test_mid_range_is_ambiguous(self):
        assert infer_agent2_method(5000) == "AMBIGUOUS"

    def test_boundary_10000_is_ambiguous(self):
        assert infer_agent2_method(10000) == "AMBIGUOUS"

    def test_above_10000_is_llm_likely(self):
        assert infer_agent2_method(10001) == "LLM_LIKELY"
        assert infer_agent2_method(539133) == "LLM_LIKELY"


class TestInferAgent2bMethod:
    def test_none_returns_unknown(self):
        assert infer_agent2b_method(None) == "UNKNOWN"

    def test_zero_is_noop(self):
        assert infer_agent2b_method(0) == "NO_OP_OR_GATE_REJECTED"

    def test_below_100_is_noop(self):
        assert infer_agent2b_method(20.9) == "NO_OP_OR_GATE_REJECTED"
        assert infer_agent2b_method(99.9) == "NO_OP_OR_GATE_REJECTED"

    def test_boundary_100_is_rule_based(self):
        assert infer_agent2b_method(100) == "RULE_BASED_LIKELY"

    def test_mid_rule_based(self):
        assert infer_agent2b_method(500) == "RULE_BASED_LIKELY"

    def test_boundary_999_is_rule_based(self):
        assert infer_agent2b_method(999.9) == "RULE_BASED_LIKELY"

    def test_1000_and_above_is_llm_likely(self):
        assert infer_agent2b_method(1000) == "LLM_LIKELY"
        assert infer_agent2b_method(9000) == "LLM_LIKELY"


# ---------------------------------------------------------------------------
# test_csi_pattern_counting
# ---------------------------------------------------------------------------


class TestCountPatterns:
    def test_empty_string(self):
        result = count_patterns("")
        assert result == {
            "csi_section_headers": 0,
            "bare_site_civil_6digit": 0,
            "wc_headings": 0,
            "work_category_no": 0,
            "division_headers": 0,
        }

    def test_csi_section_headers(self):
        text = "SECTION 03 30 00 some text SECTION 26 05 19 more text"
        assert count_patterns(text)["csi_section_headers"] == 2

    def test_bare_site_civil_numbers(self):
        # 03, 31, 32, 33 prefix followed by 4 digits
        text = "see 311000 and 320000 and 033000 and 260000"
        r = count_patterns(text)
        assert r["bare_site_civil_6digit"] == 3  # 311000, 320000, 033000 — not 260000

    def test_wc_headings_various_formats(self):
        text = "WC-01 Earthwork\nWC 02A Concrete\nWC-14 Mechanical"
        assert count_patterns(text)["wc_headings"] == 3

    def test_work_category_no(self):
        text = "Work Category No. 5 and Work Category No 12"
        assert count_patterns(text)["work_category_no"] == 2

    def test_division_headers(self):
        text = "DIVISION 14\nDIVISION 23\nDIVISION 26"
        assert count_patterns(text)["division_headers"] == 3

    def test_wc_no_false_positives(self):
        # "WC" in other context should not match WC-XX pattern
        text = "NWCA convention and WC fields in the database"
        assert count_patterns(text)["wc_headings"] == 0

    def test_bare_6digit_word_boundary(self):
        # Embedded in longer number should NOT match
        text = "1311000 and 03300099"
        assert count_patterns(text)["bare_site_civil_6digit"] == 0


# ---------------------------------------------------------------------------
# test_hypothesis_generation
# ---------------------------------------------------------------------------


class TestBuildHypotheses:
    def _signals(self, wc_headings: int = 0, site_civil: bool = False) -> dict:
        return {
            1: {"wc_headings": wc_headings, "bare_site_civil_6digit": 0},
            "_any_site_civil_text": site_civil,
        }

    def test_agent2_regex_fallback_with_wc_patterns(self):
        hyps = build_hypotheses(
            agent2_method="FALLBACK_REGEX_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={},
            agent2b_runs=[{"run_id": 1, "status": "completed", "duration_ms": 20}],
            wc_counts=[],
            raw_text_signals=self._signals(wc_headings=10),
        )
        assert any("regex fallback" in h for h in hyps)

    def test_agent2_regex_fallback_no_wc_no_hypothesis(self):
        hyps = build_hypotheses(
            agent2_method="FALLBACK_REGEX_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={},
            agent2b_runs=[{"run_id": 1}],
            wc_counts=[],
            raw_text_signals=self._signals(wc_headings=0),
        )
        assert not any("regex fallback" in h for h in hyps)

    def test_agent2_llm_dropped_site_civil_with_text(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={"14": 1, "26": 5},  # missing 31/32/33
            agent2b_runs=[{"run_id": 1}],
            wc_counts=[],
            raw_text_signals=self._signals(site_civil=True),
        )
        assert any("dropped Div" in h or "31" in h for h in hyps)

    def test_agent2_llm_all_divs_present(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={"14": 1, "26": 5, "31": 2, "32": 3, "33": 3},
            agent2b_runs=[{"run_id": 1}],
            wc_counts=[],
            raw_text_signals=self._signals(site_civil=True),
        )
        assert any("working as designed" in h for h in hyps)

    def test_agent2b_never_ran(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="UNKNOWN",
            agent2_coverage={"26": 1},
            agent2b_runs=[],
            wc_counts=[],
            raw_text_signals=self._signals(),
        )
        assert any("never ran" in h for h in hyps)

    def test_agent2b_noop_with_high_wc_count(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={"26": 1},
            agent2b_runs=[{"run_id": 1, "duration_ms": 20}],
            wc_counts=[],
            raw_text_signals=self._signals(wc_headings=12),
        )
        assert any("classifier gate rejected" in h for h in hyps)

    def test_agent2b_noop_no_work_scopes_doc(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="NO_OP_OR_GATE_REJECTED",
            agent2_coverage={"26": 1},
            agent2b_runs=[{"run_id": 1, "duration_ms": 20}],
            wc_counts=[],
            raw_text_signals=self._signals(wc_headings=2),  # under threshold
        )
        assert any("not have been uploaded" in h or "NO-OP" in h for h in hyps)

    def test_agent2b_llm_ran_but_nothing_persisted(self):
        hyps = build_hypotheses(
            agent2_method="LLM_LIKELY",
            agent2b_method="LLM_LIKELY",
            agent2_coverage={"26": 1},
            agent2b_runs=[{"run_id": 1, "duration_ms": 5000}],
            wc_counts=[],  # empty — nothing written
            raw_text_signals=self._signals(),
        )
        assert any("persisted nothing" in h for h in hyps)

    def test_returns_list_type(self):
        hyps = build_hypotheses(
            agent2_method="AMBIGUOUS",
            agent2b_method="AMBIGUOUS",
            agent2_coverage={"26": 1},
            agent2b_runs=[{"run_id": 1}],
            wc_counts=[],
            raw_text_signals=self._signals(),
        )
        assert isinstance(hyps, list)
