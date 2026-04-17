"""Agent 6: Intelligence Report Assembly (v2)

Aggregates all upstream agent outputs + data sources into a single
intelligence report. The estimator's numbers are NOT modified — this
agent provides context and flags, not corrections.

v2 flow:
  1. Query takeoff items (Agent 4 output)
  2. Aggregate rate intelligence (deviation flags, optimism score)
  3. Aggregate field calibration (Agent 5 output)
  4. Aggregate scope risk (Agent 3 gaps)
  5. Find comparable projects (Bid Intelligence)
  6. Query spec intelligence (Agent 2 output)
  7. Query PB coverage stats
  8. Compute overall risk level and confidence score
  9. Generate executive narrative (LLM with template fallback)
  10. Persist IntelligenceReportModel
  11. Return validated Agent6Output

ALL AGGREGATION IS DETERMINISTIC PYTHON.
LLM is used ONLY for the executive narrative (step 9).
"""

import json
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.assembly_tools import (
    assumption_logger_tool,
    cost_rollup_tool,
    exclusion_generator_tool,
    markup_applier_tool,
)
from apex.backend.models.equipment_rate import EquipmentRate
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.models.intelligence_report import IntelligenceReportModel

# v1 imports (kept for run_assembly_agent_v1)
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.services.library.bid_intelligence.models import BIEstimate
from apex.backend.services.library.field_actuals.service import FieldActualsService
from apex.backend.services.library.productivity_brain.models import PBLineItem, PBProject
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.utils.async_helper import run_async as _run_async
from apex.backend.utils.csi_utils import parse_csi_division

logger = logging.getLogger("apex.agent.assembly")


# ---------------------------------------------------------------------------
# v2 System prompt for executive narrative
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT_V2 = (
    "You are a senior construction estimating advisor writing a brief intelligence "
    "briefing for an estimator about to submit a competitive bid. Your audience is "
    "the estimator and their manager reviewing the bid before submission.\n\n"
    "Based on the intelligence data provided, write a 3-4 paragraph executive briefing that:\n"
    "- Opens with the overall risk assessment and confidence level\n"
    "- Highlights the top rate deviations that need attention (cite specific activities)\n"
    "- Notes any field calibration warnings (where crews historically differ from estimates)\n"
    "- Flags critical scope gaps the estimator should address\n"
    "- If comparable projects exist, reference the company's historical performance\n"
    "- Closes with a clear recommendation: submit as-is, review flagged items, or hold for revision\n\n"
    "Keep the tone direct and actionable. Estimators don't want prose — they want signals.\n"
    "Do NOT invent data. If a section has no data, say so. Do NOT modify any numbers."
)


# ---------------------------------------------------------------------------
# v2 Aggregation helpers — ALL DETERMINISTIC PYTHON
# ---------------------------------------------------------------------------


def _aggregate_rate_intelligence(db: Session, project_id: int) -> dict:
    """Query TakeoffItemV2 rows, count flags, compute optimism score."""
    items = db.query(TakeoffItemV2).filter_by(project_id=project_id).all()

    if not items:
        return {
            "total_items": 0,
            "items_ok": 0,
            "items_review": 0,
            "items_update": 0,
            "items_no_match": 0,
            "items_needs_rate": 0,
            "avg_deviation_pct": None,
            "optimism_score": None,
            "top_deviations": [],
        }

    counts = {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0, "NEEDS_RATE": 0}
    deviations = []

    for item in items:
        flag = (item.flag or "NO_DATA").upper()
        counts[flag] = counts.get(flag, 0) + 1

        if item.delta_pct is not None:
            deviations.append(
                {
                    "row_number": item.row_number,
                    "activity": item.activity,
                    "delta_pct": item.delta_pct,
                    "flag": flag,
                    "crew": item.crew,
                }
            )

    # optimism_score = average of delta_pct (positive = optimistic vs history)
    avg_dev = None
    optimism = None
    if deviations:
        vals = [d["delta_pct"] for d in deviations]
        avg_dev = round(sum(vals) / len(vals), 2)
        optimism = avg_dev  # positive = rates below history = optimistic

    # top 5 by absolute deviation
    top_devs = sorted(deviations, key=lambda d: abs(d["delta_pct"]), reverse=True)[:5]

    return {
        "total_items": len(items),
        "items_ok": counts.get("OK", 0),
        "items_review": counts.get("REVIEW", 0),
        "items_update": counts.get("UPDATE", 0),
        "items_no_match": counts.get("NO_DATA", 0),
        "items_needs_rate": counts.get("NEEDS_RATE", 0),
        "avg_deviation_pct": avg_dev,
        "optimism_score": optimism,
        "top_deviations": top_devs,
    }


