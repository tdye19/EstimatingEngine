"""Tests for assembly_parameter_extractor (Sprint 18.2.2)."""

from __future__ import annotations

from apex.backend.services import assembly_parameter_extractor as ape

# ---------------------------------------------------------------------------
# is_division_03_section
# ---------------------------------------------------------------------------


def test_is_division_03_accepts_variants():
    assert ape.is_division_03_section("03 30 00") is True
    assert ape.is_division_03_section("033000") is True
    assert ape.is_division_03_section("03") is True
    assert ape.is_division_03_section("3") is True  # stripped leading zero
    assert ape.is_division_03_section("03 30 00.13") is True


def test_is_division_03_rejects_non_concrete():
    assert ape.is_division_03_section("04 20 00") is False
    assert ape.is_division_03_section("05 12 00") is False
    assert ape.is_division_03_section("31 10 00") is False  # "31" not "3X"
    assert ape.is_division_03_section("") is False
    assert ape.is_division_03_section(None) is False


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------


def test_regex_fallback_extracts_known_patterns():
    text = """
    PART 2 - PRODUCTS
    2.1 CONCRETE MATERIALS
    A. Portland Cement: ASTM C150, Type I/II.
    B. Reinforcing Steel: ASTM A615 Grade 60, deformed.
    2.2 CONCRETE MIXES
    A. Minimum compressive strength at 28 days: 4000 psi.
    B. Slump: 3-5 inches.
    C. Air content: 5-7% for exterior exposure.
    """
    result = ape.extract_assembly_parameters(text, csi_code="03 30 00", use_llm=False)
    p = result["parameters"]
    assert p["f_c_psi"]["value"] == 4000
    assert p["rebar_grade"]["value"] == "Grade 60"
    assert "Type" in p["cement_type"]["value"]
    assert "3" in p["slump_range_inches"]["value"]
    assert "5" in p["air_entrainment_pct"]["value"]
    assert result["extraction_method"] == "regex"


def test_regex_sanity_bounds_reject_garbage_psi():
    """Stray 4-digit numbers without 'psi' must not be captured."""
    text = "See drawing 1234 for details. Reinforcing: Grade 60."
    result = ape.extract_assembly_parameters(text, use_llm=False)
    assert "f_c_psi" not in result["parameters"]


def test_psi_under_1000_rejected_by_sanity():
    text = "Sealant shall withstand 500 psi pressure."
    result = ape.extract_assembly_parameters(text, use_llm=False)
    assert "f_c_psi" not in result["parameters"]


# ---------------------------------------------------------------------------
# Normalization — aggregate size
# ---------------------------------------------------------------------------


def test_aggregate_mm_conversion():
    entry = ape._normalize_parameter(
        "aggregate_max_size_inches",
        {"value": "19mm", "source_text": "19mm aggregate", "confidence": 0.9},
        warnings=[],
    )
    assert entry is not None
    assert 0.74 <= entry["value"] <= 0.76  # 19mm ~= 0.748 in


def test_aggregate_fraction_conversion():
    entry = ape._normalize_parameter(
        "aggregate_max_size_inches",
        {"value": "3/4", "source_text": "3/4 inch", "confidence": 0.9},
        warnings=[],
    )
    assert entry is not None
    assert entry["value"] == 0.75


# ---------------------------------------------------------------------------
# LLM failure -> regex fallback
# ---------------------------------------------------------------------------


def test_llm_failure_falls_back_to_regex(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("simulated LLM failure")

    monkeypatch.setattr(ape, "_llm_extract", boom)

    text = "Minimum 4000 psi concrete. Grade 60 rebar."
    result = ape.extract_assembly_parameters(text, csi_code="03 30 00", use_llm=True)
    assert result["extraction_method"] == "regex"
    assert any("LLM extraction failed" in w for w in result["warnings"])
    assert result["parameters"]["f_c_psi"]["value"] == 4000


def test_llm_partial_marks_method(monkeypatch):
    """LLM returned usable params but also warnings -> llm_partial."""

    async def partial(*args, **kwargs):
        return (
            {
                "f_c_psi": {
                    "value": 4000,
                    "source_text": "4000 psi",
                    "confidence": 0.9,
                },
            },
            ["Could not normalize rebar_grade: malformed LLM value"],
        )

    monkeypatch.setattr(ape, "_llm_extract", partial)
    result = ape.extract_assembly_parameters("dummy", csi_code="03 30 00", use_llm=True)
    assert result["extraction_method"] == "llm_partial"
    assert result["parameters"]["f_c_psi"]["value"] == 4000


def test_empty_parameters_returns_empty_dict():
    text = "This section is about doorknobs, not concrete."
    result = ape.extract_assembly_parameters(text, csi_code="08 71 00", use_llm=False)
    assert result["parameters"] == {}


# ---------------------------------------------------------------------------
# Text window management
# ---------------------------------------------------------------------------


def test_truncation_preserves_head_and_tail(monkeypatch):
    sent_text: dict[str, str] = {}

    async def capture(text, csi_code):
        sent_text["user_prompt_text"] = text
        return ({}, [])

    monkeypatch.setattr(ape, "_llm_extract", capture)

    head = "HEAD_MARKER " + ("x" * 20_000)
    tail = ("y" * 20_000) + " TAIL_MARKER"
    long_text = head + ("M" * 5_000) + tail  # ~45K total

    ape.extract_assembly_parameters(long_text, csi_code="03 30 00", use_llm=True)

    sent = sent_text["user_prompt_text"]
    assert "HEAD_MARKER" in sent
    assert "TAIL_MARKER" in sent
    assert len(sent) <= 40_500  # 40K + separator slack


# ---------------------------------------------------------------------------
# LLM output schema (unit test the async path without monkeypatching)
# ---------------------------------------------------------------------------


def test_llm_parse_json_strips_markdown_fences():
    body = '```json\n{"parameters": {"f_c_psi": {"value": 4000, "confidence": 0.9, "source_text": "4000 psi"}}}\n```'
    data = ape._parse_llm_json(body)
    assert data["parameters"]["f_c_psi"]["value"] == 4000


def test_confidence_gets_clamped():
    entry = ape._normalize_parameter(
        "rebar_grade",
        {"value": "Grade 60", "source_text": "Grade 60", "confidence": 1.5},
        warnings=(w := []),
    )
    assert entry is not None
    assert entry["confidence"] == 1.0
    assert any("exceeds 1.0" in msg for msg in w)
