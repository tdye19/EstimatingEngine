"""Prompt templates for Agent 2's LLM-powered CSI spec parsing.

v2: Extract spec parameters (material specs, quality, standards) — NOT quantities.
"""

import json
import logging
import re

logger = logging.getLogger("apex.tools.spec_prompts")


SPEC_PARSER_SYSTEM_PROMPT = """\
You are parsing a construction specification. Extract ONLY what the spec defines:
- CSI divisions and sections that are IN SCOPE for this project
- Material specifications (concrete PSI, rebar grade/size, finish class, etc.)
- Quality and testing requirements
- Submittal requirements
- Referenced standards (ACI, ASTM, CRSI, ANSI, AWS codes)

Do NOT extract or estimate quantities, dimensions, counts, areas, volumes, or any
numeric values that would come from drawings. Those are not in specifications.

For each section found, return a JSON object with these fields:
{
  "section_number": "03 30 00",
  "section_title": "Cast-in-Place Concrete",
  "division": "03",
  "in_scope": true,
  "material_specs": { ... },
  "quality_requirements": ["..."],
  "submittals_required": ["..."],
  "referenced_standards": ["..."]
}

The material_specs object depends on the division:

For concrete (03 30 00):
  {"psi": "4000", "mix_design": "...", "aggregate_type": "...", "admixtures": "...",
   "fly_ash_pct": "...", "slump": "...", "air_content": "..."}

For rebar (03 20 00):
  {"bar_sizes": ["#4", "#5"], "spacing": "...", "grade": "60", "epoxy_coated": true,
   "splice_requirements": "..."}

For formwork (03 10 00):
  {"type": "...", "finish_class": "...", "reuse_cycles": "...", "shore_requirements": "..."}

For finishing (03 35 00):
  {"finish_class": "...", "curing_method": "...", "curing_astm": "ASTM C309",
   "tolerances_aci": "ACI 117"}

For waterproofing (07 10 00):
  {"type": "...", "thickness_mils": "...", "manufacturer": "..."}

For structural steel (05 12 00):
  {"grade": "...", "connection_type": "...", "fireproofing": "..."}

For any other division, use a generic format:
  {"requirements": ["bullet 1", "bullet 2", ...]}

Rules:
- If the spec does not specify a parameter, OMIT it. Do not guess or use default values.
- Only extract sections with valid CSI MasterFormat numbers.
- Set in_scope to false only if the spec explicitly excludes the section.
- Preserve technical terminology and product names exactly as written.
- quality_requirements: testing frequency, inspection holds, tolerances, lab requirements.
- submittals_required: shop drawings, mix designs, product data, samples, mock-ups.
- referenced_standards: list standard codes like "ACI 318", "ASTM C150", "CRSI Manual".

Respond ONLY with a JSON array. No markdown, no explanation, no preamble.

Example:
[
  {
    "section_number": "03 30 00",
    "section_title": "Cast-in-Place Concrete",
    "division": "03",
    "in_scope": true,
    "material_specs": {
      "psi": "4000",
      "aggregate_type": "crushed limestone",
      "slump": "4 inches",
      "air_content": "5-7%"
    },
    "quality_requirements": [
      "Cylinder tests per ACI 318: one set of 4 per 50 CY or fraction",
      "Slump test at point of placement"
    ],
    "submittals_required": [
      "Mix design per ACI 211",
      "Ready-mix plant certification"
    ],
    "referenced_standards": ["ACI 318", "ACI 211", "ASTM C150", "ASTM C33"]
  },
  {
    "section_number": "03 20 00",
    "section_title": "Concrete Reinforcing",
    "division": "03",
    "in_scope": true,
    "material_specs": {
      "bar_sizes": ["#4", "#5", "#6"],
      "grade": "60",
      "epoxy_coated": false
    },
    "quality_requirements": ["Mill certificates required"],
    "submittals_required": ["Shop drawings", "Mill certificates"],
    "referenced_standards": ["ASTM A615", "CRSI Manual of Standard Practice"]
  }
]

If no valid CSI sections are found, respond with an empty array: []"""


SPEC_PARSER_USER_PROMPT = """\
Parse the following construction specification text. Extract all CSI MasterFormat \
sections with their material specifications, quality requirements, submittals, and \
referenced standards. Do NOT extract quantities or dimensions.

SPECIFICATION TEXT:
---
{document_text}
---

Return ONLY the JSON array of sections found."""


def _clean_llm_json_response(raw_response: str) -> str:
    """Strip markdown code fences from an LLM response and return raw JSON.

    Gemini 2.5 Flash sometimes wraps JSON in ```json ... ``` blocks even when
    instructed not to, and may prepend an introductory sentence. This function
    extracts the JSON array from anywhere in the response.
    """
    cleaned = raw_response.strip()
    # Prefer extracting from a fenced code block (handles Gemini's style)
    code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', cleaned)
    if code_block:
        return code_block.group(1).strip()
    # Fallback: strip leading/trailing fences if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    return cleaned