def _aggregate_field_calibration(db: Session, project_id: int) -> dict:
    """Query field actuals for each takeoff item via FieldActualsService."""
    items = db.query(TakeoffItemV2).filter_by(project_id=project_id).all()

    if not items:
        return {
            "items_with_field_data": 0,
            "items_without_field_data": 0,
            "avg_calibration_factor": None,
            "optimistic_count": 0,
            "conservative_count": 0,
            "aligned_count": 0,
            "critical_alerts": [],
        }

    fa_service = FieldActualsService(db)
    with_data = 0
    without_data = 0
    cal_factors = []
    direction_counts = {"optimistic": 0, "conservative": 0, "aligned": 0, "no_data": 0}
    critical_alerts = []

    for item in items:
        field_match = fa_service.match_field_data(item.activity, item.unit)

        if not field_match or field_match.get("avg_rate") is None:
            without_data += 1
            direction_counts["no_data"] += 1
            continue

        with_data += 1
        field_avg = field_match["avg_rate"]
        est_rate = item.production_rate

        if est_rate and est_rate > 0 and field_avg > 0:
            cal_factor = round(field_avg / est_rate, 4)
            cal_factors.append(cal_factor)

            # Determine direction
            if cal_factor < 0.95:
                direction_counts["optimistic"] += 1
                direction = "optimistic"
            elif cal_factor > 1.05:
                direction_counts["conservative"] += 1
                direction = "conservative"
            else:
                direction_counts["aligned"] += 1
                direction = "aligned"

            # Critical alert: calibration factor outside 0.80-1.20
            if cal_factor < 0.80 or cal_factor > 1.20:
                critical_alerts.append(
                    {
                        "row_number": item.row_number,
                        "activity": item.activity,
                        "calibration_factor": cal_factor,
                        "direction": direction,
                        "field_avg_rate": field_avg,
                        "estimator_rate": est_rate,
                    }
                )
        else:
            without_data += 1
            direction_counts["no_data"] += 1

    avg_cal = round(sum(cal_factors) / len(cal_factors), 4) if cal_factors else None

    return {
        "items_with_field_data": with_data,
        "items_without_field_data": without_data,
        "avg_calibration_factor": avg_cal,
        "optimistic_count": direction_counts["optimistic"],
        "conservative_count": direction_counts["conservative"],
        "aligned_count": direction_counts["aligned"],
        "critical_alerts": critical_alerts[:10],  # cap at 10
    }


def _aggregate_scope_risk(db: Session, project_id: int) -> dict:
    """Query GapReport + GapItems for this project."""
    report = db.query(GapReport).filter_by(project_id=project_id).order_by(GapReport.id.desc()).first()

    if not report:
        return {
            "total_gaps": 0,
            "critical_gaps": 0,
            "watch_gaps": 0,
            "spec_vs_takeoff_gaps": 0,
            "missing_divisions": [],
            "top_risks": [],
        }

    gap_items = db.query(GapReportItem).filter_by(gap_report_id=report.id).all()

    critical = 0
    watch = 0
    svt = 0
    missing_divs = set()
    by_type = {}

    for gap in gap_items:
        severity = (gap.severity or "").lower()
        gap_type = (gap.gap_type or "").lower()

        if severity == "critical":
            critical += 1
        elif severity == "watch":
            watch += 1

        if gap_type == "spec_vs_takeoff":
            svt += 1
        elif gap_type == "missing":
            missing_divs.add(gap.division_number)

        by_type[gap_type] = by_type.get(gap_type, 0) + 1

    # Top 5 risks: critical first, then by gap_type priority
    type_priority = {"missing": 0, "spec_vs_takeoff": 1, "conflict": 2, "ambiguous": 3}
    sorted_gaps = sorted(
        gap_items,
        key=lambda g: (
            0 if (g.severity or "").lower() == "critical" else 1,
            type_priority.get((g.gap_type or "").lower(), 99),
        ),
    )
    top_risks = [
        {
            "division": g.division_number,
            "section": g.section_number,
            "title": g.title,
            "gap_type": g.gap_type,
            "severity": g.severity,
            "description": (g.description or "")[:200],
        }
        for g in sorted_gaps[:5]
    ]

    return {
        "total_gaps": report.total_gaps or len(gap_items),
        "critical_gaps": critical,
        "watch_gaps": watch,
        "spec_vs_takeoff_gaps": svt,
        "missing_divisions": sorted(missing_divs),
        "top_risks": top_risks,
    }


