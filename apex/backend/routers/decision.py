"""Decision system API routes — /api/decision/*

New endpoints alongside existing routes. Does NOT modify any existing routes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.decision_models import (
    CanonicalActivity,
    ComparableProject,
    CostBreakdownBucket,
    EstimateLine,
    EstimatorOverride,
    HistoricalRateObservation,
    RiskItem,
)
from apex.backend.models.project import Project
from apex.backend.services.decision_assembly import DecisionAssemblyEngine
from apex.backend.services.decision_benchmark import DecisionBenchmarkEngine
from apex.backend.utils.auth import require_auth
from apex.backend.utils.pagination import paginate_query

logger = logging.getLogger("apex.decision")

router = APIRouter(prefix="/api/decision", tags=["decision"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProjectContextUpdate(BaseModel):
    project_type: str | None = None
    market_sector: str | None = None
    region: str | None = None
    delivery_method: str | None = None
    contract_type: str | None = None
    complexity_level: str | None = None
    schedule_pressure: str | None = None
    size_sf: float | None = None
    scope_types: str | None = None


class QuantityItem(BaseModel):
    description: str
    quantity: float
    unit: str | None = None
    division_code: str | None = None


class EstimateRequest(BaseModel):
    quantities: list[QuantityItem]


class OverrideRequest(BaseModel):
    overridden_value: float
    override_type: str
    reason_code: str | None = None
    reason_text: str | None = None
    created_by: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_or_404(project_id: int, db: Session) -> Project:
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return proj


def _project_dict(proj: Project) -> dict:
    return {
        "id": proj.id,
        "name": proj.name,
        "project_type": getattr(proj, "project_type", None),
        "market_sector": getattr(proj, "market_sector", None),
        "region": getattr(proj, "region", None),
        "delivery_method": getattr(proj, "delivery_method", None),
        "contract_type": getattr(proj, "contract_type", None),
        "complexity_level": getattr(proj, "complexity_level", None),
        "schedule_pressure": getattr(proj, "schedule_pressure", None),
        "size_sf": proj.square_footage,
        "scope_types": getattr(proj, "scope_types", None),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.patch("/projects/{project_id}/context")
def update_project_context(
    project_id: int,
    body: ProjectContextUpdate,
    db: Session = Depends(get_db),
):
    """Update decision-system context fields on a project."""
    proj = _get_project_or_404(project_id, db)
    # size_sf in the request schema maps to the canonical Project.square_footage column
    _field_map = {"size_sf": "square_footage"}
    for field, value in body.model_dump(exclude_none=True).items():
        proj_field = _field_map.get(field, field)
        if hasattr(proj, proj_field):
            setattr(proj, proj_field, value)
    db.commit()
    db.refresh(proj)
    return _project_dict(proj)


@router.get("/projects/{project_id}/comparable-projects")
def get_comparable_projects(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Return scored comparable projects for a project, sorted by similarity desc."""
    proj = _get_project_or_404(project_id, db)
    engine = DecisionBenchmarkEngine(db)
    scored = engine.get_comparable_projects(proj)

    if not scored:
        return []

    # Batch-fetch observation counts in one query
    comp_ids = [comp.id for comp, _sim in scored]
    obs_counts = dict(
        db.query(
            HistoricalRateObservation.comparable_project_id,
            func.count(HistoricalRateObservation.id),
        )
        .filter(HistoricalRateObservation.comparable_project_id.in_(comp_ids))
        .group_by(HistoricalRateObservation.comparable_project_id)
        .all()
    )

    result = []
    for comp, sim in scored:
        result.append(
            {
                "id": comp.id,
                "name": comp.name,
                "project_type": comp.project_type,
                "region": comp.region,
                "delivery_method": comp.delivery_method,
                "final_contract_value": comp.final_contract_value,
                "data_quality_score": comp.data_quality_score,
                "context_similarity": round(sim, 4),
                "observation_count": obs_counts.get(comp.id, 0),
            }
        )
    return result


@router.get("/projects/{project_id}/benchmarks/{activity_name}")
def benchmark_activity(
    project_id: int,
    activity_name: str,
    division_code: str | None = None,
    db: Session = Depends(get_db),
):
    """Return benchmark data for a specific activity."""
    proj = _get_project_or_404(project_id, db)
    engine = DecisionBenchmarkEngine(db)
    return engine.benchmark_activity(proj, activity_name, division_code=division_code)


@router.post("/projects/{project_id}/estimate")
def run_estimate(
    project_id: int,
    body: EstimateRequest,
    db: Session = Depends(get_db),
):
    """Run a full decision estimate for a project."""
    proj = _get_project_or_404(project_id, db)
    if not body.quantities:
        raise HTTPException(status_code=400, detail="quantities list is required")

    quantities = [q.model_dump() for q in body.quantities]
    engine = DecisionAssemblyEngine(db)
    result = engine.run_estimate(proj, quantities)
    db.commit()

    return {
        "project_id": project_id,
        "line_count": result["line_count"],
        "direct_cost": result["direct_cost"],
        "final_bid_value": result["final_bid_value"],
        "risk_item_count": result["risk_item_count"],
        "needs_review_count": result["needs_review_count"],
        "low_confidence_count": result["low_confidence_count"],
        "estimate_lines": [_line_dict(ln) for ln in result["estimate_lines"]],
        "cost_breakdown": [_bucket_dict(b) for b in result["cost_breakdown"]],
        "risk_items": [_risk_dict(r) for r in result["risk_items"]],
    }