def _try_repair_json(raw: str) -> str:
    """Attempt to fix common Gemini truncation issues in a JSON array string.

    Handles:
    - Truncated arrays that cut off mid-object (finds last complete top-level ``}``)
    - Incomplete string values ending mid-word before the last complete object
    - Arrays that start with ``[`` but are missing the closing ``]``

    Uses brace-depth tracking that respects JSON string boundaries so it won't
    be confused by ``}`` characters embedded in content values.

    Returns the repaired JSON string.
    Raises ValueError if the string cannot be meaningfully repaired.
    """
    s = raw.strip()

    # Already valid — nothing to do
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass

    if not s.startswith("["):
        raise ValueError("Response does not start with '[', cannot repair")

    # Estimate how many sections the raw text intended to contain
    expected = len(re.findall(r'"section_number"', s))

    # Walk the string tracking brace depth outside of JSON strings.
    # Record the position after each top-level object closes (depth 0→1→0).
    last_complete_obj_end = -1
    complete_count = 0
    depth = 0
    in_string = False
    escape_next = False

    for i in range(1, len(s)):  # skip opening '['
        c = s[i]
        if escape_next:
            escape_next = False
            continue
        if in_string:
            if c == '\\':
                escape_next = True
            elif c == '"':
                in_string = False
            continue
        # Outside a string
        if c == '"':
            in_string = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                last_complete_obj_end = i
                complete_count += 1

    if last_complete_obj_end == -1:
        raise ValueError("No complete JSON objects found, cannot salvage")

    # Truncate to just after the last complete top-level object and close array
    candidate = s[: last_complete_obj_end + 1].rstrip().rstrip(",") + "]"

    # Validate the repaired candidate
    try:
        parsed = json.loads(candidate)
        salvaged = len(parsed) if isinstance(parsed, list) else 0
        logger.warning(
            "Repaired truncated JSON: salvaged %d of ~%d sections from malformed response",
            salvaged,
            expected,
        )
        return candidate
    except json.JSONDecodeError as exc:
        raise ValueError(f"Repair attempt still invalid JSON: {exc}") from exc


def parse_and_validate_llm_sections(raw_response: str) -> list[dict]:
    """Parse LLM response into validated section dicts (v2: spec parameters).

    Returns list of dicts with: section_number, division, section_title, in_scope,
    material_specs, quality_requirements, submittals_required, referenced_standards.

    Raises ValueError if response is not valid JSON or sections are malformed.
    """
    cleaned = _clean_llm_json_response(raw_response)

    try:
        sections = json.loads(cleaned)
    except json.JSONDecodeError as original_exc:
        logger.warning(
            "JSON parse failed on cleaned response (first 500 chars): %s",
            cleaned[:500],
        )
        try:
            repaired = _try_repair_json(cleaned)
            sections = json.loads(repaired)
        except (ValueError, json.JSONDecodeError) as repair_exc:
            logger.warning("JSON repair also failed: %s", repair_exc)
            raise original_exc

    if not isinstance(sections, list):
        raise ValueError(f"Expected JSON array, got {type(sections).__name__}")

    validated = []

    skipped_fields = 0
    skipped_numbers = 0

    for s in sections:
        # v2 required fields: section_number + section_title (or title) + division
        title = s.get("section_title") or s.get("title")
        if not s.get("section_number") or not title or not s.get("division"):
            skipped_fields += 1
            continue

        # Normalize section number to "XX XX XX" format
        raw_num = str(s["section_number"]).strip()
        digits = re.sub(r'\D', '', raw_num)
        if 3 <= len(digits) <= 5:
            digits = digits.zfill(6)
        if len(digits) != 6:
            skipped_numbers += 1
            logger.warning("Skipping section with invalid number %r (digits=%r)", raw_num, digits)
            continue
        num = f"{digits[:2]} {digits[2:4]} {digits[4:6]}"

        division = str(s.get("division", digits[:2])).strip().zfill(2)

        validated.append({
            "section_number": num,
            "section_title": str(title).strip(),
            "division": division,
            "in_scope": s.get("in_scope", True),
            "material_specs": s.get("material_specs") or {},
            "quality_requirements": s.get("quality_requirements") or [],
            "submittals_required": s.get("submittals_required") or [],
            "referenced_standards": s.get("referenced_standards") or [],
        })

    if skipped_fields or skipped_numbers:
        logger.warning(
            "Section validation: %d accepted, %d skipped (missing fields), %d skipped (bad number) out of %d total",
            len(validated), skipped_fields, skipped_numbers, len(sections),
        )

    return validated
