"""Agent 7: IMPROVE Feedback Agent.

Ingests completed project actuals and compares against original estimates
to generate productivity variance reports and feed corrections back.

Execution order:
  1. Fetch actuals + labor estimates from the DB (existing deterministic logic).
  2. variance_calculator_tool computes raw % differences (Python, unchanged).
  3. LLM (get_llm_provider(agent_number=7)) analyses the variance data, explains
     likely causes, and recommends rate adjustments for future estimates.
  4. LLM response is validated with Pydantic (Agent7VarianceItem).
  5. If the LLM is unavailable, the agent falls back to the statistical comparison
     already computed in step 2.
  6. The variance report (JSON) is stored on the latest estimate record for this
     project (estimate.variance_report_json) and returned in the output.
"""

import asyncio
import json
import logging
import re

from sqlalchemy.orm import Session

from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.estimate import Estimate
from apex.backend.agents.pipeline_contracts import (
    Agent7VarianceItem,
    validate_agent_output,
)
from apex.backend.agents.tools.improve_tools import (
    variance_calculator_tool,
    productivity_updater_tool,
    trend_analyzer_tool,
)

logger = logging.getLogger("apex.agent.improve")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

IMPROVE_SYSTEM_PROMPT = (
    "You are a construction estimating analyst. Compare these estimated rates against "
    "historical actual performance. For each significant variance, explain the likely "
    "cause and recommend whether to adjust the rate for future estimates. Consider: "
    "project complexity, market conditions, crew experience, and scope differences.\n\n"
    "## Output Format:\n"
    "Respond ONLY with a valid JSON array. No markdown fences, no explanation, "
    "no preamble — just the raw JSON array.\n\n"
    "Each object must have exactly these fields:\n"
    '  "line_item"              — string, CSI code or description of the work item\n'
    '  "estimated_rate"         — float, rate used in the estimate\n'
    '  "historical_actual_rate" — float, actual rate observed in the field\n'
    '  "variance_pct"           — float, percentage difference (positive = over-estimate)\n'
    '  "likely_cause"           — string, brief explanation of what drove the variance\n'
    '  "recommendation"         — string, concrete action for future estimates\n'
    '  "confidence"             — "high", "medium", or "low"\n'
)


# ---------------------------------------------------------------------------
# Async helper (same pattern as Agents 5 and 6)
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

def _build_improve_user_prompt(
    variances: list[dict],
    actual_items: list[dict],
    estimate_items: list[dict],
) -> str:
    """Construct the user prompt with variance data for the LLM analyst."""
    # Build a per-item comparison table
    comparison = []
    actual_by_csi = {a["csi_code"]: a for a in actual_items}
    estimate_by_csi = {e["csi_code"]: e for e in estimate_items}

    for v in variances:
        csi = v["csi_code"]
        est = estimate_by_csi.get(csi, {})
        act = actual_by_csi.get(csi, {})

        # Derive rates (cost per quantity unit) — Python does the math, not the LLM
        est_qty = est.get("estimated_quantity") or 0
        act_qty = act.get("actual_quantity") or 0
        est_cost = est.get("estimated_cost") or 0
        act_cost = act.get("actual_cost") or 0

        estimated_rate = round(est_cost / est_qty, 4) if est_qty > 0 else 0.0
        actual_rate = round(act_cost / act_qty, 4) if act_qty > 0 else 0.0

        comparison.append({
            "csi_code": csi,
            "description": est.get("description") or act.get("description") or csi,
            "estimated_quantity": est_qty,
            "actual_quantity": act_qty,
            "estimated_labor_hours": est.get("estimated_labor_hours") or 0,
            "actual_labor_hours": act.get("actual_labor_hours") or 0,
            "estimated_cost": est_cost,
            "actual_cost": act_cost,
            "estimated_rate_per_unit": estimated_rate,
            "actual_rate_per_unit": actual_rate,
            "variance_pct": v.get("variance_pct") or 0,
            "crew_type": act.get("crew_type") or "",
            "work_type": act.get("work_type") or "",
        })

    return (
        "Analyse the following estimate-vs-actual comparison and return a JSON array "
        "of variance findings as described in the system prompt.\n\n"
        "COMPARISON DATA:\n"
        + json.dumps(comparison, indent=2)
    )


# ---------------------------------------------------------------------------
# LLM response parser + Pydantic validator
# ---------------------------------------------------------------------------

def _parse_llm_improve_response(raw_content: str) -> list[Agent7VarianceItem]:
    """Strip markdown fences, parse JSON, validate each item with Pydantic."""
    content = raw_content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Agent 7 LLM: JSON parse error — {exc}")
        return []

    if not isinstance(data, list):
        logger.error(f"Agent 7 LLM: expected JSON array, got {type(data).__name__}")
        return []

    validated: list[Agent7VarianceItem] = []
    for i, item in enumerate(data):
        try:
            validated.append(Agent7VarianceItem.model_validate(item))
        except Exception as exc:
            logger.warning(f"Agent 7 LLM: skipping malformed variance item [{i}]: {exc}")

    return validated


