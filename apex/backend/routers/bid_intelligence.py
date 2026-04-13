"""Bid Intelligence router — estimation history upload, analytics, and benchmarks."""

import os

import aiofiles
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from apex.backend.config import UPLOAD_DIR
from apex.backend.db.database import get_db
from apex.backend.services.bid_intelligence.models import BIEstimate
from apex.backend.services.bid_intelligence.service import BidIntelligenceService
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/bid-intelligence",
    tags=["bid-intelligence"],
    dependencies=[Depends(require_auth)],
)

BI_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "bid_intelligence")


@router.post("/upload", response_model=APIResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accept an EstimationHistory .xlsx file and ingest via the BI service."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return APIResponse(success=False, error="File must be .xlsx")

    os.makedirs(BI_UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(BI_UPLOAD_DIR, file.filename)
    try:
        content = await file.read()
        async with aiofiles.open(dest, "wb") as fh:
            await fh.write(content)

        svc = BidIntelligenceService(db)
        result = svc.ingest_file(dest, file.filename)
        return APIResponse(success=True, data=result)
    except Exception as e:
        if os.path.exists(dest):
            os.unlink(dest)
        return APIResponse(success=False, error=str(e))


@router.get("/stats", response_model=APIResponse)
def get_stats(db: Session = Depends(get_db)):
    """Summary statistics for bid intelligence data."""
    svc = BidIntelligenceService(db)
    return APIResponse(success=True, data=svc.get_stats())


@router.get("/benchmarks", response_model=APIResponse)
def get_benchmarks(
    market_sector: str | None = Query(None),
    region: str | None = Query(None),
    estimator: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Cost benchmarks ($/CY, $/SF) with optional filters."""
    svc = BidIntelligenceService(db)
    return APIResponse(
        success=True,
        data=svc.get_benchmarks(
            market_sector=market_sector,
            region=region,
            estimator=estimator,
        ),
    )


@router.get("/comparable", response_model=APIResponse)
def get_comparable(
    conc_vol_cy: float | None = Query(None),
    building_sf: float | None = Query(None),
    market_sector: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Find comparable awarded projects by volume/SF similarity."""
    svc = BidIntelligenceService(db)
    return APIResponse(
        success=True,
        data=svc.get_comparable_projects(
            conc_vol_cy=conc_vol_cy,
            building_sf=building_sf,
            market_sector=market_sector,
            limit=limit,
        ),
    )


@router.get("/estimator-performance", response_model=APIResponse)
def get_estimator_performance(
    estimator: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Per-estimator performance stats."""
    svc = BidIntelligenceService(db)
    return APIResponse(success=True, data=svc.get_estimator_performance(estimator=estimator))


@router.get("/hit-rate", response_model=APIResponse)
def get_hit_rate(
    group_by: str = Query("market_sector"),
    db: Session = Depends(get_db),
):
    """Hit rates grouped by market_sector, region, estimator, or delivery_method."""
    svc = BidIntelligenceService(db)
    return APIResponse(success=True, data=svc.get_hit_rate_by(group_by=group_by))


@router.get("/estimates", response_model=APIResponse)
def list_estimates(
    status: str | None = Query(None),
    region: str | None = Query(None),
    market_sector: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Paginated list of all estimates with optional filters."""
    q = db.query(BIEstimate)

    if status:
        q = q.filter(BIEstimate.status == status)
    if region:
        q = q.filter(BIEstimate.region == region)
    if market_sector:
        q = q.filter(BIEstimate.market_sector == market_sector)

    total = q.count()
    rows = q.order_by(BIEstimate.bid_date.desc().nullslast()).offset((page - 1) * per_page).limit(per_page).all()

    return APIResponse(
        success=True,
        data={
            "total": total,
            "page": page,
            "per_page": per_page,
            "estimates": [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "bid_date": r.bid_date.isoformat() if r.bid_date else None,
                    "bid_amount": r.bid_amount,
                    "contract_amount": r.contract_amount,
                    "estimator": r.estimator,
                    "region": r.region,
                    "market_sector": r.market_sector,
                    "cost_per_cy": r.cost_per_cy,
                    "cost_per_sf": r.cost_per_sf,
                    "conc_vol_cy": r.conc_vol_cy,
                    "building_sf": r.building_sf,
                    "delivery_method": r.delivery_method,
                    "num_bidders": r.num_bidders,
                    "bid_delta_pct": r.bid_delta_pct,
                }
                for r in rows
            ],
        },
    )
