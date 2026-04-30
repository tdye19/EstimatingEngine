"""Agent 2B — Work Scope Parser (service layer).

Parses Work Scope documents into WorkCategory-shaped dicts. Work Scopes are
the authoritative bid-scope artifact — separate from specs, which are
technical reference only.

Public API:
  - classify_document(text, filename=None) -> str
  - parse_work_scopes(text, source_document_id=None, filename=None,
                      use_llm=True) -> dict

All numeric casting happens in Python after the LLM returns — never trusted
raw from LLM output. LLM failure falls back to regex; warnings are always
surfaced, never silently swallowed.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from apex.backend.services.llm_provider import LLMProvider, LLMProviderBillingError, get_llm_provider
from apex.backend.utils.async_helper import run_async

logger = logging.getLogger("apex.services.work_scope_parser")

# ---------------------------------------------------------------------------
# Classification (deterministic, no LLM)
# ---------------------------------------------------------------------------

_FILENAME_HINTS = (
    "work scope",
    "work_scope",
    "workscope",
    "volume 2",
    "vol 2",
    "vol_2",
)

_WC_COUNT_RE = re.compile(r"\bWC\s+(\d{1,2}[A-Z]?)\b", re.IGNORECASE)


def classify_document(text: str, filename: str | None = None) -> str:
    """Classify document as standalone / embedded / no work scope.

    Deterministic rule-based — no LLM. Uses filename hints and the
    frequency + density of ``WC <number>`` patterns.
    """
    if filename:
        lower = filename.lower()
        if any(hint in lower for hint in _FILENAME_HINTS):
            return "standalone_work_scope"

    body = text or ""
    matches = _WC_COUNT_RE.findall(body)
    unique_wc = {m.upper() for m in matches}
    density = len(matches) / max(len(body), 1) * 1000  # per 1000 chars

    if len(unique_wc) >= 3 and density > 0.5:
        return "standalone_work_scope"
    if len(unique_wc) >= 2:
        return "embedded_work_scope"
    return "no_work_scope"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_work_scopes(
    text: str,
    source_document_id: int | None = None,
    filename: str | None = None,
    use_llm: bool = True,
) -> dict:
    """Parse work scope content into WorkCategory-shaped dicts.

    Output schema matches the WorkCategory SQLAlchemy model exactly — the
    model is the source of truth. Keys in each work_categories entry are
    model column names (excluding id, created_at, updated_at).
    """
    warnings: list[str] = []
    classification = classify_document(text, filename)
    raw_sample = (text or "")[:500]

    if classification == "no_work_scope":
        return {
            "classification": classification,
            "work_categories": [],
            "parse_method": "none",
            "warnings": warnings,
            "raw_text_sample": raw_sample,
        }

    wcs: list[dict] = []
    outer_method: str

    if use_llm:
        try:
            provider = get_llm_provider(agent_number=2, suffix="B")
            resp_content = run_async(_llm_complete(text, provider))
        except LLMProviderBillingError:
            raise
        except Exception as exc:
            warnings.append(f"LLM call failed: {exc}. Fell back to regex.")
            wcs = _regex_parse(text, source_document_id, warnings)
            outer_method = "regex_fallback"
        else:
            try:
                raw_list = _parse_llm_json(resp_content)
            except (ValueError, json.JSONDecodeError) as je:
                warnings.append(f"LLM returned invalid JSON: {je}. Fell back to regex.")
                wcs = _regex_parse(text, source_document_id, warnings)
                outer_method = "regex_fallback"
            else:
                wcs = _coerce_llm_output(raw_list, source_document_id, warnings)
                outer_method = "llm"
    else:
        wcs = _regex_parse(text, source_document_id, warnings)
        outer_method = "regex"

    if not wcs:
        warnings.append(f"Classified as {classification} but no WC blocks extracted.")

    return {
        "classification": classification,
        "work_categories": wcs,
        "parse_method": outer_method,
        "warnings": warnings,
        "raw_text_sample": raw_sample,
    }


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a construction bid document parser. The input is raw text from a construction Work Scopes document.

Your job: extract each Work Category (WC) block into structured JSON.

A Work Category has this shape:
- wc_number: string like "WC 00", "WC 02", "WC 28A" (preserve spaces and letter suffixes)
- title: short descriptive name (e.g., "Site Concrete")
- work_included_items: list of strings
- work_category_notes: string or null
- specific_notes: list of strings
- add_alternates: list of {"description": str, "price_type": "add" | "deduct" | "unknown"}
- related_work_by_others: list of strings
- allowances: list of {"description": str, "amount_dollars": number}
- unit_prices: list of {"description": str, "unit": str, "rate": number}
- referenced_spec_sections: list of 6-digit CSI codes as strings, zero-padded

Return strict JSON: {"work_categories": [...]}. No prose, no markdown fences.
If a subsection is not present, use [] for lists, null for strings.

For add_alternates, set price_type = "add" if the text says "add alternate", "additive alternate", or similar; "deduct" if it says "deduct alternate", "deductive alternate", or "credit alternate"; "unknown" otherwise.

WC 00 is always "General Requirements for All Subcontractors" — it may lack Work Included or Related Work by Others; return [] for those.
"""


