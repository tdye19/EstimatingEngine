"""Decision system API routes — estimate workflow endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.engines.assembly import AssemblyEngine
from apex.backend.engines.benchmarking import BenchmarkingEngine
from apex.backend.models.decision_models import (
    BidOutcome,
    CanonicalActivity,
    ComparableProject,
    CostBreakdownBucket,
    EstimateLine,
    EstimatorOverride,
    HistoricalRateObservation,
    RiskItem,
)
from apex.backend.models.project import Project

router = APIRouter(tags=["decision"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProjectContextUpdate(BaseModel):
    project_type: Optional[str] = None
    market_sector: Optional[str] = None
    region: Optional[str] = None
    delivery_method: Optional[str] = None
    contract_type: Optional[str] = None
    complexity_level: Optional[str] = None
    schedule_pressure: Optional[str] = None
    size_sf: Optional[float] = None
    scope_types: Optional[str] = None


class QuantityItem(BaseModel):
    description: str
    quantity: float
    unit: Optional[str] = None
    division_code: Optional[str] = None


class EstimateRequest(BaseModel):
    quantities: list[QuantityItem]
    created_by: Optional[str] = None


class OverrideRequest(BaseModel):
    overridden_value: float
    override_type: str  # "unit_cost" or "total"
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    created_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_project(project_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _serialize_line(line: EstimateLine) -> dict:
    return {
        "id": line.id,
        "project_id": line.project_id,
        "estimate_run_id": line.estimate_run_id,
        "description": line.description,
        "division_code": line.division_code,
        "quantity": line.quantity,
        "unit": line.unit,
        "recommended_unit_cost": line.recommended_unit_cost,
        "recommended_total_cost": line.recommended_total_cost,
        "pricing_basis": line.pricing_basis,
        "benchmark_sample_size": line.benchmark_sample_size,
        "benchmark_p25": line.benchmark_p25,
        "benchmark_p50": line.benchmark_p50,
        "benchmark_p75": line.benchmark_p75,
        "benchmark_p90": line.benchmark_p90,
        "benchmark_mean": line.benchmark_mean,
        "benchmark_std_dev": line.benchmark_std_dev,
        "benchmark_context_similarity": line.benchmark_context_similarity,
        "confidence_score": line.confidence_score,
        "confidence_level": line.confidence_level,
        "missing_quantity": line.missing_quantity,
        "needs_review": line.needs_review,
        "explanation": line.explanation,
        "created_at": line.created_at.isoformat() if line.created_at else None,
    }


def _serialize_bucket(b: CostBreakdownBucket) -> dict:
    return {
        "id": b.id,
        "project_id": b.project_id,
        "bucket_type": b.bucket_type,
        "amount": b.amount,
        "method": b.method,
        "notes": b.notes,
    }


def _serialize_risk(r: RiskItem) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "name": r.name,
        "category": r.category,
        "probability": r.probability,
        "impact_cost": r.impact_cost,
        "impact_time_days": r.impact_time_days,
        "severity": r.severity,
        "mitigation": r.mitigation,
        "source": r.source,
        "expected_value": round((r.probability or 0) * (r.impact_cost or 0), 2),
    }


# ---------------------------------------------------------------------------
# PROJECT CONTEXT
# ---------------------------------------------------------------------------

@router.patch("/api/projects/{project_id}/context")
def update_project_context(
    project_id: int,
    body: ProjectContextUpdate,
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        if hasattr(project, field):
            setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name,
            "project_type": getattr(project, "project_type", None),
            "market_sector": getattr(project, "market_sector", None),
            "region": getattr(project, "region", None),
            "delivery_method": getattr(project, "delivery_method", None),
            "contract_type": getattr(project, "contract_type", None),
            "complexity_level": getattr(project, "complexity_level", None),
            "schedule_pressure": getattr(project, "schedule_pressure", None),
            "size_sf": getattr(project, "size_sf", None),
            "scope_types": getattr(project, "scope_types", None)}


# ---------------------------------------------------------------------------
# COMPARABLE PROJECTS
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/comparable-projects")
def list_comparable_projects(
    project_id: int,
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, db)
    engine = BenchmarkingEngine(db)
    scored = engine.get_comparable_projects(project)

    obs_counts = {}
    for comp_id, count in (
        db.query(
            HistoricalRateObservation.comparable_project_id,
            db.query(HistoricalRateObservation)
            .filter(HistoricalRateObservation.comparable_project_id ==
                    HistoricalRateObservation.comparable_project_id)
            .count
        )
        if False else []
    ):
        obs_counts[comp_id] = count

    # Simpler: bulk count per project
    from sqlalchemy import func
    counts_q = (
        db.query(
            HistoricalRateObservation.comparable_project_id,
            func.count(HistoricalRateObservation.id).label("cnt"),
        )
        .group_by(HistoricalRateObservation.comparable_project_id)
        .all()
    )
    obs_counts = {row[0]: row[1] for row in counts_q}

    results = []
    for comp, sim in scored:
        results.append({
            "id": comp.id,
            "name": comp.name,
            "project_type": comp.project_type,
            "region": comp.region,
            "delivery_method": comp.delivery_method,
            "final_contract_value": comp.final_contract_value,
            "data_quality_score": comp.data_quality_score,
            "context_similarity": round(sim, 4),
            "observation_count": obs_counts.get(comp.id, 0),
        })
    return results


# ---------------------------------------------------------------------------
# BENCHMARKS
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/benchmarks/{activity_name}")
def get_benchmark(
    project_id: int,
    activity_name: str,
    division_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, db)
    engine = BenchmarkingEngine(db)
    result = engine.benchmark_activity(project, activity_name, division_code)
    return result


# ---------------------------------------------------------------------------
# ESTIMATE EXECUTION
# ---------------------------------------------------------------------------

@router.post("/api/projects/{project_id}/estimate")
def run_estimate(
    project_id: int,
    body: EstimateRequest,
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, db)
    engine = AssemblyEngine(db)
    quantities = [q.model_dump() for q in body.quantities]
    result = engine.run_estimate(project, quantities)

    return {
        "line_count": result["line_count"],
        "direct_cost": result["direct_cost"],
        "needs_review_count": result["needs_review_count"],
        "low_confidence_count": result["low_confidence_count"],
        "final_bid_value": result["final_bid_value"],
        "risk_item_count": result["risk_item_count"],
        "estimate_lines": [_serialize_line(l) for l in result["lines"]],
        "cost_breakdown": [_serialize_bucket(b) for b in result["cost_breakdown"]],
        "risk_items": [_serialize_risk(r) for r in result["risk_items"]],
    }


# ---------------------------------------------------------------------------
# ESTIMATE LINES
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/estimate-lines")
def get_estimate_lines(
    project_id: int,
    db: Session = Depends(get_db),
):
    _get_project(project_id, db)
    lines = (
        db.query(EstimateLine)
        .filter(EstimateLine.project_id == project_id)
        .order_by(EstimateLine.division_code, EstimateLine.description)
        .all()
    )
    return [_serialize_line(l) for l in lines]


# ---------------------------------------------------------------------------
# OVERRIDE
# ---------------------------------------------------------------------------

@router.post("/api/estimate-lines/{line_id}/override")
def override_estimate_line(
    line_id: str,
    body: OverrideRequest,
    db: Session = Depends(get_db),
):
    line = db.query(EstimateLine).filter(EstimateLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Estimate line not found")

    if body.override_type == "unit_cost":
        original_value = line.recommended_unit_cost or 0.0
        line.recommended_unit_cost = body.overridden_value
        line.recommended_total_cost = round(line.quantity * body.overridden_value, 2)
    elif body.override_type == "total":
        original_value = line.recommended_total_cost or 0.0
        line.recommended_total_cost = round(body.overridden_value, 2)
        if line.quantity and line.quantity > 0:
            line.recommended_unit_cost = round(body.overridden_value / line.quantity, 2)
    else:
        raise HTTPException(status_code=400, detail="override_type must be 'unit_cost' or 'total'")

    line.pricing_basis = "estimator_override"
    line.needs_review = False

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
    db.commit()
    db.refresh(override)

    return {
        "id": override.id,
        "estimate_line_id": override.estimate_line_id,
        "original_value": override.original_value,
        "overridden_value": override.overridden_value,
        "override_type": override.override_type,
        "reason_code": override.reason_code,
        "reason_text": override.reason_text,
        "created_by": override.created_by,
        "created_at": override.created_at.isoformat() if override.created_at else None,
    }


# ---------------------------------------------------------------------------
# COST BREAKDOWN
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/cost-breakdown")
def get_cost_breakdown(
    project_id: int,
    db: Session = Depends(get_db),
):
    _get_project(project_id, db)
    buckets = (
        db.query(CostBreakdownBucket)
        .filter(CostBreakdownBucket.project_id == project_id)
        .all()
    )
    bucket_map = {b.bucket_type: b.amount for b in buckets}

    direct_cost = bucket_map.get("direct_cost", 0.0)
    final_bid = round(sum(b.amount for b in buckets), 2)

    return {
        "direct_cost": direct_cost,
        "general_conditions": bucket_map.get("general_conditions", 0.0),
        "contingency": bucket_map.get("contingency", 0.0),
        "escalation": bucket_map.get("escalation", 0.0),
        "overhead": bucket_map.get("overhead", 0.0),
        "fee": bucket_map.get("fee", 0.0),
        "final_bid": final_bid,
        "buckets": [_serialize_bucket(b) for b in buckets],
    }


# ---------------------------------------------------------------------------
# RISK ITEMS
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/risk-items")
def get_risk_items(
    project_id: int,
    db: Session = Depends(get_db),
):
    _get_project(project_id, db)
    items = (
        db.query(RiskItem)
        .filter(RiskItem.project_id == project_id)
        .all()
    )
    return [_serialize_risk(r) for r in items]


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------

@router.get("/api/decision/health")
def decision_health(db: Session = Depends(get_db)):
    return {
        "comparable_projects": db.query(ComparableProject).count(),
        "rate_observations": db.query(HistoricalRateObservation).count(),
        "canonical_activities": db.query(CanonicalActivity).count(),
    }
