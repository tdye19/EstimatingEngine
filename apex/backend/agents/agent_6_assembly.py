"""Agent 6: Estimate Assembly Agent.

Assembles all components into a structured bid estimate.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.project import Project
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.assembly_tools import (
    cost_rollup_tool,
    markup_applier_tool,
    exclusion_generator_tool,
    assumption_logger_tool,
)

logger = logging.getLogger("apex.agent.assembly")


def run_assembly_agent(db: Session, project_id: int) -> dict:
    """Assemble the full bid estimate from all components.

    Returns dict with estimate details.
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
        div_num = labor.csi_code[:2].strip()

        # Look up material cost
        mat = material_map.get(labor.csi_code)
        material_cost = 0.0
        if mat:
            material_cost = mat.unit_cost * labor.quantity

        # Equipment estimate (typically 5-15% of labor for heavy divisions)
        equipment_pct = 0.10 if div_num in ("03", "05", "31") else 0.05
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

    return validate_agent_output(6, {
        "estimate_id": estimate.id,
        "version": estimate.version,
        "total_direct_cost": estimate.total_direct_cost,
        "total_bid_amount": estimate.total_bid_amount,
        "line_items_count": len(line_items_data),
        "divisions_covered": list(rollup["by_division"].keys()),
        "bid_bond_required": bool(bid_bond),
    })
