"""Plan sets and sheets router."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.plan_set import PlanSet, PlanSheet, SheetRegion
from apex.backend.models.user import User
from apex.backend.utils.auth import get_authorized_project, require_auth
from apex.backend.utils.schemas import (
    PlanSetCreate,
    PlanSetOut,
    PlanSheetOut,
    PlanSheetUpdate,
    SheetRegionCreate,
    SheetRegionOut,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["plan-sets"], dependencies=[Depends(require_auth)])


# ── Plan sets ─────────────────────────────────────────────────────────────────


@router.post("/api/projects/{project_id}/plan-sets", response_model=PlanSetOut, status_code=201)
def create_plan_set(
    project_id: int,
    body: PlanSetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    plan_set = PlanSet(project_id=project_id, **body.model_dump())
    db.add(plan_set)
    db.commit()
    db.refresh(plan_set)
    return plan_set


@router.get("/api/projects/{project_id}/plan-sets", response_model=list[PlanSetOut])
def list_plan_sets(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    return (
        db.query(PlanSet)
        .filter(PlanSet.project_id == project_id, PlanSet.is_deleted.is_(False))
        .order_by(PlanSet.id)
        .all()
    )


@router.get("/api/plan-sets/{plan_set_id}", response_model=PlanSetOut)
def get_plan_set(
    plan_set_id: int,
    db: Session = Depends(get_db),
):
    plan_set = db.query(PlanSet).filter(PlanSet.id == plan_set_id, PlanSet.is_deleted.is_(False)).first()
    if not plan_set:
        raise HTTPException(status_code=404, detail="Plan set not found")
    return plan_set


# ── Plan sheets ───────────────────────────────────────────────────────────────


@router.get("/api/plan-sets/{plan_set_id}/sheets", response_model=list[PlanSheetOut])
def list_sheets(
    plan_set_id: int,
    db: Session = Depends(get_db),
):
    plan_set = db.query(PlanSet).filter(PlanSet.id == plan_set_id, PlanSet.is_deleted.is_(False)).first()
    if not plan_set:
        raise HTTPException(status_code=404, detail="Plan set not found")
    return (
        db.query(PlanSheet)
        .filter(PlanSheet.plan_set_id == plan_set_id, PlanSheet.is_deleted.is_(False))
        .order_by(PlanSheet.page_index)
        .all()
    )


@router.get("/api/plan-sheets/{sheet_id}", response_model=PlanSheetOut)
def get_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
):
    sheet = db.query(PlanSheet).filter(PlanSheet.id == sheet_id, PlanSheet.is_deleted.is_(False)).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Plan sheet not found")
    return sheet


@router.patch("/api/plan-sheets/{sheet_id}", response_model=PlanSheetOut)
def update_sheet(
    sheet_id: int,
    body: PlanSheetUpdate,
    db: Session = Depends(get_db),
):
    sheet = db.query(PlanSheet).filter(PlanSheet.id == sheet_id, PlanSheet.is_deleted.is_(False)).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Plan sheet not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sheet, field, value)
    db.commit()
    db.refresh(sheet)
    return sheet


# ── Sheet regions ─────────────────────────────────────────────────────────────


@router.post("/api/plan-sheets/{sheet_id}/regions", response_model=SheetRegionOut, status_code=201)
def create_region(
    sheet_id: int,
    body: SheetRegionCreate,
    db: Session = Depends(get_db),
):
    sheet = db.query(PlanSheet).filter(PlanSheet.id == sheet_id, PlanSheet.is_deleted.is_(False)).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Plan sheet not found")
    region = SheetRegion(plan_sheet_id=sheet_id, **body.model_dump())
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


@router.get("/api/plan-sheets/{sheet_id}/regions", response_model=list[SheetRegionOut])
def list_regions(
    sheet_id: int,
    db: Session = Depends(get_db),
):
    sheet = db.query(PlanSheet).filter(PlanSheet.id == sheet_id, PlanSheet.is_deleted.is_(False)).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Plan sheet not found")
    return (
        db.query(SheetRegion)
        .filter(SheetRegion.plan_sheet_id == sheet_id)
        .order_by(SheetRegion.id)
        .all()
    )