async def _llm_complete(text: str, provider: LLMProvider) -> str:
    # KCCU-scale documents (~70K chars, 8 WCs) produce ~10K-tokens of JSON.
    # 8192 truncates mid-string; 32000 leaves headroom for larger
    # Work Scopes documents without chunking.
    resp = await provider.complete(
        system_prompt=_LLM_SYSTEM_PROMPT,
        user_prompt=text,
        temperature=0.0,
        max_tokens=32000,
    )
    return resp.content


def _parse_llm_json(content: str) -> list[dict]:
    body = _strip_json_fences(content)
    data = json.loads(body)
    wcs = data.get("work_categories", [])
    if not isinstance(wcs, list):
        raise ValueError("LLM 'work_categories' is not a list")
    return wcs


def _strip_json_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _coerce_llm_output(
    raw_list: list[dict],
    source_document_id: int | None,
    warnings: list[str],
) -> list[dict]:
    out: list[dict] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        wc_num = _normalize_wc_number(raw.get("wc_number"))
        wc = _build_empty_wc(
            wc_num,
            source_document_id,
            parse_method="llm",
            parse_confidence=0.85,
        )

        wc["title"] = _as_str_or_empty(raw.get("title"))
        wc["work_included_items"] = _as_str_list(raw.get("work_included_items"))

        notes_val = raw.get("work_category_notes")
        if isinstance(notes_val, str) and notes_val.strip():
            wc["work_category_notes"] = notes_val.strip()

        wc["specific_notes"] = _as_str_list(raw.get("specific_notes"))
        wc["related_work_by_others"] = _as_str_list(raw.get("related_work_by_others"))
        wc["add_alternates"] = _coerce_add_alternates(raw.get("add_alternates"))
        wc["allowances"] = _coerce_allowances(raw.get("allowances"), wc_num, warnings)
        wc["unit_prices"] = _coerce_unit_prices(raw.get("unit_prices"), wc_num, warnings)
        wc["referenced_spec_sections"] = _coerce_csi_list(raw.get("referenced_spec_sections"), wc_num, warnings)

        out.append(wc)
    return out


# ---------------------------------------------------------------------------
# Per-field coercion helpers
# ---------------------------------------------------------------------------


def _build_empty_wc(
    wc_num: str,
    source_document_id: int | None,
    parse_method: str,
    parse_confidence: float,
) -> dict:
    """Return a dict pre-populated with model-aligned defaults.

    Keys match WorkCategory columns (excluding id, created_at, updated_at).
    project_id is None — the persistence layer sets it later (Spec 18.1.3).
    """
    return {
        "project_id": None,
        "wc_number": wc_num,
        "title": "",
        "work_included_items": [],
        "work_category_notes": None,
        "specific_notes": [],
        "related_work_by_others": [],
        "add_alternates": [],
        "allowances": [],
        "unit_prices": [],
        "referenced_spec_sections": [],
        "source_document_id": source_document_id,
        "source_page_start": None,
        "source_page_end": None,
        "parse_method": parse_method,
        "parse_confidence": parse_confidence,
    }


