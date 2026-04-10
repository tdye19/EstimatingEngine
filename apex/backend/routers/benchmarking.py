"""Multi-project benchmarking router — compare estimates across projects to
identify pricing patterns and institutional knowledge."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from apex.backend.db.database import get_db
from apex.backend.models.estimate import Estimate
from apex.backend.models.project import Project
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/benchmarking",
    tags=["benchmarking"],
    dependencies=[Depends(require_auth)],
)


@router.get("/projects", response_model=APIResponse)
def benchmark_projects(
    project_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return cost-per-SF and division breakdowns across all completed projects for benchmarking."""
    query = db.query(Project).filter(Project.is_deleted == False)  # noqa: E712
    if project_type:
        query = query.filter(Project.project_type == project_type)
    projects = query.order_by(Project.created_at.desc()).limit(limit).all()
    if not projects:
        return APIResponse(success=True, data={"projects": [], "stats": {}})

    project_ids = [p.id for p in projects]

    # Batch: get latest estimate version per project in one query
    latest_version = (
        db.query(
            Estimate.project_id,
            func.max(Estimate.version).label("max_version"),
        )
        .filter(
            Estimate.project_id.in_(project_ids),
            Estimate.is_deleted == False,  # noqa: E712
        )
        .group_by(Estimate.project_id)
        .subquery()
    )
    estimates = (
        db.query(Estimate)
        .join(
            latest_version,
            (Estimate.project_id == latest_version.c.project_id)
            & (Estimate.version == latest_version.c.max_version),
        )
        .filter(Estimate.is_deleted == False)  # noqa: E712
        .all()
    )
    est_by_project = {e.project_id: e for e in estimates}

    rows = []
    for p in projects:
        estimate = est_by_project.get(p.id)
        if not estimate:
            continue

        sq_ft = p.square_footage or 0
        cost_per_sf = (estimate.total_bid_amount / sq_ft) if sq_ft > 0 else None

        by_div: dict[str, float] = {}
        for li in estimate.line_items or []:
            div = li.division_number or "00"
            by_div[div] = by_div.get(div, 0.0) + (li.total_cost or 0.0)

        rows.append(
            {
                "project_id": p.id,
                "project_number": p.project_number,
                "project_name": p.name,
                "project_type": p.project_type,
                "status": p.status,
                "square_footage": sq_ft,
                "total_bid_amount": estimate.total_bid_amount,
                "cost_per_sf": round(cost_per_sf, 2) if cost_per_sf else None,
                "total_labor_cost": estimate.total_labor_cost,
                "total_material_cost": estimate.total_material_cost,
                "bid_date": p.bid_date,
                "by_division": by_div,
                "estimate_version": estimate.version,
            }
        )

    if not rows:
        return APIResponse(success=True, data={"projects": [], "stats": {}})

    # Aggregate stats
    costs_per_sf = [r["cost_per_sf"] for r in rows if r["cost_per_sf"] is not None]
    totals = [r["total_bid_amount"] for r in rows]

    stats = {
        "project_count": len(rows),
        "avg_cost_per_sf": round(sum(costs_per_sf) / len(costs_per_sf), 2) if costs_per_sf else None,
        "min_cost_per_sf": round(min(costs_per_sf), 2) if costs_per_sf else None,
        "max_cost_per_sf": round(max(costs_per_sf), 2) if costs_per_sf else None,
        "avg_total_bid": round(sum(totals) / len(totals), 2) if totals else None,
    }

    return APIResponse(success=True, data={"projects": rows, "stats": stats})


@router.get("/division-trends", response_model=APIResponse)
def division_cost_trends(
    project_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return average % of total cost per CSI division across all projects — useful for
    identifying where a current estimate deviates from historical norms."""
    query = db.query(Project).filter(Project.is_deleted == False)  # noqa: E712
    if project_type:
        query = query.filter(Project.project_type == project_type)
    projects = query.all()
    project_ids = [p.id for p in projects]

    # Batch: get latest estimate per project
    latest_version = (
        db.query(
            Estimate.project_id,
            func.max(Estimate.version).label("max_version"),
        )
        .filter(
            Estimate.project_id.in_(project_ids),
            Estimate.is_deleted == False,  # noqa: E712
        )
        .group_by(Estimate.project_id)
        .subquery()
    )
    estimates = (
        db.query(Estimate)
        .join(
            latest_version,
            (Estimate.project_id == latest_version.c.project_id)
            & (Estimate.version == latest_version.c.max_version),
        )
        .filter(Estimate.is_deleted == False)  # noqa: E712
        .all()
    )
    est_by_project = {e.project_id: e for e in estimates}

    div_totals: dict[str, list[float]] = {}
    project_count = 0

    for p in projects:
        estimate = est_by_project.get(p.id)
        if not estimate or not estimate.total_bid_amount:
            continue

        project_count += 1
        for li in estimate.line_items or []:
            div = li.division_number or "00"
            pct = (li.total_cost or 0.0) / estimate.total_bid_amount * 100
            div_totals.setdefault(div, []).append(pct)

    trends = {
        div: {
            "avg_pct": round(sum(pcts) / len(pcts), 2),
            "min_pct": round(min(pcts), 2),
            "max_pct": round(max(pcts), 2),
            "sample_count": len(pcts),
        }
        for div, pcts in sorted(div_totals.items())
    }

    return APIResponse(
        success=True,
        data={"project_count": project_count, "division_trends": trends},
    )
