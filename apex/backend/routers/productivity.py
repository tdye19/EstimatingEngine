"""Productivity library router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.productivity_history import ProductivityHistory
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    ProductivityHistoryOut, ProductivityUpdate, APIResponse,
)

router = APIRouter(prefix="/api/productivity-library", tags=["productivity"], dependencies=[Depends(require_auth)])


@router.get("", response_model=APIResponse)
def get_productivity_library(
    csi_code: str = None,
    work_type: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(ProductivityHistory).filter(
        ProductivityHistory.is_deleted == False,  # noqa: E712
    )

    if csi_code:
        query = query.filter(ProductivityHistory.csi_code == csi_code)
    if work_type:
        query = query.filter(ProductivityHistory.work_type.ilike(f"%{work_type}%"))

    records = query.order_by(ProductivityHistory.csi_code).all()

    return APIResponse(
        success=True,
        data=[ProductivityHistoryOut.model_validate(r).model_dump(mode="json") for r in records],
    )


@router.put("/{csi_code}", response_model=APIResponse)
def update_productivity_rate(
    csi_code: str,
    data: ProductivityUpdate,
    db: Session = Depends(get_db),
):
    record = db.query(ProductivityHistory).filter(
        ProductivityHistory.csi_code == csi_code,
        ProductivityHistory.is_deleted == False,  # noqa: E712
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail=f"No productivity record for CSI code {csi_code}")

    if data.productivity_rate is not None:
        record.productivity_rate = data.productivity_rate
    if data.crew_type is not None:
        record.crew_type = data.crew_type
    if data.notes is not None:
        record.notes = data.notes

    db.commit()
    db.refresh(record)

    return APIResponse(
        success=True,
        message="Productivity rate updated",
        data=ProductivityHistoryOut.model_validate(record).model_dump(mode="json"),
    )
