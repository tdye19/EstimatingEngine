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

import json
import logging
import re

from sqlalchemy.orm import Session

from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.estimate import Estimate
from apex.backend.models.gap_report import GapReport
from apex.backend.agents.pipeline_contracts import (
    Agent7VarianceItem,
    validate_agent_output,
)
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.utils.async_helper import run_async as _run_async
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
    skipped = 0
    for i, item in enumerate(data):
        try:
            validated.append(Agent7VarianceItem.model_validate(item))
        except Exception as exc:
            skipped += 1
            logger.warning(f"Agent 7 LLM: skipping malformed variance item [{i}]: {exc}")

    if skipped:
        logger.warning(f"Agent 7 LLM: {skipped}/{len(data)} items skipped due to malformed data")

    return validated


# ---------------------------------------------------------------------------
# Async LLM call
# ---------------------------------------------------------------------------

async def _llm_variance_analysis(
    variances: list[dict],
    actual_items: list[dict],
    estimate_items: list[dict],
    provider,
) -> tuple[list[Agent7VarianceItem] | None, int, int]:
    """Send variance data to LLM; return (items, input_tokens, output_tokens)."""
    user_prompt = _build_improve_user_prompt(variances, actual_items, estimate_items)
    try:
        response = await provider.complete(
            system_prompt=IMPROVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )
        logger.info(
            f"Agent 7 LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"total_tokens={response.input_tokens + response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )
        items = _parse_llm_improve_response(response.content)
        logger.info(f"Agent 7 LLM: parsed {len(items)} validated variance items")
        return (
            items, response.input_tokens, response.output_tokens,
            response.cache_creation_input_tokens, response.cache_read_input_tokens,
        )
    except Exception as exc:
        logger.error(f"Agent 7 LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


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
# Rule-based fallback — produces recommendations without an LLM
# ---------------------------------------------------------------------------

def _generate_fallback_recommendations(
    estimate,  # Estimate DB object (with .line_items loaded), or None
    critical_gap_count: int = 0,
) -> list[Agent7VarianceItem]:
    # FALLBACK: Rule-based path when LLM unavailable (Sprint 8)
    items: list[Agent7VarianceItem] = []

    if estimate is not None:
        contingency_pct = float(estimate.contingency_pct or 0.0)
        overhead_pct = float(estimate.overhead_pct or 0.0)
        profit_pct = float(estimate.profit_pct or 0.0)
        total_direct_cost = float(estimate.total_direct_cost or 0.0)
        line_items = estimate.line_items or []

        # Contingency checks
        if contingency_pct < 5.0:
            items.append(Agent7VarianceItem(
                line_item="Contingency Rate",
                estimated_rate=contingency_pct,
                historical_actual_rate=5.0,
                variance_pct=round(contingency_pct - 5.0, 2),
                likely_cause="LOW — industry standard is 5-10% for commercial",
                recommendation="Increase contingency to at least 5% to cover unforeseen conditions",
                confidence="medium",
            ))
        elif contingency_pct > 15.0:
            items.append(Agent7VarianceItem(
                line_item="Contingency Rate",
                estimated_rate=contingency_pct,
                historical_actual_rate=15.0,
                variance_pct=round(contingency_pct - 15.0, 2),
                likely_cause="HIGH — review for over-padding",
                recommendation="Review contingency basis; values above 15% may indicate scope uncertainty",
                confidence="medium",
            ))

        # Overhead check
        if overhead_pct > 20.0:
            items.append(Agent7VarianceItem(
                line_item="Overhead Rate",
                estimated_rate=overhead_pct,
                historical_actual_rate=18.0,
                variance_pct=round(overhead_pct - 18.0, 2),
                likely_cause="Review overhead — above typical 10-18% range",
                recommendation="Review overhead allocation; typical commercial range is 10-18%",
                confidence="medium",
            ))

        # Profit margin checks
        if profit_pct < 3.0:
            items.append(Agent7VarianceItem(
                line_item="Profit Margin",
                estimated_rate=profit_pct,
                historical_actual_rate=3.0,
                variance_pct=round(profit_pct - 3.0, 2),
                likely_cause="Thin margin — consider risk exposure",
                recommendation="Review if margin covers project risk; consider raising to at least 3%",
                confidence="medium",
            ))
        elif profit_pct > 20.0:
            items.append(Agent7VarianceItem(
                line_item="Profit Margin",
                estimated_rate=profit_pct,
                historical_actual_rate=20.0,
                variance_pct=round(profit_pct - 20.0, 2),
                likely_cause="Aggressive margin — may reduce bid competitiveness",
                recommendation="Verify market conditions justify margin above 20%",
                confidence="medium",
            ))

        # Line item concentration check — any single item > 40% of subtotal
        if total_direct_cost > 0 and line_items:
            for li in line_items:
                li_cost = float(li.total_cost or 0.0)
                if li_cost <= 0:
                    continue
                li_pct = (li_cost / total_direct_cost) * 100.0
                if li_pct > 40.0:
                    label = li.description or li.csi_code
                    items.append(Agent7VarianceItem(
                        line_item=label,
                        estimated_rate=round(li_pct, 2),
                        historical_actual_rate=40.0,
                        variance_pct=round(li_pct - 40.0, 2),
                        likely_cause=(
                            f"Concentration risk — {label} represents {li_pct:.1f}% of estimate"
                        ),
                        recommendation=(
                            "Verify scope completeness; high concentration may indicate missing line items"
                        ),
                        confidence="medium",
                    ))

        # Missing CSI divisions check — expect ≥6 of divisions 1-14
        if line_items:
            present_divisions: set[int] = set()
            for li in line_items:
                try:
                    div_num = int(str(li.division_number).split(".")[0].strip())
                    if 1 <= div_num <= 14:
                        present_divisions.add(div_num)
                except (ValueError, AttributeError):
                    pass
            n_primary = len(present_divisions)
            if n_primary < 6:
                items.append(Agent7VarianceItem(
                    line_item="CSI Division Coverage",
                    estimated_rate=float(n_primary),
                    historical_actual_rate=6.0,
                    variance_pct=round((n_primary - 6.0) / 6.0 * 100.0, 2),
                    likely_cause=(
                        f"Possible missing scope — only {n_primary} of 14 primary CSI divisions represented"
                    ),
                    recommendation=(
                        "Review estimate for missing divisions; typical commercial projects cover 6+ divisions"
                    ),
                    confidence="low",
                ))

    # Gap coverage check — Agent 3 critical gaps
    if critical_gap_count > 5:
        items.append(Agent7VarianceItem(
            line_item="Scope Gap Risk",
            estimated_rate=float(critical_gap_count),
            historical_actual_rate=5.0,
            variance_pct=round((critical_gap_count - 5.0) / 5.0 * 100.0, 2),
            likely_cause=f"Scope risk — {critical_gap_count} critical gaps identified in spec analysis",
            recommendation=(
                "Address critical scope gaps before finalising bid; unresolved gaps increase cost risk"
            ),
            confidence="medium",
        ))

    # Always include a note that rule-based review was used
    items.append(Agent7VarianceItem(
        line_item="Review Note",
        estimated_rate=0.0,
        historical_actual_rate=0.0,
        variance_pct=0.0,
        likely_cause="AI-powered review unavailable — rule-based review provided",
        recommendation="Re-run with LLM available for enhanced variance analysis and recommendations",
        confidence="low",
    ))

    return items


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_improve_agent(db: Session, project_id: int, use_llm: bool = True) -> dict:
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

    # Fetch the latest estimate and gap report now so the rule-based fallback
    # can access financial percentages and critical gap count if needed.
    latest_estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .first()
    )

    latest_gap_report = (
        db.query(GapReport)
        .filter(
            GapReport.project_id == project_id,
            GapReport.is_deleted == False,  # noqa: E712
        )
        .order_by(GapReport.id.desc())
        .first()
    )
    critical_gap_count = int(latest_gap_report.critical_count or 0) if latest_gap_report else 0

    variance_items: list[Agent7VarianceItem] = []
    variance_method = "statistical"
    variance_tokens_used = 0
    _in_tok = 0
    _out_tok = 0

    if not use_llm:
        # FALLBACK: Rule-based path when LLM unavailable (Sprint 8)
        logger.warning("Agent 7: use_llm=False — skipping LLM, using rule-based fallback")
        variance_items = _generate_fallback_recommendations(latest_estimate, critical_gap_count)
        variance_method = "rule_based"
    else:
        try:
            from apex.backend.services.llm_provider import get_llm_provider
            provider = get_llm_provider(agent_number=7)
            llm_available = _run_async(provider.health_check())

            if llm_available:
                logger.info(
                    f"Agent 7: LLM provider '{provider.provider_name}/{provider.model_name}' "
                    "is available — generating LLM variance analysis"
                )
                llm_items, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
                    _llm_variance_analysis(variances, actual_items, estimate_items, provider)
                )
                variance_tokens_used = _in_tok + _out_tok
                if llm_items:
                    log_token_usage(
                        db=db,
                        project_id=project_id,
                        agent_number=7,
                        provider=provider.provider_name,
                        model=provider.model_name,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        cache_creation_tokens=_cache_create,
                        cache_read_tokens=_cache_read,
                    )
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
            # FALLBACK: Rule-based path when LLM unavailable (Sprint 8)
            logger.warning(
                f"Agent 7: LLM call failed ({exc}) — using rule-based fallback"
            )
            variance_items = _generate_fallback_recommendations(latest_estimate, critical_gap_count)
            variance_method = "rule_based"

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
