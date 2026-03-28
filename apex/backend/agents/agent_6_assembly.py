"""Agent 6: Estimate Assembly Agent.

Assembles all components into a structured bid estimate, then calls an LLM
to generate an executive summary for the bid cover page.

Execution order:
  1. Python assembles the full estimate (deterministic math — unchanged).
  2. LLM generates the executive summary using get_llm_provider(agent_number=6,
     suffix="SUMMARY"), which maps to AGENT_6_SUMMARY_PROVIDER / AGENT_6_SUMMARY_MODEL.
  3. The LLM receives estimate data (line items, subtotals, markups, grand total)
     but NEVER touches the numbers.  All arithmetic stays in Python.
  4. If the LLM is unavailable the agent falls back to a template-based summary.
  5. The summary is stored in estimate.executive_summary for PDF export.
"""

import json
import logging

from sqlalchemy.orm import Session

from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.project import Project
from apex.backend.models.equipment_rate import EquipmentRate
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.utils.async_helper import run_async as _run_async
from apex.backend.utils.csi_utils import parse_csi_division
from apex.backend.agents.tools.assembly_tools import (
    cost_rollup_tool,
    markup_applier_tool,
    exclusion_generator_tool,
    assumption_logger_tool,
)

logger = logging.getLogger("apex.agent.assembly")


# ---------------------------------------------------------------------------
# System prompt — written once at module load
# ---------------------------------------------------------------------------

SUMMARY_SYSTEM_PROMPT = (
    "You are a senior construction estimator writing an executive summary for a competitive "
    "bid proposal. The audience is a project owner, construction manager, or architect "
    "evaluating bids from multiple general contractors. Your summary should:\n"
    "- Open with the project scope and building type\n"
    "- Highlight the key cost drivers and major scope items\n"
    "- Note any significant assumptions, allowances, or exclusions that affect the total\n"
    "- Close with a confident, professional statement of the contractor's qualifications\n\n"
    "Keep the tone professional and concise — 2-3 paragraphs maximum. "
    "Do NOT recalculate or modify any dollar amounts. Present the numbers exactly as provided."
)


# ---------------------------------------------------------------------------
# User prompt builder for the summary LLM call
# ---------------------------------------------------------------------------

def _build_summary_user_prompt(
    project,
    estimate: Estimate,
    line_items_data: list[dict],
    rollup: dict,
    exclusions: list,
    assumptions,
) -> str:
    """Construct the user prompt with full estimate data for the executive summary."""
    data = {
        "project": {
            "id": project.id,
            "name": getattr(project, "name", ""),
            "project_number": getattr(project, "project_number", ""),
            "project_type": getattr(project, "project_type", ""),
        },
        "estimate": {
            "version": estimate.version,
            "total_direct_cost": estimate.total_direct_cost,
            "total_labor_cost": estimate.total_labor_cost,
            "total_material_cost": estimate.total_material_cost,
            "overhead_pct": estimate.overhead_pct,
            "overhead_amount": estimate.overhead_amount,
            "profit_pct": estimate.profit_pct,
            "profit_amount": estimate.profit_amount,
            "contingency_pct": estimate.contingency_pct,
            "contingency_amount": estimate.contingency_amount,
            "total_bid_amount": estimate.total_bid_amount,
            "bid_bond_required": bool(estimate.bid_bond_required),
        },
        "divisions_covered": list(rollup["by_division"].keys()),
        "line_items": [
            {
                "division": item["division_number"],
                "csi_code": item["csi_code"],
                "description": item["description"],
                "quantity": item["quantity"],
                "unit_of_measure": item["unit_of_measure"],
                "total_cost": item["total_cost"],
            }
            for item in line_items_data
        ],
        "exclusions": exclusions,
        "assumptions": assumptions,
    }
    return (
        "Generate an executive summary for the following bid estimate. "
        "Do NOT recalculate or modify any numbers — summarize the scope and findings only.\n\n"
        + json.dumps(data, indent=2)
    )


# ---------------------------------------------------------------------------
# Async LLM call for summary
# ---------------------------------------------------------------------------

