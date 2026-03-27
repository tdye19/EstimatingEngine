"""Batch import router.

Prefix: /api/batch-import

Endpoints
---------
POST   /upload-zip                  — Upload a zip archive and kick off scanning
POST   /process-group/{group_id}    — Process all files in a DocumentGroup
GET    /groups                      — List all DocumentGroups with status counts
GET    /groups/{group_id}           — Get group details with all associated documents
PUT    /associations/{assoc_id}     — Reclassify a document role / relink library entry
POST   /process-winest/{assoc_id}   — Parse a single WinEst file
"""

import logging
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.document_association import DocumentAssociation, DocumentGroup
from apex.backend.services.batch_import_service import BatchImportResult, BatchImportService
from apex.backend.services.ws_manager import ws_manager
from apex.backend.utils.auth import get_current_user, require_auth

logger = logging.getLogger("apex.routers.batch_import")

router = APIRouter(
    prefix="/api/batch-import",
    tags=["batch-import"],
    dependencies=[Depends(require_auth)],
)

_service = BatchImportService()

# Max zip upload size — configurable via MAX_BATCH_ZIP_MB env var
_MAX_ZIP_BYTES: int = int(os.getenv("MAX_BATCH_ZIP_MB", "1000")) * 1024 * 1024


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AssociationUpdateRequest(BaseModel):
    document_role: Optional[str] = None
    library_entry_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload-zip", response_model=BatchImportResult)
async def upload_zip(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a zip file containing historical project files.

    The zip is extracted to a temp directory, files are detected and grouped by
    top-level subfolder, and DB records are created for every group.  Returns a
    :class:`BatchImportResult` summarising what was found.

    Maximum file size: 500 MB.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # Stream to a temp file while enforcing the size cap
    tmp_path = os.path.join(
        tempfile.gettempdir(), f"apex_zip_{uuid.uuid4().hex}.zip"
    )
    total_bytes = 0
    try:
        with open(tmp_path, "wb") as fh:
            while True:
                chunk = await file.read(256 * 1024)  # 256 KB
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > _MAX_ZIP_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Zip file exceeds the {_MAX_ZIP_BYTES // (1024 * 1024)} MB limit",
                    )
                fh.write(chunk)

        logger.info(
            "Received zip '%s' (%.1f MB) from user %d",
            file.filename,
            total_bytes / 1024 / 1024,
            current_user.id,
        )

        result = _service.process_zip(
            zip_path=tmp_path,
            user_id=current_user.id,
            db=db,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return result


@router.post("/process-group/{group_id}")
def process_group(
    group_id: int = Path(..., description="ID of the DocumentGroup to process"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Process all unparsed files in a DocumentGroup.

    WinEst files are parsed into HistoricalLineItem records; spec PDFs are run
    through Agent 1 (ingestion).  Progress events are broadcast over WebSocket
    using the group_id as the channel key.
    """
    group = db.query(DocumentGroup).filter(DocumentGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="DocumentGroup not found")

    ws_manager.broadcast_batch_sync(
        group_id,
        {"event": "batch_group_started", "group_id": group_id, "group_name": group.name},
    )

    try:
        summary = _service.process_batch_group(group_id=group_id, db=db)
    except Exception as exc:
        ws_manager.broadcast_batch_sync(
            group_id,
            {"event": "batch_group_error", "group_id": group_id, "error": str(exc)},
        )
        logger.error("process_batch_group failed for group %d: %s", group_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    ws_manager.broadcast_batch_sync(
        group_id,
        {"event": "batch_group_complete", "group_id": group_id, "summary": summary},
    )
    return {"success": True, "data": summary}


@router.get("/groups")
def list_groups(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all DocumentGroups with file counts and parse status."""
    groups = (
        db.query(DocumentGroup)
        .order_by(DocumentGroup.created_at.desc())
        .all()
    )
    rows = []
    for g in groups:
        assocs   = g.associations or []
        total    = len(assocs)
        parsed   = sum(1 for a in assocs if a.parsed)
        rows.append({
            "id":                 g.id,
            "name":               g.name,
            "library_entry_id":   g.library_entry_id,
            "project_id":         g.project_id,
            "file_count":         total,
            "parsed_count":       parsed,
            "pending_count":      total - parsed,
            "created_at":         g.created_at.isoformat() if g.created_at else None,
        })
    return {"success": True, "data": rows}


@router.get("/groups/{group_id}")
def get_group(
    group_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get DocumentGroup details with all associated documents."""
    group = db.query(DocumentGroup).filter(DocumentGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="DocumentGroup not found")

    docs = []
    for assoc in (group.associations or []):
        doc = assoc.document
        docs.append({
            "association_id":    assoc.id,
            "document_id":       doc.id             if doc else None,
            "filename":          doc.filename        if doc else None,
            "file_type":         doc.file_type       if doc else None,
            "document_role":     assoc.document_role,
            "parsed":            assoc.parsed,
            "parsed_at":         assoc.parsed_at.isoformat() if assoc.parsed_at else None,
            "parse_errors":      assoc.parse_errors,
            "processing_status": doc.processing_status if doc else None,
        })

    return {
        "success": True,
        "data": {
            "id":               group.id,
            "name":             group.name,
            "library_entry_id": group.library_entry_id,
            "project_id":       group.project_id,
            "created_at":       group.created_at.isoformat() if group.created_at else None,
            "documents":        docs,
        },
    }


@router.put("/associations/{assoc_id}")
def update_association(
    assoc_id: int = Path(...),
    body: AssociationUpdateRequest = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Reclassify a document role or relink it to a different library entry.

    Accepted ``document_role`` values: ``spec``, ``winest_bid``, ``rfi``,
    ``addendum``, ``schedule``, ``submittal``, ``manual``, ``plans``,
    ``blueprints``, ``as_built``, ``change_order``, ``bid_tab``,
    ``subcontractor_quote``, ``other``.
    """
    assoc = (
        db.query(DocumentAssociation)
        .filter(DocumentAssociation.id == assoc_id)
        .first()
    )
    if not assoc:
        raise HTTPException(status_code=404, detail="DocumentAssociation not found")

    if body.document_role is not None:
        if body.document_role not in DocumentAssociation.VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid document_role '{body.document_role}'. "
                    f"Valid values: {sorted(DocumentAssociation.VALID_ROLES)}"
                ),
            )
        assoc.document_role = body.document_role

    if body.library_entry_id is not None:
        assoc.library_entry_id = body.library_entry_id

    db.commit()
    return {
        "success": True,
        "data": {
            "id":               assoc.id,
            "document_role":    assoc.document_role,
            "library_entry_id": assoc.library_entry_id,
        },
    }


@router.post("/process-winest/{assoc_id}")
def process_winest(
    assoc_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Parse a single WinEst file and return the created HistoricalLineItems."""
    try:
        items = _service.process_winest_file(doc_association_id=assoc_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("process_winest failed for assoc %d: %s", assoc_id, exc)
        raise HTTPException(status_code=500, detail="WinEst processing failed")

    return {
        "success": True,
        "data": {
            "line_items_created": len(items),
            "items": [
                {
                    "id":                item.id,
                    "description":       item.description,
                    "csi_code":          item.csi_code,
                    "csi_division":      item.csi_division,
                    "csi_division_name": item.csi_division_name,
                    "quantity":          item.quantity,
                    "unit_of_measure":   item.unit_of_measure,
                    "unit_cost":         item.unit_cost,
                    "total_cost":        item.total_cost,
                    "labor_hours":       item.labor_hours,
                    "productivity_rate": item.productivity_rate,
                }
                for item in items
            ],
        },
    }
