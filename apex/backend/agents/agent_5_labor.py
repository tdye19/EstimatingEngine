"""Agent 5 — Field Actuals Comparison Layer (v2)

Three-way comparison for every takeoff line item:
  1. Estimator's rate for THIS bid (from TakeoffItemV2)
  2. Historical ESTIMATING average (from PB via Agent 4)
  3. Historical FIELD average (from field_actuals tables)

NO LLM. ALL MATH IS DETERMINISTIC PYTHON.

Inputs:
  - TakeoffItemV2 rows (from Agent 4) with estimator_rate and historical_avg_rate
  - FieldActualsLineItem data (from field_actuals service)

Outputs:
  - FieldActualsComparison list
  - Calibration factors and direction indicators
"""

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import (
    FieldActualsComparison,
    validate_agent_output,
)
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.services.field_actuals.service import FieldActualsService

logger = logging.getLogger("apex.agent.labor")


# ---------------------------------------------------------------------------
# Main agent entry point (v2)
# ---------------------------------------------------------------------------


def run_labor_agent(db: Session, project_id: int) -> dict:
    """Compare takeoff line items against field actuals.

    For each TakeoffItemV2 row:
      1. estimator_rate = what this estimator entered (row.production_rate)
      2. estimating_avg_rate = PB historical avg (row.historical_avg_rate, from Agent 4)
      3. field_avg_rate = what crews actually produce (from field_actuals service)

    Returns validated Agent5Output dict.
    """
    # ── Step 1: Load takeoff items from Agent 4 ──────────────────────────
    rows = (
        db.query(TakeoffItemV2)
        .filter(
            TakeoffItemV2.project_id == project_id,
        )
        .order_by(TakeoffItemV2.row_number)
        .all()
    )

    if not rows:
        logger.info(
            "Agent 5: no TakeoffItemV2 rows for project %d — returning empty output",
            project_id,
        )
        return validate_agent_output(
            5,
            {
                "items_compared": 0,
                "items_with_field_data": 0,
                "items_without_field_data": 0,
                "comparisons": [],
                "avg_calibration_factor": None,
                "calibration_summary": {
                    "optimistic": 0,
                    "conservative": 0,
                    "aligned": 0,
                    "no_data": 0,
                },
            },
        )

    # ── Step 2: Initialize field actuals service ─────────────────────────
    fa_service = FieldActualsService(db)

    # ── Step 3: Build comparisons ────────────────────────────────────────
    comparisons: list[dict] = []
    calibration_factors: list[float] = []
    direction_counts = {"optimistic": 0, "conservative": 0, "aligned": 0, "no_data": 0}

    for row in rows:
        estimator_rate = row.production_rate
        estimating_avg = row.historical_avg_rate

        # Look up field actuals
        field_match = fa_service.match_field_data(
            activity=row.activity,
            unit=row.unit,
        )

        if field_match and field_match["avg_rate"]:
            field_avg = field_match["avg_rate"]
            field_count = field_match["sample_count"]
            field_projects = field_match["projects"]

            # Estimating-to-field delta: how far are PB estimates from field reality?
            est_to_field_delta = None
            if estimating_avg and estimating_avg > 0:
                est_to_field_delta = round(((estimating_avg - field_avg) / field_avg) * 100, 2)

            # Entered-to-field delta: how far is THIS estimator from field reality?
            entered_to_field_delta = None
            if estimator_rate and estimator_rate > 0:
                entered_to_field_delta = round(((estimator_rate - field_avg) / field_avg) * 100, 2)

            # Calibration factor: field_avg / estimating_avg
            cal_factor = None
            cal_direction = "no_data"
            if estimating_avg and estimating_avg > 0:
                cal_factor = round(field_avg / estimating_avg, 4)
                calibration_factors.append(cal_factor)

                if cal_factor < 0.90:
                    cal_direction = "optimistic"
                elif cal_factor > 1.10:
                    cal_direction = "conservative"
                else:
                    cal_direction = "aligned"

            # Build recommendation text
            recommendation = _build_recommendation(
                row.activity,
                row.unit,
                estimator_rate,
                estimating_avg,
                field_avg,
                cal_factor,
                cal_direction,
            )

            direction_counts[cal_direction] += 1

            comparisons.append(
                FieldActualsComparison(
                    line_item_row=row.row_number,
                    activity=row.activity,
                    unit=row.unit,
                    estimator_rate=estimator_rate,
                    estimating_avg_rate=estimating_avg,
                    field_avg_rate=field_avg,
                    field_sample_count=field_count,
                    estimating_to_field_delta_pct=est_to_field_delta,
                    entered_to_field_delta_pct=entered_to_field_delta,
                    calibration_factor=cal_factor,
                    calibration_direction=cal_direction,
                    recommendation=recommendation,
                    field_projects=field_projects,
                ).model_dump()
            )

        else:
            # No field data available
            direction_counts["no_data"] += 1

            comparisons.append(
                FieldActualsComparison(
                    line_item_row=row.row_number,
                    activity=row.activity,
                    unit=row.unit,
                    estimator_rate=estimator_rate,
                    estimating_avg_rate=estimating_avg,
                    calibration_direction="no_data",
                    recommendation="No field actuals available for this activity. Rate based on estimating history only.",
                ).model_dump()
            )

    # ── Step 4: Compute summary ──────────────────────────────────────────
    items_with = sum(1 for c in comparisons if c["calibration_direction"] != "no_data")
    items_without = len(comparisons) - items_with
    avg_cal = round(sum(calibration_factors) / len(calibration_factors), 4) if calibration_factors else None

    logger.info(
        "Agent 5: %d items compared, %d with field data, %d without, avg_cal=%.4f",
        len(comparisons),
        items_with,
        items_without,
        avg_cal if avg_cal is not None else 0.0,
    )

    # ── Step 5: Return validated output ──────────────────────────────────
    return validate_agent_output(
        5,
        {
            "items_compared": len(comparisons),
            "items_with_field_data": items_with,
            "items_without_field_data": items_without,
            "comparisons": comparisons,
            "avg_calibration_factor": avg_cal,
            "calibration_summary": direction_counts,
        },
    )


