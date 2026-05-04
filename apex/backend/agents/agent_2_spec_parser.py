"""Agent 2: Spec Parser Agent (v2 — parameter extraction, no quantities).

Parses CSI MasterFormat specs to identify in-scope divisions and extract
material specifications, quality requirements, and referenced standards.
Does NOT extract quantities — those come from drawings, not specs.

Uses LLM parsing only — no regex fallback. If the provider is unavailable
or the LLM response is invalid, the agent raises and halts the pipeline.
Regex fallback has been removed: it produces structurally plausible but
semantically wrong SpecSection rows that silently poison downstream agents.
"""

import logging
import time
from collections import Counter

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.spec_tools import (
    division_mapper_tool,
    keyword_tagger_tool,
    llm_parse_spec_sections,
)
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.services.assembly_parameter_extractor import (
    extract_assembly_parameters,
    is_division_03_section,
)
from apex.backend.services.llm_provider import LLMProviderBillingError
from apex.backend.services.token_tracker import TokenBudgetExceeded, log_token_usage
from apex.backend.services.ws_manager import ws_manager
from apex.backend.utils.async_helper import run_async as _run_async

logger = logging.getLogger("apex.agent.spec_parser")


class Agent2ProviderUnavailableError(RuntimeError):
    """Raised when Agent 2's LLM provider cannot be initialised or fails health check.

    Pipeline must halt — regex fallback is not permitted because it produces
    structurally plausible but semantically wrong SpecSection rows.
    """


class Agent2LLMParseFailure(RuntimeError):
    """Raised when the LLM returns an invalid or unparseable response during spec parsing.

    Distinct from LLMProviderBillingError (billing) and
    Agent2ProviderUnavailableError (connectivity). Indicates the provider
    was reachable but its output failed validation or JSON extraction.
    """


def _parse_document(doc_text: str, provider) -> tuple[list[dict], str, int, int]:
    """Return (extracted_sections, parse_method, input_tokens, output_tokens).

    LLM-only path. Raises Agent2LLMParseFailure if the provider returns an
    invalid or unparseable response. Raises LLMProviderBillingError on 402.
    Regex fallback has been removed — caller must handle failure explicitly.
    """
    try:
        sections, in_tok, out_tok = _run_async(llm_parse_spec_sections(doc_text, provider))
        return sections, "llm", in_tok, out_tok
    except LLMProviderBillingError:
        raise
    except Exception as e:
        raise Agent2LLMParseFailure(
            f"LLM spec parse failed: {e}"
        ) from e


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


def _upsert_spec_section(
    db: Session,
    *,
    project_id: int,
    doc_id: int,
    section_data: dict,
    division_number: str,
    work_desc: str,
    keywords: list[str],
    standards: list[str],
    submittals: list[str],
    raw_content: str,
) -> str:
    """Upsert one SpecSection row keyed on (project_id, section_number).

    Returns one of: "new", "replaced", "skipped", "error".

    Longest-content-wins policy on work_description — HF-21 (Sprint 18.3.0).
    Caller is responsible for the outer db.commit() per-doc; this helper
    flushes after INSERT so the unique-constraint race window is tiny.
    """
    section_number = section_data["section_number"]

    def _apply_fields(row: "SpecSection") -> None:
        row.document_id = doc_id
        row.division_number = division_number
        row.title = section_data.get("title", "")
        row.work_description = work_desc
        row.materials_referenced = standards
        row.execution_requirements = ""
        row.submittal_requirements = "\n".join(submittals) if submittals else ""
        row.keywords = keywords
        row.raw_text = raw_content[:5000] if raw_content else ""
        row.in_scope = section_data.get("in_scope", True)
        row.material_specs = section_data.get("material_specs", {})
        row.quality_requirements = section_data.get("quality_requirements", [])
        row.referenced_standards = standards

    existing = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.section_number == section_number,
        )
        .first()
    )

    if existing is None:
        row = SpecSection(project_id=project_id, section_number=section_number)
        _apply_fields(row)
        db.add(row)
        try:
            db.flush()
            return "new"
        except IntegrityError:
            # Race: another session inserted the same (project_id, section_number)
            # between our SELECT and INSERT. Rollback and fall through to the
            # update branch using the row that won the race.
            db.rollback()
            existing = (
                db.query(SpecSection)
                .filter(
                    SpecSection.project_id == project_id,
                    SpecSection.section_number == section_number,
                )
                .first()
            )
            if existing is None:
                # Vanishingly unlikely: the racing transaction rolled back.
                # One retry only — do not loop.
                row = SpecSection(
                    project_id=project_id, section_number=section_number
                )
                _apply_fields(row)
                db.add(row)
                db.flush()
                return "new"

    # existing is set, either from the initial query or from the race branch.
    if len(work_desc or "") > len(existing.work_description or ""):
        _apply_fields(existing)
        return "replaced"
    return "skipped"


