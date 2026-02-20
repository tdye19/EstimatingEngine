"""Agent 2: Spec Parser Agent.

Parses CSI MasterFormat Division specs into structured scope items.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.agents.tools.spec_tools import (
    section_extractor_tool,
    division_mapper_tool,
    keyword_tagger_tool,
    parse_section_parts,
)

logger = logging.getLogger("apex.agent.spec_parser")


def run_spec_parser_agent(db: Session, project_id: int) -> dict:
    """Parse all spec documents for a project into structured sections.

    Returns dict with sections_parsed count and details.
    """
    # Get all completed spec documents
    documents = db.query(Document).filter(
        Document.project_id == project_id,
        Document.processing_status == "completed",
        Document.classification == "spec",
        Document.is_deleted == False,  # noqa: E712
    ).all()

    # Also include unclassified documents (they might contain specs)
    general_docs = db.query(Document).filter(
        Document.project_id == project_id,
        Document.processing_status == "completed",
        Document.classification.in_(["general", None]),
        Document.is_deleted == False,  # noqa: E712
    ).all()

    all_docs = documents + general_docs
    total_sections = 0
    doc_results = []

    for doc in all_docs:
        if not doc.raw_text:
            continue

        try:
            # Extract CSI sections from raw text
            extracted = section_extractor_tool(doc.raw_text)

            sections_created = 0
            for section_data in extracted:
                div_info = division_mapper_tool(section_data["section_number"])
                keywords = keyword_tagger_tool(section_data.get("content", ""))
                parts = parse_section_parts(section_data.get("content", ""))

                spec_section = SpecSection(
                    project_id=project_id,
                    document_id=doc.id,
                    division_number=div_info["division_number"],
                    section_number=section_data["section_number"],
                    title=section_data["title"],
                    work_description=parts["work_description"],
                    materials_referenced=parts["materials_referenced"],
                    execution_requirements=parts["execution_requirements"],
                    submittal_requirements=parts["submittal_requirements"],
                    keywords=keywords,
                    raw_text=section_data.get("content", "")[:5000],
                )
                db.add(spec_section)
                sections_created += 1

            db.commit()
            total_sections += sections_created

            # Reclassify document as spec if it had sections
            if sections_created > 0 and doc.classification != "spec":
                doc.classification = "spec"
                db.commit()

            doc_results.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "sections_found": sections_created,
                "status": "success",
            })

        except Exception as e:
            logger.error(f"Failed to parse document {doc.id}: {e}")
            doc_results.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "sections_found": 0,
                "status": "error",
                "error": str(e),
            })

    return {
        "sections_parsed": total_sections,
        "documents_processed": len(all_docs),
        "results": doc_results,
    }