async def _llm_generate_summary(
    project,
    estimate: Estimate,
    line_items_data: list[dict],
    rollup: dict,
    exclusions: list,
    assumptions,
    provider,
) -> tuple[str | None, int, int]:
    """Call LLM to generate an executive summary.

    Returns (text, input_tokens, output_tokens).
    """
    user_prompt = _build_summary_user_prompt(
        project, estimate, line_items_data, rollup, exclusions, assumptions
    )
    try:
        response = await provider.complete(
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        logger.info(
            f"Agent 6 summary LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"total_tokens={response.input_tokens + response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )
        return (
            response.content.strip(), response.input_tokens, response.output_tokens,
            response.cache_creation_input_tokens, response.cache_read_input_tokens,
        )
    except Exception as exc:
        logger.error(f"Agent 6 summary LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


# ---------------------------------------------------------------------------
# Template-based fallback summary
# ---------------------------------------------------------------------------

def _template_summary(estimate: Estimate, rollup: dict, exclusions: list, assumptions) -> str:
    """Generate a template-based executive summary when the LLM is unavailable."""
    divisions = ", ".join(
        f"Division {d}" for d in rollup["by_division"].keys()
    ) or "various divisions"

    if isinstance(exclusions, list) and exclusions:
        excl_text = "; ".join(str(e) for e in exclusions)
    else:
        excl_text = "None noted"

    if isinstance(assumptions, list) and assumptions:
        assump_text = "; ".join(str(a) for a in assumptions)
    elif isinstance(assumptions, dict):
        assump_text = "; ".join(f"{k}: {v}" for k, v in assumptions.items())
    else:
        assump_text = "Standard industry assumptions apply"

    return (
        f"This bid proposal encompasses work across {divisions}, "
        f"with a total bid amount of ${estimate.total_bid_amount:,.2f}. "
        f"The estimate includes direct costs of ${estimate.total_direct_cost:,.2f} "
        f"covering labor, materials, and equipment, with overhead at "
        f"{estimate.overhead_pct:.0f}%, profit at {estimate.profit_pct:.0f}%, "
        f"and contingency at {estimate.contingency_pct:.0f}%.\n\n"
        f"Key assumptions include: {assump_text}. "
        f"Exclusions from this proposal: {excl_text}.\n\n"
        f"All pricing reflects current market conditions and is based on the scope "
        f"of work as defined in the project specifications. This estimate is valid "
        f"for 30 days from the date of submission."
    )


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_assembly_agent(db: Session, project_id: int) -> dict:
    """Assemble the full bid estimate from all components.

    Returns dict with estimate details and executive summary.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get labor estimates
    labor_items = db.query(LaborEstimate).filter(
        LaborEstimate.project_id == project_id,
        LaborEstimate.is_deleted == False,  # noqa: E712
    ).all()

    # Get spec sections for division info
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).all()
    section_map = {s.section_number: s for s in sections}

    # Get material prices
    all_material_prices = db.query(MaterialPrice).filter(
        MaterialPrice.is_deleted == False,  # noqa: E712
    ).all()
    material_map = {}
    for mp in all_material_prices:
        material_map[mp.csi_code] = mp

    # Determine version
    existing_count = db.query(Estimate).filter(
        Estimate.project_id == project_id,
        Estimate.is_deleted == False,  # noqa: E712
    ).count()

    # Build line items
    line_items_data = []
    for labor in labor_items:
        div_num = parse_csi_division(labor.csi_code)

        # Look up material cost
        mat = material_map.get(labor.csi_code)
        material_cost = 0.0
        if mat:
            material_cost = mat.unit_cost * labor.quantity

        # Equipment estimate — look up from DB, fall back to defaults
        eq_rate = db.query(EquipmentRate).filter(
            EquipmentRate.division_number == div_num,
            EquipmentRate.is_deleted == False,  # noqa: E712
        ).first()
        equipment_pct = eq_rate.equipment_pct if eq_rate else (0.10 if div_num in ("03", "05", "31") else 0.05)
        equipment_cost = labor.total_labor_cost * equipment_pct

        total_cost = labor.total_labor_cost + material_cost + equipment_cost

        line_items_data.append({
            "division_number": div_num,
            "csi_code": labor.csi_code,
            "description": f"{labor.work_type or labor.csi_code} - {labor.crew_type or 'General'}",
            "quantity": labor.quantity,
            "unit_of_measure": labor.productivity_unit or "EA",
            "labor_cost": labor.total_labor_cost,
            "material_cost": round(material_cost, 2),
            "equipment_cost": round(equipment_cost, 2),
            "subcontractor_cost": 0.0,
            "total_cost": round(total_cost, 2),
            "unit_cost": round(total_cost / labor.quantity, 2) if labor.quantity else 0,
        })

    # Cost rollup
    rollup = cost_rollup_tool(line_items_data)

    # Apply markups
    markups = markup_applier_tool(
        direct_cost=rollup["totals"]["total_direct"],
        overhead_pct=10.0,
        profit_pct=8.0,
        contingency_pct=5.0,
    )

    # Generate exclusions and assumptions
    parsed_sections = [{"division_number": s.division_number} for s in sections]
    exclusions = exclusion_generator_tool(parsed_sections, project.project_type)
    assumptions = assumption_logger_tool({"project_type": project.project_type})

    # Detect bid bond requirements from specs
    bid_bond = 0
    for s in sections:
        if s.raw_text and "bid bond" in (s.raw_text or "").lower():
            bid_bond = 1
            break

    # Create estimate (Python math only — numbers are final before LLM is called)
    estimate = Estimate(
        project_id=project_id,
        version=existing_count + 1,
        status="draft",
        total_direct_cost=rollup["totals"]["total_direct"],
        total_labor_cost=rollup["totals"]["total_labor"],
        total_material_cost=rollup["totals"]["total_material"],
        total_subcontractor_cost=rollup["totals"]["total_subcontractor"],
        gc_markup_pct=markups["gc_markup_pct"],
        gc_markup_amount=markups["gc_markup_amount"],
        overhead_pct=markups["overhead_pct"],
        overhead_amount=markups["overhead_amount"],
        profit_pct=markups["profit_pct"],
        profit_amount=markups["profit_amount"],
        contingency_pct=markups["contingency_pct"],
        contingency_amount=markups["contingency_amount"],
        total_bid_amount=markups["total_bid_amount"],
        exclusions=exclusions,
        assumptions=assumptions,
        alternates=[],
        bid_bond_required=bid_bond,
        summary_json=rollup["by_division"],
    )
    db.add(estimate)
    db.commit()
    db.refresh(estimate)

    # Create line items
    for item_data in line_items_data:
        line_item = EstimateLineItem(
            estimate_id=estimate.id,
            division_number=item_data["division_number"],
            csi_code=item_data["csi_code"],
            description=item_data["description"],
            quantity=item_data["quantity"],
            unit_of_measure=item_data["unit_of_measure"],
            labor_cost=item_data["labor_cost"],
            material_cost=item_data["material_cost"],
            equipment_cost=item_data["equipment_cost"],
            subcontractor_cost=item_data["subcontractor_cost"],
            total_cost=item_data["total_cost"],
            unit_cost=item_data["unit_cost"],
        )
        db.add(line_item)

    db.commit()

    # -----------------------------------------------------------------------
    # LLM executive summary — for PDF cover page only; numbers are NOT touched
    # -----------------------------------------------------------------------
    executive_summary: str | None = None
    summary_method = "template"
    summary_tokens_used = 0
    _in_tok = 0
    _out_tok = 0

    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=6, suffix="SUMMARY")
        llm_available = _run_async(provider.health_check())

        if llm_available:
            logger.info(
                f"Agent 6 summary: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — generating executive summary"
            )
            llm_text, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
                _llm_generate_summary(
                    project, estimate, line_items_data, rollup, exclusions, assumptions, provider
                )
            )
            summary_tokens_used = _in_tok + _out_tok
            if llm_text:
                log_token_usage(
                    db=db,
                    project_id=project_id,
                    agent_number=6,
                    provider=provider.provider_name,
                    model=provider.model_name,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                    estimate_id=estimate.id,
                    cache_creation_tokens=_cache_create,
                    cache_read_tokens=_cache_read,
                )
                executive_summary = llm_text
                summary_method = "llm"
                logger.info(
                    f"Agent 6 summary: LLM summary generated "
                    f"({summary_tokens_used} tokens, method=llm)"
                )
            else:
                logger.warning("Agent 6 summary: LLM returned empty content — using template fallback")
        else:
            logger.info(
                f"Agent 6 summary: LLM provider '{provider.provider_name}' unreachable — "
                "using template fallback"
            )
    except Exception as exc:
        logger.warning(f"Agent 6 summary: could not initialise LLM provider ({exc}) — using template fallback")

    if executive_summary is None:
        executive_summary = _template_summary(estimate, rollup, exclusions, assumptions)
        summary_method = "template"

    # Persist the summary — estimate numbers are unchanged
    estimate.executive_summary = executive_summary
    db.commit()

    logger.info(
        f"Agent 6 complete: estimate_id={estimate.id} version={estimate.version} "
        f"total_bid={estimate.total_bid_amount:.2f} summary_method={summary_method} "
        f"summary_tokens={summary_tokens_used}"
    )

    return validate_agent_output(6, {
        "estimate_id": estimate.id,
        "version": estimate.version,
        "total_direct_cost": estimate.total_direct_cost,
        "total_bid_amount": estimate.total_bid_amount,
        "line_items_count": len(line_items_data),
        "divisions_covered": list(rollup["by_division"].keys()),
        "bid_bond_required": bool(bid_bond),
        "executive_summary": executive_summary,
        "summary_method": summary_method,
        "summary_tokens_used": summary_tokens_used,
    })
