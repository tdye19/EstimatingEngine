"""IMPROVE feedback tools for Agent 7."""

import logging

from sqlalchemy.orm import Session

from apex.backend.models.productivity_history import ProductivityHistory

logger = logging.getLogger("apex.tools.improve")


def actual_importer_tool(rows: list[dict]) -> list[dict]:
    """Validate and normalize imported actual data rows.

    Expected row keys: csi_code, description, actual_quantity, actual_labor_hours, actual_cost
    Returns cleaned rows.
    """
    cleaned = []
    for row in rows:
        csi = row.get("csi_code", "").strip()
        if not csi:
            continue

        cleaned.append(
            {
                "csi_code": csi,
                "description": row.get("description", ""),
                "actual_quantity": float(row.get("actual_quantity", 0) or 0),
                "actual_labor_hours": float(row.get("actual_labor_hours", 0) or 0),
                "actual_cost": float(row.get("actual_cost", 0) or 0),
                "crew_type": row.get("crew_type", ""),
                "work_type": row.get("work_type", ""),
            }
        )
    return cleaned


def variance_calculator_tool(estimate_items: list[dict], actual_items: list[dict]) -> list[dict]:
    """Calculate variance between estimated and actual values.

    Returns list of variance items with hours/cost variance and percentage.
    """
    # Build lookup by CSI code
    estimate_map = {}
    for item in estimate_items:
        csi = item.get("csi_code", "")
        if csi not in estimate_map:
            estimate_map[csi] = item
        else:
            # Merge quantities
            estimate_map[csi]["estimated_quantity"] = estimate_map[csi].get("estimated_quantity", 0) + item.get(
                "estimated_quantity", 0
            )
            estimate_map[csi]["estimated_labor_hours"] = estimate_map[csi].get("estimated_labor_hours", 0) + item.get(
                "estimated_labor_hours", 0
            )
            estimate_map[csi]["estimated_cost"] = estimate_map[csi].get("estimated_cost", 0) + item.get(
                "estimated_cost", 0
            )

    variances = []
    for actual in actual_items:
        csi = actual.get("csi_code", "")
        est = estimate_map.get(csi, {})

        est_hours = est.get("estimated_labor_hours", 0) or 0
        act_hours = actual.get("actual_labor_hours", 0) or 0
        est_cost = est.get("estimated_cost", 0) or 0
        act_cost = actual.get("actual_cost", 0) or 0
        est_qty = est.get("estimated_quantity", 0) or 0
        act_qty = actual.get("actual_quantity", 0) or 0

        var_hours = act_hours - est_hours
        var_cost = act_cost - est_cost
        var_pct = ((act_cost - est_cost) / est_cost * 100) if est_cost else 0

        variances.append(
            {
                "csi_code": csi,
                "description": actual.get("description", est.get("description", "")),
                "estimated_quantity": est_qty,
                "actual_quantity": act_qty,
                "estimated_labor_hours": est_hours,
                "actual_labor_hours": act_hours,
                "estimated_cost": est_cost,
                "actual_cost": act_cost,
                "variance_hours": round(var_hours, 2),
                "variance_cost": round(var_cost, 2),
                "variance_pct": round(var_pct, 2),
            }
        )

    return variances


def productivity_updater_tool(
    db: Session,
    csi_code: str,
    actual_rate: float,
    unit_of_measure: str,
    work_type: str,
    crew_type: str = None,
    source_project: str = None,
    source_project_id: int = None,
) -> dict:
    """Update productivity history with new actual data.

    Computes weighted average with existing data.
    """
    existing = (
        db.query(ProductivityHistory)
        .filter(
            ProductivityHistory.csi_code == csi_code,
            ProductivityHistory.work_type == work_type,
            ProductivityHistory.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    if existing:
        # Calculate new weighted average
        total_samples = sum(r.sample_count for r in existing) + 1
        total_weighted = sum(r.productivity_rate * r.sample_count for r in existing) + actual_rate
        new_avg = total_weighted / total_samples
        new_confidence = min(0.95, 0.5 + total_samples * 0.05)

        # Update the first matching record with new average
        primary = existing[0]
        primary.productivity_rate = round(new_avg, 4)
        primary.sample_count = total_samples
        primary.confidence_score = new_confidence
        db.commit()

        action = "updated"
    else:
        new_avg = actual_rate
        action = "created"

    # Always insert the new actual data point
    new_record = ProductivityHistory(
        csi_code=csi_code,
        work_type=work_type,
        crew_type=crew_type or "General Crew",
        productivity_rate=actual_rate,
        unit_of_measure=unit_of_measure,
        source_project=source_project,
        source_project_id=source_project_id,
        is_actual=1,
        confidence_score=0.8,
        sample_count=1,
    )
    db.add(new_record)
    db.commit()

    return {
        "csi_code": csi_code,
        "action": action,
        "new_weighted_rate": round(new_avg, 4),
        "total_samples": (sum(r.sample_count for r in existing) + 1) if existing else 1,
    }


def trend_analyzer_tool(db: Session, csi_code: str) -> dict:
    """Analyze productivity trends for a CSI code over time."""
    records = (
        db.query(ProductivityHistory)
        .filter(
            ProductivityHistory.csi_code == csi_code,
            ProductivityHistory.is_actual == 1,
            ProductivityHistory.is_deleted == False,  # noqa: E712
        )
        .order_by(ProductivityHistory.created_at)
        .all()
    )

    if not records:
        return {"csi_code": csi_code, "trend": "no_data", "data_points": 0}

    rates = [r.productivity_rate for r in records]

    if len(rates) < 2:
        return {
            "csi_code": csi_code,
            "trend": "insufficient_data",
            "data_points": 1,
            "current_rate": rates[0],
        }

    # Simple trend: compare first half average to second half average
    mid = len(rates) // 2
    first_half = sum(rates[:mid]) / len(rates[:mid])
    second_half = sum(rates[mid:]) / len(rates[mid:])

    if second_half > first_half * 1.05:
        trend = "improving"
    elif second_half < first_half * 0.95:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "csi_code": csi_code,
        "trend": trend,
        "data_points": len(rates),
        "first_half_avg": round(first_half, 4),
        "second_half_avg": round(second_half, 4),
        "current_rate": rates[-1],
        "all_rates": [round(r, 4) for r in rates],
    }
