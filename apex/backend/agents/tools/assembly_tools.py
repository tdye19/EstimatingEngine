"""Estimate assembly tools for Agent 6."""

import re
import logging

logger = logging.getLogger("apex.tools.assembly")


def cost_rollup_tool(line_items: list[dict]) -> dict:
    """Roll up costs by division from line items.

    Args:
        line_items: list of dicts with division_number, labor_cost, material_cost, etc.

    Returns:
        dict with total costs and per-division breakdown
    """
    by_division = {}
    totals = {
        "total_labor": 0.0,
        "total_material": 0.0,
        "total_equipment": 0.0,
        "total_subcontractor": 0.0,
        "total_direct": 0.0,
    }

    for item in line_items:
        div = item.get("division_number", "00")
        labor = item.get("labor_cost", 0) or 0
        material = item.get("material_cost", 0) or 0
        equipment = item.get("equipment_cost", 0) or 0
        sub = item.get("subcontractor_cost", 0) or 0
        total = labor + material + equipment + sub

        if div not in by_division:
            by_division[div] = {
                "division_number": div,
                "labor_cost": 0,
                "material_cost": 0,
                "equipment_cost": 0,
                "subcontractor_cost": 0,
                "total_cost": 0,
                "item_count": 0,
            }

        by_division[div]["labor_cost"] += labor
        by_division[div]["material_cost"] += material
        by_division[div]["equipment_cost"] += equipment
        by_division[div]["subcontractor_cost"] += sub
        by_division[div]["total_cost"] += total
        by_division[div]["item_count"] += 1

        totals["total_labor"] += labor
        totals["total_material"] += material
        totals["total_equipment"] += equipment
        totals["total_subcontractor"] += sub
        totals["total_direct"] += total

    return {
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "by_division": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in by_division.items()},
    }


def markup_applier_tool(
    direct_cost: float,
    overhead_pct: float = 10.0,
    profit_pct: float = 8.0,
    contingency_pct: float = 5.0,
    gc_markup_pct: float = 0.0,
) -> dict:
    """Apply markups to direct cost.

    Returns dict with all amounts and total bid.
    """
    gc_markup = direct_cost * (gc_markup_pct / 100)
    subtotal_1 = direct_cost + gc_markup

    overhead = subtotal_1 * (overhead_pct / 100)
    subtotal_2 = subtotal_1 + overhead

    profit = subtotal_2 * (profit_pct / 100)
    subtotal_3 = subtotal_2 + profit

    contingency = subtotal_3 * (contingency_pct / 100)
    total_bid = subtotal_3 + contingency

    return {
        "direct_cost": round(direct_cost, 2),
        "gc_markup_pct": gc_markup_pct,
        "gc_markup_amount": round(gc_markup, 2),
        "overhead_pct": overhead_pct,
        "overhead_amount": round(overhead, 2),
        "profit_pct": profit_pct,
        "profit_amount": round(profit, 2),
        "contingency_pct": contingency_pct,
        "contingency_amount": round(contingency, 2),
        "total_bid_amount": round(total_bid, 2),
    }


def exclusion_generator_tool(parsed_sections: list[dict], project_type: str = "commercial") -> list[str]:
    """Generate standard exclusions based on what's NOT in the parsed specs."""
    standard_exclusions = [
        "Hazardous material abatement and disposal",
        "Overtime and shift premiums unless specifically noted",
        "Permits and fees by Owner unless noted",
        "Testing and inspection services by Owner",
        "Furniture, fixtures, and equipment (FF&E) unless noted",
        "Security and temporary fencing beyond standard requirements",
    ]

    # Check for missing major divisions and add exclusions
    divisions_present = set(s.get("division_number", "") for s in parsed_sections)

    if "21" not in divisions_present:
        standard_exclusions.append("Fire suppression systems (Division 21)")
    if "22" not in divisions_present:
        standard_exclusions.append("Plumbing systems (Division 22)")
    if "23" not in divisions_present:
        standard_exclusions.append("HVAC systems (Division 23)")
    if "26" not in divisions_present:
        standard_exclusions.append("Electrical systems (Division 26)")
    if "31" not in divisions_present:
        standard_exclusions.append("Earthwork and site grading (Division 31)")
    if "32" not in divisions_present:
        standard_exclusions.append("Exterior improvements and paving (Division 32)")

    return standard_exclusions


def assumption_logger_tool(project_data: dict) -> list[str]:
    """Generate standard assumptions for the estimate."""
    assumptions = [
        "Work performed during normal business hours (7AM-3:30PM, M-F)",
        "Site access and staging area provided by Owner",
        "Adequate power and water available on site",
        "No soil remediation or environmental issues",
        "All dimensions verified from construction documents",
        "Subcontractor pricing based on competitive bid market",
        "Material pricing valid for 30 days from estimate date",
        "Quantities based on plan takeoff; field verification recommended",
    ]

    project_type = project_data.get("project_type", "commercial")
    if project_type == "healthcare":
        assumptions.append("ICRA/ILSM protocols included in overhead")
        assumptions.append("After-hours work for occupied facility areas")
    elif project_type == "industrial":
        assumptions.append("No special industrial hygiene requirements beyond OSHA standards")

    return assumptions
