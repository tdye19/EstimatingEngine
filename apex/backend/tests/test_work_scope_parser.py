"""Tests for Agent 2B — Work Scope Parser (Spec 18.1.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from apex.backend.models.work_category import WorkCategory
from apex.backend.services import work_scope_parser as wsp

# ---------------------------------------------------------------------------
# classify_document
# ---------------------------------------------------------------------------


def test_classify_standalone_by_filename():
    assert wsp.classify_document("", filename="Work Scopes Vol 2.pdf") == "standalone_work_scope"
    assert wsp.classify_document("", filename="KCCU_Volume_2_Work_Scopes.pdf") == "standalone_work_scope"


def test_classify_standalone_by_content_density():
    text = "\n".join(f"WC {i:02d}\nSome content about category {i}." for i in range(8))
    assert wsp.classify_document(text) == "standalone_work_scope"


def test_classify_embedded():
    filler = "This is generic specification text content. " * 100
    text = filler + "\nWC 03 Concrete section follows.\n" + filler + "\nWC 05 Metals section.\n" + filler
    assert wsp.classify_document(text) == "embedded_work_scope"


def test_classify_none():
    assert wsp.classify_document("No work scopes here, just random spec content.") == "no_work_scope"


# ---------------------------------------------------------------------------
# Regex fallback — block extraction
# ---------------------------------------------------------------------------


def test_regex_fallback_extracts_wc_blocks():
    text = """WC 02 - Earthwork
Work Included:
- Excavation
- Grading

WC 03 - Concrete
Work Included:
- Foundation concrete
- Slab on grade

