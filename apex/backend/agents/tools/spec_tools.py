"""Spec parsing tools for Agent 2."""

import json
import os
import re
import logging

logger = logging.getLogger("apex.tools.spec")

_AGENT_2_CHUNK_PAGES = int(os.environ.get("AGENT_2_CHUNK_PAGES", "40"))
_TOKEN_CHUNK_THRESHOLD = 500_000  # estimated tokens; trigger chunking above this
# Output-protection: even large-context providers (Gemini 1M, Anthropic 200K)
# truncate output at max_tokens.  Chunk large specs so each chunk produces
# fewer sections → smaller output → no truncation.
_OUTPUT_SAFE_WORDS = int(os.environ.get("AGENT_2_OUTPUT_SAFE_WORDS", "15000"))

# CSI Division ranges
DIVISION_RANGES = {
    "03": (30000, 39999),
    "04": (40000, 49999),
    "05": (50000, 59999),
    "06": (60000, 69999),
    "07": (70000, 79999),
    "08": (80000, 89999),
    "09": (90000, 99999),
    "10": (100000, 109999),
    "11": (110000, 119999),
    "12": (120000, 129999),
    "13": (130000, 139999),
    "14": (140000, 149999),
    "21": (210000, 219999),
    "22": (220000, 229999),
    "23": (230000, 239999),
    "26": (260000, 269999),
    "27": (270000, 279999),
    "28": (280000, 289999),
    "31": (310000, 319999),
    "32": (320000, 329999),
    "33": (330000, 339999),
}


def chunk_document(text: str, max_words: int = 3000) -> list[str]:
    """Split document into chunks on paragraph boundaries, not mid-sentence."""
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_chunk: list[str] = []
    current_word_count = 0

    for para in paragraphs:
        word_count = len(para.split())
        if current_word_count + word_count > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_word_count = word_count
        else:
            current_chunk.append(para)
            current_word_count += word_count

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks if chunks else [text]


