"""Assembly Parameter Extractor (Sprint 18.2.2).

Extracts the 8 WinEst assembly-dialog parameters from a single spec
section's text. Designed for CSI Division 03 (Concrete) — the only
division where these parameters are well-defined today.

Service layer only. No DB writes, no pipeline wiring, no API — Agent 2
integration ships in 18.2.3.

Public API
----------
  - is_division_03_section(csi_code) -> bool
  - extract_assembly_parameters(section_text, csi_code, use_llm=True) -> dict

Output schema (see apex/backend/models/spec_section.py module docstring):
  {
    "parameters": {
      "<name>": {"value": ..., "source_text": "...", "confidence": 0.0-1.0},
      ...
    },
    "extracted_at": "ISO-8601",
    "extraction_method": "llm" | "regex" | "llm_partial",
    "warnings": [str, ...],
    "source_text_length": int,
  }

Same design principles as Sprint 18.1.2 (work_scope_parser):
LLM primary, regex fallback, non-swallow warnings, deterministic Python
normalization of all numeric/categorical values after the LLM returns.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apex.backend.services.llm_provider import LLMProvider, get_llm_provider
from apex.backend.utils.async_helper import run_async

logger = logging.getLogger("apex.services.assembly_parameter_extractor")

# ---------------------------------------------------------------------------
# Parameter specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    name: str
    value_type: str  # "int", "float", "string"
    description: str  # used in LLM prompt
    llm_confidence_base: float
    regex_pattern: str | None
    regex_confidence: float = 0.45


PARAM_SPECS: list[ParamSpec] = [
    ParamSpec(
        name="f_c_psi",
        value_type="int",
        description="Concrete compressive strength at 28 days, in psi.",
        llm_confidence_base=0.92,
        regex_pattern=r"(?i)(\d{3,5})\s*psi\b",
    ),
    ParamSpec(
        name="cement_type",
        value_type="string",
        description=(
            "Portland cement type (e.g., 'Type I', 'Type II', 'Type I/II', "
            "'Type III', 'Type V'). ASTM C150 unless otherwise specified."
        ),
        llm_confidence_base=0.88,
        regex_pattern=r"(?i)(?:Portland\s+cement\s+)?Type\s+(I{1,3}(?:/II)?|IV|V)\b",
    ),
    ParamSpec(
        name="aggregate_max_size_inches",
        value_type="float",
        description=(
            "Maximum coarse aggregate nominal size in inches (e.g., 0.75, "
            "1.0, 1.5). Convert fractions to decimals."
        ),
        llm_confidence_base=0.85,
        regex_pattern=None,
    ),
    ParamSpec(
        name="slump_range_inches",
        value_type="string",
        description=(
            "Slump range in inches as a string, e.g., '3-5' or '4±1'. "
            "Preserve the format the spec uses."
        ),
        llm_confidence_base=0.90,
        regex_pattern=(
            r"(?i)slump[^.]{0,60}?"
            r"(\d{1,2}(?:\.\d)?\s*(?:[-\u00b1to]+)\s*\d{1,2}(?:\.\d)?)"
            r"\s*(?:inch|in\.|\")"
        ),
    ),
    ParamSpec(
        name="air_entrainment_pct",
        value_type="string",
        description=(
            "Air entrainment percentage range, e.g., '5-7' or '4.5-7.5'. "
            "If spec says 'none' or 'not required', use the string 'none'. "
            "Preserve the format."
        ),
        llm_confidence_base=0.82,
        regex_pattern=(
            r"(?i)air(?:\s+content|\s+entrainment)[^.]{0,40}?"
            r"(\d{1,2}(?:\.\d)?\s*(?:[-\u00b1to]+)\s*\d{1,2}(?:\.\d)?)\s*%?"
        ),
    ),
    ParamSpec(
        name="rebar_grade",
        value_type="string",
        description=(
            "Reinforcing steel grade, e.g., 'Grade 60', 'Grade 75'. "
            "ASTM A615 unless specified otherwise."
        ),
        llm_confidence_base=0.95,
        regex_pattern=r"(?i)Grade\s+(40|60|75|80|100)\b",
    ),
    ParamSpec(
        name="finish_class",
        value_type="string",
        description=(
            "Concrete surface finish class per ACI 117 (e.g., 'Class A', "
            "'Class B') or descriptive finish (e.g., 'troweled smooth', "
            "'broom finish', 'float finish')."
        ),
        llm_confidence_base=0.78,
        regex_pattern=None,
    ),
    ParamSpec(
        name="curing_method",
        value_type="string",
        description=(
            "Curing method (e.g., 'moist cure 7 days', 'curing compound "
            "ASTM C309', 'wet cure with burlap'). Include duration if "
            "specified."
        ),
        llm_confidence_base=0.80,
        regex_pattern=None,
    ),
]

_PARAM_SPEC_BY_NAME: dict[str, ParamSpec] = {s.name: s for s in PARAM_SPECS}


# ---------------------------------------------------------------------------
# is_division_03_section
# ---------------------------------------------------------------------------

_DIV_RE = re.compile(r"^\s*0?3\b")


def is_division_03_section(csi_code: str | None) -> bool:
    """Return True if csi_code is any variant of CSI Division 03."""
    if not csi_code:
        return False
    cleaned = str(csi_code).strip()
    if not cleaned:
        return False
    # Accept "03", "3", "03 30 00", "033000", "03 30 00.13", etc.
    compact = re.sub(r"\s+", "", cleaned)
    if compact.startswith("03") or compact.startswith("3"):
        # "3" alone is ambiguous but accepted per spec ("some docs strip
        # leading zero"). "3X..." where X is a digit is invalid (e.g., "31"
        # would be Division 31); require either exact "3"/"03" or a
        # non-digit boundary after.
        if compact in {"3", "03"}:
            return True
        if compact.startswith("03"):
            return True
        # compact starts with "3" followed by a digit -> a different division
        if compact[1:2].isdigit():
            return False
        return True
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract_assembly_parameters(
    section_text: str,
    csi_code: str | None = None,
    use_llm: bool = True,
) -> dict:
    """Extract WinEst assembly parameters from a single spec section."""
    warnings: list[str] = []
    parameters: dict[str, dict] = {}
    extraction_method = "regex"

    if use_llm:
        truncated, truncated_len_original = _truncate_for_llm(section_text or "")
        if truncated_len_original is not None:
            warnings.append(
                f"Section text truncated from {truncated_len_original} "
                f"to {len(truncated)} chars for LLM extraction"
            )
        try:
            llm_params, llm_warnings = run_async(
                _llm_extract(truncated, csi_code)
            )
        except Exception as exc:
            warnings.append(
                f"LLM extraction failed: {exc}. Falling back to regex."
            )
            parameters = _regex_extract(section_text or "")
            extraction_method = "regex"
        else:
            warnings.extend(llm_warnings)
            parameters = llm_params
            extraction_method = "llm_partial" if llm_warnings else "llm"
    else:
        parameters = _regex_extract(section_text or "")
        extraction_method = "regex"

    return {
        "parameters": parameters,
        "extracted_at": datetime.utcnow().isoformat(),
        "extraction_method": extraction_method,
        "warnings": warnings,
        "source_text_length": len(section_text or ""),
    }


# ---------------------------------------------------------------------------
# Text window management
# ---------------------------------------------------------------------------

_MAX_LLM_TEXT = 40_000
_TRUNCATION_SEPARATOR = "\n...[truncated middle]...\n"


def _truncate_for_llm(text: str) -> tuple[str, int | None]:
    """Return (possibly_truncated_text, original_len_if_truncated_else_None).

    If text > 40000 chars, returns first 20K + separator + last 20K.
    Front-loads Part 2 (Products) and keeps Part 3 (Execution) — finishes,
    curing often live in Part 3.
    """
    if len(text) <= _MAX_LLM_TEXT:
        return text, None
    original_len = len(text)
    head = text[: _MAX_LLM_TEXT // 2]
    tail = text[-_MAX_LLM_TEXT // 2 :]
    return head + _TRUNCATION_SEPARATOR + tail, original_len


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a construction specification parser for structural concrete work.

Your job: read a spec section and extract up to 8 structured assembly parameters.
These parameters are the dialog questions a construction estimating tool
(WinEst) asks when pricing a concrete assembly.

Target parameters (all optional - extract only what the spec states):

1. f_c_psi (integer) - Concrete compressive strength at 28 days, in psi.
2. cement_type (string) - Portland cement type (Type I, I/II, III, V, etc.).
3. aggregate_max_size_inches (float) - Max coarse aggregate nominal size, inches (convert fractions).
4. slump_range_inches (string) - Slump range in inches, preserve spec format (e.g., "3-5", "4+/-1").
5. air_entrainment_pct (string) - Air content range (e.g., "5-7"), or "none" if not required.
6. rebar_grade (string) - Reinforcing steel grade (e.g., "Grade 60").
7. finish_class (string) - Surface finish class or description (e.g., "Class A", "troweled smooth").
8. curing_method (string) - Curing method with duration (e.g., "moist cure 7 days").

For each parameter you extract, return:
  - value: the extracted value (correct type per the list above)
  - source_text: the exact spec excerpt that justified the value (keep it short - one sentence or clause)
  - confidence: your confidence 0.0-1.0

Do NOT hallucinate values. If a parameter is not explicitly stated in the
section, OMIT IT from the output entirely. Do not return nulls, "N/A",
or guesses based on "typical" values.

If the spec states multiple values for the same parameter (e.g., "4000 psi
for slabs, 3000 psi for footings"), return the first one with a source_text
that notes the qualifier. Do not try to return multiple.

Return strict JSON with this shape (only include keys you found):
{
  "parameters": {
    "f_c_psi": {"value": 4000, "source_text": "...", "confidence": 0.9}
  }
}

No prose, no markdown fences. If nothing extracts, return {"parameters": {}}.
"""