def _find_comparable_projects(db: Session, project_id: int) -> dict:
    """Query BIEstimate for similar projects by sector/region/volume."""
    project = db.query(Project).get(project_id)

    empty = {
        "comparable_count": 0,
        "avg_bid_amount": None,
        "avg_cost_per_cy": None,
        "avg_production_mh_per_cy": None,
        "company_hit_rate": None,
        "comparables": [],
    }

    if not project:
        return empty

    # Build query — filter by available criteria
    q = db.query(BIEstimate).filter(BIEstimate.bid_amount.isnot(None))

    region = getattr(project, "location", None)
    sector = getattr(project, "project_type", None)

    # Try matching with both region and sector, then relax
    if region and sector:
        matched = q.filter(
            BIEstimate.region == region,
            BIEstimate.market_sector == sector,
        ).all()
        if not matched:
            matched = q.filter(BIEstimate.market_sector == sector).all()
        if not matched:
            matched = q.filter(BIEstimate.region == region).all()
    elif sector:
        matched = q.filter(BIEstimate.market_sector == sector).all()
    elif region:
        matched = q.filter(BIEstimate.region == region).all()
    else:
        matched = q.all()

    if not matched:
        return empty

    # Prefer Awarded, then Closed
    awarded = [m for m in matched if (m.status or "").lower() == "awarded"]
    closed = [m for m in matched if (m.status or "").lower() == "closed"]
    pool = awarded + closed if (awarded or closed) else matched

    # Compute stats
    bid_amounts = [m.bid_amount for m in pool if m.bid_amount]
    avg_bid = round(sum(bid_amounts) / len(bid_amounts), 2) if bid_amounts else None

    costs_per_cy = [m.cost_per_cy for m in pool if m.cost_per_cy]
    avg_cpc = round(sum(costs_per_cy) / len(costs_per_cy), 2) if costs_per_cy else None

    mh_per_cy = []
    for m in pool:
        if m.production_mh and m.conc_vol_cy and m.conc_vol_cy > 0:
            mh_per_cy.append(round(m.production_mh / m.conc_vol_cy, 4))
    avg_mh = round(sum(mh_per_cy) / len(mh_per_cy), 4) if mh_per_cy else None

    # Hit rate = awarded / (awarded + closed)
    total_decided = len(awarded) + len(closed)
    hit_rate = round(len(awarded) / total_decided * 100, 1) if total_decided > 0 else None

    # Top 5 comparables
    top5 = pool[:5]
    comparables = [
        {
            "name": m.name,
            "status": m.status,
            "region": m.region,
            "bid_amount": m.bid_amount,
            "cost_per_cy": m.cost_per_cy,
            "conc_vol_cy": m.conc_vol_cy,
        }
        for m in top5
    ]

    return {
        "comparable_count": len(pool),
        "avg_bid_amount": avg_bid,
        "avg_cost_per_cy": avg_cpc,
        "avg_production_mh_per_cy": avg_mh,
        "company_hit_rate": hit_rate,
        "comparables": comparables,
    }


def _get_spec_intelligence(db: Session, project_id: int) -> dict:
    """Count parsed spec sections and material specs."""
    sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    total = len(sections)
    with_material = sum(
        1 for s in sections if s.material_specs and str(s.material_specs) not in ("null", "{}", "[]", "None")
    )

    return {
        "sections_parsed": total,
        "material_specs_extracted": with_material,
    }


def _get_pb_coverage(db: Session) -> dict:
    """Stats on Productivity Brain data available."""
    project_count = db.query(func.count(PBProject.id)).scalar() or 0
    item_count = db.query(func.count(PBLineItem.id)).scalar() or 0
    activity_count = db.query(func.count(func.distinct(PBLineItem.activity))).scalar() or 0

    return {
        "pb_projects_loaded": project_count,
        "pb_activities_available": activity_count,
        "pb_total_line_items": item_count,
    }


# ---------------------------------------------------------------------------
# v2 Risk scoring — deterministic
# ---------------------------------------------------------------------------


