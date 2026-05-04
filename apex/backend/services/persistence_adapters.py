"""Persistence adapters — bridge agent outputs into Phase 1 domain tables.

Rules:
- Never modify agent logic. Adapters run after an agent succeeds.
- All writes are best-effort: a failure here must not fail the pipeline run.
- Every created row links back to agent_run_log_id for full provenance.
"""

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger("apex.adapters")


# ---------------------------------------------------------------------------
# Agent 1 → PlanSet + PlanSheet
# ---------------------------------------------------------------------------


def adapt_agent1_plan_sets(
    db: Session,
    project_id: int,
    agent1_result: dict,
    agent_run_log_id: int | None,
) -> None:
    """Create PlanSet + PlanSheet rows from agent 1 ingestion output.

    One PlanSet per successfully processed PDF/DOCX document.
    One PlanSheet row per page within that document.
    WinEst files (pages == 0) are skipped — they have no sheet geometry.
    """
    from apex.backend.models.document import Document
    from apex.backend.models.plan_set import PlanSet, PlanSheet

    results = agent1_result.get("results", [])
    if not results:
        return

    created_sets = 0
    created_sheets = 0

    for doc_result in results:
        if doc_result.get("status") != "success":
            continue

        pages = doc_result.get("pages") or 0
        if pages == 0:
            # WinEst / non-drawing documents — no sheet rows to write
            continue

        doc_id = doc_result.get("document_id")
        filename = doc_result.get("filename", "")

        try:
            # Idempotent: skip if a PlanSet already exists for this document
            existing = db.query(PlanSet).filter(PlanSet.upload_id == doc_id).first()
            if existing:
                logger.debug(
                    "adapt_agent1: PlanSet already exists for doc_id=%d, skipping", doc_id
                )
                continue

            plan_set = PlanSet(
                project_id=project_id,
                upload_id=doc_id,
                source_filename=filename,
                sheet_count=pages,
                status="ready",
            )
            db.add(plan_set)
            db.flush()  # get plan_set.id before writing sheets

            for page_idx in range(pages):
                sheet = PlanSheet(
                    project_id=project_id,
                    plan_set_id=plan_set.id,
                    page_index=page_idx,
                )
                db.add(sheet)

            db.commit()
            created_sets += 1
            created_sheets += pages
            logger.info(
                "adapt_agent1: created PlanSet id=%d with %d sheets for doc_id=%d (run_log=%s)",
                plan_set.id,
                pages,
                doc_id,
                agent_run_log_id,
            )

        except Exception as exc:
            db.rollback()
            logger.warning(
                "adapt_agent1: failed to write PlanSet for doc_id=%d: %s", doc_id, exc
            )

    if created_sets:
        logger.info(
            "adapt_agent1: project=%d — %d plan sets, %d sheets written",
            project_id,
            created_sets,
            created_sheets,
        )


# ---------------------------------------------------------------------------
# Agent 4 → TakeoffLayer + PlanTakeoffItem
# ---------------------------------------------------------------------------

# Unit normalization: map WinEst unit strings to the Phase 1 enum vocabulary.
_UNIT_MAP = {
    "SF": "SF",
    "SY": "SF",  # square yard → keep as-is for now; estimator can correct
    "LF": "LF",
    "CY": "CY",
    "EA": "EA",
    "LS": "EA",
    "TN": "TN",
    "TON": "TN",
    "LB": "LB",
    "HR": "EA",
    "DAY": "EA",
    "MH": "EA",
}

# Derive measurement_type from unit
_UNIT_TO_MEASUREMENT = {
    "SF": "area",
    "SY": "area",
    "LF": "linear",
    "CY": "volume",
    "EA": "count",
    "LS": "count",
    "TN": "count",
    "TON": "count",
    "LB": "count",
}


def adapt_agent4_takeoff_items(
    db: Session,
    project_id: int,
    agent4_result: dict,
    agent_run_log_id: int | None,
) -> None:
    """Create TakeoffLayer + PlanTakeoffItem rows from agent 4 output.

    One TakeoffLayer is created per agent run (named 'Rate Intelligence').
    One PlanTakeoffItem is created per recommendation with:
      - source_method='ai'
      - review_status='unreviewed'
      - agent_run_log_id for full provenance

    Prior items from previous runs are NOT deleted — each run creates a new
    layer, preserving the review history of earlier runs.
    """
    from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer

    recommendations = agent4_result.get("recommendations", [])
    if not recommendations:
        return

    try:
        layer = TakeoffLayer(
            project_id=project_id,
            name="Rate Intelligence",
            layer_type="count",
            trade_focus=None,
            plan_sheet_id=None,
            scope_package_id=None,
        )
        db.add(layer)
        db.flush()

        items_written = 0
        for rec in recommendations:
            unit_raw = (rec.get("unit") or "").strip().upper()
            unit = _UNIT_MAP.get(unit_raw, unit_raw) or None
            measurement_type = _UNIT_TO_MEASUREMENT.get(unit_raw)

            confidence_str = rec.get("confidence", "none")
            # Map confidence label → numeric: high=0.9, medium=0.65, low=0.3, none=None
            confidence_map = {"high": 0.9, "medium": 0.65, "low": 0.3}
            confidence = confidence_map.get(confidence_str)

            item = PlanTakeoffItem(
                project_id=project_id,
                plan_sheet_id=None,
                takeoff_layer_id=layer.id,
                agent_run_log_id=agent_run_log_id,
                item_type="count",
                label=rec.get("activity"),
                measurement_type=measurement_type,
                quantity=rec.get("quantity"),
                unit=unit if unit else None,
                source_method="ai",
                confidence=confidence,
                review_status="unreviewed",
            )
            db.add(item)
            items_written += 1

        db.commit()
        logger.info(
            "adapt_agent4: project=%d — layer id=%d, %d takeoff items written (run_log=%s)",
            project_id,
            layer.id,
            items_written,
            agent_run_log_id,
        )

    except Exception as exc:
        db.rollback()
        logger.warning("adapt_agent4: failed to write takeoff layer/items for project=%d: %s", project_id, exc)
