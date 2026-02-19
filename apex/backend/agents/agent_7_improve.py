"""Agent 7: IMPROVE Feedback Agent.

Ingests completed project actuals and compares against original estimates
to generate productivity variance reports and feed corrections back.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.agents.tools.improve_tools import (
    variance_calculator_tool,
    productivity_updater_tool,
    trend_analyzer_tool,
)

logger = logging.getLogger("apex.agent.improve")


def run_improve_agent(db: Session, project_id: int) -> dict:
    """Process actuals and generate variance report, update productivity rates.

    Returns dict with variance analysis results.
    """
    # Get existing actuals for this project
    actuals = db.query(ProjectActual).filter(
        ProjectActual.project_id == project_id,
        ProjectActual.is_deleted == False,  # noqa: E712
    ).all()

    if not actuals:
        return {
            "actuals_processed": 0,
            "message": "No actuals data found for this project",
        }

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

    # Calculate variances
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
    accuracy = (1 - abs(total_act - total_est) / total_est * 1) * 100 if total_est > 0 else 0
    accuracy = max(0, min(100, accuracy))

    return {
        "actuals_processed": len(actuals),
        "variances_calculated": len(variances),
        "productivity_updates": len(updates),
        "accuracy_score": round(accuracy, 1),
        "total_estimated_cost": round(total_est, 2),
        "total_actual_cost": round(total_act, 2),
        "overall_variance_pct": round((total_act - total_est) / total_est * 100, 2) if total_est > 0 else 0,
        "trends": trends,
    }
