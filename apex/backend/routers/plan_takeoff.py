"""Plan takeoff layers and items router."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.plan_set import PlanSheet
from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer
from apex.backend.models.user import User
from apex.backend.utils.auth import get_authorized_project, require_auth
from apex.backend.utils.schemas import (
    PlanTakeoffItemCreate,
    PlanTakeoffItemOut,
    PlanTakeoffItemUpdate,
    TakeoffLayerCreate,
    TakeoffLayerOut,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["plan-takeoff"], dependencies=[Depends(require_auth)])


# ── Takeoff layers ────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/takeoff-layers", response_model=list[TakeoffLayerOut])
def list_takeoff_layers(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    return (
        db.query(TakeoffLayer)
        .filter(TakeoffLayer.project_id == project_id, TakeoffLayer.is_deleted.is_(False))
        .order_by(TakeoffLayer.id)
        .all()
    )


@router.post("/api/plan-sheets/{sheet_id}/takeoff-layers", response_model=TakeoffLayerOut, status_code=201)
def create_takeoff_layer(
    sheet_id: int,
    body: TakeoffLayerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    sheet = db.query(PlanSheet).filter(PlanSheet.id == sheet_id, PlanSheet.is_deleted.is_(False)).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Plan sheet not found")
    get_authorized_project(sheet.project_id, user, db)
    layer = TakeoffLayer(
        project_id=sheet.project_id,
        plan_sheet_id=sheet_id,
        created_by=user.id,
        **body.model_dump(),
    )
    db.add(layer)
    db.commit()
    db.refresh(layer)
    return layer


@router.get("/api/takeoff-layers/{layer_id}", response_model=TakeoffLayerOut)
def get_takeoff_layer(
    layer_id: int,
    db: Session = Depends(get_db),
):
    layer = db.query(TakeoffLayer).filter(TakeoffLayer.id == layer_id, TakeoffLayer.is_deleted.is_(False)).first()
    if not layer:
        raise HTTPException(status_code=404, detail="Takeoff layer not found")
    return layer


# ── Takeoff items ─────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/takeoff-items", response_model=list[PlanTakeoffItemOut])
def list_takeoff_items(
    project_id: int,
    sheet_id: int | None = None,
    layer_id: int | None = None,
    review_status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    q = db.query(PlanTakeoffItem).filter(
        PlanTakeoffItem.project_id == project_id,
        PlanTakeoffItem.is_deleted.is_(False),
    )
    if sheet_id is not None:
        q = q.filter(PlanTakeoffItem.plan_sheet_id == sheet_id)
    if layer_id is not None:
        q = q.filter(PlanTakeoffItem.takeoff_layer_id == layer_id)
    if review_status is not None:
        q = q.filter(PlanTakeoffItem.review_status == review_status)
    return q.order_by(PlanTakeoffItem.id).all()


@router.post("/api/takeoff-layers/{layer_id}/items", response_model=PlanTakeoffItemOut, status_code=201)
def create_takeoff_item(
    layer_id: int,
    body: PlanTakeoffItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    layer = db.query(TakeoffLayer).filter(TakeoffLayer.id == layer_id, TakeoffLayer.is_deleted.is_(False)).first()
    if not layer:
        raise HTTPException(status_code=404, detail="Takeoff layer not found")
    get_authorized_project(layer.project_id, user, db)
    item = PlanTakeoffItem(
        project_id=layer.project_id,
        plan_sheet_id=layer.plan_sheet_id,
        takeoff_layer_id=layer_id,
        created_by=user.id,
        **body.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/api/takeoff-items/{item_id}", response_model=PlanTakeoffItemOut)
def update_takeoff_item(
    item_id: int,
    body: PlanTakeoffItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    item = db.query(PlanTakeoffItem).filter(PlanTakeoffItem.id == item_id, PlanTakeoffItem.is_deleted.is_(False)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Takeoff item not found")
    get_authorized_project(item.project_id, user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    item.updated_by = user.id
    db.commit()
    db.refresh(item)
    return item


@router.post("/api/takeoff-items/{item_id}/confirm", response_model=PlanTakeoffItemOut)
def confirm_takeoff_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    item = db.query(PlanTakeoffItem).filter(PlanTakeoffItem.id == item_id, PlanTakeoffItem.is_deleted.is_(False)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Takeoff item not found")
    get_authorized_project(item.project_id, user, db)
    item.review_status = "confirmed"
    item.updated_by = user.id
    db.commit()
    db.refresh(item)
    return item


@router.post("/api/takeoff-items/{item_id}/reject", response_model=PlanTakeoffItemOut)
def reject_takeoff_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    item = db.query(PlanTakeoffItem).filter(PlanTakeoffItem.id == item_id, PlanTakeoffItem.is_deleted.is_(False)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Takeoff item not found")
    get_authorized_project(item.project_id, user, db)
    item.review_status = "rejected"
    item.updated_by = user.id
    db.commit()
    db.refresh(item)
    return item
