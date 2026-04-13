"""Agent 1: Document Ingestion Agent.

Intakes raw project documents (PDFs, specs, drawings, addenda),
extracts text, classifies, and stores structured metadata.

Also handles WinEst intake:
  - .est  → parsed via olefile (OLE2 native format)
  - .xlsx → auto-detected as WinEst Format 1 or Format 2 by column headers;
            if headers don't match either format the file is treated as a
            generic spreadsheet and processed normally.

When WinEst files are detected, the agent sets pipeline_mode='winest_import'
in its output so the orchestrator can skip Agent 2 (Spec Parser) and
optionally Agent 4 (Quantity Takeoff) if quantities are already present.
"""

import logging

from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.document_tools import (
    docx_reader_tool,
    file_classifier_tool,
    pdf_reader_tool,
)
from apex.backend.models.document import Document

logger = logging.getLogger("apex.agent.ingestion")

# File types that trigger WinEst-specific parsing
_WINEST_NATIVE_TYPES = {"est"}
_WINEST_EXCEL_TYPES = {"xlsx", "xls"}


def run_ingestion_agent(db: Session, project_id: int) -> dict:
    """Process all pending documents for a project.

    Returns a dict with documents_processed count, per-doc results, and —
    when WinEst files are found — pipeline_mode='winest_import' plus the
    consolidated list of parsed line items.
    """
    from apex.backend.utils.winest_parser import parse_winest_file

    documents = (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
            Document.processing_status == "pending",
            Document.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    results = []
    processed = 0
    all_winest_items: list[dict] = []
    is_winest_pipeline = False

    for doc in documents:
        try:
            doc.processing_status = "processing"
            db.commit()

            # ------------------------------------------------------------------
            # WinEst native .est file
            # ------------------------------------------------------------------
            if doc.file_type in _WINEST_NATIVE_TYPES:
                winest_result = parse_winest_file(doc.file_path)

                if not winest_result["success"]:
                    raise Exception(
                        winest_result["error"]
                        or "Unable to read this .est file. Please export as .xlsx from WinEst instead."
                    )

                line_items = winest_result["line_items"]
                winest_format = winest_result["format_detected"]
                all_winest_items.extend(line_items)
                is_winest_pipeline = True

                doc.raw_text = ""
                doc.page_count = 0
                doc.classification = "winest_import"
                doc.processing_status = "completed"
                doc.metadata_json = {
                    "winest_format": winest_format,
                    "winest_line_items": line_items,
                    "line_item_count": len(line_items),
                    "warnings": winest_result["warnings"],
                }
                db.commit()

                processed += 1
                results.append(
                    {
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "classification": "winest_import",
                        "pages": 0,
                        "chars": 0,
                        "status": "success",
                        "winest_format": winest_format,
                    }
                )
                continue  # skip standard text-extraction path

            # ------------------------------------------------------------------
            # WinEst Excel export (.xlsx / .xls) — try auto-detection first
            # ------------------------------------------------------------------
            if doc.file_type in _WINEST_EXCEL_TYPES:
                winest_result = parse_winest_file(doc.file_path)

                if winest_result["success"] and winest_result["format_detected"] != "unknown_xlsx":
                    line_items = winest_result["line_items"]
                    winest_format = winest_result["format_detected"]
                    all_winest_items.extend(line_items)
                    is_winest_pipeline = True

                    doc.raw_text = ""
                    doc.page_count = 0
                    doc.classification = "winest_import"
                    doc.processing_status = "completed"
                    doc.metadata_json = {
                        "winest_format": winest_format,
                        "winest_line_items": line_items,
                        "line_item_count": len(line_items),
                        "warnings": winest_result["warnings"],
                    }
                    db.commit()

                    processed += 1
                    results.append(
                        {
                            "document_id": doc.id,
                            "filename": doc.filename,
                            "classification": "winest_import",
                            "pages": 0,
                            "chars": 0,
                            "status": "success",
                            "winest_format": winest_format,
                        }
                    )
                    continue  # skip standard text-extraction path
                # Headers didn't match either WinEst format → fall through to
                # standard text processing below (treat as generic spreadsheet).

            # ------------------------------------------------------------------
            # Standard document processing (PDF, DOCX, plain text, generic xlsx)
            # ------------------------------------------------------------------
            raw_text = ""
            page_count = 0

            if doc.file_type in ("pdf", "application/pdf"):
                pdf_result = pdf_reader_tool(doc.file_path)
                if pdf_result["error"]:
                    raise Exception(pdf_result["error"])
                page_count = pdf_result["total_pages"]
                raw_text = "\n\n".join(p["text"] for p in pdf_result["pages"])

            elif doc.file_type in (
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ):
                docx_result = docx_reader_tool(doc.file_path)
                if docx_result["error"]:
                    raise Exception(docx_result["error"])
                page_count = max(1, docx_result["total_paragraphs"] // 30)
                raw_text = "\n".join(docx_result["paragraphs"])

            else:
                # For unsupported types, try reading as plain text
                try:
                    with open(doc.file_path, errors="ignore") as f:
                        raw_text = f.read()
                    page_count = max(1, len(raw_text) // 3000)
                except Exception:
                    raw_text = ""
                    page_count = 0

            # Classify document
            text_sample = raw_text[:2000] if raw_text else ""
            classification = file_classifier_tool(doc.filename, text_sample)

            doc.raw_text = raw_text
            doc.page_count = page_count
            doc.classification = classification
            doc.processing_status = "completed"
            doc.metadata_json = {
                "char_count": len(raw_text),
                "page_count": page_count,
                "classification": classification,
            }
            db.commit()

            processed += 1
            results.append(
                {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "classification": classification,
                    "pages": page_count,
                    "chars": len(raw_text),
                    "status": "success",
                }
            )

        except Exception as e:
            logger.error(f"Failed to process document {doc.id}: {e}")
            doc.processing_status = "error"
            doc.metadata_json = {"error": str(e)}
            db.commit()

            results.append(
                {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "status": "error",
                    "error": str(e),
                }
            )

    output: dict = {
        "documents_processed": processed,
        "total_documents": len(documents),
        "results": results,
    }

    if is_winest_pipeline:
        output["pipeline_mode"] = "winest_import"
        output["winest_line_items"] = all_winest_items
        logger.info(
            f"WinEst import detected — {len(all_winest_items)} line items extracted "
            f"from {processed} file(s). Orchestrator will skip Agent 2."
        )

    return validate_agent_output(1, output)
