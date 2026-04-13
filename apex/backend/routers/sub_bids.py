"""Subcontractor bid comparison router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.sub_bid import SubBidPackage
from apex.backend.services.sub_bid_service import SubBidService
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/sub-bids",
    tags=["sub-bids"],
    dependencies=[Depends(require_auth)],
)


class PackageCreate(BaseModel):
    trade: str
    csi_division: str | None = None
    base_scope_items: list | None = None


class BidCreate(BaseModel):
    subcontractor_name: str
    total_bid_amount: float | None = None
    line_items: list[dict] | None = None


@router.post("/{project_id}/packages", response_model=APIResponse, status_code=201)
def create_package(
    project_id: int,
    body: PackageCreate,
    db: Session = Depends(get_db),
):
    svc = SubBidService(db)
    pkg = svc.create_package(
        project_id=project_id,
        trade=body.trade,
        csi_division=body.csi_division,
        base_scope_items=body.base_scope_items,
    )
    return APIResponse(success=True, data={"id": pkg.id, "trade": pkg.trade})


@router.get("/{project_id}/packages", response_model=APIResponse)
def list_packages(
    project_id: int,
    db: Session = Depends(get_db),
):
    pkgs = db.query(SubBidPackage).filter(SubBidPackage.project_id == project_id).all()
    return APIResponse(
        success=True,
        data=[
            {
                "id": p.id,
                "trade": p.trade,
                "csi_division": p.csi_division,
                "bid_count": len(p.bids),
            }
            for p in pkgs
        ],
    )


@router.post("/{project_id}/packages/{package_id}/bids", response_model=APIResponse, status_code=201)
def add_bid(
    project_id: int,
    package_id: int,
    body: BidCreate,
    db: Session = Depends(get_db),
):
    pkg = (
        db.query(SubBidPackage)
        .filter(
            SubBidPackage.id == package_id,
            SubBidPackage.project_id == project_id,
        )
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    svc = SubBidService(db)
    bid = svc.add_bid(
        package_id=package_id,
        subcontractor_name=body.subcontractor_name,
        total_bid_amount=body.total_bid_amount,
        line_items=body.line_items,
    )
    return APIResponse(success=True, data={"id": bid.id, "subcontractor_name": bid.subcontractor_name})


@router.get("/{project_id}/packages/{package_id}/bids", response_model=APIResponse)
def list_bids(
    project_id: int,
    package_id: int,
    db: Session = Depends(get_db),
):
    pkg = (
        db.query(SubBidPackage)
        .filter(
            SubBidPackage.id == package_id,
            SubBidPackage.project_id == project_id,
        )
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    return APIResponse(
        success=True,
        data=[
            {
                "id": b.id,
                "subcontractor_name": b.subcontractor_name,
                "total_bid_amount": b.total_bid_amount,
                "normalized": b.normalized,
                "line_item_count": len(b.line_items),
            }
            for b in pkg.bids
        ],
    )


@router.post("/{project_id}/packages/{package_id}/compare", response_model=APIResponse)
def compare_bids(
    project_id: int,
    package_id: int,
    db: Session = Depends(get_db),
):
    pkg = (
        db.query(SubBidPackage)
        .filter(
            SubBidPackage.id == package_id,
            SubBidPackage.project_id == project_id,
        )
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    svc = SubBidService(db)
    # Normalize first if not already done
    svc.normalize_bids(package_id)
    result = svc.compare_bids(package_id)
    return APIResponse(success=True, data=result)
