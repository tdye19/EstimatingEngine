"""Agent 4: Quantity Takeoff Agent.

Extracts measurable quantities from scope descriptions and drawing references.
Uses LLM-first extraction (Claude Sonnet) when a provider is available;
falls back to regex per-section extraction if the LLM is unavailable or fails.
"""

import asyncio
import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.gap_report import GapReport
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.agents.tools.takeoff_tools import (
    quantity_calculator_tool,
    drawing_reference_linker_tool,
)

logger = logging.getLogger("apex.agent.takeoff")


# ---------------------------------------------------------------------------
# Pydantic contract for individual takeoff items returned by the LLM
# ---------------------------------------------------------------------------

class LLMTakeoffItem(BaseModel):
    """Validated takeoff item parsed from LLM JSON response."""

    description: str
    quantity: float
    unit: str                                    # SF, LF, CY, EA, LS, …
    csi_code: str
    source: Literal["specified", "estimated"]
    confidence: Literal["high", "medium", "low"]
    unreasonable_flag: Optional[bool] = False
    notes: Optional[str] = None

    @field_validator("unit", mode="before")
    @classmethod
    def _normalise_unit(cls, v: str) -> str:
        return str(v).upper().strip()

    @field_validator("csi_code", mode="before")
    @classmethod
    def _normalise_csi_code(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("quantity", mode="before")
    @classmethod
    def _normalise_quantity(cls, v) -> float:
        """Accept numeric quantities and clean comma-formatted strings."""
        if isinstance(v, (int, float)):
            return float(v)
        cleaned = str(v).replace(",", "").strip()
        return float(cleaned)

    @field_validator("source", mode="before")
    @classmethod
    def _normalise_source(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, v: str) -> str:
        return str(v).lower().strip()


# ---------------------------------------------------------------------------
# System prompt (built once at module load)
# ---------------------------------------------------------------------------

TAKEOFF_SYSTEM_PROMPT = (
    "You are a senior construction quantity surveyor. Extract ALL quantifiable items "
    "from these specification sections. For each item, determine the quantity, unit of "
    "measure, and CSI code.\n\n"
    "## Standard Construction Units — always convert to these:\n"
    "  SF  = Square Feet      (floors, walls, ceilings, roofing, paving)\n"
    "  LF  = Linear Feet      (piping, conduit, curbs, fencing, trim)\n"
    "  CY  = Cubic Yards      (concrete, earthwork, fill)\n"
    "  CF  = Cubic Feet       (smaller volumes)\n"
    "  SY  = Square Yards     (site paving, carpet)\n"
    "  EA  = Each             (doors, windows, fixtures, equipment units)\n"
    "  LS  = Lump Sum         (work without a measurable quantity)\n"
    "  TON = Tons             (structural steel, aggregate)\n"
    "  LB  = Pounds           (rebar, miscellaneous metals)\n"
    "  GAL = Gallons          (paint, sealers, fluids)\n"
    "  SQ  = Squares          (roofing, 1 SQ = 100 SF)\n"
    "  HR  = Hours            (time-based items)\n\n"
    "## Number Format Handling — convert all written or formatted numbers to plain floats:\n"
    '  "twelve hundred"  → 1200.0\n'
    '  "1,200 SF"        → 1200.0\n'
    '  "1200 SF"         → 1200.0\n'
    '  "twenty-five"     → 25.0\n\n'
    "## Flagging Unreasonable Quantities:\n"
    'Set "unreasonable_flag": true when a quantity seems implausible for the building '
    "size or scope (e.g., 10 SF of concrete slab for a commercial building, or "
    "1,000,000 LF of piping). Apply engineering judgment based on the apparent building type.\n\n"
    "## Vague Quantities (\"as required\", \"as needed\", \"per plans\", \"where shown\"):\n"
    "Estimate a reasonable quantity based on building type and typical industry ratios "
    "(e.g., 1 duplex outlet per 150 SF for office, 1 sprinkler head per 130 SF). "
    'Set "source": "estimated" and "confidence": "low" for all such items.\n\n'
    "## Gap Analysis Items:\n"
    "The user prompt may include gap analysis items — scope identified as missing from "
    "the specs. Provide estimated quantities for these gap items and set "
    '"source": "estimated".\n\n'
    "## Source Field:\n"
    '  "specified"  — quantity is explicitly stated or clearly calculable from the spec\n'
    '  "estimated"  — quantity is implied, vague, or derived from gap analysis\n\n'
    "## Confidence Field:\n"
    '  "high"   — explicit numeric quantity in standard units\n'
    '  "medium" — quantity calculable with minor assumptions\n'
    '  "low"    — vague spec language or gap-analysis-derived estimate\n\n'
    "## Output Format:\n"
    "Respond ONLY with a valid JSON array. No markdown fences, no explanation, "
    "no preamble — just the raw JSON array.\n\n"
    "Each object must have exactly these fields:\n"
    '  "description"       — clear description of the scope item\n'
    '  "quantity"          — numeric value as a float\n'
    '  "unit"              — one of: SF, LF, CY, CF, SY, EA, LS, TON, LB, GAL, SQ, HR\n'
    '  "csi_code"          — CSI MasterFormat section number (e.g., "03 30 00")\n'
    '  "source"            — "specified" or "estimated"\n'
    '  "confidence"        — "high", "medium", or "low"\n'
    '  "unreasonable_flag" — true if the quantity seems wrong, false otherwise\n'
    '  "notes"             — brief explanation for estimated items or flags (null otherwise)\n\n'
    "Extract EVERY distinct quantifiable item. Multiple items per CSI section are expected "
    "and encouraged — a concrete section might yield slab SF, wall CY, and footing CY as "
    "separate items."
)


# ---------------------------------------------------------------------------
# Async helper (same pattern used by Agent 2 and Agent 3)
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

def _build_user_prompt(sections: list, gap_items: list) -> str:
    """Construct the user-facing prompt containing spec sections + gap items."""
    spec_data = []
    for s in sections:
        text = ""
        if s.work_description:
            text += s.work_description + "\n"
        if s.execution_requirements:
            text += s.execution_requirements + "\n"
        if s.raw_text and not text.strip():
            text = s.raw_text
        spec_data.append({
            "section_number": s.section_number,
            "title": s.title,
            "division": s.division_number,
            "content": text.strip()[:3000],   # per-section cap to stay within context
        })

    gap_data = [
        {
            "division_number": g.division_number,
            "section_number": g.section_number,
            "title": g.title,
            "gap_type": g.gap_type,
            "severity": g.severity,
            "description": g.description,
        }
        for g in gap_items
    ]

    parts = [
        "SPEC SECTIONS — extract all quantifiable items; mark source as 'specified' "
        "when the quantity is explicit, 'estimated' when vague or inferred:",
        json.dumps(spec_data, indent=2),
    ]
    if gap_data:
        parts += [
            "\nGAP ANALYSIS ITEMS — scope identified as missing from the specs. "
            "Provide estimated quantities for each gap item and set source='estimated':",
            json.dumps(gap_data, indent=2),
        ]
    parts.append(
        "\nExtract ALL quantifiable takeoff items from the spec sections above and "
        "provide estimated quantities for every gap analysis item."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM response parser + Pydantic validator
# ---------------------------------------------------------------------------

def _parse_llm_takeoff_response(raw_content: str) -> list[LLMTakeoffItem]:
    """Strip markdown fences, parse JSON, and validate each item with Pydantic."""
    content = raw_content.strip()
    # Strip optional markdown code fences (```json … ```)
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Agent 4 LLM: JSON parse error — {exc}")
        return []

    if not isinstance(data, list):
        logger.error(f"Agent 4 LLM: expected JSON array, got {type(data).__name__}")
        return []

    validated: list[LLMTakeoffItem] = []
    for i, item in enumerate(data):
        try:
            validated.append(LLMTakeoffItem.model_validate(item))
        except Exception as exc:
            logger.warning(f"Agent 4 LLM: skipping malformed takeoff item [{i}]: {exc}")

    return validated


# ---------------------------------------------------------------------------
# Async LLM call
# ---------------------------------------------------------------------------

async def _llm_takeoff(
    sections: list,
    gap_items: list,
    provider,
) -> tuple[list[LLMTakeoffItem] | None, int, int]:
    """Send spec + gap context to LLM and return (validated_items, input_tokens, output_tokens)."""
    user_prompt = _build_user_prompt(sections, gap_items)
    try:
        response = await provider.complete(
            system_prompt=TAKEOFF_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=8192,
        )
        logger.info(
            f"Agent 4 LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"total_tokens={response.input_tokens + response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )
        items = _parse_llm_takeoff_response(response.content)
        logger.info(f"Agent 4 LLM: parsed {len(items)} validated takeoff items")
        return items, response.input_tokens, response.output_tokens
    except Exception as exc:
        logger.error(f"Agent 4 LLM: call failed — {exc}")
        return None, 0, 0


# ---------------------------------------------------------------------------
# Confidence literal → float conversion
# ---------------------------------------------------------------------------

_CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.90,
    "medium": 0.65,
    "low": 0.35,
}


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_takeoff_agent(db: Session, project_id: int) -> dict:
    """Generate quantity takeoff items from parsed spec sections.

    Execution order:
      1. Try LLM path — get_llm_provider(agent_number=4), health-check, call LLM.
         The LLM receives both spec sections AND gap analysis results so it can
         attempt quantities for gap items (marked "estimated") as well as items
         with explicit quantities (marked "specified").
      2. If LLM is unavailable or returns nothing, fall back to per-section
         regex extraction (original logic, unchanged).

    Returns dict validated against the Agent4Output pipeline contract.
    """
    # Fetch all parsed spec sections for this project
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).all()

    # Fetch gap items from the most recent gap report for this project
    gap_report = (
        db.query(GapReport)
        .filter(
            GapReport.project_id == project_id,
            GapReport.is_deleted == False,  # noqa: E712
        )
        .order_by(GapReport.id.desc())
        .first()
    )
    gap_items = gap_report.items if gap_report else []

    items_created = 0
    section_results = []
    takeoff_method = "regex"
    tokens_used = 0
    _in_tok = 0
    _out_tok = 0

    # -----------------------------------------------------------------------
    # Attempt LLM-powered quantity takeoff
    # -----------------------------------------------------------------------
    provider = None
    llm_available = False

    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=4)
        llm_available = _run_async(provider.health_check())
        if llm_available:
            logger.info(
                f"Agent 4: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — attempting LLM quantity takeoff"
            )
        else:
            logger.info(
                f"Agent 4: LLM provider '{provider.provider_name}' is unreachable — "
                "using regex fallback"
            )
    except Exception as exc:
        logger.warning(
            f"Agent 4: could not initialise LLM provider ({exc}) — using regex fallback"
        )

    if llm_available and provider is not None and sections:
        llm_items, _in_tok, _out_tok = _run_async(_llm_takeoff(sections, gap_items, provider))
        tokens_used = _in_tok + _out_tok

        if llm_items:
            log_token_usage(
                db=db,
                project_id=project_id,
                agent_number=4,
                provider=provider.provider_name,
                model=provider.model_name,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
            )
            takeoff_method = "llm"
            # Build a lookup so LLM items can be linked back to their SpecSection
            section_by_number = {s.section_number: s for s in sections}

            for item in llm_items:
                section = section_by_number.get(item.csi_code)
                section_id = section.id if section else None
                confidence_float = _CONFIDENCE_MAP.get(item.confidence, 0.65)

                # Compose notes: include source tag, optional LLM notes, and flag
                note_parts = [f"source={item.source}"]
                if item.notes:
                    note_parts.append(item.notes)
                if item.unreasonable_flag:
                    note_parts.append("WARNING: quantity flagged as potentially unreasonable")
                notes_str = " | ".join(note_parts)

                takeoff = TakeoffItem(
                    project_id=project_id,
                    spec_section_id=section_id,
                    csi_code=item.csi_code,
                    description=item.description[:500],
                    quantity=item.quantity,
                    unit_of_measure=item.unit,
                    confidence=confidence_float,
                    notes=notes_str,
                )
                db.add(takeoff)
                items_created += 1

                section_results.append({
                    "section_id": section_id,
                    "section_number": item.csi_code,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "confidence": confidence_float,
                    "drawings": [],
                    "source": item.source,
                })

            db.commit()
            logger.info(
                f"Agent 4: LLM path succeeded — {items_created} takeoff items created "
                f"(provider={provider.provider_name}, model={provider.model_name}, "
                f"tokens_used={tokens_used})"
            )
        else:
            logger.warning(
                "Agent 4: LLM returned no valid takeoff items — falling back to regex extraction"
            )

    # -----------------------------------------------------------------------
    # Regex fallback — original per-section extraction logic
    # -----------------------------------------------------------------------
    if takeoff_method == "regex":
        logger.info("Agent 4: using regex quantity extraction (fallback path)")

        for section in sections:
            try:
                # Combine work description and execution requirements for extraction
                text_to_parse = ""
                if section.work_description:
                    text_to_parse += section.work_description + "\n"
                if section.execution_requirements:
                    text_to_parse += section.execution_requirements + "\n"
                if section.raw_text and not text_to_parse.strip():
                    text_to_parse = section.raw_text

                if not text_to_parse.strip():
                    continue

                qty_result = quantity_calculator_tool(text_to_parse)
                drawing_refs = drawing_reference_linker_tool(text_to_parse)

                takeoff = TakeoffItem(
                    project_id=project_id,
                    spec_section_id=section.id,
                    csi_code=section.section_number,
                    description=f"{section.title} - {qty_result['description'][:200]}",
                    quantity=qty_result["quantity"],
                    unit_of_measure=qty_result["unit"],
                    drawing_reference=", ".join(drawing_refs) if drawing_refs else None,
                    confidence=qty_result["confidence"],
                )
                db.add(takeoff)
                items_created += 1

                section_results.append({
                    "section_id": section.id,
                    "section_number": section.section_number,
                    "quantity": qty_result["quantity"],
                    "unit": qty_result["unit"],
                    "confidence": qty_result["confidence"],
                    "drawings": drawing_refs,
                })

            except Exception as e:
                logger.error(f"Failed takeoff for section {section.id}: {e}")
                section_results.append({
                    "section_id": section.id,
                    "section_number": section.section_number,
                    "error": str(e),
                })

        db.commit()

    logger.info(
        f"Agent 4 complete: {items_created} items created, "
        f"method={takeoff_method}, tokens_used={tokens_used}, "
        f"sections={len(sections)}, gap_items={len(gap_items)}"
    )

    return validate_agent_output(4, {
        "items_created": items_created,
        "sections_processed": len(sections),
        "results": section_results,
        "takeoff_method": takeoff_method,
        "tokens_used": tokens_used,
    })
