"""Material Pricing CRUD router."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth, require_role
from apex.backend.utils.schemas import (
    APIResponse,
    MaterialPriceCreate,
    MaterialPriceOut,
    MaterialPriceUpdate,
)

router = APIRouter(prefix="/api/material-prices", tags=["materials"])

_admin_or_estimator = require_role("admin", "estimator")
_admin = require_role("admin")


# ── List / Search ────────────────────────────────────────────────────


@router.get("", response_model=APIResponse)
def list_material_prices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: str | None = Query(None),
    region: str | None = Query(None),
    _user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    query = db.query(MaterialPrice).filter(MaterialPrice.is_deleted == False)  # noqa: E712

    if search:
        pattern = f"%{search}%"
        query = query.filter((MaterialPrice.csi_code.ilike(pattern)) | (MaterialPrice.description.ilike(pattern)))

    if region:
        query = query.filter(MaterialPrice.region == region)

    items = query.offset(skip).limit(limit).all()
    return APIResponse(data=[MaterialPriceOut.model_validate(i).model_dump() for i in items])


# ── Get Single ───────────────────────────────────────────────────────


@router.get("/{price_id}", response_model=APIResponse)
def get_material_price(
    price_id: int,
    _user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    item = (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.id == price_id,
            MaterialPrice.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Material price not found")
    return APIResponse(data=MaterialPriceOut.model_validate(item).model_dump())


# ── Create ───────────────────────────────────────────────────────────


@router.post("", response_model=APIResponse, status_code=201)
def create_material_price(
    body: MaterialPriceCreate,
    _user: User = Depends(_admin_or_estimator),
    db: Session = Depends(get_db),
):
    item = MaterialPrice(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return APIResponse(data=MaterialPriceOut.model_validate(item).model_dump())


# ── Update ───────────────────────────────────────────────────────────


@router.put("/{price_id}", response_model=APIResponse)
def update_material_price(
    price_id: int,
    body: MaterialPriceUpdate,
    _user: User = Depends(_admin_or_estimator),
    db: Session = Depends(get_db),
):
    item = (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.id == price_id,
            MaterialPrice.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Material price not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    item.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(item)
    return APIResponse(data=MaterialPriceOut.model_validate(item).model_dump())


# ── Soft Delete ──────────────────────────────────────────────────────


@router.delete("/{price_id}", status_code=204)
def delete_material_price(
    price_id: int,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    item = (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.id == price_id,
            MaterialPrice.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Material price not found")

    item.is_deleted = True
    item.updated_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
