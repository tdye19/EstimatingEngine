"""Agent 2B - Work Scope Parser orchestration (Sprint 18.1).

Runs after Agent 2 (Spec Parser), before Agent 4 (Rate Match).

Responsibilities:
  1. Iterate all documents for the project.
  2. Run parser.classify_document() on each doc's raw_text.
  3. For docs classified as standalone_work_scope or embedded_work_scope,
     run parser.parse_work_scopes() with LLM path.
  4. Upsert WorkCategory rows keyed on (project_id, wc_number).
  5. Broadcast WebSocket progress (type="work_scope_update").
  6. Return Agent2BOutput contract.

LLM usage is inside the parser service - this agent does not call LLMs
directly. All money math / deterministic logic lives in the parser
(validated in Sprint 18.1.2 + HF-19 + HF-19b). This agent is pure
orchestration + DB persistence + WS broadcast.

Failures bubble up normally (Python exception flow); the orchestrator
wraps this call in try/except so downstream agents keep running.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import (
    Agent2BOutput,
    validate_agent_output,
)
from apex.backend.models.document import Document
from apex.backend.models.work_category import WorkCategory
from apex.backend.services.work_scope_parser import (
    classify_document,
    parse_work_scopes,
)
from apex.backend.services.ws_manager import ws_manager

logger = logging.getLogger("apex.agent.work_scope_parser")


def _broadcast(project_id: int, status: str, message: str) -> None:
    """Push a work_scope_update event to connected WS clients.

    Uses a dedicated `type` so frontend listeners can namespace 2B progress
    separately from the main pipeline_update stream.
    """
    ws_manager.broadcast_sync(
        project_id,
        {
            "type": "work_scope_update",
            "project_id": project_id,
            "agent_number": "2B",
            "agent_name": "Work Scope Parser",
            "status": status,
            "message": message,
        },
    )


def run_work_scope_agent(
    db: Session,
    project_id: int,
    use_llm: bool = True,
) -> dict:
    """Entry point. Matches the shape of run_spec_parser_agent et al."""
    start = time.monotonic()
    warnings: list[str] = []
    parse_methods: dict[str, int] = {"llm": 0, "regex": 0, "regex_fallback": 0}
    classification_summary: dict[str, int] = {
        "standalone_work_scope": 0,
        "embedded_work_scope": 0,
        "no_work_scope": 0,
    }

    docs = (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .filter(Document.is_deleted == False)  # noqa: E712
        .all()
    )

    _broadcast(
        project_id,
        status="running",
        message=f"Scanning {len(docs)} documents for work scope content...",
    )

    created = 0
    updated = 0
    parsed = 0

    for idx, doc in enumerate(docs):
        text = doc.raw_text or ""
        if not text.strip():
            warnings.append(f"Document {doc.id} ({doc.filename}) has empty raw_text; skipped.")
            continue

        classification = classify_document(text, doc.filename)
        classification_summary[classification] = classification_summary.get(classification, 0) + 1

        if classification == "no_work_scope":
            continue

        _broadcast(
            project_id,
            status="running",
            message=f"Parsing work scopes from {doc.filename} ({idx + 1}/{len(docs)})...",
        )

        result = parse_work_scopes(
            text,
            source_document_id=doc.id,
            filename=doc.filename,
            use_llm=use_llm,
        )
        parsed += 1
        warnings.extend(result.get("warnings", []))

        # Per-WC parse method counts (what actually landed on each row)
        for wc_dict in result["work_categories"]:
            method = wc_dict.get("parse_method") or "regex"
            parse_methods[method] = parse_methods.get(method, 0) + 1

        if result.get("parse_method") == "regex_fallback":
            logger.warning(
                "Doc %d (%s) fell back to regex. Reason: %s",
                doc.id,
                doc.filename,
                "; ".join(result.get("warnings", [])[:3]) or "unspecified",
            )

        for wc_dict in result["work_categories"]:
            wc_number = wc_dict["wc_number"]
            persist_fields = {k: v for k, v in wc_dict.items() if k != "project_id"}

            existing = (
                db.query(WorkCategory)
                .filter(WorkCategory.project_id == project_id)
                .filter(WorkCategory.wc_number == wc_number)
                .first()
            )

            if existing is not None:
                for key, value in persist_fields.items():
                    setattr(existing, key, value)
                updated += 1
            else:
                db.add(WorkCategory(project_id=project_id, **persist_fields))
                created += 1

    db.commit()

    duration_ms = (time.monotonic() - start) * 1000

    output_dict = Agent2BOutput(
        project_id=project_id,
        documents_examined=len(docs),
        documents_parsed=parsed,
        work_categories_created=created,
        work_categories_updated=updated,
        parse_methods=parse_methods,
        classification_summary=classification_summary,
        warnings=warnings,
        duration_ms=duration_ms,
    ).model_dump()

    _broadcast(
        project_id,
        status="complete",
        message=(
            f"Parsed {parsed}/{len(docs)} docs. "
            f"{created} WCs created, {updated} updated. "
            f"Methods: {parse_methods}"
        ),
    )

    # No entry in _CONTRACT_MAP for 2B (it's not in the numbered int slots),
    # so validate_agent_output returns the dict unchanged. Call it anyway for
    # consistency with the other agents' exit pattern.
    return validate_agent_output(agent_number=0, output=output_dict)
