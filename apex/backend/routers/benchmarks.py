"""Benchmark data router — list, filter, and recompute ProductivityBenchmark records."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from apex.backend.db.database import get_db
from apex.backend.models.productivity_benchmark import ProductivityBenchmark
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse
from apex.backend.services.benchmark_engine import compute_benchmarks, get_benchmark_summary

router = APIRouter(
    prefix="/api/benchmarks",
    tags=["benchmarks"],
    dependencies=[Depends(require_auth)],
)


def _benchmark_to_dict(b: ProductivityBenchmark) -> dict:
    return {
        "id": b.id,
        "csi_code": b.csi_code,
        "csi_division": b.csi_division,
        "description": b.description,
        "project_type": b.project_type,
        "region": b.region,
        "unit_of_measure": b.unit_of_measure,
        "avg_unit_cost": b.avg_unit_cost,
        "min_unit_cost": b.min_unit_cost,
        "max_unit_cost": b.max_unit_cost,
        "std_dev": b.std_dev,
        "avg_labor_cost_per_unit": b.avg_labor_cost_per_unit,
        "avg_material_cost_per_unit": b.avg_material_cost_per_unit,
        "avg_equipment_cost_per_unit": b.avg_equipment_cost_per_unit,
        "avg_sub_cost_per_unit": b.avg_sub_cost_per_unit,
        "avg_labor_hours_per_unit": b.avg_labor_hours_per_unit,
        "sample_size": b.sample_size,
        "confidence_score": b.confidence_score,
        "last_computed_at": b.last_computed_at.isoformat() if b.last_computed_at else None,
    }


@router.get("/summary", response_model=APIResponse)
def benchmark_summary(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return summary stats: total benchmarks, division coverage, avg sample size, last computed."""
    summary = get_benchmark_summary(db, current_user.organization_id)
    return APIResponse(success=True, data=summary)


@router.get("/", response_model=APIResponse)
def list_benchmarks(
    csi_division: Optional[str] = Query(None, description="Two-digit CSI division, e.g. '03'"),
    project_type: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """List all benchmarks for the user's org with optional filters."""
    q = db.query(ProductivityBenchmark).filter(
        ProductivityBenchmark.organization_id == current_user.organization_id,
        ProductivityBenchmark.is_deleted.is_(False),
    )
    if csi_division:
        q = q.filter(ProductivityBenchmark.csi_division == csi_division)
    if project_type:
        q = q.filter(ProductivityBenchmark.project_type == project_type)
    if region:
        q = q.filter(ProductivityBenchmark.region == region)

    benchmarks = q.order_by(ProductivityBenchmark.csi_code).all()
    return APIResponse(
        success=True,
        data={"benchmarks": [_benchmark_to_dict(b) for b in benchmarks], "total": len(benchmarks)},
    )


@router.post("/compute", response_model=APIResponse)
def recompute_benchmarks(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Trigger full benchmark recomputation for the user's org."""
    results = compute_benchmarks(db, current_user.organization_id)
    return APIResponse(
        success=True,
        message=f"Recomputed {len(results)} benchmark records.",
        data={"recomputed": len(results)},
    )


@router.get("/{csi_code:path}", response_model=APIResponse)
def benchmark_detail(
    csi_code: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return all project_type/region breakdowns for a specific CSI code."""
    rows = (
        db.query(ProductivityBenchmark)
        .filter(
            ProductivityBenchmark.organization_id == current_user.organization_id,
            ProductivityBenchmark.csi_code == csi_code,
            ProductivityBenchmark.is_deleted.is_(False),
        )
        .order_by(ProductivityBenchmark.project_type, ProductivityBenchmark.region)
        .all()
    )
    if not rows:
        return APIResponse(success=False, message="No benchmark found for this CSI code.", data=None)
    return APIResponse(
        success=True,
        data={"csi_code": csi_code, "breakdowns": [_benchmark_to_dict(r) for r in rows]},
    )
