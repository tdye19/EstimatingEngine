"""Agent 2: Spec Parser Agent.

Parses CSI MasterFormat Division specs into structured scope items.
Uses LLM parsing when a provider is available; falls back to regex.
"""

import asyncio
import logging
from sqlalchemy.orm import Session
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.agents.tools.spec_tools import (
    regex_parse_spec_sections,
    section_extractor_tool,
    division_mapper_tool,
    keyword_tagger_tool,
    parse_section_parts,
    llm_parse_spec_sections,
)

logger = logging.getLogger("apex.agent.spec_parser")


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running inside an existing event loop (e.g. Jupyter / some test runners)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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


def run_spec_parser_agent(db: Session, project_id: int) -> dict:
    """Parse all spec documents for a project into structured sections.

    Uses LLM-first parsing with regex fallback.
    Returns dict with sections_parsed count, parse_method, and per-doc details.

    Uses Gemini 2.5 Flash for cost optimization — 10x cheaper than Sonnet for
    structured extraction. Upgrade to Sonnet via AGENT_2_PROVIDER=anthropic if
    parsing quality degrades on complex specs.
    """
    # Resolve LLM provider once for this run (Agent 2 routes to Gemini 2.5 Flash)
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