WC 05 - Metals
Work Included:
- Structural steel
"""
    result = wsp.parse_work_scopes(text, use_llm=False)
    assert result["parse_method"] == "regex"
    wcs = result["work_categories"]
    assert len(wcs) == 3
    assert [wc["wc_number"] for wc in wcs] == ["WC 02", "WC 03", "WC 05"]
    assert wcs[0]["title"] == "Earthwork"
    assert wcs[0]["work_included_items"] == ["Excavation", "Grading"]
    assert wcs[0]["parse_method"] == "regex"
    assert wcs[0]["parse_confidence"] == 0.45


# ---------------------------------------------------------------------------
# CSI code normalization
# ---------------------------------------------------------------------------


def test_csi_code_normalization():
    assert wsp.normalize_csi_code("32 13 13") == "321313"
    assert wsp.normalize_csi_code("260500") == "260500"
    assert wsp.normalize_csi_code("03.30.00") == "033000"
    assert wsp.normalize_csi_code("03 30 00.01") == "033000"  # drops sub-level
    assert wsp.normalize_csi_code("03 30") == "033000"  # pads 4 -> 6
    assert wsp.normalize_csi_code("abc") is None
    assert wsp.normalize_csi_code("") is None
    assert wsp.normalize_csi_code(None) is None

    # Coerce-list path emits a warning for bad input
    warnings: list[str] = []
    result = wsp._coerce_csi_list(["32 13 13", "abc", "03 30 00"], "WC 02", warnings)
    assert result == ["321313", "033000"]
    assert any("Skipped invalid CSI code" in w for w in warnings)


# ---------------------------------------------------------------------------
# Numeric casting from LLM output
# ---------------------------------------------------------------------------


def test_allowance_amount_cast_from_llm():
    raw = [
        {
            "wc_number": "WC 10",
            "title": "Testing",
            "allowances": [
                {
                    "description": "Unforeseen conditions",
                    "amount_dollars": "not a number",
                },
                {"description": "Permit fees", "amount_dollars": "$1,500.00"},
                {"description": "Raw int", "amount_dollars": 2500},
            ],
        }
    ]
    warnings: list[str] = []
    out = wsp._coerce_llm_output(raw, source_document_id=None, warnings=warnings)
    allowances = out[0]["allowances"]

    assert allowances[0]["amount_dollars"] is None
    assert allowances[1]["amount_dollars"] == 1500.0
    assert allowances[2]["amount_dollars"] == 2500.0
    assert any("Could not cast amount_dollars" in w for w in warnings)
    assert any("not a number" in w for w in warnings)


def test_unit_price_rate_cast_from_llm():
    raw = [
        {
            "wc_number": "WC 02",
            "title": "Earthwork",
            "unit_prices": [
                {"description": "Rock excavation", "unit": "CY", "rate": "garbage"},
                {"description": "Topsoil", "unit": "CY", "rate": "$45.50"},
                {"description": "Import fill", "unit": "CY", "rate": 38.0},
            ],
        }
    ]
    warnings: list[str] = []
    out = wsp._coerce_llm_output(raw, source_document_id=None, warnings=warnings)
    up = out[0]["unit_prices"]

    assert up[0]["rate"] is None
    assert up[1]["rate"] == 45.5
    assert up[2]["rate"] == 38.0
    assert any("Could not cast rate" in w for w in warnings)


# ---------------------------------------------------------------------------
# Alternate price_type inference
# ---------------------------------------------------------------------------


def test_alternate_price_type_inference():
    assert wsp.infer_price_type("Add Alternate #1: Upgrade finishes") == "add"
    assert wsp.infer_price_type("Additive Alternate: Extra landscaping") == "add"
    assert wsp.infer_price_type("Deduct Alternate #2: Omit skylights") == "deduct"
    assert wsp.infer_price_type("Deductive Alternate: Cheaper flooring") == "deduct"
    assert wsp.infer_price_type("Credit Alternate: Owner-supplied doors") == "deduct"
    assert wsp.infer_price_type("Alternate #3: Bare reference") == "unknown"

    # Coerce path propagates inference when LLM omits price_type
    raw = [
        {
            "wc_number": "WC 09",
            "title": "Finishes",
            "add_alternates": [
                {"description": "Add Alternate #1: Upgrade carpet"},
                {"description": "Deduct Alternate #2: Omit wall covering"},
                {"description": "Alternate #3: Bare reference"},
            ],
        }
    ]
    out = wsp._coerce_llm_output(raw, source_document_id=None, warnings=[])
    pts = [a["price_type"] for a in out[0]["add_alternates"]]
    assert pts == ["add", "deduct", "unknown"]


# ---------------------------------------------------------------------------
# LLM failure -> regex fallback
# ---------------------------------------------------------------------------


def test_llm_invalid_json_falls_back_to_regex():
    """HF-19b regression: truncated/invalid JSON must fall back, not crash.

    A too-low max_tokens caused Claude to truncate mid-string on KCCU-scale
    input. The fallback path must surface the JSON error as a warning and
    still deliver regex-parsed WCs.
    """
    text = (
        "WC 02 - Earthwork\n"
        "Work Included:\n"
        "- Excavation\n"
        "\n"
        "WC 03 - Concrete\n"
        "Work Included:\n"
        "- Slab on grade\n"
    )

    # Simulate Claude returning a truncated (unterminated) JSON string
    truncated_body = (
        '{"work_categories": [{"wc_number": "WC 02", ' '"title": "Earthwork", "work_included_items": ["Excavati'
    )
    fake_resp = MagicMock()
    fake_resp.content = truncated_body

    provider = MagicMock()
    provider.complete = AsyncMock(return_value=fake_resp)

    with patch.object(wsp, "get_llm_provider", return_value=provider):
        result = wsp.parse_work_scopes(text, use_llm=True)

    assert result["parse_method"] == "regex_fallback"
    assert any("invalid JSON" in w for w in result["warnings"])
    nums = [wc["wc_number"] for wc in result["work_categories"]]
    assert nums == ["WC 02", "WC 03"]


def test_llm_failure_falls_back_to_regex():
    text = (
        "WC 02 - Earthwork\n"
        "Work Included:\n"
        "- Excavation\n"
        "\n"
        "WC 03 - Concrete\n"
        "Work Included:\n"
        "- Slab on grade\n"
    )

    failing_provider = MagicMock()
    failing_provider.complete = AsyncMock(side_effect=RuntimeError("rate limit"))

    with patch.object(wsp, "get_llm_provider", return_value=failing_provider):
        result = wsp.parse_work_scopes(text, use_llm=True)

    assert result["parse_method"] == "regex_fallback"
    assert any("LLM call failed" in w for w in result["warnings"])
    assert any("rate limit" in w for w in result["warnings"])
    nums = [wc["wc_number"] for wc in result["work_categories"]]
    assert nums == ["WC 02", "WC 03"]


# ---------------------------------------------------------------------------
# HF-19 — KCCU-format block splitter + boilerplate stripper
# ---------------------------------------------------------------------------


def test_kccu_format_extracts_multiple_wcs():
    """Simulates KCCU running-header format with 3 sections."""
    text = (
        "Cover page text\n"
        "The Christman Co WC 00-1 WC 00 General Requirements\n"
        "For all Subcontractors\n"
        "KCCU HQ Proposal Section\n"
        "Body content for WC 00 page 1\n"
        "The Christman Co WC 00-2 WC 00 General Requirements\n"
        "For all Subcontractors\n"
        "KCCU HQ Proposal Section\n"
        "Body content for WC 00 page 2\n"
        "The Christman Co WC 05-1 WC 05 Site Concrete\n"
        "For all Subcontractors\n"
        "KCCU HQ Proposal Section\n"
        "Body content for WC 05\n"
        "The Christman Co WC 28A-1 WC 28A Generator Procurement\n"
        "For all Subcontractors\n"
        "KCCU HQ Proposal Section\n"
        "Body content for WC 28A\n"
    )
    blocks = wsp._split_into_wc_blocks(text)
    assert len(blocks) == 3
    assert [b["wc_number"] for b in blocks] == ["WC 00", "WC 05", "WC 28A"]
    assert blocks[0]["title"] == "General Requirements"
    assert blocks[1]["title"] == "Site Concrete"
    assert blocks[2]["title"] == "Generator Procurement"


def test_running_boilerplate_stripped():
    """Repeated lines (with varying numbers) are stripped."""
    text = (
        "WC 00-1 WC 00 General Requirements\n"
        "Some unique body content line\n"
        "WC 00-2 WC 00 General Requirements\n"
        "Another unique body line\n"
        "WC 00-3 WC 00 General Requirements\n"
        "More unique content\n"
    )
    out = wsp._strip_running_boilerplate(text, threshold=3)
    # Running header (digits normalized -> identical) appears 3x -> stripped
    assert "WC 00-1 WC 00 General Requirements" not in out
    assert "WC 00-2 WC 00 General Requirements" not in out
    # Unique body lines preserved
    assert "Some unique body content line" in out
    assert "Another unique body line" in out
    assert "More unique content" in out


def test_kccu_space_before_dash_variant():
    """Real KCCU PDF extracts both 'WC 00-1' and 'WC 02 -1' — both must match."""
    text = (
        "The Christman Co WC 00-1 WC 00 General Requirements\n"
        "Body for WC 00\n"
        "The Christman Co Page WC 02 -1 WC 02 Earthwork\n"
        "Body for WC 02\n"
        "The Christman Co Page WC 28A -1 WC 28A Electrical\n"
        "Body for WC 28A\n"
    )
    blocks = wsp._split_into_wc_blocks(text)
    assert [b["wc_number"] for b in blocks] == ["WC 00", "WC 02", "WC 28A"]
    assert blocks[0]["title"] == "General Requirements"
    assert blocks[1]["title"] == "Earthwork"
    assert blocks[2]["title"] == "Electrical"


def test_kccu_mode_requires_two_markers():
    """Synthetic input with 1 stray '-1' marker falls through to standalone."""
    text = "WC 01 - Concrete Work\n" "Work Included\n" "- Formwork\n" "Note: reference WC 02-1 elsewhere in document\n"
    blocks = wsp._split_into_wc_blocks(text)
    # Should find 1 block via standalone mode, NOT 2 via KCCU mode
    assert len(blocks) == 1
    assert blocks[0]["wc_number"] == "WC 01"


# ---------------------------------------------------------------------------
# Output schema matches the WorkCategory model columns
# ---------------------------------------------------------------------------


def test_output_schema_matches_model_columns():
    text = (
        "WC 02 - Earthwork\n"
        "Work Included:\n"
        "- Excavation\n"
        "- Grading\n"
        "\n"
        "WC 03 - Concrete\n"
        "Work Included:\n"
        "- Slab on grade\n"
    )
    result = wsp.parse_work_scopes(text, use_llm=False)
    assert result["work_categories"], "expected regex fallback to extract WCs"

    model_cols = {col.name for col in WorkCategory.__table__.columns}
    db_generated = {"id", "created_at", "updated_at"}

    for wc in result["work_categories"]:
        for key in wc.keys():
            assert key in model_cols, f"Output key {key!r} is not a WorkCategory column"
            assert key not in db_generated, f"Output should not include DB-generated column {key!r}"
