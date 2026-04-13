"""Material prices router — look up unit costs for construction materials."""

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.estimate import Estimate
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/material-prices",
    tags=["material-prices"],
    dependencies=[Depends(require_auth)],
)


class PriceLookupRequest(BaseModel):
    csi_code: str
    description: str = ""
    unit: str = "EA"


class BulkPriceLookupRequest(BaseModel):
    items: list[PriceLookupRequest]


@router.post("/lookup", response_model=APIResponse)
async def lookup_price(data: PriceLookupRequest):
    """Look up the unit cost for a single material."""
    from apex.backend.services.material_price_service import get_material_price

    result = await get_material_price(data.csi_code, data.description, data.unit)
    return APIResponse(success=True, data=result)


@router.post("/lookup/bulk", response_model=APIResponse)
async def lookup_prices_bulk(data: BulkPriceLookupRequest):
    """Look up unit costs for multiple materials in one call."""
    from apex.backend.services.material_price_service import get_material_prices_bulk

    items = [i.model_dump() for i in data.items]
    results = await get_material_prices_bulk(items)
    return APIResponse(success=True, data=results)


@router.get("/benchmarks", response_model=APIResponse)
def list_benchmarks():
    """Return all built-in benchmark rates with their CSI codes and units."""
    from apex.backend.services.material_price_service import BENCHMARK_RATES

    rows = []
    for (csi_prefix, unit), entry in sorted(BENCHMARK_RATES.items()):
        rows.append(
            {
                "csi_prefix": csi_prefix,
                "unit": unit,
                "description": entry["description"],
                "unit_cost": entry["unit_cost"],
            }
        )
    return APIResponse(success=True, data=rows)


@router.get("/projects/{project_id}/material-costs", response_model=APIResponse)
def get_project_material_costs(project_id: int, db: Session = Depends(get_db)):
    """Return material cost breakdown for the latest project estimate."""
    estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .first()
    )
    if not estimate:
        return APIResponse(success=True, data=None, message="No estimate available")

    by_div: dict[str, dict] = {}
    for li in estimate.line_items or []:
        div = li.division_number or "00"
        if div not in by_div:
            by_div[div] = {"material_cost": 0.0, "labor_cost": 0.0, "total_cost": 0.0}
        by_div[div]["material_cost"] += li.material_cost or 0.0
        by_div[div]["labor_cost"] += li.labor_cost or 0.0
        by_div[div]["total_cost"] += li.total_cost or 0.0

    return APIResponse(
        success=True,
        data={
            "estimate_id": estimate.id,
            "version": estimate.version,
            "total_material_cost": estimate.total_material_cost,
            "by_division": by_div,
            "provider_configured": bool(os.getenv("MATERIAL_PRICE_API")),
            "provider": os.getenv("MATERIAL_PRICE_API", "benchmark"),
        },
    )