def _compute_risk_level(rate_intel: dict, field_cal: dict, scope_risk: dict, pb_coverage: dict) -> tuple:
    """Compute overall risk level and confidence score.

    Risk factors (each 0-25 points, total 0-100):
    - Rate deviation: % of items flagged UPDATE (>20% off)
    - Field calibration: % of items with optimistic direction
    - Scope gaps: count of critical + spec_vs_takeoff gaps
    - Data coverage: % of items with PB match + field data

    Risk levels:
    - 0-25: "low"
    - 26-50: "moderate"
    - 51-75: "high"
    - 76-100: "critical"

    Confidence = inverse of data gaps (more data = higher confidence)
    """
    risk_score = 0.0

    # Factor 1: Rate deviation (0-25)
    total = rate_intel.get("total_items", 0)
    if total > 0:
        update_pct = rate_intel.get("items_update", 0) / total
        risk_score += min(update_pct * 100, 25.0)  # 100% update → 25 pts

    # Factor 2: Field calibration (0-25)
    with_data = field_cal.get("items_with_field_data", 0)
    if with_data > 0:
        optimistic_pct = field_cal.get("optimistic_count", 0) / with_data
        risk_score += min(optimistic_pct * 50, 25.0)  # 50% optimistic → 25 pts

    # Factor 3: Scope gaps (0-25)
    critical_gaps = scope_risk.get("critical_gaps", 0)
    svt_gaps = scope_risk.get("spec_vs_takeoff_gaps", 0)
    gap_score = min((critical_gaps * 5 + svt_gaps * 3), 25.0)
    risk_score += gap_score

    # Factor 4: Data coverage deficit (0-25)
    if total > 0:
        no_match_pct = rate_intel.get("items_no_match", 0) / total
        no_field_pct = field_cal.get("items_without_field_data", 0) / max(total, 1)
        coverage_deficit = (no_match_pct + no_field_pct) / 2
        risk_score += min(coverage_deficit * 50, 25.0)

    risk_score = round(min(risk_score, 100.0), 1)

    # Risk level
    if risk_score <= 25:
        level = "low"
    elif risk_score <= 50:
        level = "moderate"
    elif risk_score <= 75:
        level = "high"
    else:
        level = "critical"

    # Confidence: more data = higher confidence
    data_points = 0
    max_data_points = 0

    if total > 0:
        max_data_points += total
        data_points += total - rate_intel.get("items_no_match", 0)

    if total > 0:
        max_data_points += total
        data_points += field_cal.get("items_with_field_data", 0)

    pb_loaded = pb_coverage.get("pb_projects_loaded", 0)
    if pb_loaded > 0:
        data_points += 10  # bonus for having PB data
    max_data_points += 10

    confidence = round((data_points / max_data_points * 100), 1) if max_data_points > 0 else 0.0

    return level, confidence


# ---------------------------------------------------------------------------
# Spec retrieval helpers for Agent 6 narrative
# ---------------------------------------------------------------------------

_NARRATIVE_RETRIEVAL_QUERIES = [
    "project scope summary key requirements",
    "quality control testing inspection standards",
    "material specifications performance requirements",
    "special conditions risk factors allowances",
]


def _retrieve_spec_context_for_narrative(project_id: int) -> str:
    """Retrieve key spec language to ground the Agent 6 narrative in actual project specs.

    Returns a formatted REFERENCE MATERIAL block, or "" if retrieval unavailable.
    """
    try:
        from apex.backend.retrieval.embedder import is_available

        if not is_available():
            return ""

        from apex.backend.retrieval.retriever import format_for_agent, search_multi
        from apex.backend.retrieval.store import collection_exists

        if not collection_exists(project_id):
            return ""

        chunks = search_multi(
            project_id,
            queries=_NARRATIVE_RETRIEVAL_QUERIES,
            top_k_each=2,
            min_score=0.3,
        )

        if not chunks:
            return ""

        logger.info(f"Agent 6: retrieved {len(chunks)} spec chunks for narrative context (project {project_id})")
        return format_for_agent(chunks, label="PROJECT SPEC REFERENCE")

    except Exception as exc:
        logger.warning(f"Agent 6: spec retrieval failed (non-fatal): {exc}")
        return ""


# ---------------------------------------------------------------------------
# v2 Narrative — LLM with template fallback
# ---------------------------------------------------------------------------


