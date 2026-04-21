"""Work Categories router (Sprint 18.1).

GET /api/projects/{project_id}/work-categories
GET /api/projects/{project_id}/work-categories/{wc_id}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.project import Project
from apex.backend.models.work_category import WorkCategory
from apex.backend.utils.auth import require_auth

router = APIRouter(
    prefix="/api/projects/{project_id}/work-categories",
    tags=["work-categories"],
    dependencies=[Depends(require_auth)],
)


def _serialize_wc(wc: WorkCategory) -> dict:
    return {
        "id": wc.id,
        "wc_number": wc.wc_number,
        "title": wc.title,
        "work_included_items": wc.work_included_items,
        "work_category_notes": wc.work_category_notes,
        "specific_notes": wc.specific_notes,
        "related_work_by_others": wc.related_work_by_others,
        "add_alternates": wc.add_alternates,
        "allowances": wc.allowances,
        "unit_prices": wc.unit_prices,
        "referenced_spec_sections": wc.referenced_spec_sections,
        "source_document_id": wc.source_document_id,
        "source_page_start": wc.source_page_start,
        "source_page_end": wc.source_page_end,
        "parse_method": wc.parse_method,
        "parse_confidence": wc.parse_confidence,
        "created_at": wc.created_at.isoformat() if wc.created_at else None,
        "updated_at": wc.updated_at.isoformat() if wc.updated_at else None,
    }


@router.get("")
def list_work_categories(project_id: int, db: Session = Depends(get_db)):
    """Return all WorkCategory rows for a project, ordered by wc_number."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rows = db.query(WorkCategory).filter(WorkCategory.project_id == project_id).order_by(WorkCategory.wc_number).all()
    return [_serialize_wc(wc) for wc in rows]


@router.get("/{wc_id}")
def get_work_category(
    project_id: int,
    wc_id: int,
    db: Session = Depends(get_db),
):
    """Return a single WorkCategory by ID, scoped to the project."""
    wc = db.query(WorkCategory).filter(WorkCategory.id == wc_id).filter(WorkCategory.project_id == project_id).first()
    if not wc:
        raise HTTPException(status_code=404, detail="Work category not found")
    return _serialize_wc(wc)
