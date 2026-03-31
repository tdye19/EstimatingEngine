"""Agent 5: Labor Productivity Agent.

Applies historical labor productivity data to takeoff quantities
to produce labor hour estimates.

Execution order:
  1. Try LLM path — get_llm_provider(agent_number=5), health-check, call LLM.
     The LLM receives all takeoff items and the FULL productivity rate table so it
     can match each item to the closest historical rate (exact/similar/estimated).
  2. Python recalculates ALL math from the matched DB record — the LLM only
     suggests matches; Python does the arithmetic.  Never trust LLM math on a bid.
  3. If the LLM is unavailable or returns nothing, falls back to direct DB /
     default rate lookup (original logic, unchanged).
"""

import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.models.project import Project
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.productivity_history import ProductivityHistory
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.benchmark_engine import query_benchmarks
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.utils.async_helper import run_async as _run_async
from apex.backend.utils.csi_utils import normalize_uom
from apex.backend.agents.tools.labor_tools import (
    productivity_lookup_tool,
    crew_config_tool,
    duration_calculator_tool,
)

logger = logging.getLogger("apex.agent.labor")


# ---------------------------------------------------------------------------
# Pydantic contract for individual matches returned by the LLM
# ---------------------------------------------------------------------------

class LLMProductivityMatch(BaseModel):
    """Validated productivity match parsed from LLM JSON response."""

    takeoff_item_id: int
    matched_productivity_id: Optional[int] = None  # None = no match, flag for review
    labor_hours: float          # LLM suggestion — recalculated in Python
    labor_rate_per_unit: float  # units per crew-hour from the matched record
    crew_size: int
    total_labor_cost: float     # LLM suggestion — recalculated in Python
    match_confidence: Literal["exact", "similar", "estimated"]
    notes: Optional[str] = None

    @field_validator("match_confidence", mode="before")
    @classmethod
    def _norm_confidence(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("labor_hours", "labor_rate_per_unit", "total_labor_cost", mode="before")
    @classmethod
    def _to_float(cls, v) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        return float(str(v).replace(",", "").strip())

    @field_validator("crew_size", mode="before")
    @classmethod
    def _to_int(cls, v) -> int:
        return int(v)


# ---------------------------------------------------------------------------
# System prompt (built once at module load)
# ---------------------------------------------------------------------------

LABOR_SYSTEM_PROMPT = (
    "You are a construction labor estimator. Match each takeoff item to the most "
    "appropriate historical productivity rate. If no exact match exists, select the "
    "closest activity and note the confidence level.\n\n"
    "## Matching Rules:\n"
    "  'exact'     — CSI code and work type match precisely\n"
    "  'similar'   — same CSI division (first 2 digits) or a closely related activity\n"
    "  'estimated' — no reasonable historical match; use closest available rate and flag\n\n"
    "## CSI Code Fuzzy Matching:\n"
    "Prefer the closest CSI code. '03 30 00' may match '03 31 00' as 'similar'. "
    "Only fall back across divisions when truly no same-division rate exists.\n\n"
    "## Unit Conversions:\n"
    "When the takeoff unit differs from the historical rate unit, apply the conversion "
    "factor and document it in notes. Common factors: 1 SY = 9 SF, 1 CY = 27 CF, "
    "1 SQ = 100 SF.\n\n"
    "## No Match:\n"
    "If no reasonable match exists, set matched_productivity_id to null, "
    "labor_rate_per_unit to 0, crew_size to 0, labor_hours to 0, "
    "total_labor_cost to 0, match_confidence to 'estimated', and set notes to "
    "'FLAGGED FOR MANUAL REVIEW'.\n\n"
    "## Output Format:\n"
    "Respond ONLY with a valid JSON array. No markdown fences, no explanation, "
    "no preamble — just the raw JSON array.\n\n"
    "Each object must have exactly these fields:\n"
    '  "takeoff_item_id"         — integer, ID of the takeoff item\n'
    '  "matched_productivity_id" — integer ID of the matched rate record, or null\n'
    '  "labor_hours"             — estimated crew hours (float)\n'
    '  "labor_rate_per_unit"     — units produced per crew hour (float)\n'
    '  "crew_size"               — number of workers in the crew (integer)\n'
    '  "total_labor_cost"        — estimated total cost in dollars (float)\n'
    '  "match_confidence"        — "exact", "similar", or "estimated"\n'
    '  "notes"                   — brief explanation of match or unit conversion, or null\n'
)


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

def _build_labor_user_prompt(takeoff_items: list, productivity_records: list) -> str:
    """Construct the user-facing prompt with takeoff items + full rate table."""
    items_data = [
        {
            "id": item.id,
            "csi_code": item.csi_code,
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit_of_measure,
        }
        for item in takeoff_items
    ]

    rates_data = [
        {
            "id": rec.id,
            "csi_code": rec.csi_code,
            "work_type": rec.work_type,
            "crew_type": rec.crew_type,
            "productivity_rate": rec.productivity_rate,
            "unit_of_measure": rec.unit_of_measure,
            "confidence_score": rec.confidence_score,
            "sample_count": rec.sample_count,
            "region": rec.region,
            "notes": rec.notes,
        }
        for rec in productivity_records
    ]

    return "\n".join([
        "TAKEOFF ITEMS — match each to the best historical productivity rate:",
        json.dumps(items_data, indent=2),
        "\nHISTORICAL PRODUCTIVITY RATE TABLE — full database:",
        json.dumps(rates_data, indent=2),
        "\nFor each takeoff item, find the most appropriate rate record and return "
        "the JSON array described in the system prompt.",
    ])


# ---------------------------------------------------------------------------
# LLM response parser + Pydantic validator
# ---------------------------------------------------------------------------

def _parse_llm_labor_response(raw_content: str) -> list[LLMProductivityMatch]:
    """Strip markdown fences, parse JSON, validate each item with Pydantic."""
    content = raw_content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Agent 5 LLM: JSON parse error — {exc}")
        return []

    if not isinstance(data, list):
        logger.error(f"Agent 5 LLM: expected JSON array, got {type(data).__name__}")
        return []

    validated: list[LLMProductivityMatch] = []
    skipped = 0
    for i, item in enumerate(data):
        logger.debug("Agent 5 LLM raw item [%d]: %s", i, item)
        try:
            validated.append(LLMProductivityMatch.model_validate(item))
        except Exception as exc:
            skipped += 1
            logger.warning(f"Agent 5 LLM: skipping malformed match [{i}]: {exc}")

    if skipped:
        logger.warning(f"Agent 5 LLM: {skipped}/{len(data)} items skipped due to malformed data")

    return validated


# ---------------------------------------------------------------------------
# Async LLM call
# ---------------------------------------------------------------------------

async def _llm_labor_match(
    takeoff_items: list,
    productivity_records: list,
    provider,
) -> tuple[list[LLMProductivityMatch] | None, int, int]:
    """Send takeoff items + rate table to LLM; return (matches, input_tokens, output_tokens)."""
    user_prompt = _build_labor_user_prompt(takeoff_items, productivity_records)
    try:
        response = await provider.complete(
            system_prompt=LABOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )
        logger.info(
            f"Agent 5 LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"total_tokens={response.input_tokens + response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )
        matches = _parse_llm_labor_response(response.content)
        logger.info(f"Agent 5 LLM: parsed {len(matches)} validated matches")
        return (
            matches, response.input_tokens, response.output_tokens,
            response.cache_creation_input_tokens, response.cache_read_input_tokens,
        )
    except Exception as exc:
        logger.error(f"Agent 5 LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


# ---------------------------------------------------------------------------
# Python math verification — LLM suggests the match; Python owns all arithmetic
# ---------------------------------------------------------------------------

_MATCH_CONFIDENCE_TO_FLOAT: dict[str, float] = {
    "exact": 0.95,
    "similar": 0.75,
    "estimated": 0.45,
}


def _verified_compute(
    match: LLMProductivityMatch,
    item,  # TakeoffItem
    prod_by_id: dict,
) -> dict:
    """
    Python recomputes all labor arithmetic from the LLM's suggested match.

    The LLM's numeric suggestions (labor_hours, total_labor_cost) are discarded.
    Only its match decision (matched_productivity_id, match_confidence, notes) is kept.
    All calculations are derived from the authoritative DB record.
    """
    prod = prod_by_id.get(match.matched_productivity_id)

    if prod is None:
        logger.warning(
            "Agent 5: LLM returned matched_productivity_id=%s for item %d (%s) "
            "but no DB record found — signalling fallback",
            match.matched_productivity_id, item.id, item.csi_code,
        )
        # Return sentinel so the caller can fall back to DB lookup
        return None

    # Pull authoritative values from the DB record — ignore LLM's numeric guesses
    rate = prod.productivity_rate if prod.productivity_rate > 0 else 1.0
    crew = crew_config_tool(prod.crew_type or "General Crew")
    crew_size = crew["size"]
    hourly_rate = crew["hourly_rate"]

    # Python does all the math
    crew_hours = item.quantity / rate
    total_man_hours = crew_hours * crew_size
    crew_days = crew_hours / 8.0
    total_labor_cost = total_man_hours * hourly_rate

    return {
        "rate": round(rate, 4),
        "unit": prod.unit_of_measure,
        "crew_type": prod.crew_type or "General Crew",
        "work_type": prod.work_type,
        "labor_hours": round(crew_hours, 2),
        "crew_days": round(crew_days, 2),
        "total_man_hours": round(total_man_hours, 2),
        "crew_size": crew_size,
        "hourly_rate": hourly_rate,
        "total_labor_cost": round(total_labor_cost, 2),
        "confidence": _MATCH_CONFIDENCE_TO_FLOAT.get(match.match_confidence, 0.65),
        "matched_productivity_id": match.matched_productivity_id,
        "match_confidence": match.match_confidence,
        "notes": match.notes,
    }


# ---------------------------------------------------------------------------
# DB lookup helper — shared by the DB fallback path and LLM gap-fill
# ---------------------------------------------------------------------------

def _db_estimate_item(
    db: Session,
    project_id: int,
    item,  # TakeoffItem
) -> tuple[object, dict, float]:
    """Look up rate from DB / defaults and build a LaborEstimate.

    Returns (estimate_obj, result_dict, total_man_hours).
    Raises on failure so the caller can record the error.
    """
    prod = productivity_lookup_tool(db, item.csi_code)
    crew = crew_config_tool(prod["crew_type"])
    duration = duration_calculator_tool(
        quantity=item.quantity,
        rate=prod["rate"],
        crew_size=crew["size"],
    )
    labor_cost = duration["total_man_hours"] * crew["hourly_rate"]

    estimate = LaborEstimate(
        project_id=project_id,
        takeoff_item_id=item.id,
        csi_code=item.csi_code,
        work_type=prod["work_type"],
        crew_type=prod["crew_type"],
        productivity_rate=prod["rate"],
        productivity_unit=prod["unit"],
        quantity=item.quantity,
        labor_hours=duration["labor_hours"],
        crew_size=crew["size"],
        crew_days=duration["crew_days"],
        hourly_rate=crew["hourly_rate"],
        total_labor_cost=round(labor_cost, 2),
    )

    result = {
        "takeoff_item_id": item.id,
        "csi_code": item.csi_code,
        "quantity": item.quantity,
        "rate": prod["rate"],
        "crew_type": prod["crew_type"],
        "labor_hours": duration["labor_hours"],
        "labor_cost": round(labor_cost, 2),
        "confidence": prod["confidence"],
    }

    return estimate, result, duration["total_man_hours"]


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------

def _try_benchmark(db: Session, org_id, item, project_type):
    """Return a qualifying ProductivityBenchmark for this item, or None.

    Uses normalize_uom to ensure UOM strings match the benchmark index
    (e.g. "SQ FT" → "SF") before querying so we avoid false cache misses.
    """
    if not org_id:
        return None
    norm_uom = normalize_uom(item.unit_of_measure)
    return query_benchmarks(
        db,
        organization_id=org_id,
        csi_code=item.csi_code,
        unit_of_measure=norm_uom,
        project_type=project_type,
        region=None,
    )


def _benchmark_estimate_item(
    db: Session,
    project_id: int,
    item,  # TakeoffItem
    benchmark,  # ProductivityBenchmark
) -> tuple[object, dict, float]:
    """Build a LaborEstimate from benchmark avg rates.

    Python owns ALL arithmetic — the benchmark supplies rate inputs only.
    Returns (estimate_obj, result_dict, total_man_hours).
    """
    lhpu = benchmark.avg_labor_hours_per_unit or 0.0  # labor-hours per unit
    lcpu = benchmark.avg_labor_cost_per_unit or 0.0   # labor cost per unit

    # Python does the math
    total_man_hours = round(item.quantity * lhpu, 2)
    total_labor_cost = round(item.quantity * lcpu, 2)
    productivity_rate = round(1.0 / lhpu, 4) if lhpu > 0 else 0.0
    hourly_rate = round(lcpu / lhpu, 2) if lhpu > 0 else 0.0
    crew_days = round(total_man_hours / 8.0, 2)

    estimate = LaborEstimate(
        project_id=project_id,
        takeoff_item_id=item.id,
        csi_code=item.csi_code,
        work_type=benchmark.description,
        crew_type="Benchmark Average",
        productivity_rate=productivity_rate,
        productivity_unit=benchmark.unit_of_measure,
        quantity=item.quantity,
        labor_hours=total_man_hours,
        crew_size=1,
        crew_days=crew_days,
        hourly_rate=hourly_rate,
        total_labor_cost=total_labor_cost,
    )

    result = {
        "takeoff_item_id": item.id,
        "csi_code": item.csi_code,
        "quantity": item.quantity,
        "rate": productivity_rate,
        "crew_type": "Benchmark Average",
        "labor_hours": total_man_hours,
        "labor_cost": total_labor_cost,
        "confidence": benchmark.confidence_score or 0.0,
        "source": "historical_benchmark",
        "notes": (
            f"Benchmark: sample_size={benchmark.sample_size}, "
            f"confidence={benchmark.confidence_score:.2f}"
        ),
    }

    return estimate, result, total_man_hours


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_labor_agent(db: Session, project_id: int) -> dict:
    """Apply productivity rates to takeoff items and generate labor estimates.

    Execution order:
      1. Try LLM path — get_llm_provider(agent_number=5), health-check, call LLM.
         The LLM receives all takeoff items and the FULL productivity rate table so it
         can match each item to the closest historical rate (exact/similar/estimated).
      2. Python recalculates ALL math from the matched DB record — the LLM only
         suggests matches; Python does the arithmetic.
      3. If the LLM is unavailable or returns nothing, falls back to direct DB /
         default rate lookup (original logic, unchanged).

    Returns dict validated against the Agent5Output pipeline contract.
    """
    takeoff_items = db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id,
        TakeoffItem.is_deleted == False,  # noqa: E712
    ).all()

    estimates_created = 0
    total_labor_cost = 0.0
    total_labor_hours = 0.0
    item_results = []
    labor_method = "db"
    tokens_used = 0
    _in_tok = 0
    _out_tok = 0

    # -----------------------------------------------------------------------
    # 0.  Load project metadata needed for benchmark lookup
    # -----------------------------------------------------------------------
    project = db.query(Project).filter(Project.id == project_id).first()
    org_id = project.organization_id if project else None
    proj_type = project.project_type if project else None

    # -----------------------------------------------------------------------
    # 0b. Benchmark pre-pass — check each item before LLM/DB fallback
    # -----------------------------------------------------------------------
    benchmark_hits = 0
    benchmark_covered_ids: set[int] = set()
    non_benchmark_items: list = []

    for item in takeoff_items:
        bm = _try_benchmark(db, org_id, item, proj_type)
        if bm and (bm.confidence_score or 0.0) >= 0.5 and (bm.sample_size or 0) >= 5:
            try:
                est, result, man_hours = _benchmark_estimate_item(db, project_id, item, bm)
                db.add(est)
                estimates_created += 1
                total_labor_cost += result["labor_cost"]
                total_labor_hours += man_hours
                item_results.append(result)
                benchmark_covered_ids.add(item.id)
                benchmark_hits += 1
            except Exception as exc:
                logger.error(f"Agent 5 benchmark: failed for item {item.id}: {exc}")
                non_benchmark_items.append(item)
        else:
            non_benchmark_items.append(item)

    logger.info(
        f"Agent 5: {benchmark_hits}/{len(takeoff_items)} items used historical benchmarks"
    )
    # Commit benchmark estimates if no further processing is needed
    if not non_benchmark_items and benchmark_hits > 0:
        db.commit()

    # -----------------------------------------------------------------------
    # 1.  Attempt LLM-powered productivity matching (non-benchmark items only)
    # -----------------------------------------------------------------------
    provider = None
    llm_available = False

    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=5)
        llm_available = _run_async(provider.health_check())
        if llm_available:
            logger.info(
                f"Agent 5: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — attempting LLM productivity matching"
            )
        else:
            logger.info(
                f"Agent 5: LLM provider '{provider.provider_name}' is unreachable — "
                "using DB lookup fallback"
            )
    except Exception as exc:
        logger.warning(
            f"Agent 5: could not initialise LLM provider ({exc}) — using DB lookup fallback"
        )

    if llm_available and provider is not None and non_benchmark_items:
        # Fetch ALL historical productivity records to give the LLM full context
        all_productivity = db.query(ProductivityHistory).filter(
            ProductivityHistory.is_deleted == False,  # noqa: E712
        ).all()
        prod_by_id = {rec.id: rec for rec in all_productivity}
        items_by_id = {item.id: item for item in non_benchmark_items}

        llm_matches, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
            _llm_labor_match(non_benchmark_items, all_productivity, provider)
        )
        tokens_used = _in_tok + _out_tok

        if llm_matches:
            log_token_usage(
                db=db,
                project_id=project_id,
                agent_number=5,
                provider=provider.provider_name,
                model=provider.model_name,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
                cache_creation_tokens=_cache_create,
                cache_read_tokens=_cache_read,
            )
            labor_method = "llm"
            matched_item_ids: set[int] = set()

            llm_fallback_count = 0
            for match in llm_matches:
                item = items_by_id.get(match.takeoff_item_id)
                if item is None:
                    logger.warning(
                        f"Agent 5 LLM: unknown takeoff_item_id={match.takeoff_item_id} — skipping"
                    )
                    continue

                # 2. Python verifies / recomputes all arithmetic from DB record
                c = _verified_compute(match, item, prod_by_id)
                matched_item_ids.add(item.id)

                # If _verified_compute returned None (bad match ID), fall back
                # to DB lookup so the item gets a real rate instead of $0.
                if c is None:
                    try:
                        estimate, result, man_hours = _db_estimate_item(db, project_id, item)
                        result["source"] = "db_fallback_from_llm"
                        db.add(estimate)
                        estimates_created += 1
                        total_labor_cost += result["labor_cost"]
                        total_labor_hours += man_hours
                        item_results.append(result)
                        llm_fallback_count += 1
                        logger.info(
                            "Agent 5: item '%s' (%s) LLM returned invalid match — "
                            "using db_fallback rate: $%.2f",
                            item.description[:50], item.csi_code,
                            result["labor_cost"],
                        )
                    except Exception as exc:
                        logger.error(
                            f"Agent 5 DB fallback for LLM item {item.id}: {exc}"
                        )
                        item_results.append({
                            "takeoff_item_id": item.id,
                            "csi_code": item.csi_code,
                            "error": str(exc),
                            "source": None,
                        })
                    continue

                estimate = LaborEstimate(
                    project_id=project_id,
                    takeoff_item_id=item.id,
                    csi_code=item.csi_code,
                    work_type=c["work_type"],
                    crew_type=c["crew_type"],
                    productivity_rate=c["rate"],
                    productivity_unit=c["unit"],
                    quantity=item.quantity,
                    labor_hours=c["labor_hours"],
                    crew_size=c["crew_size"],
                    crew_days=c["crew_days"],
                    hourly_rate=c["hourly_rate"],
                    total_labor_cost=c["total_labor_cost"],
                )
                db.add(estimate)
                estimates_created += 1
                total_labor_cost += c["total_labor_cost"]
                total_labor_hours += c["total_man_hours"]

                item_results.append({
                    "takeoff_item_id": item.id,
                    "csi_code": item.csi_code,
                    "quantity": item.quantity,
                    "rate": c["rate"],
                    "crew_type": c["crew_type"],
                    "labor_hours": c["labor_hours"],
                    "labor_cost": c["total_labor_cost"],
                    "confidence": c["confidence"],
                    "match_confidence": c["match_confidence"],
                    "matched_productivity_id": c["matched_productivity_id"],
                    "notes": c["notes"],
                    "source": "llm_verified",
                })

            if llm_fallback_count:
                logger.warning(
                    "Agent 5: %d/%d LLM matches had invalid productivity IDs — "
                    "used DB fallback rates",
                    llm_fallback_count, len(llm_matches),
                )

            # DB fallback for any items the LLM did not return a match for
            unmatched = [item for item in non_benchmark_items if item.id not in matched_item_ids]
            if unmatched:
                logger.warning(
                    f"Agent 5 LLM: {len(unmatched)} items had no LLM match — "
                    "applying DB lookup"
                )
                for item in unmatched:
                    try:
                        estimate, result, man_hours = _db_estimate_item(db, project_id, item)
                        result["source"] = "bls_default"
                        db.add(estimate)
                        estimates_created += 1
                        total_labor_cost += result["labor_cost"]
                        total_labor_hours += man_hours
                        item_results.append(result)
                    except Exception as exc:
                        logger.error(
                            f"Agent 5 DB gap-fill: failed for takeoff item {item.id}: {exc}"
                        )
                        item_results.append({
                            "takeoff_item_id": item.id,
                            "csi_code": item.csi_code,
                            "error": str(exc),
                            "source": None,
                        })

            db.commit()
            logger.info(
                f"Agent 5: LLM path succeeded — {estimates_created} estimates created "
                f"(provider={provider.provider_name}, model={provider.model_name}, "
                f"tokens_used={tokens_used})"
            )
        else:
            logger.warning(
                "Agent 5: LLM returned no valid matches — falling back to DB lookup"
            )

    # -----------------------------------------------------------------------
    # 3.  DB / default-rate fallback — original per-item logic (non-benchmark items only)
    # -----------------------------------------------------------------------
    if labor_method == "db" and non_benchmark_items:
        logger.info("Agent 5: using direct DB / default-rate lookup (fallback path)")
        for item in non_benchmark_items:
            try:
                estimate, result, man_hours = _db_estimate_item(db, project_id, item)
                result["source"] = "bls_default"
                db.add(estimate)
                estimates_created += 1
                total_labor_cost += result["labor_cost"]
                total_labor_hours += man_hours
                item_results.append(result)
            except Exception as exc:
                logger.error(f"Failed labor estimate for takeoff item {item.id}: {exc}")
                item_results.append({
                    "takeoff_item_id": item.id,
                    "csi_code": item.csi_code,
                    "error": str(exc),
                })
        db.commit()

    benchmark_coverage = (
        round(benchmark_hits / len(takeoff_items), 4) if takeoff_items else 0.0
    )
    logger.info(
        f"Agent 5 complete: {estimates_created} estimates, method={labor_method}, "
        f"tokens_used={tokens_used}, items={len(takeoff_items)}, "
        f"benchmark_coverage={benchmark_coverage:.1%}"
    )

    return validate_agent_output(5, {
        "estimates_created": estimates_created,
        "total_labor_cost": round(total_labor_cost, 2),
        "total_labor_hours": round(total_labor_hours, 2),
        "items_processed": len(takeoff_items),
        "results": item_results,
        "labor_method": labor_method,
        "tokens_used": tokens_used,
        "benchmark_coverage": benchmark_coverage,
    })
