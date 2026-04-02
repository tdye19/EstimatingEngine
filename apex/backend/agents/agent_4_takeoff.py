"""Agent 4 — Rate Recommendation Engine (v2)

Takes the estimator's uploaded takeoff (WinEst .xlsx or CSV) and matches
each line item against Productivity Brain historical data. Produces rate
recommendations with deviation flags.

NO LLM. NO QUANTITY GENERATION. ALL MATH IS DETERMINISTIC PYTHON.

Inputs:
  - Uploaded takeoff file(s) on the project (detected by classification)
  - Productivity Brain data in the database

Outputs:
  - TakeoffItemV2 rows saved to DB with rate recommendations
  - Agent4Output contract

Flow:
  1. Find uploaded takeoff document(s) for this project
  2. Parse using takeoff_parser
  3. Match against PB using rate_engine
  4. Save TakeoffItemV2 rows with recommendations
  5. Return Agent4Output
"""

import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.models.document import Document
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.takeoff_parser.parser import parse_takeoff
from apex.backend.services.rate_engine.matcher import RateMatchingEngine

logger = logging.getLogger("apex.agent.takeoff")


# ---------------------------------------------------------------------------
# Main agent entry point (v2)
# ---------------------------------------------------------------------------

def run_takeoff_agent(db: Session, project_id: int) -> dict:
    """Match estimator takeoff against Productivity Brain historical rates.

    1. Find the most recent takeoff/xlsx/csv document for this project.
    2. Parse it into TakeoffLineItem list via takeoff_parser.
    3. Match against PB data via RateMatchingEngine.
    4. Save TakeoffItemV2 rows (clean slate per run).
    5. Return validated Agent4Output.
    """
    # ── Step 1: Find takeoff document ────────────────────────────────────
    doc = _find_takeoff_document(db, project_id)

    if doc is None:
        logger.info(
            "Agent 4: no takeoff file found for project %d — returning empty output",
            project_id,
        )
        return validate_agent_output(4, {
            "takeoff_items_parsed": 0,
            "items_matched": 0,
            "items_unmatched": 0,
            "recommendations": [],
            "flags_summary": {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0},
            "parse_format": None,
            "overall_optimism_score": None,
        })

    # ── Step 2: Parse takeoff file ───────────────────────────────────────
    logger.info("Agent 4: parsing takeoff file %s (doc_id=%d)", doc.filename, doc.id)
    items, fmt = parse_takeoff(doc.file_path)
    logger.info("Agent 4: parsed %d line items (format=%s)", len(items), fmt)

    if not items:
        logger.warning("Agent 4: parser returned 0 items from %s", doc.filename)
        return validate_agent_output(4, {
            "takeoff_items_parsed": 0,
            "items_matched": 0,
            "items_unmatched": 0,
            "recommendations": [],
            "flags_summary": {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0},
            "parse_format": fmt,
            "overall_optimism_score": None,
        })

    # ── Step 3: Match against PB historical data ─────────────────────────
    engine = RateMatchingEngine(db)
    recommendations = engine.match_all(items)
    optimism = engine.compute_optimism_score(recommendations)
    flags = engine.flags_summary(recommendations)

    items_matched = sum(1 for r in recommendations if r.flag != "NO_DATA")
    items_unmatched = sum(1 for r in recommendations if r.flag == "NO_DATA")

    logger.info(
        "Agent 4: %d matched, %d unmatched, optimism=%.2f%%",
        items_matched,
        items_unmatched,
        optimism if optimism is not None else 0.0,
    )

    # ── Step 4: Save TakeoffItemV2 rows (clean slate) ────────────────────
    db.query(TakeoffItemV2).filter(
        TakeoffItemV2.project_id == project_id,
    ).delete(synchronize_session="fetch")

    for rec in recommendations:
        row = TakeoffItemV2(
            project_id=project_id,
            row_number=rec.line_item_row,
            wbs_area=rec.wbs_area,
            activity=rec.activity,
            quantity=rec.estimator_rate,  # estimator's production rate stored as reference
            unit=rec.unit,
            crew=rec.crew,
            production_rate=rec.estimator_rate,
            labor_cost_per_unit=rec.labor_cost_per_unit,
            material_cost_per_unit=rec.material_cost_per_unit,
            historical_avg_rate=rec.historical_avg_rate,
            historical_min_rate=rec.historical_min_rate,
            historical_max_rate=rec.historical_max_rate,
            sample_count=rec.sample_count,
            confidence=rec.confidence,
            delta_pct=rec.delta_pct,
            flag=rec.flag,
            matching_projects=json.dumps(rec.matching_projects) if rec.matching_projects else None,
        )
        db.add(row)

    db.commit()
    logger.info("Agent 4: saved %d TakeoffItemV2 rows for project %d", len(recommendations), project_id)

    # ── Step 5: Return validated output ──────────────────────────────────
    return validate_agent_output(4, {
        "takeoff_items_parsed": len(items),
        "items_matched": items_matched,
        "items_unmatched": items_unmatched,
        "recommendations": [r.model_dump() for r in recommendations],
        "flags_summary": flags,
        "parse_format": fmt,
        "overall_optimism_score": optimism,
    })