def _build_narrative_prompt(report_data: dict, spec_context: str = "") -> str:
    """Build the user prompt with all intelligence data for the LLM."""
    ri = report_data.get("rate_intelligence", {})
    fc = report_data.get("field_calibration", {})
    sr = report_data.get("scope_risk", {})
    cp = report_data.get("comparable_projects", {})
    lines = [
        f"Project: {report_data.get('project_name', 'Unknown')}",
        f"Overall Risk: {report_data.get('overall_risk_level', 'unknown')} "
        f"| Confidence: {report_data.get('confidence_score', 0)}%",
        f"Takeoff Items: {report_data.get('takeoff_item_count', 0)}",
        "",
        "=== RATE INTELLIGENCE ===",
        f"{ri.get('items_ok', 0)} items OK, "
        f"{ri.get('items_review', 0)} need REVIEW, "
        f"{ri.get('items_update', 0)} need UPDATE, "
        f"{ri.get('items_no_match', 0)} have no historical data.",
    ]

    if ri.get("optimism_score") is not None:
        lines.append(f"Overall optimism score: {ri['optimism_score']}% (positive = rates below history = optimistic)")

    top_devs = ri.get("top_deviations", [])
    if top_devs:
        lines.append("Top deviations:")
        for d in top_devs:
            lines.append(f"  - {d['activity']}: {d['delta_pct']:+.1f}% ({d['flag']})")

    lines += [
        "",
        "=== FIELD CALIBRATION ===",
        f"{fc.get('items_with_field_data', 0)} items with field data, {fc.get('items_without_field_data', 0)} without.",
        f"Optimistic: {fc.get('optimistic_count', 0)}, "
        f"Conservative: {fc.get('conservative_count', 0)}, "
        f"Aligned: {fc.get('aligned_count', 0)}.",
    ]

    alerts = fc.get("critical_alerts", [])
    if alerts:
        lines.append("Critical calibration alerts:")
        for a in alerts[:5]:
            lines.append(f"  - {a['activity']}: cal_factor={a['calibration_factor']:.2f} ({a['direction']})")

    lines += [
        "",
        "=== SCOPE RISK ===",
        f"{sr.get('critical_gaps', 0)} critical gaps, {sr.get('spec_vs_takeoff_gaps', 0)} spec-vs-takeoff gaps.",
    ]

    missing = sr.get("missing_divisions", [])
    if missing:
        lines.append(f"Missing divisions: {', '.join(missing)}")

    top_risks = sr.get("top_risks", [])
    if top_risks:
        lines.append("Top risks:")
        for r in top_risks[:3]:
            lines.append(f"  - [{r['severity']}] {r['title']} ({r['gap_type']})")

    lines += [
        "",
        "=== COMPARABLE PROJECTS ===",
    ]
    if cp.get("comparable_count", 0) > 0:
        lines.append(
            f"{cp['comparable_count']} similar bids found. "
            f"Company hit rate: {cp.get('company_hit_rate', 'N/A')}%. "
            f"Avg bid: ${cp.get('avg_bid_amount', 0):,.0f}"
        )
    else:
        lines.append("No comparable projects found in bid intelligence database.")

    if spec_context:
        lines += ["", spec_context]

    return "\n".join(lines)


