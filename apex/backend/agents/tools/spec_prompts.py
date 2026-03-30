"""Prompt templates for Agent 2's LLM-powered CSI spec parsing."""

import json
import logging
import re

logger = logging.getLogger("apex.tools.spec_prompts")


SPEC_PARSER_SYSTEM_PROMPT = """You are a construction specification parser specializing in CSI MasterFormat 2016.

Your task: Extract all specification sections from the provided construction document text. For each section found, identify:

1. **section_number** — The CSI MasterFormat section number (format: XX XX XX, e.g., "03 30 00" for Cast-in-Place Concrete)
2. **title** — The section title as written in the document
3. **division** — The 2-digit CSI division number (first two digits, e.g., "03" for Concrete)
4. **content** — The full text content of that section (all paragraphs, articles, and sub-articles)
5. **page_reference** — Page number(s) where this section appears, if identifiable from the text

Rules:
- Only extract sections that have a valid CSI MasterFormat number
- Include ALL content under each section — articles, sub-articles, paragraphs, notes, and referenced standards
- If a section spans multiple pages, capture all content
- Do not invent sections that don't exist in the document
- If the document references a section but doesn't include its content, note it with content: "Referenced but not included"
- Preserve technical terminology, product names, and specification language exactly as written

Respond ONLY with a JSON array. No markdown, no explanation, no preamble. Example format:
[
  {
    "section_number": "03 30 00",
    "title": "Cast-in-Place Concrete",
    "division": "03",
    "content": "PART 1 - GENERAL\\n1.1 SUMMARY\\nA. This section includes...",
    "page_reference": "45-52"
  }
]

If no valid CSI sections are found in the text, respond with an empty array: []"""


SPEC_PARSER_USER_PROMPT = """Parse the following construction specification document text and extract all CSI MasterFormat sections as JSON.

DOCUMENT TEXT:
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
    - Truncated arrays that cut off mid-object (finds last complete ``}``)
    - Incomplete string values ending mid-word before the last complete object
    - Arrays that start with ``[`` but are missing the closing ``]``

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

    # Find the position of the last complete '}' in the string
    last_brace = s.rfind("}")
    if last_brace == -1:
        raise ValueError("No closing brace '}' found, cannot salvage any objects")

    # Truncate to just after the last '}' and close the array
    candidate = s[: last_brace + 1].rstrip()

    # Strip any trailing comma left after the last object
    candidate = candidate.rstrip(",").rstrip()

    # Close the array if needed
    if not candidate.endswith("]"):
        candidate += "]"

    # Validate the repaired candidate
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError as exc:
        raise ValueError(f"Repair attempt still invalid JSON: {exc}") from exc


def parse_and_validate_llm_sections(raw_response: str) -> list[dict]:
    """Parse LLM response into validated section dicts.

    Raises ValueError if response is not valid JSON or sections are malformed.
    """
    cleaned = _clean_llm_json_response(raw_response)

    try:
        sections = json.loads(cleaned)
    except json.JSONDecodeError as original_exc:
        try:
            repaired = _try_repair_json(cleaned)
            sections = json.loads(repaired)
            logger.warning(
                "Repaired truncated JSON: salvaged %d sections from malformed response",
                len(sections) if isinstance(sections, list) else 0,
            )
        except (ValueError, json.JSONDecodeError):
            raise original_exc

    if not isinstance(sections, list):
        raise ValueError(f"Expected JSON array, got {type(sections).__name__}")

    validated = []

    for s in sections:
        # Required fields check
        if not all(k in s for k in ("section_number", "title", "division", "content")):
            continue  # Skip malformed entries

        # Normalize section number to "XX XX XX" format
        raw_num = str(s["section_number"]).strip()
        digits = re.sub(r'\D', '', raw_num)
        if len(digits) != 6:
            continue  # Skip invalid section numbers
        num = f"{digits[:2]} {digits[2:4]} {digits[4:6]}"

        division = str(s.get("division", digits[:2])).strip().zfill(2)

        validated.append({
            "section_number": num,
            "title": str(s["title"]).strip(),
            "division": division,
            "content": str(s["content"]),
            "page_reference": str(s.get("page_reference", "")),
        })

    return validated