async def _llm_extract(
    text: str, csi_code: str | None
) -> tuple[dict, list[str]]:
    """Call LLM, parse JSON, validate + normalize each parameter.

    Raises on: connection error, empty response, JSON parse failure, or
    "parameters" key not being a dict. The outer caller catches and
    falls back to regex.
    """
    provider: LLMProvider = get_llm_provider(agent_number=2, suffix="PARAMS")
    user_prompt = f"CSI section {csi_code or 'unknown'}:\n\n{text}"
    resp = await provider.complete(
        system_prompt=_LLM_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=8192,
    )
    content = (resp.content or "").strip()
    if not content:
        raise ValueError("LLM returned empty content")

    data = _parse_llm_json(content)
    raw_params = data.get("parameters")
    if not isinstance(raw_params, dict):
        raise ValueError("LLM 'parameters' is not a dict")

    warnings: list[str] = []
    normalized: dict[str, dict] = {}
    for name, raw_entry in raw_params.items():
        if name not in _PARAM_SPEC_BY_NAME:
            warnings.append(f"Ignoring unknown parameter returned by LLM: {name!r}")
            continue
        if not isinstance(raw_entry, dict):
            warnings.append(
                f"Could not normalize {name}: LLM returned non-dict entry"
            )
            continue
        norm = _normalize_parameter(name, raw_entry, warnings)
        if norm is not None:
            normalized[name] = norm

    return normalized, warnings