def _normalize_wc_number(value: Any) -> str:
    if value is None:
        return "WC ??"
    s = str(value).strip()
    if not s:
        return "WC ??"
    # Ensure there's a space between "WC" and the number
    m = re.match(r"^WC\s*(\d{1,2}[A-Z]?)\s*$", s, re.IGNORECASE)
    if m:
        return f"WC {m.group(1).upper()}"
    return s


def _as_str_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def _safe_float(value: Any) -> tuple[float | None, str | None]:
    """Cast arbitrary LLM/regex input to float. Returns (value, error_msg)."""
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        # bool is an int subclass — reject to avoid surprises
        return None, f"unexpected bool numeric: {value!r}"
    if isinstance(value, int | float):
        return float(value), None
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None, None
        try:
            return float(cleaned), None
        except ValueError:
            return None, f"unparseable numeric: {value!r}"
    return None, f"unexpected numeric type: {type(value).__name__}"


def _coerce_add_alternates(value: Any) -> list[dict]:
    """Normalize add_alternates to [{description, price_type}].

    Accepts LLM dicts with a ``price_type`` field; falls back to keyword
    inference from the description when absent or invalid.
    """
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        desc = _as_str_or_empty(item.get("description"))
        if not desc:
            continue
        pt_raw = item.get("price_type")
        pt = str(pt_raw).strip().lower() if isinstance(pt_raw, str) else ""
        if pt not in ("add", "deduct", "unknown"):
            pt = infer_price_type(desc)
        out.append({"description": desc, "price_type": pt})
    return out


def infer_price_type(description: str) -> str:
    """Classify an alternate line as add / deduct / unknown by keyword."""
    d = (description or "").lower()
    has_deduct = bool(re.search(r"\b(deduct|deductive|credit)\s+alternate\b|\bdeduct\b", d))
    has_add = bool(re.search(r"\b(add|additive)\s+alternate\b|\badditive\b", d))
    if has_deduct and not has_add:
        return "deduct"
    if has_add and not has_deduct:
        return "add"
    # Bare "add" without "alternate" — weaker signal, still treat as add
    if re.search(r"\badd\b", d) and not has_deduct:
        return "add"
    return "unknown"


def _coerce_allowances(
    value: Any,
    wc_num: str,
    warnings: list[str],
) -> list[dict]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        desc = _as_str_or_empty(item.get("description"))
        if not desc:
            continue
        raw_amt = item.get("amount_dollars")
        if raw_amt is None:
            raw_amt = item.get("amount")  # tolerate legacy LLM key
        amount, err = _safe_float(raw_amt)
        if err:
            warnings.append(f"Could not cast amount_dollars for {wc_num} allowance " f"'{desc}': {err}")
        out.append({"description": desc, "amount_dollars": amount})
    return out


def _coerce_unit_prices(
    value: Any,
    wc_num: str,
    warnings: list[str],
) -> list[dict]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        desc = _as_str_or_empty(item.get("description") or item.get("item"))
        if not desc:
            continue
        unit = _as_str_or_empty(item.get("unit"))
        raw_rate = item.get("rate")
        if raw_rate is None:
            raw_rate = item.get("price")  # tolerate legacy LLM key
        rate, err = _safe_float(raw_rate)
        if err:
            warnings.append(f"Could not cast rate for {wc_num} unit price '{desc}': {err}")
        out.append({"description": desc, "unit": unit, "rate": rate})
    return out