async def _llm_generate_narrative(report_data: dict, provider, spec_context: str = "") -> tuple:
    """Call LLM to generate the executive narrative.

    Returns (text, input_tokens, output_tokens, cache_create, cache_read).
    """
    user_prompt = (
        "Generate an intelligence briefing for the following bid estimate data. "
        "Do NOT invent data or modify any numbers — summarize the signals only. "
        "Where REFERENCE MATERIAL from project specs is provided, cite specific "
        "section numbers in your narrative (e.g., 'per Section 03 30 00').\n\n"
        + _build_narrative_prompt(report_data, spec_context=spec_context)
    )
    try:
        response = await provider.complete(
            system_prompt=NARRATIVE_SYSTEM_PROMPT_V2,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        logger.info(
            f"Agent 6 v2 narrative LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )
        return (
            response.content.strip(),
            response.input_tokens,
            response.output_tokens,
            response.cache_creation_input_tokens,
            response.cache_read_input_tokens,
        )
    except Exception as exc:
        logger.error(f"Agent 6 v2 narrative LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


def _generate_fallback_narrative(report_data: dict) -> str:
    """Template-based narrative when LLM unavailable."""
    level = report_data.get("overall_risk_level", "unknown")
    confidence = report_data.get("confidence_score", 0)
    project_name = report_data.get("project_name", "Unknown Project")
    ri = report_data.get("rate_intelligence", {})
    fc = report_data.get("field_calibration", {})
    sr = report_data.get("scope_risk", {})
    cp = report_data.get("comparable_projects", {})

    # Auto-recommendation based on risk level
    if level == "low":
        rec = "Submit as-is. No significant risk signals detected."
    elif level == "moderate":
        rec = "Review flagged items before submission. Moderate risk signals present."
    elif level == "high":
        rec = "Hold for revision. Multiple high-risk signals require estimator review."
    else:
        rec = "Hold for revision. Critical risk signals detected — management review recommended."

    return (
        f"Intelligence Report for {project_name}\n"
        f"Risk Level: {level.upper()} | Confidence: {confidence}%\n\n"
        f"RATE INTELLIGENCE: {ri.get('items_ok', 0)} items aligned, "
        f"{ri.get('items_review', 0)} need review, "
        f"{ri.get('items_update', 0)} need update. "
        f"Average deviation: {ri.get('avg_deviation_pct', 'N/A')}%.\n\n"
        f"FIELD CALIBRATION: {fc.get('items_with_field_data', 0)} items with field data, "
        f"{fc.get('optimistic_count', 0)} optimistic (risk), "
        f"{fc.get('conservative_count', 0)} conservative, "
        f"{fc.get('aligned_count', 0)} aligned.\n\n"
        f"SCOPE RISK: {sr.get('critical_gaps', 0)} critical gaps, "
        f"{sr.get('spec_vs_takeoff_gaps', 0)} spec-vs-takeoff gaps. "
        f"Missing divisions: {', '.join(sr.get('missing_divisions', [])) or 'none'}.\n\n"
        f"COMPARABLE PROJECTS: {cp.get('comparable_count', 0)} found"
        + (f", avg bid ${cp['avg_bid_amount']:,.0f}" if cp.get("avg_bid_amount") else "")
        + (f", hit rate {cp['company_hit_rate']}%" if cp.get("company_hit_rate") else "")
        + ".\n\n"
        f"Recommendation: {rec}"
    )


# ---------------------------------------------------------------------------
# v2 Main entry point
# ---------------------------------------------------------------------------


def run_assembly_agent(db: Session, project_id: int, use_llm: bool = True) -> dict:
    """Assemble the intelligence report from all upstream data.

    Args:
        db: SQLAlchemy session.
        project_id: ID of the project.
        use_llm: When False, skip the LLM call and use template narrative.

    Returns dict validated against Agent6Output contract.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project_name = getattr(project, "name", None) or f"Project {project_id}"

    # 1-2. Rate intelligence
    rate_intel = _aggregate_rate_intelligence(db, project_id)

    # 3. Field calibration
    field_cal = _aggregate_field_calibration(db, project_id)

    # 4. Scope risk
    scope_risk = _aggregate_scope_risk(db, project_id)

    # 5. Comparable projects
    comparables = _find_comparable_projects(db, project_id)

    # 6. Spec intelligence
    spec_intel = _get_spec_intelligence(db, project_id)

    # 7. PB coverage
    pb_coverage = _get_pb_coverage(db)

    # 8. Overall risk level and confidence
    risk_level, confidence = _compute_risk_level(rate_intel, field_cal, scope_risk, pb_coverage)

    # Compute takeoff totals
    takeoff_items = db.query(TakeoffItemV2).filter_by(project_id=project_id).all()
    takeoff_total_labor = sum((item.labor_cost_per_unit or 0) * (item.quantity or 0) for item in takeoff_items)
    takeoff_total_material = sum((item.material_cost_per_unit or 0) * (item.quantity or 0) for item in takeoff_items)

    # Assemble report data for narrative generation
    report_data = {
        "project_name": project_name,
        "takeoff_item_count": rate_intel["total_items"],
        "overall_risk_level": risk_level,
        "confidence_score": confidence,
        "rate_intelligence": rate_intel,
        "field_calibration": field_cal,
        "scope_risk": scope_risk,
        "comparable_projects": comparables,
    }

    # 9. Executive narrative — LLM with template fallback
    narrative = None
    narrative_method = "template"
    narrative_tokens = 0
    _in_tok = 0
    _out_tok = 0

    # Retrieve spec context to ground the narrative in actual project spec language
    spec_context = _retrieve_spec_context_for_narrative(project_id)
    if spec_context:
        logger.info("Agent 6 v2: injecting spec retrieval context into narrative prompt")

    if not use_llm:
        logger.info("Agent 6 v2: use_llm=False — using template narrative")
    else:
        try:
            from apex.backend.services.llm_provider import get_llm_provider

            provider = get_llm_provider(agent_number=6, suffix="SUMMARY")
            llm_available = _run_async(provider.health_check())

            if llm_available:
                logger.info(
                    f"Agent 6 v2: LLM provider '{provider.provider_name}/{provider.model_name}' "
                    "available — generating narrative"
                )
                llm_text, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
                    _llm_generate_narrative(report_data, provider, spec_context=spec_context)
                )
                narrative_tokens = _in_tok + _out_tok
                if llm_text:
                    log_token_usage(
                        db=db,
                        project_id=project_id,
                        agent_number=6,
                        provider=provider.provider_name,
                        model=provider.model_name,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        cache_creation_tokens=_cache_create,
                        cache_read_tokens=_cache_read,
                    )
                    narrative = llm_text
                    narrative_method = "llm"
                    logger.info(f"Agent 6 v2: LLM narrative generated ({narrative_tokens} tokens)")
                else:
                    logger.warning("Agent 6 v2: LLM returned empty — using template")
            else:
                logger.warning("Agent 6 v2: LLM unreachable — using template")
        except Exception as exc:
            logger.warning(f"Agent 6 v2: LLM failed ({exc}) — using template")

    if narrative is None:
        narrative = _generate_fallback_narrative(report_data)
        narrative_method = "template"

    # 10. Persist IntelligenceReportModel
    existing_count = db.query(func.count(IntelligenceReportModel.id)).filter_by(project_id=project_id).scalar() or 0

    report_model = IntelligenceReportModel(
        project_id=project_id,
        version=existing_count + 1,
        takeoff_item_count=rate_intel["total_items"],
        takeoff_total_labor=round(takeoff_total_labor, 2) if takeoff_total_labor else None,
        takeoff_total_material=round(takeoff_total_material, 2) if takeoff_total_material else None,
        rate_intelligence_json=json.dumps(rate_intel),
        field_calibration_json=json.dumps(field_cal),
        scope_risk_json=json.dumps(scope_risk),
        comparable_projects_json=json.dumps(comparables),
        spec_sections_parsed=spec_intel["sections_parsed"],
        material_specs_extracted=spec_intel["material_specs_extracted"],
        overall_risk_level=risk_level,
        confidence_score=confidence,
        executive_narrative=narrative,
        narrative_method=narrative_method,
        pb_projects_loaded=pb_coverage["pb_projects_loaded"],
        pb_activities_available=pb_coverage["pb_activities_available"],
        narrative_tokens_used=narrative_tokens,
    )
    db.add(report_model)
    db.commit()
    db.refresh(report_model)

    logger.info(
        f"Agent 6 v2 complete: report_id={report_model.id} version={report_model.version} "
        f"risk={risk_level} confidence={confidence} narrative_method={narrative_method} "
        f"tokens={narrative_tokens}"
    )

    # 11. Return validated Agent6Output
    return validate_agent_output(
        6,
        {
            "report_id": report_model.id,
            "report_version": report_model.version,
            "overall_risk_level": risk_level,
            "confidence_score": confidence,
            "rate_items_flagged": rate_intel["items_review"] + rate_intel["items_update"],
            "scope_gaps_found": scope_risk["total_gaps"],
            "field_calibration_alerts": len(field_cal["critical_alerts"]),
            "comparable_projects_found": comparables["comparable_count"],
            "narrative_method": narrative_method,
            "narrative_tokens_used": narrative_tokens,
        },
    )


# ===========================================================================
# DEPRECATED — v1 estimate assembly (kept for "spec" pipeline mode fallback)
# ===========================================================================

# v1 System prompt
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
    user_prompt = _build_summary_user_prompt(project, estimate, line_items_data, rollup, exclusions, assumptions)
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
            response.content.strip(),
            response.input_tokens,
            response.output_tokens,
            response.cache_creation_input_tokens,
            response.cache_read_input_tokens,
        )
    except Exception as exc:
        logger.error(f"Agent 6 summary LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


# FALLBACK: Rule-based path when LLM unavailable (Sprint 8)
def _generate_fallback_summary(
    project,
    estimate: Estimate,
    line_items_data: list[dict],
    rollup: dict,
    exclusions: list,
    assumptions,
) -> str:
    """Generate a template-based executive summary when the LLM is unavailable."""
    # FALLBACK: Rule-based path when LLM unavailable (Sprint 8)
    project_name = getattr(project, "name", None) or f"Project {project.id}"

    divisions = ", ".join(f"Division {d}" for d in rollup["by_division"].keys()) or "various divisions"

    line_item_count = len(line_items_data)

    sorted_items = sorted(line_items_data, key=lambda x: x.get("total_cost", 0), reverse=True)
    top_3 = [item["description"] for item in sorted_items[:3]]
    top_3_text = "; ".join(top_3) if top_3 else "N/A"

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
        f"AI-generated summary unavailable — template summary provided\n\n"
        f"Project: {project_name}. This bid proposal encompasses {line_item_count} line "
        f"item(s) across {divisions}, with a total bid amount of "
        f"${estimate.total_bid_amount:,.2f}. The estimate includes direct costs of "
        f"${estimate.total_direct_cost:,.2f} covering labor, materials, and equipment, "
        f"with overhead at {estimate.overhead_pct:.0f}%, profit at "
        f"{estimate.profit_pct:.0f}%, and contingency at "
        f"{estimate.contingency_pct:.0f}%.\n\n"
        f"Top cost categories: {top_3_text}. "
        f"Key assumptions include: {assump_text}. "
        f"Exclusions from this proposal: {excl_text}.\n\n"
        f"All pricing reflects current market conditions and is based on the scope "
        f"of work as defined in the project specifications. This estimate is valid "
        f"for 30 days from the date of submission."
    )


# DEPRECATED — v1 estimate assembly
def run_assembly_agent_v1(db: Session, project_id: int, use_llm: bool = True) -> dict:
    """Assemble the full bid estimate from all components.

    DEPRECATED — v1 path. Kept for backward compatibility with "spec" pipeline mode.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get labor estimates
    labor_items = (
        db.query(LaborEstimate)
        .filter(
            LaborEstimate.project_id == project_id,
            LaborEstimate.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    # Get spec sections for division info
    sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    # Get material prices
    all_material_prices = (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    material_map = {}
    for mp in all_material_prices:
        material_map[mp.csi_code] = mp

    # Determine version
    existing_count = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .count()
    )

    # Build line items
    line_items_data = []
    for labor in labor_items:
        div_num = parse_csi_division(labor.csi_code)

        # Look up material cost
        mat = material_map.get(labor.csi_code)
        material_cost = 0.0
        if mat:
            material_cost = mat.unit_cost * labor.quantity

        # Equipment estimate
        eq_rate = (
            db.query(EquipmentRate)
            .filter(
                EquipmentRate.division_number == div_num,
                EquipmentRate.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        equipment_pct = eq_rate.equipment_pct if eq_rate else (0.10 if div_num in ("03", "05", "31") else 0.05)
        equipment_cost = labor.total_labor_cost * equipment_pct

        total_cost = labor.total_labor_cost + material_cost + equipment_cost

        line_items_data.append(
            {
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
            }
        )

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

    # Create estimate
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

    # LLM executive summary
    executive_summary: str | None = None
    summary_method = "template"
    summary_tokens_used = 0
    _in_tok = 0
    _out_tok = 0

    if not use_llm:
        logger.info("Agent 6 v1 summary: use_llm=False — skipping LLM call, using fallback summary")
    else:
        try:
            from apex.backend.services.llm_provider import get_llm_provider

            provider = get_llm_provider(agent_number=6, suffix="SUMMARY")
            llm_available = _run_async(provider.health_check())

            if llm_available:
                logger.info(
                    f"Agent 6 v1 summary: LLM provider '{provider.provider_name}/{provider.model_name}' "
                    "is available — generating executive summary"
                )
                llm_text, _in_tok, _out_tok, _cache_create, _cache_read = _run_async(
                    _llm_generate_summary(project, estimate, line_items_data, rollup, exclusions, assumptions, provider)
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
                    logger.info(f"Agent 6 v1 summary: LLM summary generated ({summary_tokens_used} tokens, method=llm)")
                else:
                    logger.warning("Agent 6 v1 summary: LLM returned empty content — using fallback summary")
            else:
                logger.warning(
                    f"Agent 6 v1 summary: LLM provider '{provider.provider_name}' unreachable — using fallback summary"
                )
        except Exception as exc:
            logger.warning(f"Agent 6 v1 summary: LLM call failed ({exc}) — using fallback summary")

    if executive_summary is None:
        executive_summary = _generate_fallback_summary(
            project, estimate, line_items_data, rollup, exclusions, assumptions
        )
        summary_method = "template"

    estimate.executive_summary = executive_summary
    db.commit()

    logger.info(
        f"Agent 6 v1 complete: estimate_id={estimate.id} version={estimate.version} "
        f"total_bid={estimate.total_bid_amount:.2f} summary_method={summary_method} "
        f"summary_tokens={summary_tokens_used}"
    )

    # v1 returns Agent6Output_V1-compatible dict but validated against v2 contract
    # with report_id=0 to signal v1 path
    return validate_agent_output(
        6,
        {
            "report_id": 0,
            "report_version": estimate.version,
            "overall_risk_level": "unknown",
            "confidence_score": None,
            "rate_items_flagged": 0,
            "scope_gaps_found": 0,
            "field_calibration_alerts": 0,
            "comparable_projects_found": 0,
            "narrative_method": summary_method,
            "narrative_tokens_used": summary_tokens_used,
        },
    )