async def llm_parse_spec_sections(
    document_text: str, provider
) -> tuple[list[dict], int, int]:
    """Use LLM to extract CSI MasterFormat sections from spec text.

    Returns (sections, total_input_tokens, total_output_tokens).
    sections is a list of dicts: {section_number, division_number, title, content}.
    Sends full text to Anthropic (200K), Gemini (1M), and OpenRouter (large-context
    models including Gemini); chunks for Ollama (small context).
    Raises an exception on parse failure — caller should fall back to regex.
    """
    from apex.backend.agents.tools.spec_prompts import (
        SPEC_PARSER_SYSTEM_PROMPT,
        SPEC_PARSER_USER_PROMPT,
        parse_and_validate_llm_sections,
    )

    word_count = len(document_text.split())
    estimated_tokens = word_count * 1.3
    max_words_per_chunk = _AGENT_2_CHUNK_PAGES * 250  # 250 words ≈ 1 page

    if estimated_tokens > _TOKEN_CHUNK_THRESHOLD:
        chunks = chunk_document(document_text, max_words=max_words_per_chunk)
        logger.info(
            "Agent 2: estimated %.0f tokens exceeds threshold %d — using %d chunks "
            "of ~%d words each (provider=%s)",
            estimated_tokens,
            _TOKEN_CHUNK_THRESHOLD,
            len(chunks),
            max_words_per_chunk,
            provider.provider_name,
        )
    elif provider.provider_name not in ("anthropic", "gemini", "openrouter"):
        chunks = chunk_document(document_text, max_words=3000)
    elif word_count > _OUTPUT_SAFE_WORDS:
        # Input fits in context window but output may truncate at max_tokens
        # when the spec contains many sections.  Chunk to keep output bounded.
        chunks = chunk_document(document_text, max_words=_OUTPUT_SAFE_WORDS)
        logger.info(
            "Agent 2: %d words exceeds output-safe threshold %d — splitting into "
            "%d chunks to prevent output truncation (provider=%s)",
            word_count,
            _OUTPUT_SAFE_WORDS,
            len(chunks),
            provider.provider_name,
        )
    else:
        chunks = [document_text]

    all_sections: dict[str, dict] = {}  # keyed by section_number for deduplication
    total_input_tokens = 0
    total_output_tokens = 0

    async def _parse_chunk(text: str) -> list[dict]:
        """Send one chunk to the LLM and return validated sections."""
        user_prompt = SPEC_PARSER_USER_PROMPT.format(document_text=text)
        response = await provider.complete(
            system_prompt=SPEC_PARSER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=16384,
        )
        nonlocal total_input_tokens, total_output_tokens
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        finish = response.finish_reason or "unknown"
        logger.info(
            "Agent 2 chunk response: %d chars, %d input_tokens, %d output_tokens, "
            "finish_reason=%s, first 200 chars: %s",
            len(response.content),
            response.input_tokens,
            response.output_tokens,
            finish,
            response.content[:200],
        )
        logger.debug(
            "Agent 2 chunk response last 200 chars: %s",
            response.content[-200:],
        )
        if finish == "MAX_TOKENS":
            logger.warning(
                "Agent 2: LLM hit MAX_TOKENS — response likely truncated "
                "(%d output tokens, provider=%s)", response.output_tokens,
                provider.provider_name,
            )
        return parse_and_validate_llm_sections(response.content)

    for i, chunk in enumerate(chunks):
        try:
            sections = await _parse_chunk(chunk)
        except json.JSONDecodeError:
            # One level of re-splitting — split the chunk in half and retry each half
            logger.warning("Chunk %d JSON parse failed, re-splitting into 2 sub-chunks", i)
            mid = len(chunk) // 2
            # Snap the split point to the nearest paragraph boundary
            boundary = chunk.rfind("\n\n", 0, mid)
            if boundary == -1:
                boundary = mid
            sub_chunks = [chunk[:boundary].strip(), chunk[boundary:].strip()]
            sections = []
            for j, sub in enumerate(sub_chunks):
                if not sub:
                    continue
                try:
                    sections.extend(await _parse_chunk(sub))
                except json.JSONDecodeError:
                    logger.warning(
                        "Chunk %d sub-chunk %d also failed JSON parse — skipping", i, j
                    )

        for s in sections:
            key = s["section_number"]
            if key not in all_sections:
                all_sections[key] = s

    # Normalize to v2 dict shape (spec parameters, no content/quantities)
    result = []
    for s in all_sections.values():
        result.append({
            "section_number": s["section_number"],
            "division_number": s["division"],
            "title": s.get("section_title") or s.get("title", ""),
            "in_scope": s.get("in_scope", True),
            "material_specs": s.get("material_specs", {}),
            "quality_requirements": s.get("quality_requirements", []),
            "submittals_required": s.get("submittals_required", []),
            "referenced_standards": s.get("referenced_standards", []),
        })

    section_nums = [s["section_number"] for s in result]
    logger.info(
        "Agent 2 LLM: %d sections extracted from %d chunks (%d in / %d out tokens): %s",
        len(result),
        len(chunks),
        total_input_tokens,
        total_output_tokens,
        ", ".join(section_nums) if section_nums else "(none)",
    )

    return result, total_input_tokens, total_output_tokens


def section_extractor_tool(text: str, division_range: str = None) -> list[dict]:
    """Extract CSI MasterFormat sections from raw text.

    Delegates to regex_parse_spec_sections. Kept for backwards compatibility.
    """
    return regex_parse_spec_sections(text, division_range=division_range)


def regex_parse_spec_sections(text: str, division_range: str = None) -> list[dict]:
    """Extract CSI MasterFormat sections using regex (rule-based fallback).

    Identifies sections and extracts referenced standards from the text.
    Does NOT attempt to extract material parameters or quantities —
    the fallback guarantees "we know what divisions are in the spec."
    Returns list of dicts compatible with the v2 agent output shape.
    """
    sections = []

    # Pattern: SECTION XX XX XX or XX XX XX - Title
    pattern = r'(?:SECTION\s+)?(\d{2})\s+(\d{2})\s+(\d{2})(?:\s*[-–—]\s*(.+?))?(?:\n|$)'
    matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))

    for i, match in enumerate(matches):
        div = match.group(1)
        sec_num = f"{match.group(1)} {match.group(2)} {match.group(3)}"
        title = match.group(4).strip() if match.group(4) else f"Section {sec_num}"

        if division_range and div != division_range:
            continue

        # Extract raw text between this section and the next for standard/submittal extraction
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 5000, len(text))
        raw_content = text[start:end].strip()

        # Extract referenced standards (best-effort regex)
        standards = re.findall(r'(?:ASTM|ACI|AISI|ANSI|AWS|CRSI|AISC)\s+[A-Z]?\d+(?:[/-]\d+)?', raw_content)
        standards = sorted(set(s.strip() for s in standards))

        # Extract submittals (best-effort regex)
        submittals = []
        sub_match = re.search(r'(?i)SUBMITTALS?(.*?)(?=\n\s*\d+\.\d+|\nPART|$)', raw_content, re.DOTALL)
        if sub_match:
            sub_lines = [l.strip() for l in sub_match.group(1).strip().split('\n') if l.strip()]
            submittals = sub_lines[:10]

        sections.append({
            "section_number": sec_num,
            "division_number": div,
            "title": title,
            "in_scope": True,
            "material_specs": {},
            "quality_requirements": [],
            "submittals_required": submittals,
            "referenced_standards": standards,
            "raw_content": raw_content[:3000],
        })

    return sections