def _coerce_csi_list(
    value: Any,
    wc_num: str,
    warnings: list[str],
) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for raw in value:
        norm = normalize_csi_code(raw)
        if norm is None:
            warnings.append(f"Skipped invalid CSI code reference in {wc_num}: {raw!r}")
            continue
        out.append(norm)
    # De-duplicate while preserving order of first appearance
    seen = set()
    unique = []
    for code in out:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def normalize_csi_code(raw: Any) -> str | None:
    """Normalize a CSI reference to a zero-padded 6-digit string.

    Accepts forms like "32 13 13", "32.13.13", "03 30 00.01".
    Returns None for malformed input (non-digit, wrong length).
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[\s.\-]", "", str(raw))
    if not cleaned or not cleaned.isdigit():
        return None
    if len(cleaned) > 6:
        cleaned = cleaned[:6]  # drop level-3/4 sub-segment
    elif len(cleaned) == 4:
        cleaned = cleaned + "00"  # "0330" -> "033000"
    if len(cleaned) != 6:
        return None
    return cleaned


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

_SUBSECTION_PATTERNS: dict[str, re.Pattern] = {
    "work_included_items": re.compile(r"^\s*Work\s+Included\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "work_category_notes": re.compile(
        r"^\s*Work\s+Category\s+Notes\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "specific_notes": re.compile(
        r"^\s*Specific\s+Notes(?:\s+and\s+Details)?\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "add_alternates": re.compile(r"^\s*Add\s+Alternates?\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "related_work_by_others": re.compile(
        r"^\s*Related\s+Work\s+by\s+Others\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "allowances": re.compile(r"^\s*Allowances?\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "unit_prices": re.compile(r"^\s*Unit\s+Prices?\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
}

# Primary: first-page-of-section marker (KCCU/Christman PDF format).
# The "-1" suffix identifies page 1 of section XX, signaling section start.
# Tolerates optional whitespace before the dash — pdfplumber extracts both
# "WC 00-1" and "WC 02 -1" depending on source layout.
_FIRST_PAGE_RE = re.compile(
    r"\bWC\s+(?P<num>\d{1,2}[A-Z]?)\s*-\s*1\b",
    re.IGNORECASE,
)

# Secondary: standalone WC header (synthetic/clean-PDF format).
# Matches "WC XX" or "WC XX - Title" on its own line.
_STANDALONE_HEADER_RE = re.compile(
    r"^\s*WC\s+(?P<num>\d{1,2}[A-Z]?)" r"(?:\s*[-:\u2014\u2013]\s*(?P<title>.+?))?" r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Title extractor for KCCU-format first-page running header.
# Header line format: "... WC XX-1 WC XX <title>" (with optional space
# before the "-1"). The trailing "Page WC XX -1 WC XX <title>" variant
# also appears in KCCU — the prefix is absorbed by the leading .*? context.
_KCCU_TITLE_RE = re.compile(
    r"\bWC\s+(?P<num>\d{1,2}[A-Z]?)\s*-\s*1\s+WC\s+\d{1,2}[A-Z]?\s+(?P<title>.+?)$",
    re.IGNORECASE | re.MULTILINE,
)

_BULLET_RE = re.compile(
    r"^[ \t]*(?:[\u2022\-\*\u25E6\u25AA]|(?:\d+[\.\)]))[ \t]+(.+?)[ \t]*$",
    re.MULTILINE,
)

_CSI_INLINE_RE = re.compile(r"\b(\d{2})[\s.\-]*(\d{2})[\s.\-]*(\d{2})(?:\.\d{1,2})?\b")

_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")

_UOM_HINT_RE = re.compile(
    r"\b(SF|SY|CY|LF|EA|LS|TON|TONS|GAL|CF|HR|DAY|MO|LB|LBS)\b",
    re.IGNORECASE,
)


def _regex_parse(
    text: str,
    source_document_id: int | None,
    warnings: list[str],
) -> list[dict]:
    blocks = _split_into_wc_blocks(text or "")
    out = []
    for b in blocks:
        wc = _build_empty_wc(
            b["wc_number"],
            source_document_id,
            parse_method="regex",
            parse_confidence=0.45,
        )
        # HF-19: strip running headers BEFORE subsection extraction
        # (title already extracted into b["title"] by block splitter)
        cleaned_block = _strip_running_boilerplate(b["block"])
        wc["title"] = b["title"] or _first_content_line(cleaned_block)
        sections = _extract_subsections(cleaned_block)

        wc["work_included_items"] = _bulleted(sections.get("work_included_items", ""))
        notes = sections.get("work_category_notes", "").strip()
        if notes:
            wc["work_category_notes"] = notes
        wc["specific_notes"] = _bulleted(sections.get("specific_notes", ""))
        wc["related_work_by_others"] = _bulleted(sections.get("related_work_by_others", ""))
        wc["add_alternates"] = _regex_add_alternates(sections.get("add_alternates", ""))
        wc["allowances"] = _regex_allowances(sections.get("allowances", ""), b["wc_number"], warnings)
        wc["unit_prices"] = _regex_unit_prices(sections.get("unit_prices", ""), b["wc_number"], warnings)
        wc["referenced_spec_sections"] = _regex_csi_codes(cleaned_block, b["wc_number"], warnings)
        out.append(wc)
    return out


def _split_into_wc_blocks(text: str) -> list[dict]:
    """Split text into per-WC blocks.

    Primary: find "WC XX-1" first-page markers (KCCU/Christman PDF format).
    Fallback: find standalone "WC XX" line headers (synthetic/clean format).

    Returns list of {"wc_number": "WC XX", "title": str, "block": str}.
    """
    if not text:
        return []

    # KCCU mode requires >=2 first-page markers (guards against synthetic
    # inputs that might coincidentally contain one "WC 01-1"-like string).
    kccu_matches = list(_FIRST_PAGE_RE.finditer(text))
    if len(kccu_matches) >= 2:
        return _blocks_from_kccu_markers(text, kccu_matches)

    std_matches = list(_STANDALONE_HEADER_RE.finditer(text))
    if std_matches:
        return _blocks_from_standalone_headers(text, std_matches)

    return []


def _blocks_from_kccu_markers(text: str, matches: list) -> list[dict]:
    """Extract blocks using KCCU 'WC XX-1' first-page markers.

    Dedupes by WC number — the running header repeats the section's
    first-page marker on every page, but only the first occurrence
    defines the section boundary.
    """
    seen_nums: set[str] = set()
    unique_matches = []
    for m in matches:
        num = m.group("num").upper()
        if num not in seen_nums:
            seen_nums.add(num)
            unique_matches.append(m)

    blocks = []
    for i, m in enumerate(unique_matches):
        num = m.group("num").upper()
        # Block starts at start of line containing this match
        line_start = text.rfind("\n", 0, m.start()) + 1
        # Block ends at start of line containing next match, or EOF
        if i + 1 < len(unique_matches):
            next_start = unique_matches[i + 1].start()
            line_end = text.rfind("\n", 0, next_start) + 1
        else:
            line_end = len(text)
        raw = text[line_start:line_end]
        title = _extract_kccu_title(raw, num)
        blocks.append(
            {
                "wc_number": f"WC {num}",
                "title": title,
                "block": raw,
            }
        )
    return blocks


def _blocks_from_standalone_headers(text: str, matches: list) -> list[dict]:
    """Extract blocks from standalone 'WC XX' line headers (clean format)."""
    blocks = []
    for i, m in enumerate(matches):
        num = m.group("num").upper()
        title = (m.group("title") or "").strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end]
        blocks.append(
            {
                "wc_number": f"WC {num}",
                "title": title,
                "block": raw,
            }
        )
    return blocks


def _extract_kccu_title(block: str, num: str) -> str:
    """Extract WC title from the first 'WC XX-1 WC XX <title>' in block.

    Returns first-line title only — multi-line titles are truncated to the
    first line. Acceptable imperfection; LLM path recovers accurate titles
    when the LLM is available.
    """
    for m in _KCCU_TITLE_RE.finditer(block):
        if m.group("num").upper() == num:
            return m.group("title").strip()
    return ""


def _strip_running_boilerplate(text: str, threshold: int = 3) -> str:
    """Strip lines that repeat >=threshold times after digit normalization.

    Catches running page headers (same text except page numbers) and static
    repeated boilerplate (project name, location tags, running footers).
    Preserves non-repeating body content.

    Digit normalization is key: "WC 00-1 ..." and "WC 00-2 ..." normalize
    to identical strings and are detected as repeats.
    """
    lines = text.splitlines(keepends=False)
    if not lines:
        return text

    def _normalize(line: str) -> str | None:
        s = line.strip()
        if len(s) < 5:
            return None  # too short to meaningfully count as boilerplate
        return re.sub(r"\d+", "#", s)

    counts = Counter(n for n in (_normalize(line) for line in lines) if n is not None)
    boilerplate = {k for k, v in counts.items() if v >= threshold}

    return "\n".join(line for line in lines if _normalize(line) not in boilerplate)


def _first_content_line(block: str) -> str:
    lines = block.splitlines()
    if len(lines) < 2:
        return ""
    for line in lines[1:]:
        s = line.strip()
        if not s:
            continue
        if _looks_like_subsection_header(s):
            continue
        return s
    return ""


def _looks_like_subsection_header(line: str) -> bool:
    probe = line + "\n"
    return any(pat.match(probe) for pat in _SUBSECTION_PATTERNS.values())


def _extract_subsections(block: str) -> dict[str, str]:
    hits: list[tuple[int, int, str]] = []
    for name, pat in _SUBSECTION_PATTERNS.items():
        for m in pat.finditer(block):
            hits.append((m.start(), m.end(), name))
    hits.sort(key=lambda x: x[0])
    result = {}
    for i, (_start, end, name) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(block)
        result[name] = block[end:next_start].strip()
    return result


def _bulleted(chunk: str) -> list[str]:
    if not chunk:
        return []
    hits = _BULLET_RE.findall(chunk)
    if hits:
        return [h.strip() for h in hits if h.strip()]
    # Fallback: each non-empty line becomes an item
    return [line.strip() for line in chunk.splitlines() if line.strip()]


def _regex_add_alternates(chunk: str) -> list[dict]:
    if not chunk:
        return []
    return [{"description": desc, "price_type": infer_price_type(desc)} for desc in _bulleted(chunk)]


def _regex_allowances(chunk: str, wc_num: str, warnings: list[str]) -> list[dict]:
    if not chunk:
        return []
    out = []
    for desc in _bulleted(chunk):
        amount, err = _extract_dollar_amount(desc)
        if err:
            warnings.append(f"Could not cast amount_dollars for {wc_num} allowance " f"'{desc}': {err}")
        out.append({"description": desc, "amount_dollars": amount})
    return out


def _regex_unit_prices(chunk: str, wc_num: str, warnings: list[str]) -> list[dict]:
    if not chunk:
        return []
    out = []
    for desc in _bulleted(chunk):
        rate, err = _extract_dollar_amount(desc)
        if err:
            warnings.append(f"Could not cast rate for {wc_num} unit price '{desc}': {err}")
        unit_match = _UOM_HINT_RE.search(desc)
        unit = unit_match.group(1).upper() if unit_match else ""
        out.append({"description": desc, "unit": unit, "rate": rate})
    return out


def _extract_dollar_amount(text: str) -> tuple[float | None, str | None]:
    m = _DOLLAR_RE.search(text or "")
    if not m:
        return None, None
    return _safe_float(m.group(1))


def _regex_csi_codes(block: str, wc_num: str, warnings: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _CSI_INLINE_RE.finditer(block):
        raw = m.group(0)
        joined = m.group(1) + m.group(2) + m.group(3)
        normalized = normalize_csi_code(joined)
        if normalized is None:
            warnings.append(f"Skipped invalid CSI code reference in {wc_num}: {raw!r}")
            continue
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found