def _parse_llm_json(content: str) -> dict:
    body = _strip_json_fences(content)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc


def _strip_json_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Regex fallback path
# ---------------------------------------------------------------------------


def _regex_extract(text: str) -> dict:
    """Best-effort regex extraction. Only attempts params with a pattern."""
    out: dict[str, dict] = {}
    if not text:
        return out
    for spec in PARAM_SPECS:
        if spec.regex_pattern is None:
            continue
        m = re.search(spec.regex_pattern, text)
        if not m:
            continue
        raw_value = m.group(1) if m.groups() else m.group(0)
        source = m.group(0)[:200]
        entry = {
            "value": raw_value,
            "source_text": source,
            "confidence": spec.regex_confidence,
        }
        # Regex normalization warnings are dropped on purpose — regex path
        # is opportunistic; failures here just mean "skip this param".
        normalized = _normalize_parameter(spec.name, entry, warnings=[])
        if normalized is not None:
            out[spec.name] = normalized
    return out


# ---------------------------------------------------------------------------
# Per-parameter normalization
# ---------------------------------------------------------------------------


def _normalize_parameter(
    name: str,
    raw_entry: dict,
    warnings: list[str],
) -> dict | None:
    """Validate + normalize a single parameter entry.

    Returns the entry with value coerced per its ParamSpec, or None if it
    can't be rescued (with a warning appended in that case).
    """
    spec = _PARAM_SPEC_BY_NAME.get(name)
    if spec is None:
        return None

    raw_value = raw_entry.get("value")
    source_text = raw_entry.get("source_text")
    confidence = raw_entry.get("confidence")

    normalizer = _NORMALIZERS[name]
    normalized_value = normalizer(raw_value, warnings, name=name)
    if normalized_value is None:
        return None

    return {
        "value": normalized_value,
        "source_text": (str(source_text).strip() if source_text else "")[:300],
        "confidence": _clamp_confidence(confidence, warnings, name=name),
    }


def _clamp_confidence(
    value: Any, warnings: list[str], *, name: str
) -> float:
    try:
        v = float(value) if value is not None else 0.5
    except (TypeError, ValueError):
        warnings.append(
            f"Non-numeric confidence for {name!r}, defaulting to 0.5"
        )
        return 0.5
    if v > 1.0:
        warnings.append(
            f"Confidence for {name!r} exceeds 1.0 (LLM bug); clamping."
        )
        return 1.0
    if v < 0.0:
        warnings.append(
            f"Confidence for {name!r} negative; clamping to 0.0."
        )
        return 0.0
    return v


