"""Agent 1: Document Ingestion Agent.

Intakes raw project documents (PDFs, specs, drawings, addenda),
extracts text, classifies, and stores structured metadata.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.document import Document
from apex.backend.agents.tools.document_tools import (
    pdf_reader_tool,
    docx_reader_tool,
    file_classifier_tool,
)

logger = logging.getLogger("apex.agent.ingestion")


def run_ingestion_agent(db: Session, project_id: int) -> dict:
    """Process all pending documents for a project.

    Returns dict with documents_processed count and per-doc results.
    """
    documents = db.query(Document).filter(
        Document.project_id == project_id,
        Document.processing_status == "pending",
        Document.is_deleted == False,  # noqa: E712
    ).all()

    results = []
    processed = 0

    for doc in documents:
        try:
            doc.processing_status = "processing"
            db.commit()

            raw_text = ""
            page_count = 0

            if doc.file_type in ("pdf", "application/pdf"):
                pdf_result = pdf_reader_tool(doc.file_path)
                if pdf_result["error"]:
                    raise Exception(pdf_result["error"])
                page_count = pdf_result["total_pages"]
                raw_text = "\n\n".join(p["text"] for p in pdf_result["pages"])

            elif doc.file_type in ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
                docx_result = docx_reader_tool(doc.file_path)
                if docx_result["error"]:
                    raise Exception(docx_result["error"])
                page_count = max(1, docx_result["total_paragraphs"] // 30)
                raw_text = "\n".join(docx_result["paragraphs"])

            else:
                # For unsupported types, try reading as text
                try:
                    with open(doc.file_path, "r", errors="ignore") as f:
                        raw_text = f.read()
                    page_count = max(1, len(raw_text) // 3000)
                except Exception:
                    raw_text = ""
                    page_count = 0

            # Classify document
            text_sample = raw_text[:2000] if raw_text else ""
            classification = file_classifier_tool(doc.filename, text_sample)

            # Update document record
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
            results.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "classification": classification,
                "pages": page_count,
                "chars": len(raw_text),
                "status": "success",
            })

        except Exception as e:
            logger.error(f"Failed to process document {doc.id}: {e}")
            doc.processing_status = "error"
            doc.metadata_json = {"error": str(e)}
            db.commit()

            results.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "status": "error",
                "error": str(e),
            })

    return {
        "documents_processed": processed,
        "total_documents": len(documents),
        "results": results,
    }
