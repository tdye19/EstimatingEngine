"""Agent 4: Quantity Takeoff Agent.

Extracts measurable quantities from scope descriptions and drawing references.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.takeoff_tools import (
    quantity_calculator_tool,
    drawing_reference_linker_tool,
)

logger = logging.getLogger("apex.agent.takeoff")


def run_takeoff_agent(db: Session, project_id: int) -> dict:
    """Generate quantity takeoff items from parsed spec sections.

    Returns dict with items_created count and details.
    """
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).all()

    items_created = 0
    section_results = []

    for section in sections:
        try:
            # Combine work description and execution requirements for quantity extraction
            text_to_parse = ""
            if section.work_description:
                text_to_parse += section.work_description + "\n"
            if section.execution_requirements:
                text_to_parse += section.execution_requirements + "\n"
            if section.raw_text and not text_to_parse.strip():
                text_to_parse = section.raw_text

            if not text_to_parse.strip():
                continue

            # Extract quantities
            qty_result = quantity_calculator_tool(text_to_parse)

            # Extract drawing references
            drawing_refs = drawing_reference_linker_tool(text_to_parse)

            # Create takeoff item
            takeoff = TakeoffItem(
                project_id=project_id,
                spec_section_id=section.id,
                csi_code=section.section_number,
                description=f"{section.title} - {qty_result['description'][:200]}",
                quantity=qty_result["quantity"],
                unit_of_measure=qty_result["unit"],
                drawing_reference=", ".join(drawing_refs) if drawing_refs else None,
                confidence=qty_result["confidence"],
            )
            db.add(takeoff)
            items_created += 1

            section_results.append({
                "section_id": section.id,
                "section_number": section.section_number,
                "quantity": qty_result["quantity"],
                "unit": qty_result["unit"],
                "confidence": qty_result["confidence"],
                "drawings": drawing_refs,
            })

        except Exception as e:
            logger.error(f"Failed takeoff for section {section.id}: {e}")
            section_results.append({
                "section_id": section.id,
                "section_number": section.section_number,
                "error": str(e),
            })

    db.commit()

    return validate_agent_output(4, {
        "items_created": items_created,
        "sections_processed": len(sections),
        "results": section_results,
    })
