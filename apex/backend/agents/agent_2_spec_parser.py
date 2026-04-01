"""Agent 2: Spec Parser Agent (v2 — parameter extraction, no quantities).

Parses CSI MasterFormat specs to identify in-scope divisions and extract
material specifications, quality requirements, and referenced standards.
Does NOT extract quantities — those come from drawings, not specs.

Uses LLM parsing when a provider is available; falls back to regex.
"""

import json
import logging
from sqlalchemy.orm import Session
from apex.backend.utils.async_helper import run_async as _run_async
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.agents.tools.spec_tools import (
    regex_parse_spec_sections,
    division_mapper_tool,
    keyword_tagger_tool,
    llm_parse_spec_sections,
)

logger = logging.getLogger("apex.agent.spec_parser")


def _parse_document(
    doc_text: str, use_llm: bool, provider
) -> tuple[list[dict], str, int, int]:
    """Return (extracted_sections, parse_method, input_tokens, output_tokens)."""
    if use_llm and provider is not None:
        try:
            sections, in_tok, out_tok = _run_async(llm_parse_spec_sections(doc_text, provider))
            return sections, "llm", in_tok, out_tok
        except Exception as e:
            logger.warning(f"LLM parse failed, falling back to regex: {e}")

    return regex_parse_spec_sections(doc_text), "regex", 0, 0


def _build_work_description(section_data: dict) -> str:
    """Build a work_description string from v2 spec parameters for downstream agents."""
    parts = []
    title = section_data.get("title", "")
    if title:
        parts.append(title)

    mat = section_data.get("material_specs", {})
    if mat:
        # Flatten material specs into readable lines
        for k, v in mat.items():
            if isinstance(v, list):
                parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            elif isinstance(v, bool):
                parts.append(f"{k}: {'Yes' if v else 'No'}")
            elif v is not None:
                parts.append(f"{k}: {v}")

    quals = section_data.get("quality_requirements", [])
    if quals:
        parts.append("Quality: " + "; ".join(quals[:5]))

    return "\n".join(parts) if parts else ""


def run_spec_parser_agent(db: Session, project_id: int) -> dict:
    """Parse all spec documents for a project into structured sections.

    v2: Extracts spec parameters (materials, quality, standards) — not quantities.
    Uses LLM-first parsing with regex fallback.
    Returns dict with sections_parsed count, parse_method, and per-doc details.

    Uses Gemini 2.5 Flash (via OpenRouter) for cost optimization — 10x cheaper
    than Sonnet for structured extraction. Upgrade to Sonnet via
    AGENT_2_PROVIDER=anthropic if parsing quality degrades on complex specs.
    Also supports direct Gemini API via AGENT_2_PROVIDER=gemini.
    """
    # Resolve LLM provider once for this run (Agent 2 defaults to Gemini via OpenRouter)
    provider = None
    llm_available = False
    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider(agent_number=2)
        llm_available = _run_async(provider.health_check())
        if llm_available:
            logger.info(f"LLM provider '{provider.provider_name}' is available — using LLM parsing")
        else:
            logger.info(f"LLM provider '{provider.provider_name}' is not reachable — using regex fallback")
    except Exception as e:
        logger.warning(f"Could not initialise LLM provider ({e}), using regex fallback")

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
    run_parse_methods: list[str] = []

    for doc in all_docs:
        if not doc.raw_text:
            continue

        try:
            extracted, parse_method, in_tok, out_tok = _parse_document(
                doc.raw_text, llm_available, provider
            )
            run_parse_methods.append(parse_method)
            if parse_method == "llm" and provider is not None and (in_tok or out_tok):
                log_token_usage(
                    db=db,
                    project_id=project_id,
                    agent_number=2,
                    provider=provider.provider_name,
                    model=provider.model_name,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )

            sections_created = 0
            for section_data in extracted:
                div_info = division_mapper_tool(section_data["section_number"])

                # Build backward-compatible fields from v2 data so Agents 3/4 still work
                work_desc = _build_work_description(section_data)
                raw_content = section_data.get("raw_content", "")

                # Extract keywords from work description + raw content
                keywords = keyword_tagger_tool(work_desc + " " + raw_content)

                # Referenced standards serve as materials_referenced for backward compat
                standards = section_data.get("referenced_standards", [])
                submittals = section_data.get("submittals_required", [])

                spec_section = SpecSection(
                    project_id=project_id,
                    document_id=doc.id,
                    division_number=div_info["division_number"],
                    section_number=section_data["section_number"],
                    title=section_data.get("title", ""),
                    # Backward-compatible fields (Agents 3/4 read these)
                    work_description=work_desc,
                    materials_referenced=standards,
                    execution_requirements="",
                    submittal_requirements="\n".join(submittals) if submittals else "",
                    keywords=keywords,
                    raw_text=raw_content[:5000] if raw_content else "",
                    # v2 spec parameter fields
                    in_scope=section_data.get("in_scope", True),
                    material_specs=section_data.get("material_specs", {}),
                    quality_requirements=section_data.get("quality_requirements", []),
                    referenced_standards=standards,
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
                "parse_method": parse_method,
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

    # Overall parse method: "llm" if any doc used LLM, else "regex"
    overall_parse_method = "llm" if "llm" in run_parse_methods else "regex"
    logger.info(f"Agent 2 complete: {total_sections} sections parsed via {overall_parse_method}")

    return validate_agent_output(2, {
        "sections_parsed": total_sections,
        "documents_processed": len(all_docs),
        "parse_method": overall_parse_method,
        "results": doc_results,
    })