def _build_recommendation(
    activity: str,
    unit: str | None,
    estimator_rate: float | None,
    estimating_avg: float | None,
    field_avg: float,
    cal_factor: float | None,
    cal_direction: str,
) -> str:
    """Generate human-readable guidance for a single line item."""
    unit_str = f" {unit}" if unit else ""

    if cal_direction == "aligned":
        return "Field data aligns with estimating history. Rate is well-calibrated."

    if cal_direction == "optimistic" and cal_factor is not None:
        pct_adjust = round((1 - cal_factor) * 100, 0)
        return (
            f"Field crews produce {field_avg:.1f}{unit_str}/MH on {activity.lower()} "
            f"vs estimating avg of {estimating_avg:.1f}{unit_str}/MH. "
            f"Consider adjusting rate down {pct_adjust:.0f}%."
        )

    if cal_direction == "conservative" and cal_factor is not None:
        pct_adjust = round((cal_factor - 1) * 100, 0)
        return (
            f"Field crews produce {field_avg:.1f}{unit_str}/MH on {activity.lower()} "
            f"vs estimating avg of {estimating_avg:.1f}{unit_str}/MH. "
            f"Estimating rates are conservative by {pct_adjust:.0f}%. Potential bid advantage."
        )

    return "No field actuals available for this activity. Rate based on estimating history only."


# ===========================================================================
# DEPRECATED — v1 labor productivity agent (LLM-based rate matching)
# ===========================================================================