# ---------------------------------------------------------------------------
# Async LLM call
# ---------------------------------------------------------------------------

async def _llm_variance_analysis(
    variances: list[dict],
    actual_items: list[dict],
    estimate_items: list[dict],
    provider,
) -> tuple[list[Agent7VarianceItem] | None, int]:
    """Send variance data to LLM; return (items, tokens_used)."""
    user_prompt = _build_improve_user_prompt(variances, actual_items, estimate_items)
    try:
        response = await provider.complete(
            system_prompt=IMPROVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )
        tokens = response.input_tokens + response.output_tokens
        logger.info(
            f"Agent 7 LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"total_tokens={tokens} duration_ms={response.duration_ms:.0f}ms"
        )
        items = _parse_llm_improve_response(response.content)
        logger.info(f"Agent 7 LLM: parsed {len(items)} validated variance items")
        return items, tokens
    except Exception as exc:
        logger.error(f"Agent 7 LLM: call failed — {exc}")
        return None, 0


# ---------------------------------------------------------------------------
# Statistical fallback — converts raw variance dicts to Agent7VarianceItem shape
# ---------------------------------------------------------------------------

def _statistical_variance_items(
    variances: list[dict],
    actual_items: list[dict],
    estimate_items: list[dict],
) -> list[Agent7VarianceItem]:
    """Produce variance items from raw % diff when LLM is unavailable."""
    actual_by_csi = {a["csi_code"]: a for a in actual_items}
    estimate_by_csi = {e["csi_code"]: e for e in estimate_items}
    items: list[Agent7VarianceItem] = []

    for v in variances:
        csi = v["csi_code"]
        est = estimate_by_csi.get(csi, {})
        act = actual_by_csi.get(csi, {})

        est_qty = est.get("estimated_quantity") or 0
        act_qty = act.get("actual_quantity") or 0
        est_cost = est.get("estimated_cost") or 0
        act_cost = act.get("actual_cost") or 0

        estimated_rate = round(est_cost / est_qty, 4) if est_qty > 0 else 0.0
        actual_rate = round(act_cost / act_qty, 4) if act_qty > 0 else 0.0
        var_pct = float(v.get("variance_pct") or 0)

        if abs(var_pct) >= 10:
            cause = f"Variance of {var_pct:+.1f}% detected — manual review recommended"
            recommendation = "Review rate and adjust if variance pattern persists across projects"
            confidence = "medium"
        else:
            cause = f"Variance of {var_pct:+.1f}% is within acceptable tolerance"
            recommendation = "No adjustment required at this time"
            confidence = "high"

        items.append(Agent7VarianceItem(
            line_item=csi,
            estimated_rate=estimated_rate,
            historical_actual_rate=actual_rate,
            variance_pct=var_pct,
            likely_cause=cause,
            recommendation=recommendation,
            confidence=confidence,
        ))

    return items


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_improve_agent(db: Session, project_id: int) -> dict:
    """Process actuals and generate variance report, update productivity rates.

    Returns dict with variance analysis results validated against Agent7Output.
    """
    # Get existing actuals for this project
    actuals = db.query(ProjectActual).filter(
        ProjectActual.project_id == project_id,
        ProjectActual.is_deleted == False,  # noqa: E712
    ).all()

    if not actuals:
        return validate_agent_output(7, {
            "actuals_processed": 0,
            "variances_calculated": 0,
            "productivity_updates": 0,
            "accuracy_score": 0.0,
            "total_estimated_cost": 0.0,
            "total_actual_cost": 0.0,
            "overall_variance_pct": 0.0,
            "variance_method": None,
            "variance_tokens_used": 0,
            "variance_items": [],
            "message": "No actuals data found for this project",
        })

    # Get labor estimates for comparison
    labor_estimates = db.query(LaborEstimate).filter(
        LaborEstimate.project_id == project_id,
        LaborEstimate.is_deleted == False,  # noqa: E712
    ).all()

    # Get takeoff items for quantity data
    takeoff_items = db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id,
        TakeoffItem.is_deleted == False,  # noqa: E712
    ).all()
    takeoff_map = {t.id: t for t in takeoff_items}

    # Build estimate items for comparison
    estimate_items = []
    for le in labor_estimates:
        takeoff = takeoff_map.get(le.takeoff_item_id)
        estimate_items.append({
            "csi_code": le.csi_code,
            "description": le.work_type or "",
            "estimated_quantity": takeoff.quantity if takeoff else le.quantity,
            "estimated_labor_hours": le.labor_hours * le.crew_size,
            "estimated_cost": le.total_labor_cost,
        })

    actual_items = [
        {
            "csi_code": a.csi_code,
            "description": a.description or "",
            "actual_quantity": a.actual_quantity or 0,
            "actual_labor_hours": a.actual_labor_hours or 0,
            "actual_cost": a.actual_cost or 0,
            "crew_type": a.crew_type or "",
            "work_type": a.work_type or "",
        }
        for a in actuals
    ]

    # -----------------------------------------------------------------------
    # Step 1: Python calculates raw variances (deterministic — never touched by LLM)
    # -----------------------------------------------------------------------
    variances = variance_calculator_tool(estimate_items, actual_items)

    # Update actuals with variance data
    actual_map = {a.csi_code: a for a in actuals}
    for v in variances:
        actual_record = actual_map.get(v["csi_code"])
        if actual_record:
            actual_record.estimated_quantity = v["estimated_quantity"]
            actual_record.estimated_labor_hours = v["estimated_labor_hours"]
            actual_record.estimated_cost = v["estimated_cost"]
            actual_record.variance_hours = v["variance_hours"]
            actual_record.variance_cost = v["variance_cost"]
            actual_record.variance_pct = v["variance_pct"]

    db.commit()

    # Update productivity rates based on actuals
    updates = []
    for actual in actual_items:
        if actual["actual_quantity"] > 0 and actual["actual_labor_hours"] > 0:
            actual_rate = actual["actual_quantity"] / actual["actual_labor_hours"]
            update_result = productivity_updater_tool(
                db=db,
                csi_code=actual["csi_code"],
                actual_rate=actual_rate,
                unit_of_measure="EA",
                work_type=actual.get("work_type", "General"),
                crew_type=actual.get("crew_type"),
                source_project=f"Project {project_id}",
                source_project_id=project_id,
            )
            updates.append(update_result)

    # Analyze trends
    trends = {}
    csi_codes = set(a["csi_code"] for a in actual_items)
    for csi in csi_codes:
        trend = trend_analyzer_tool(db, csi)
        trends[csi] = trend

    # Calculate overall accuracy score
    total_est = sum(v.get("estimated_cost", 0) for v in variances)
    total_act = sum(v.get("actual_cost", 0) for v in variances)
    accuracy = (1 - abs(total_act - total_est) / total_est) * 100 if total_est > 0 else 0
    accuracy = max(0, min(100, accuracy))
    overall_variance_pct = (
        round((total_act - total_est) / total_est * 100, 2) if total_est > 0 else 0
    )

    # -----------------------------------------------------------------------
    # Step 2: LLM variance analysis — explains causes, recommends adjustments
    # -----------------------------------------------------------------------
    variance_items: list[Agent7VarianceItem] = []
    variance_method = "statistical"
    variance_tokens_used = 0

    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=7)
        llm_available = _run_async(provider.health_check())

        if llm_available:
            logger.info(
                f"Agent 7: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — generating LLM variance analysis"
            )
            llm_items, variance_tokens_used = _run_async(
                _llm_variance_analysis(variances, actual_items, estimate_items, provider)
            )
            if llm_items:
                variance_items = llm_items
                variance_method = "llm"
                logger.info(
                    f"Agent 7 LLM: analysis complete — {len(variance_items)} items, "
                    f"{variance_tokens_used} tokens, method=llm"
                )
            else:
                logger.warning(
                    "Agent 7 LLM: returned no valid items — falling back to statistical comparison"
                )
        else:
            logger.info(
                f"Agent 7: LLM provider '{provider.provider_name}' unreachable — "
                "using statistical fallback"
            )
    except Exception as exc:
        logger.warning(
            f"Agent 7: could not initialise LLM provider ({exc}) — "
            "using statistical fallback"
        )

    if not variance_items:
        variance_items = _statistical_variance_items(variances, actual_items, estimate_items)
        variance_method = "statistical"

    # -----------------------------------------------------------------------
    # Step 3: Store variance report on the latest estimate for this project
    # -----------------------------------------------------------------------
    variance_report = {
        "variance_method": variance_method,
        "variance_tokens_used": variance_tokens_used,
        "accuracy_score": round(accuracy, 1),
        "overall_variance_pct": overall_variance_pct,
        "items": [item.model_dump() for item in variance_items],
        "trends": trends,
    }

    latest_estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .first()
    )
    if latest_estimate:
        latest_estimate.variance_report_json = variance_report
        db.commit()
        logger.info(
            f"Agent 7: variance report stored on estimate_id={latest_estimate.id} "
            f"(project_id={project_id})"
        )
    else:
        logger.warning(
            f"Agent 7: no estimate found for project_id={project_id} — "
            "variance report not persisted to estimate record"
        )

    logger.info(
        f"Agent 7 complete: actuals={len(actuals)} variances={len(variances)} "
        f"updates={len(updates)} accuracy={accuracy:.1f}% method={variance_method}"
    )

    return validate_agent_output(7, {
        "actuals_processed": len(actuals),
        "variances_calculated": len(variances),
        "productivity_updates": len(updates),
        "accuracy_score": round(accuracy, 1),
        "total_estimated_cost": round(total_est, 2),
        "total_actual_cost": round(total_act, 2),
        "overall_variance_pct": overall_variance_pct,
        "variance_method": variance_method,
        "variance_tokens_used": variance_tokens_used,
        "variance_items": [item.model_dump() for item in variance_items],
    })