# -- f_c_psi ---------------------------------------------------------------


def _norm_f_c_psi(value: Any, warnings: list[str], *, name: str) -> int | None:
    try:
        if isinstance(value, bool):
            return None  # bool is int subclass; reject
        if isinstance(value, (int, float)):
            v = int(round(float(value)))
        elif isinstance(value, str):
            s = re.sub(r"[^\d.]", "", value)
            if not s:
                return None
            v = int(round(float(s)))
        else:
            return None
    except (ValueError, TypeError):
        warnings.append(f"Could not cast {name} to int: {value!r}")
        return None
    if v < 1000 or v > 20000:
        # Out of physically plausible concrete range.
        return None
    return v


# -- cement_type -----------------------------------------------------------

_CEMENT_KNOWN = {"Type I", "Type II", "Type I/II", "Type III", "Type IV", "Type V"}


def _norm_cement_type(
    value: Any, warnings: list[str], *, name: str
) -> str | None:
    if not isinstance(value, str):
        return None
    v = re.sub(r"\s+", " ", value.strip())
    if not v:
        return None
    # Prepend "Type " if the LLM/regex returned a bare roman numeral
    if not v.lower().startswith("type "):
        v = f"Type {v}"
    # Canonicalize the roman-numeral portion to uppercase
    v = re.sub(
        r"(?i)^Type\s+([ivx/]+)",
        lambda m: f"Type {m.group(1).upper()}",
        v,
    )
    if v not in _CEMENT_KNOWN:
        warnings.append(f"Unrecognized cement_type {v!r}; keeping as-is.")
    return v


# -- aggregate_max_size_inches ---------------------------------------------


def _norm_aggregate(
    value: Any, warnings: list[str], *, name: str
) -> float | None:
    v: float | None = None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
    elif isinstance(value, str):
        s = value.strip().lower()
        if not s:
            return None
        if "mm" in s:
            num = re.search(r"(\d+(?:\.\d+)?)", s)
            if not num:
                return None
            v = float(num.group(1)) * 0.03937  # mm -> inches
        elif "/" in s:
            frac = re.search(r"(\d+)\s*/\s*(\d+)", s)
            if not frac or int(frac.group(2)) == 0:
                return None
            # Optional whole-number prefix, e.g., "1 1/2"
            whole = re.match(r"\s*(\d+)\s+\d+\s*/\s*\d+", s)
            base = float(whole.group(1)) if whole else 0.0
            v = base + float(frac.group(1)) / float(frac.group(2))
        else:
            num = re.search(r"(\d+(?:\.\d+)?)", s)
            if not num:
                return None
            v = float(num.group(1))
    else:
        return None

    if v is None or v < 0.1 or v > 3.0:
        return None
    return round(v, 3)


# -- slump_range_inches ----------------------------------------------------


def _norm_slump(value: Any, warnings: list[str], *, name: str) -> str | None:
    if not isinstance(value, str):
        if value is None:
            return None
        value = str(value)
    s = value.strip()
    if not s:
        return None
    return s


# -- air_entrainment_pct ---------------------------------------------------

_AIR_NONE_TERMS = ("none", "not required", "n/a", "zero", "0", "0%")


def _norm_air(value: Any, warnings: list[str], *, name: str) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    lower = s.lower()
    for term in _AIR_NONE_TERMS:
        if lower == term or lower.startswith(term):
            return "none"
    return s


# -- rebar_grade -----------------------------------------------------------


def _norm_rebar(value: Any, warnings: list[str], *, name: str) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"(\d{2,3})", s)
    if not m:
        return None
    n = int(m.group(1))
    if n not in (40, 60, 75, 80, 100):
        warnings.append(f"Unrecognized rebar_grade number {n}; keeping as-is.")
    return f"Grade {n}"


# -- finish_class / curing_method (simple strip) ---------------------------


def _norm_string_passthrough(
    value: Any, warnings: list[str], *, name: str
) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


_NORMALIZERS = {
    "f_c_psi": _norm_f_c_psi,
    "cement_type": _norm_cement_type,
    "aggregate_max_size_inches": _norm_aggregate,
    "slump_range_inches": _norm_slump,
    "air_entrainment_pct": _norm_air,
    "rebar_grade": _norm_rebar,
    "finish_class": _norm_string_passthrough,
    "curing_method": _norm_string_passthrough,
}
