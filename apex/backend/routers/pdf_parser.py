"""PDF parser router — extract tables and CSI codes from project PDFs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.document import Document
from apex.backend.services.pdf_parser_service import PDFParserService
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/pdf-parser",
    tags=["pdf-parser"],
    dependencies=[Depends(require_auth)],
)


@router.post("/{project_id}/parse-pdfs", response_model=APIResponse)
def parse_project_pdfs(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Parse all unprocessed PDFs for a project, extracting tables and CSI codes."""
    svc = PDFParserService(db)
    result = svc.parse_project_pdfs(project_id)
    return APIResponse(success=True, data=result)


@router.post("/{project_id}/documents/{document_id}/parse", response_model=APIResponse)
def parse_single_document(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    """Parse a single PDF document for table extraction and CSI mapping."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    svc = PDFParserService(db)
    result = svc.parse_document(doc)
    return APIResponse(success=True, data=result)