def division_mapper_tool(section_number: str) -> dict:
    """Map a section number to its CSI division."""
    parts = section_number.strip().split()
    if parts:
        div = parts[0].zfill(2)
        from apex.backend.utils.csi_utils import get_division_name
        return {
            "division_number": div,
            "division_name": get_division_name(div),
            "section_number": section_number.strip(),
        }
    return {"division_number": "00", "division_name": "Unknown", "section_number": section_number}


def keyword_tagger_tool(text: str) -> list[str]:
    """Extract relevant construction keywords from text."""
    keyword_patterns = [
        r'\b(concrete|reinforcing|rebar|formwork|cast-in-place|precast)\b',
        r'\b(steel|structural|framing|decking|joist|fabrication)\b',
        r'\b(masonry|brick|block|mortar|grout)\b',
        r'\b(waterproofing|insulation|roofing|membrane|flashing|sealant)\b',
        r'\b(drywall|gypsum|plaster|ceiling|tile|paint|coating|flooring|carpet)\b',
        r'\b(door|window|hardware|glazing|storefront|curtain\s*wall)\b',
        r'\b(electrical|lighting|switchboard|panel|conduit|wiring)\b',
        r'\b(plumbing|piping|fixture|valve|drain|hvac|ductwork)\b',
        r'\b(excavation|grading|backfill|compaction|earthwork)\b',
        r'\b(fire\s*stop|firestopping|fire\s*protection|sprinkler)\b',
        r'\b(demolition|abatement|hazmat)\b',
        r'\b(submittal|shop\s*drawing|mock-up|sample|testing)\b',
    ]
    keywords = set()
    text_lower = text.lower()
    for pattern in keyword_patterns:
        for m in re.finditer(pattern, text_lower):
            keywords.add(m.group(0).strip())
    return sorted(keywords)


def parse_section_parts(content: str) -> dict:
    """Parse a spec section into Part 1 (General), Part 2 (Products), Part 3 (Execution)."""
    result = {
        "work_description": "",
        "materials_referenced": [],
        "execution_requirements": "",
        "submittal_requirements": "",
    }

    # Try to split on PART headers
    parts = re.split(r'(?i)PART\s+(\d)', content)

    full_text = content

    # Extract work description (Part 1 / General)
    part1_match = re.search(r'(?i)PART\s+1.*?(?=PART\s+2|$)', content, re.DOTALL)
    if part1_match:
        part1 = part1_match.group(0)
        result["work_description"] = part1[:1500].strip()

        # Extract submittal requirements
        sub_match = re.search(r'(?i)SUBMITTALS?(.*?)(?=\n\s*\d+\.\d+|\nPART|$)', part1, re.DOTALL)
        if sub_match:
            result["submittal_requirements"] = sub_match.group(1).strip()[:500]

    # Extract materials (Part 2 / Products)
    part2_match = re.search(r'(?i)PART\s+2.*?(?=PART\s+3|$)', content, re.DOTALL)
    if part2_match:
        part2 = part2_match.group(0)
        materials = re.findall(r'(?i)(?:ASTM|AISI|ACI|ANSI|AWS)\s+[A-Z]?\d+', part2)
        materials += re.findall(r'(?i)(?:manufacturer|product):\s*(.+?)(?:\n|$)', part2)
        result["materials_referenced"] = list(set(m.strip() for m in materials))[:20]

    # Extract execution requirements (Part 3)
    part3_match = re.search(r'(?i)PART\s+3.*', content, re.DOTALL)
    if part3_match:
        result["execution_requirements"] = part3_match.group(0)[:1500].strip()

    # If no PART structure found, do best-effort extraction
    if not part1_match and not part2_match:
        result["work_description"] = content[:1500].strip()
        materials = re.findall(r'(?i)(?:ASTM|AISI|ACI|ANSI|AWS)\s+[A-Z]?\d+', content)
        result["materials_referenced"] = list(set(m.strip() for m in materials))[:20]

    return result
