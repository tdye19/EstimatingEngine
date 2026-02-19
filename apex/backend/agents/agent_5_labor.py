"""Agent 5: Labor Productivity Agent.

Applies historical labor productivity data to takeoff quantities
to produce labor hour estimates.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.agents.tools.labor_tools import (
    productivity_lookup_tool,
    crew_config_tool,
    duration_calculator_tool,
)

logger = logging.getLogger("apex.agent.labor")


def run_labor_agent(db: Session, project_id: int) -> dict:
    """Apply productivity rates to takeoff items and generate labor estimates.

    Returns dict with estimates_created count and total labor cost.
    """
    takeoff_items = db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id,
        TakeoffItem.is_deleted == False,  # noqa: E712
    ).all()

    estimates_created = 0
    total_labor_cost = 0.0
    total_labor_hours = 0.0
    item_results = []

    for item in takeoff_items:
        try:
            # Look up productivity rate
            prod = productivity_lookup_tool(db, item.csi_code)

            # Get crew configuration
            crew = crew_config_tool(prod["crew_type"])

            # Calculate duration
            duration = duration_calculator_tool(
                quantity=item.quantity,
                rate=prod["rate"],
                crew_size=crew["size"],
            )

            labor_cost = duration["total_man_hours"] * crew["hourly_rate"]

            # Create labor estimate
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
            total_labor_cost += labor_cost
            total_labor_hours += duration["total_man_hours"]

            item_results.append({
                "takeoff_item_id": item.id,
                "csi_code": item.csi_code,
                "quantity": item.quantity,
                "rate": prod["rate"],
                "crew_type": prod["crew_type"],
                "labor_hours": duration["labor_hours"],
                "labor_cost": round(labor_cost, 2),
                "confidence": prod["confidence"],
            })

        except Exception as e:
            logger.error(f"Failed labor estimate for takeoff item {item.id}: {e}")
            item_results.append({
                "takeoff_item_id": item.id,
                "csi_code": item.csi_code,
                "error": str(e),
            })

    db.commit()

    return {
        "estimates_created": estimates_created,
        "total_labor_cost": round(total_labor_cost, 2),
        "total_labor_hours": round(total_labor_hours, 2),
        "items_processed": len(takeoff_items),
        "results": item_results,
    }