def _enrich_division_03_parameters(
    db: Session,
    project_id: int,
    use_llm: bool = True,
) -> dict:
    """Run assembly parameter extraction on all Division 03 sections.

    Post-parse enrichment phase (Sprint 18.2.3). Called after SpecSection
    rows are committed. Each Division 03 section gets one LLM call for
    parameter extraction. Per-section failures are captured in warnings —
    never re-raised — so downstream agents keep running.

    Returns an AssemblyParameterEnrichment-shaped dict.
    """
    start = time.monotonic()
    warnings: list[str] = []
    extraction_methods: dict[str, int] = {}
    enriched = 0

    all_sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    div_03_sections = [s for s in all_sections if is_division_03_section(s.section_number)]
    total = len(div_03_sections)

    if total == 0:
        return {
            "division_03_count": 0,
            "enriched": 0,
            "extraction_methods": {},
            "warnings": [],
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    ws_manager.broadcast_sync(
        project_id,
        {
            "type": "assembly_params_update",
            "project_id": project_id,
            "status": "running",
            "message": f"Extracting assembly parameters from {total} concrete sections...",
            "progress": {"current": 0, "total": total},
        },
    )

    for idx, section in enumerate(div_03_sections, start=1):
        # HF-20: Sprint 18.2.3 read raw_text, but the v2 LLM parser
        # (llm_parse_spec_sections) populates work_description and leaves
        # raw_text empty. work_description is the authoritative per-section
        # content field today. raw_text is kept as a secondary fallback for
        # any alternate parse path (e.g., regex) that might populate it.
        text = (section.work_description or section.raw_text or "").strip()
        if not text:
            warnings.append(
                f"Section {section.section_number} (id={section.id}) "
                f"has empty work_description and raw_text; skipped."
            )
        else:
            try:
                result = extract_assembly_parameters(
                    text,
                    csi_code=section.section_number,
                    use_llm=use_llm,
                )
                # Persist only the schema documented in spec_section.py.
                # warnings + source_text_length are runtime data, not stored.
                section.assembly_parameters_json = {
                    "parameters": result["parameters"],
                    "extracted_at": result["extracted_at"],
                    "extraction_method": result["extraction_method"],
                }
                method = result["extraction_method"]
                extraction_methods[method] = extraction_methods.get(method, 0) + 1
                enriched += 1

                for w in result.get("warnings", []):
                    warnings.append(f"[{section.section_number}] {w}")

            except LLMProviderBillingError:
                raise
            except Exception as exc:
                # Non-swallow: one section's failure never blocks the rest.
                warnings.append(f"Extraction failed for section {section.section_number} " f"(id={section.id}): {exc}")
                logger.exception(
                    "Assembly parameter extraction failed for section %d",
                    section.id,
                )

        ws_manager.broadcast_sync(
            project_id,
            {
                "type": "assembly_params_update",
                "project_id": project_id,
                "status": "running",
                "message": f"Enriched {idx}/{total}: {section.section_number}",
                "progress": {"current": idx, "total": total},
            },
        )

    db.commit()

    duration_ms = (time.monotonic() - start) * 1000
    ws_manager.broadcast_sync(
        project_id,
        {
            "type": "assembly_params_update",
            "project_id": project_id,
            "status": "complete",
            "message": (f"Parameter extraction complete: {enriched}/{total} sections enriched."),
            "progress": {"current": total, "total": total},
        },
    )

    return {
        "division_03_count": total,
        "enriched": enriched,
        "extraction_methods": extraction_methods,
        "warnings": warnings,
        "duration_ms": duration_ms,
    }


def run_spec_parser_agent(db: Session, project_id: int) -> dict:
    """Parse all spec documents for a project into structured sections.

    v2: Extracts spec parameters (materials, quality, standards) — not quantities.
    LLM parsing only — no regex fallback. Raises Agent2ProviderUnavailableError
    if the provider cannot be reached; raises Agent2LLMParseFailure if the LLM
    response cannot be parsed. Either exception halts the pipeline.

    Uses Gemini 2.5 Flash (via OpenRouter) for cost optimization — 10x cheaper
    than Sonnet for structured extraction. Upgrade to Sonnet via
    AGENT_2_PROVIDER=anthropic if parsing quality degrades on complex specs.
    Also supports direct Gemini API via AGENT_2_PROVIDER=gemini.
    """
    # Resolve LLM provider once for this run (Agent 2 defaults to Gemini via OpenRouter).
    # Hard-fail if provider unavailable — no regex fallback is permitted.
    try:
        from apex.backend.services.llm_provider import get_llm_provider

        provider = get_llm_provider(agent_number=2)
        llm_available = _run_async(provider.health_check())
        if not llm_available:
            raise Agent2ProviderUnavailableError(
                f"LLM provider '{provider.provider_name}' failed health check — "
                "spec parsing requires LLM and cannot fall back to regex"
            )
        logger.info(f"LLM provider '{provider.provider_name}' is available — using LLM parsing")
    except (Agent2ProviderUnavailableError, LLMProviderBillingError):
        raise
    except Exception as e:
        raise Agent2ProviderUnavailableError(
            f"Could not initialise LLM provider: {e}"
        ) from e

    # HF-26: clean-slate per project. Without this, SpecSection rows from
    # earlier code paths (or from previously-misclassified docs) accumulate
    # forever — _upsert_spec_section dedupes on (project_id, section_number)
    # but never deletes orphans, so re-triggers can grow the count but
    # never shrink it. Mirrors Agent 3.5's delete-then-insert contract.
    db.query(SpecSection).filter(SpecSection.project_id == project_id).delete(
        synchronize_session=False
    )
    db.commit()

    # Load all completed documents, then accept only spec-classified ones.
    # work_scope / drawing / general / addendum / schedule each have dedicated
    # agents; processing them here wastes tokens and triggers spurious
    # section-validator warnings (e.g. non-CSI numbers like "03A", "26 ALL").
    _candidate_docs = (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
            Document.processing_status == "completed",
            Document.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    all_docs = [d for d in _candidate_docs if d.classification == "spec"]

    _skip_counts: Counter[str] = Counter(
        d.classification or "unclassified"
        for d in _candidate_docs
        if d.classification != "spec"
    )
    _spec_count = len(all_docs)
    if _skip_counts:
        _skip_parts = ", ".join(
            f"{n} {cls} skipped" for cls, n in sorted(_skip_counts.items())
        )
        logger.info(
            "Agent 2: filtered input — %d spec docs accepted, %s",
            _spec_count,
            _skip_parts,
        )
    else:
        logger.info(
            "Agent 2: filtered input — %d spec docs accepted, none skipped",
            _spec_count,
        )

    total_docs = len(all_docs)
    total_sections = 0
    doc_results = []
    run_parse_methods: list[str] = []
    # HF-21 upsert counters — surfaced in output_data for AgentRunLog observability.
    upsert_new = 0
    upsert_replaced = 0
    upsert_skipped = 0
    upsert_errors = 0
    upsert_warnings: list[str] = []

    try:
        for doc_idx, doc in enumerate(all_docs):
            if not doc.raw_text:
                continue

            try:
                extracted, parse_method, in_tok, out_tok = _parse_document(doc.raw_text, provider)
                run_parse_methods.append(parse_method)
                if in_tok or out_tok:
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

                    try:
                        outcome = _upsert_spec_section(
                            db,
                            project_id=project_id,
                            doc_id=doc.id,
                            section_data=section_data,
                            division_number=div_info["division_number"],
                            work_desc=work_desc,
                            keywords=keywords,
                            standards=standards,
                            submittals=submittals,
                            raw_content=raw_content,
                        )
                    except Exception as exc:
                        upsert_errors += 1
                        upsert_warnings.append(
                            f"Upsert failed for {section_data.get('section_number')} "
                            f"(doc {doc.id}): {exc}"
                        )
                        logger.exception(
                            "SpecSection upsert failed for %s on doc %d",
                            section_data.get("section_number"),
                            doc.id,
                        )
                        continue

                    if outcome == "new":
                        upsert_new += 1
                        sections_created += 1
                    elif outcome == "replaced":
                        upsert_replaced += 1
                        sections_created += 1
                    else:  # "skipped"
                        upsert_skipped += 1

                db.commit()
                total_sections += sections_created

                # HF-26: removed self-promotion. Documents retain their Agent 1
                # classification. The general/None secondary filter above gives
                # unclassified docs a chance on every run; permanent re-classification
                # to "spec" was creating a feedback loop where any non-spec doc
                # (e.g., winest.xlsx) that yielded a single section-shaped fragment
                # got locked into the spec pool forever.

                doc_results.append(
                    {
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "sections_found": sections_created,
                        "parse_method": parse_method,
                        "status": "success",
                    }
                )

            except TokenBudgetExceeded as exc:
                docs_remaining = total_docs - doc_idx - 1
                logger.error(
                    "Budget exceeded on document %r (doc %d/%d); %d document(s) remain unprocessed: %s",
                    doc.filename,
                    doc_idx + 1,
                    total_docs,
                    docs_remaining,
                    exc,
                )
                raise TokenBudgetExceeded(
                    exc.project_id,
                    exc.tokens_used,
                    exc.cost_used,
                    document_name=doc.filename,
                    docs_remaining=docs_remaining,
                ) from exc

            except LLMProviderBillingError:
                raise

            except Agent2LLMParseFailure:
                raise

            except Exception as e:
                logger.error(f"Failed to process document {doc.id}: {e}")
                doc_results.append(
                    {
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "sections_found": 0,
                        "status": "error",
                        "error": str(e),
                    }
                )

    except (Agent2LLMParseFailure, Agent2ProviderUnavailableError) as exc:
        # Hard failure — remove any partial SpecSection rows so downstream
        # agents never consume incomplete or missing-doc data from this run.
        logger.error(
            "Agent 2 hard failure — removing partial SpecSection rows for project %d: %s",
            project_id,
            exc,
        )
        db.query(SpecSection).filter(SpecSection.project_id == project_id).delete(
            synchronize_session=False
        )
        db.commit()
        raise

    # Overall parse method: "llm" if any doc used LLM, else "regex"
    overall_parse_method = "llm" if "llm" in run_parse_methods else "regex"
    logger.info(f"Agent 2 complete: {total_sections} sections parsed via {overall_parse_method}")

    # HF-21 observability — one summary line per run; individual errors were
    # already appended to upsert_warnings at the point of failure.
    if upsert_replaced or upsert_new or upsert_skipped:
        summary = (
            f"Upserted {upsert_replaced} existing sections; "
            f"inserted {upsert_new} new; skipped {upsert_skipped} shorter duplicates"
        )
        logger.info("Agent 2 dedup: %s", summary)
        upsert_warnings.append(summary)

    # Sprint 18.2.3: Division 03 assembly parameter enrichment.
    # Defense in depth — enrichment must never break Agent 2's existing contract.
    try:
        enrichment_result = _enrich_division_03_parameters(db, project_id, use_llm=True)
    except LLMProviderBillingError:
        raise
    except Exception as exc:
        logger.exception("Assembly parameter enrichment phase failed wholesale")
        enrichment_result = {
            "division_03_count": 0,
            "enriched": 0,
            "extraction_methods": {},
            "warnings": [f"Enrichment phase crashed: {exc}"],
            "duration_ms": 0.0,
        }

    return validate_agent_output(
        2,
        {
            "sections_parsed": total_sections,
            "documents_processed": len(all_docs),
            "parse_method": overall_parse_method,
            "results": doc_results,
            "assembly_parameters": enrichment_result,
            "dedup": {
                "inserted": upsert_new,
                "replaced": upsert_replaced,
                "skipped": upsert_skipped,
                "errors": upsert_errors,
                "warnings": upsert_warnings,
            },
        },
    )