def _find_takeoff_document(db: Session, project_id: int) -> Optional[Document]:
    """Find the most recent takeoff document for a project.

    Looks for documents classified as 'takeoff', 'winest', or 'xlsx',
    or with filename ending in .xlsx or .csv.
    """
    # First try: explicit classification match
    doc = (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
            Document.is_deleted == False,  # noqa: E712
            Document.classification.in_(["takeoff", "winest", "xlsx"]),
        )
        .order_by(Document.id.desc())
        .first()
    )
    if doc:
        return doc

    # Second try: filename extension match
    doc = (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
            Document.is_deleted == False,  # noqa: E712
        )
        .order_by(Document.id.desc())
        .all()
    )
    for d in doc:
        if d.filename and (d.filename.lower().endswith(".xlsx") or d.filename.lower().endswith(".csv")):
            return d

    return None


# ===========================================================================
# DEPRECATED — v1 quantity generation (kept for backward compatibility)
# ===========================================================================

# Pydantic contract for individual takeoff items returned by the LLM (v1)
class LLMTakeoffItem(BaseModel):
    """Validated takeoff item parsed from LLM JSON response."""

    description: str
    quantity: float
    unit: str                                    # SF, LF, CY, EA, LS, ...
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


def _build_user_prompt(sections: list, gap_items: list) -> str:
    """Construct the user-facing prompt containing spec sections + gap items."""
    import json as _json
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
            "content": text.strip()[:3000],
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
        _json.dumps(spec_data, indent=2),
    ]
    if gap_data:
        parts += [
            "\nGAP ANALYSIS ITEMS — scope identified as missing from the specs. "
            "Provide estimated quantities for each gap item and set source='estimated':",
            _json.dumps(gap_data, indent=2),
        ]
    parts.append(
        "\nExtract ALL quantifiable takeoff items from the spec sections above and "
        "provide estimated quantities for every gap analysis item."
    )
    return "\n".join(parts)


def _parse_llm_takeoff_response(raw_content: str) -> list[LLMTakeoffItem]:
    """Strip markdown fences, parse JSON, and validate each item with Pydantic."""
    content = raw_content.strip()
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
    skipped = 0
    for i, item in enumerate(data):
        try:
            validated.append(LLMTakeoffItem.model_validate(item))
        except Exception as exc:
            skipped += 1
            logger.warning(f"Agent 4 LLM: skipping malformed takeoff item [{i}]: {exc}")

    if skipped:
        logger.warning(f"Agent 4 LLM: {skipped}/{len(data)} items skipped due to malformed data")

    return validated


_CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.90,
    "medium": 0.65,
    "low": 0.35,
}


# DEPRECATED — v1 quantity generation from specs via LLM
def run_takeoff_agent_v1(db: Session, project_id: int) -> dict:
    """Generate quantity takeoff items from parsed spec sections.

    DEPRECATED — v1 only. Kept for backward compatibility.
    Use run_takeoff_agent() (v2) which matches uploaded takeoffs against PB data.
    """
    from apex.backend.models.spec_section import SpecSection
    from apex.backend.models.takeoff_item import TakeoffItem
    from apex.backend.models.gap_report import GapReport
    from apex.backend.utils.async_helper import run_async as _run_async
    from apex.backend.services.token_tracker import log_token_usage
    from apex.backend.agents.tools.takeoff_tools import (
        quantity_calculator_tool,
        drawing_reference_linker_tool,
    )

    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).all()

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

    provider = None
    llm_available = False

    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=4)
        llm_available = _run_async(provider.health_check())
        if llm_available:
            logger.info(
                f"Agent 4 v1: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — attempting LLM quantity takeoff"
            )
        else:
            logger.info(
                f"Agent 4 v1: LLM provider '{provider.provider_name}' is unreachable — "
                "using regex fallback"
            )
    except Exception as exc:
        logger.warning(
            f"Agent 4 v1: could not initialise LLM provider ({exc}) — using regex fallback"
        )

    if llm_available and provider is not None and sections:
        async def _llm_takeoff(sections, gap_items, provider):
            user_prompt = _build_user_prompt(sections, gap_items)
            try:
                response = await provider.complete(
                    system_prompt=TAKEOFF_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.1,
                    max_tokens=8192,
                )
                items = _parse_llm_takeoff_response(response.content)
                return (
                    items, response.input_tokens, response.output_tokens,
                    response.cache_creation_input_tokens, response.cache_read_input_tokens,
                )
            except Exception as exc:
                logger.error(f"Agent 4 v1 LLM: call failed — {exc}")
                return None, 0, 0, 0, 0

        llm_items, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
            _llm_takeoff(sections, gap_items, provider)
        )
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
                cache_creation_tokens=_cache_create,
                cache_read_tokens=_cache_read,
            )
            takeoff_method = "llm"
            section_by_number = {s.section_number: s for s in sections}

            for item in llm_items:
                section = section_by_number.get(item.csi_code)
                section_id = section.id if section else None
                confidence_float = _CONFIDENCE_MAP.get(item.confidence, 0.65)

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
        else:
            logger.warning(
                "Agent 4 v1: LLM returned no valid takeoff items — falling back to regex extraction"
            )

    if takeoff_method == "regex":
        for section in sections:
            try:
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
        f"Agent 4 v1 complete: {items_created} items created, "
        f"method={takeoff_method}, tokens_used={tokens_used}"
    )

    # Note: v1 output validates against the OLD contract shape which no longer
    # matches Agent4Output v2. This function is only kept for reference.
    return {
        "items_created": items_created,
        "sections_processed": len(sections),
        "results": section_results,
        "takeoff_method": takeoff_method,
        "tokens_used": tokens_used,
    }