# Pydantic contract for v1 LLM matches
class LLMProductivityMatch(BaseModel):
    """Validated productivity match parsed from LLM JSON response."""

    takeoff_item_id: int
    matched_productivity_id: int | None = None
    labor_hours: float
    labor_rate_per_unit: float
    crew_size: int
    total_labor_cost: float
    match_confidence: Literal["exact", "similar", "estimated"]
    notes: str | None = None

    @field_validator("match_confidence", mode="before")
    @classmethod
    def _norm_confidence(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("labor_hours", "labor_rate_per_unit", "total_labor_cost", mode="before")
    @classmethod
    def _to_float(cls, v) -> float:
        if isinstance(v, int | float):
            return float(v)
        return float(str(v).replace(",", "").strip())

    @field_validator("crew_size", mode="before")
    @classmethod
    def _to_int(cls, v) -> int:
        return int(v)


LABOR_SYSTEM_PROMPT = (
    "You are a construction labor estimator. Match each takeoff item to the most "
    "appropriate historical productivity rate. If no exact match exists, select the "
    "closest activity and note the confidence level.\n\n"
    "## Matching Rules:\n"
    "  'exact'     — CSI code and work type match precisely\n"
    "  'similar'   — same CSI division (first 2 digits) or a closely related activity\n"
    "  'estimated' — no reasonable historical match; use closest available rate and flag\n\n"
    "## Output Format:\n"
    "Respond ONLY with a valid JSON array.\n\n"
    "Each object must have exactly these fields:\n"
    '  "takeoff_item_id", "matched_productivity_id", "labor_hours",\n'
    '  "labor_rate_per_unit", "crew_size", "total_labor_cost",\n'
    '  "match_confidence", "notes"\n'
)


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
        }
        for rec in productivity_records
    ]

    return "\n".join(
        [
            "TAKEOFF ITEMS — match each to the best historical productivity rate:",
            json.dumps(items_data, indent=2),
            "\nHISTORICAL PRODUCTIVITY RATE TABLE — full database:",
            json.dumps(rates_data, indent=2),
        ]
    )


def _parse_llm_labor_response(raw_content: str) -> list[LLMProductivityMatch]:
    """Strip markdown fences, parse JSON, validate each item with Pydantic."""
    content = raw_content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Agent 5 v1 LLM: JSON parse error — {exc}")
        return []

    if not isinstance(data, list):
        return []

    validated: list[LLMProductivityMatch] = []
    for _i, item in enumerate(data):
        try:
            validated.append(LLMProductivityMatch.model_validate(item))
        except Exception:
            pass

    return validated


_MATCH_CONFIDENCE_TO_FLOAT: dict[str, float] = {
    "exact": 0.95,
    "similar": 0.75,
    "estimated": 0.45,
}


# DEPRECATED — v1 labor productivity agent
def run_labor_agent_v1(db: Session, project_id: int) -> dict:
    """Apply productivity rates to takeoff items and generate labor estimates.

    DEPRECATED — v1 only. Kept for backward compatibility.
    Use run_labor_agent() (v2) which compares against field actuals.
    """
    from apex.backend.agents.tools.labor_tools import (
        crew_config_tool,
        duration_calculator_tool,
        productivity_lookup_tool,
    )
    from apex.backend.models.labor_estimate import LaborEstimate
    from apex.backend.models.project import Project
    from apex.backend.models.takeoff_item import TakeoffItem

    takeoff_items = (
        db.query(TakeoffItem)
        .filter(
            TakeoffItem.project_id == project_id,
            TakeoffItem.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    estimates_created = 0
    total_labor_cost = 0.0
    total_labor_hours = 0.0
    item_results = []
    labor_method = "db"
    tokens_used = 0

    db.query(Project).filter(Project.id == project_id).first()

    # DB fallback path
    for item in takeoff_items:
        try:
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
            db.add(estimate)
            estimates_created += 1
            total_labor_cost += round(labor_cost, 2)
            total_labor_hours += duration["total_man_hours"]
            item_results.append(
                {
                    "takeoff_item_id": item.id,
                    "csi_code": item.csi_code,
                    "quantity": item.quantity,
                    "rate": prod["rate"],
                    "crew_type": prod["crew_type"],
                    "labor_hours": duration["labor_hours"],
                    "labor_cost": round(labor_cost, 2),
                    "confidence": prod["confidence"],
                    "source": "bls_default",
                }
            )
        except Exception as exc:
            logger.error(f"Agent 5 v1: failed for takeoff item {item.id}: {exc}")
            item_results.append(
                {
                    "takeoff_item_id": item.id,
                    "csi_code": item.csi_code,
                    "error": str(exc),
                }
            )

    db.commit()

    # Note: v1 output no longer matches Agent5Output v2. Kept for reference only.
    return {
        "estimates_created": estimates_created,
        "total_labor_cost": round(total_labor_cost, 2),
        "total_labor_hours": round(total_labor_hours, 2),
        "items_processed": len(takeoff_items),
        "results": item_results,
        "labor_method": labor_method,
        "tokens_used": tokens_used,
        "benchmark_coverage": 0.0,
    }