@router.get("/projects/{project_id}/estimate-lines")
def get_estimate_lines(
    project_id: int,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Return EstimateLine rows for a project (paginated)."""
    _get_project_or_404(project_id, db)
    query = (
        db.query(EstimateLine)
        .filter(EstimateLine.project_id == project_id)
        .order_by(EstimateLine.division_code, EstimateLine.description)
    )
    page = paginate_query(query, offset=offset, limit=limit)
    page["items"] = [_line_dict(ln) for ln in page["items"]]
    return page


@router.post("/estimate-lines/{line_id}/override")
def override_estimate_line(
    line_id: str,
    body: OverrideRequest,
    db: Session = Depends(get_db),
):
    """Apply an estimator override to a line item."""
    line = db.query(EstimateLine).filter(EstimateLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail=f"EstimateLine {line_id} not found")

    original_value = line.recommended_unit_cost or 0.0
    override = EstimatorOverride(
        estimate_line_id=line_id,
        original_value=original_value,
        overridden_value=body.overridden_value,
        override_type=body.override_type,
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        created_by=body.created_by,
    )
    db.add(override)

    # Update line
    line.recommended_unit_cost = body.overridden_value
    line.recommended_total_cost = round(line.quantity * body.overridden_value, 2)
    line.pricing_basis = "estimator_override"
    line.needs_review = False
    db.commit()
    db.refresh(line)
    return _line_dict(line)


@router.get("/projects/{project_id}/cost-breakdown")
def get_cost_breakdown(
    project_id: int,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Return cost breakdown buckets for a project (paginated)."""
    _get_project_or_404(project_id, db)
    query = db.query(CostBreakdownBucket).filter(CostBreakdownBucket.project_id == project_id)
    page = paginate_query(query, offset=offset, limit=limit)
    buckets = page["items"]

    bucket_map = {b.bucket_type: b.amount for b in buckets}

    direct_cost = bucket_map.get("direct_cost", 0.0)
    final_bid = round(sum(b.amount for b in buckets), 2)

    return {
        "items": [_bucket_dict(b) for b in buckets],
        "total": page["total"],
        "offset": page["offset"],
        "limit": page["limit"],
        "direct_cost": direct_cost,
        "general_conditions": bucket_map.get("general_conditions", 0.0),
        "contingency": bucket_map.get("contingency", 0.0),
        "escalation": bucket_map.get("escalation", 0.0),
        "overhead": bucket_map.get("overhead", 0.0),
        "fee": bucket_map.get("fee", 0.0),
        "final_bid": final_bid,
    }


@router.get("/projects/{project_id}/risk-items")
def get_risk_items(
    project_id: int,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Return risk items for a project with expected_value computed (paginated)."""
    _get_project_or_404(project_id, db)
    query = db.query(RiskItem).filter(RiskItem.project_id == project_id)
    page = paginate_query(query, offset=offset, limit=limit)
    result = []
    for item in page["items"]:
        d = _risk_dict(item)
        d["expected_value"] = round((item.probability or 0.0) * (item.impact_cost or 0.0), 2)
        result.append(d)
    page["items"] = result
    return page


@router.get("/health")
def decision_health(db: Session = Depends(get_db)):
    """Decision system health check."""
    return {
        "comparable_projects": db.query(ComparableProject).count(),
        "rate_observations": db.query(HistoricalRateObservation).count(),
        "canonical_activities": db.query(CanonicalActivity).count(),
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _line_dict(ln: EstimateLine) -> dict:
    return {
        "id": ln.id,
        "project_id": ln.project_id,
        "description": ln.description,
        "division_code": ln.division_code,
        "quantity": ln.quantity,
        "unit": ln.unit,
        "recommended_unit_cost": ln.recommended_unit_cost,
        "recommended_total_cost": ln.recommended_total_cost,
        "pricing_basis": ln.pricing_basis,
        "benchmark_sample_size": ln.benchmark_sample_size,
        "benchmark_p25": ln.benchmark_p25,
        "benchmark_p50": ln.benchmark_p50,
        "benchmark_p75": ln.benchmark_p75,
        "benchmark_p90": ln.benchmark_p90,
        "benchmark_mean": ln.benchmark_mean,
        "benchmark_std_dev": ln.benchmark_std_dev,
        "benchmark_context_similarity": ln.benchmark_context_similarity,
        "confidence_score": ln.confidence_score,
        "confidence_level": ln.confidence_level,
        "needs_review": ln.needs_review,
        "explanation": ln.explanation,
    }


def _bucket_dict(b: CostBreakdownBucket) -> dict:
    return {
        "id": b.id,
        "bucket_type": b.bucket_type,
        "amount": b.amount,
        "method": b.method,
        "notes": b.notes,
    }


def _risk_dict(r: RiskItem) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "category": r.category,
        "probability": r.probability,
        "impact_cost": r.impact_cost,
        "severity": r.severity,
        "mitigation": r.mitigation,
    }
