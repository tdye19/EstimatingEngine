"""Decision system API routes.

Architecture §13: API contract for the estimating decision system.

Routes:
  POST   /estimate-runs                          — start a new estimate run
  GET    /estimate-runs/{run_id}                 — get run status + totals
  GET    /estimate-runs/{run_id}/scope-items     — list scope items
  PATCH  /scope-items/{item_id}                  — update scope item status
  POST   /estimate-runs/{run_id}/scope-items/manual  — add manual scope item
  GET    /estimate-runs/{run_id}/quantities       — list quantity items
  PATCH  /quantity-items/{qty_id}                — update a quantity
  GET    /estimate-runs/{run_id}/estimate-lines   — list estimate lines
  PATCH  /estimate-lines/{line_id}               — accept / override a line
  POST   /estimate-lines/{line_id}/override       — capture estimator override
  GET    /estimate-runs/{run_id}/risk-items       — list risk items
  POST   /estimate-runs/{run_id}/risk-items       — add a risk item
  PATCH  /risk-items/{risk_id}                    — update a risk item
  GET    /estimate-runs/{run_id}/cost-breakdown    — commercial rollup
  POST   /estimate-runs/{run_id}/bid-outcome       — record bid result
  GET    /comparable-projects                      — list comparable projects
  POST   /comparable-projects                      — add comparable project
  GET    /ontology/activities                      — list canonical activities
  POST   /estimate-runs/{run_id}/price             — run pricing engine
"""

import json
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.utils.auth import require_auth
from apex.backend.utils.pagination import paginate_query

router = APIRouter(prefix="/api/decision", tags=["decision-system"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EstimateRunCreate(BaseModel):
    project_id: int
    created_by: Optional[str] = None
    context_snapshot: Optional[dict] = None


class EstimateRunOut(BaseModel):
    id: str
    project_id: int
    version_number: int
    run_status: str
    started_at: datetime
    completed_at: Optional[datetime]
    total_direct_cost: Optional[float]
    total_indirect_cost: Optional[float]
    total_risk: Optional[float]
    total_escalation: Optional[float]
    total_fee: Optional[float]
    final_bid_value: Optional[float]

    class Config:
        from_attributes = True


class ScopeItemCreate(BaseModel):
    canonical_name: str
    division_code: Optional[str] = None
    work_package: Optional[str] = None
    activity_family: Optional[str] = None
    scope_status: str = "review_required"
    inclusion_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    description: Optional[str] = None
    notes: Optional[str] = None


class ScopeItemPatch(BaseModel):
    scope_status: Optional[str] = None
    inclusion_confidence: Optional[float] = None
    notes: Optional[str] = None


class ScopeItemOut(BaseModel):
    id: str
    estimate_run_id: str
    canonical_name: str
    division_code: Optional[str]
    scope_status: str
    inclusion_confidence: float
    description: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


class QuantityPatch(BaseModel):
    quantity_value: Optional[float] = None
    unit: Optional[str] = None
    source: Optional[str] = None


class EstimateLinePatch(BaseModel):
    line_status: Optional[str] = None   # accepted | overridden | excluded
    estimator_unit_cost: Optional[float] = None
    estimator_total_cost: Optional[float] = None


class OverrideCreate(BaseModel):
    original_value: float
    overridden_value: float
    override_type: str  # unit_cost | quantity | scope_status | line_excluded
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    created_by: Optional[str] = None


class RiskItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    probability: float = Field(default=0.5, ge=0.0, le=1.0)
    impact_cost: float = Field(default=0.0, ge=0.0)
    impact_time_days: Optional[int] = None
    severity: str = "medium"
    mitigation: Optional[str] = None
    source: Optional[str] = None
    linked_scope_item_id: Optional[str] = None


class RiskItemOut(BaseModel):
    id: str
    estimate_run_id: str
    name: str
    category: Optional[str]
    probability: float
    impact_cost: float
    severity: str
    expected_value: float   # computed: probability × impact_cost

    class Config:
        from_attributes = True


class BidOutcomeCreate(BaseModel):
    outcome: str   # won | lost | no_bid | pending
    final_bid_submitted: Optional[float] = None
    winning_bid_value: Optional[float] = None
    delta_to_winner: Optional[float] = None
    notes: Optional[str] = None


class ComparableProjectCreate(BaseModel):
    name: str
    project_type: str
    region: str
    market_sector: Optional[str] = None
    size_sf: Optional[float] = None
    contract_type: Optional[str] = None
    delivery_method: Optional[str] = None
    scope_types: Optional[List[str]] = None
    complexity_level: Optional[str] = None
    schedule_pressure: Optional[str] = None
    data_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_system: Optional[str] = None


class PriceRunRequest(BaseModel):
    """Trigger the pricing engine for scope items in this run that have quantities."""
    min_quantity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_run_or_404(run_id: str, db: Session):
    from apex.backend.models.decision_models import EstimateRun
    run = db.query(EstimateRun).filter(EstimateRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"EstimateRun {run_id} not found")
    return run


# ── Estimate runs ─────────────────────────────────────────────────────────────

@router.post("/estimate-runs", status_code=status.HTTP_201_CREATED)
def create_estimate_run(
    body: EstimateRunCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Start a new versioned estimate run for a project. §13.3"""
    from apex.backend.models.decision_models import EstimateRun
    from apex.backend.models.project import Project

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Auto-increment version
    from sqlalchemy import func
    max_ver = db.query(func.max(EstimateRun.version_number)).filter(
        EstimateRun.project_id == body.project_id
    ).scalar() or 0

    ctx_snapshot = body.context_snapshot
    if ctx_snapshot is None:
        # Build from project context fields
        ctx_snapshot = {
            "project_type": project.project_type,
            "market_sector": getattr(project, "market_sector", None),
            "region": project.location,
            "size_sf": project.square_footage,
            "delivery_method": getattr(project, "delivery_method", None),
            "contract_type": getattr(project, "contract_type", None),
            "complexity_level": getattr(project, "complexity_level", None),
            "schedule_pressure": getattr(project, "schedule_pressure", None),
        }

    run = EstimateRun(
        project_id=body.project_id,
        version_number=max_ver + 1,
        run_status="in_progress",
        created_by=body.created_by,
        context_snapshot=json.dumps(ctx_snapshot),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "version_number": run.version_number, "run_status": run.run_status}


@router.get("/estimate-runs/{run_id}")
def get_estimate_run(
    run_id: str,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    run = _get_run_or_404(run_id, db)
    return {
        "id": run.id,
        "project_id": run.project_id,
        "version_number": run.version_number,
        "run_status": run.run_status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "total_direct_cost": run.total_direct_cost,
        "total_indirect_cost": run.total_indirect_cost,
        "total_risk": run.total_risk,
        "total_escalation": run.total_escalation,
        "total_fee": run.total_fee,
        "final_bid_value": run.final_bid_value,
    }


# ── Scope items ───────────────────────────────────────────────────────────────

@router.get("/estimate-runs/{run_id}/scope-items")
def list_scope_items(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """List scope items for a run (paginated). §13.4"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import ScopeItem
    query = db.query(ScopeItem).filter(ScopeItem.estimate_run_id == run_id)
    page = paginate_query(query, offset=offset, limit=limit)
    page["items"] = [
        {
            "id": s.id,
            "canonical_name": s.canonical_name,
            "division_code": s.division_code,
            "scope_status": s.scope_status,
            "inclusion_confidence": s.inclusion_confidence,
            "description": s.description,
            "notes": s.notes,
        }
        for s in page["items"]
    ]
    return page


@router.post("/estimate-runs/{run_id}/scope-items/manual", status_code=201)
def add_manual_scope_item(
    run_id: str,
    body: ScopeItemCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Manually add a scope item to a run. §13.4"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import ScopeItem
    item = ScopeItem(
        estimate_run_id=run_id,
        canonical_name=body.canonical_name,
        division_code=body.division_code,
        work_package=body.work_package,
        activity_family=body.activity_family,
        scope_status=body.scope_status,
        inclusion_confidence=body.inclusion_confidence,
        description=body.description,
        notes=body.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "canonical_name": item.canonical_name}


@router.patch("/scope-items/{item_id}")
def patch_scope_item(
    item_id: str,
    body: ScopeItemPatch,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Update scope item status. §13.4"""
    from apex.backend.models.decision_models import ScopeItem
    item = db.query(ScopeItem).filter(ScopeItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="ScopeItem not found")
    if body.scope_status is not None:
        item.scope_status = body.scope_status
    if body.inclusion_confidence is not None:
        item.inclusion_confidence = body.inclusion_confidence
    if body.notes is not None:
        item.notes = body.notes
    db.commit()
    return {"id": item.id, "scope_status": item.scope_status}


# ── Quantities ────────────────────────────────────────────────────────────────

@router.get("/estimate-runs/{run_id}/quantities")
def list_quantities(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """List quantity items for a run (paginated). §13.5"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import QuantityItem
    query = db.query(QuantityItem).filter(QuantityItem.estimate_run_id == run_id)
    page = paginate_query(query, offset=offset, limit=limit)
    page["items"] = [
        {
            "id": q.id,
            "scope_item_id": q.scope_item_id,
            "quantity_value": q.quantity_value,
            "unit": q.unit,
            "source": q.source,
            "quantity_confidence": q.quantity_confidence,
            "missing_flag": q.missing_flag,
        }
        for q in page["items"]
    ]
    return page


@router.patch("/quantity-items/{qty_id}")
def patch_quantity(
    qty_id: str,
    body: QuantityPatch,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Estimator updates a quantity. §13.5"""
    from apex.backend.models.decision_models import QuantityItem
    item = db.query(QuantityItem).filter(QuantityItem.id == qty_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="QuantityItem not found")
    if body.quantity_value is not None:
        item.quantity_value = body.quantity_value
        item.missing_flag = False
        item.quantity_confidence = max(item.quantity_confidence, 0.9)
        item.source = body.source or "manual"
    if body.unit is not None:
        item.unit = body.unit
    db.commit()
    return {"id": item.id, "quantity_value": item.quantity_value, "unit": item.unit}


# ── Estimate lines ────────────────────────────────────────────────────────────

@router.get("/estimate-runs/{run_id}/estimate-lines")
def list_estimate_lines(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """List estimate lines for a run (paginated). §13.7"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import EstimateLine
    query = db.query(EstimateLine).filter(EstimateLine.estimate_run_id == run_id)
    page = paginate_query(query, offset=offset, limit=limit)
    page["items"] = [
        {
            "id": l.id,
            "description": l.description,
            "division_code": l.division_code,
            "quantity": l.quantity,
            "unit": l.unit,
            "recommended_unit_cost": l.recommended_unit_cost,
            "recommended_total_cost": l.recommended_total_cost,
            "estimator_unit_cost": l.estimator_unit_cost,
            "estimator_total_cost": l.estimator_total_cost,
            "pricing_basis": l.pricing_basis,
            "benchmark_p50": l.benchmark_p50,
            "benchmark_sample_size": l.benchmark_sample_size,
            "confidence_level": l.confidence_level,
            "line_status": l.line_status,
            "missing_quantity": l.missing_quantity,
            "explanation": l.explanation,
        }
        for l in page["items"]
    ]
    return page


@router.patch("/estimate-lines/{line_id}")
def patch_estimate_line(
    line_id: str,
    body: EstimateLinePatch,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Accept or override an estimate line. §13.7"""
    from apex.backend.models.decision_models import EstimateLine
    line = db.query(EstimateLine).filter(EstimateLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="EstimateLine not found")
    if body.line_status is not None:
        line.line_status = body.line_status
    if body.estimator_unit_cost is not None:
        line.estimator_unit_cost = body.estimator_unit_cost
        line.estimator_total_cost = round(body.estimator_unit_cost * line.quantity, 2)
        line.line_status = "overridden"
    if body.estimator_total_cost is not None:
        line.estimator_total_cost = body.estimator_total_cost
    db.commit()
    return {"id": line.id, "line_status": line.line_status}


@router.post("/estimate-lines/{line_id}/override", status_code=201)
def create_override(
    line_id: str,
    body: OverrideCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Capture an estimator override. §13.7 / §9.16"""
    from apex.backend.models.decision_models import EstimateLine, EstimatorOverride
    line = db.query(EstimateLine).filter(EstimateLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="EstimateLine not found")
    override = EstimatorOverride(
        estimate_run_id=line.estimate_run_id,
        estimate_line_id=line_id,
        original_value=body.original_value,
        overridden_value=body.overridden_value,
        override_type=body.override_type,
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        created_by=body.created_by,
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    return {"id": override.id, "override_type": override.override_type}


# ── Risk items ────────────────────────────────────────────────────────────────

@router.get("/estimate-runs/{run_id}/risk-items")
def list_risk_items(
    run_id: str,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """List risk items with expected values. §13.8"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import RiskItem
    items = db.query(RiskItem).filter(RiskItem.estimate_run_id == run_id).all()
    total_ev = sum(r.probability * r.impact_cost for r in items)
    return {
        "total_expected_value": round(total_ev, 2),
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "category": r.category,
                "probability": r.probability,
                "impact_cost": r.impact_cost,
                "expected_value": round(r.probability * r.impact_cost, 2),
                "severity": r.severity,
                "mitigation": r.mitigation,
            }
            for r in items
        ],
    }


@router.post("/estimate-runs/{run_id}/risk-items", status_code=201)
def add_risk_item(
    run_id: str,
    body: RiskItemCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Register a risk item for a run. §13.8"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import RiskItem
    risk = RiskItem(
        estimate_run_id=run_id,
        name=body.name,
        category=body.category,
        probability=body.probability,
        impact_cost=body.impact_cost,
        impact_time_days=body.impact_time_days,
        severity=body.severity,
        mitigation=body.mitigation,
        source=body.source,
        linked_scope_item_id=body.linked_scope_item_id,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return {
        "id": risk.id,
        "expected_value": round(risk.probability * risk.impact_cost, 2),
    }


# ── Commercial rollup ─────────────────────────────────────────────────────────

@router.get("/estimate-runs/{run_id}/cost-breakdown")
def get_cost_breakdown(
    run_id: str,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Get commercial rollup for a run. §13.9"""
    _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import CostBreakdownBucket
    buckets = db.query(CostBreakdownBucket).filter(
        CostBreakdownBucket.estimate_run_id == run_id
    ).all()
    breakdown = {b.bucket_type: b.amount for b in buckets}
    total = sum(breakdown.values())
    return {"buckets": breakdown, "total": round(total, 2)}


# ── Bid outcomes ──────────────────────────────────────────────────────────────

@router.post("/estimate-runs/{run_id}/bid-outcome", status_code=201)
def record_bid_outcome(
    run_id: str,
    body: BidOutcomeCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Record post-bid result. §13.10"""
    run = _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import BidOutcome
    outcome = BidOutcome(
        project_id=run.project_id,
        estimate_run_id=run_id,
        outcome=body.outcome,
        final_bid_submitted=body.final_bid_submitted,
        winning_bid_value=body.winning_bid_value,
        delta_to_winner=body.delta_to_winner,
        notes=body.notes,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return {"id": outcome.id, "outcome": outcome.outcome}


# ── Comparable projects ───────────────────────────────────────────────────────

@router.get("/comparable-projects")
def list_comparable_projects(
    project_type: Optional[str] = None,
    region: Optional[str] = None,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    from apex.backend.models.decision_models import ComparableProject
    q = db.query(ComparableProject)
    if project_type:
        q = q.filter(ComparableProject.project_type == project_type)
    if region:
        q = q.filter(ComparableProject.region == region)
    projects = q.all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "project_type": p.project_type,
            "region": p.region,
            "market_sector": p.market_sector,
            "size_sf": p.size_sf,
            "data_quality_score": p.data_quality_score,
        }
        for p in projects
    ]


@router.post("/comparable-projects", status_code=201)
def create_comparable_project(
    body: ComparableProjectCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    from apex.backend.models.decision_models import ComparableProject
    cp = ComparableProject(
        name=body.name,
        project_type=body.project_type,
        region=body.region,
        market_sector=body.market_sector,
        size_sf=body.size_sf,
        contract_type=body.contract_type,
        delivery_method=body.delivery_method,
        scope_types=json.dumps(body.scope_types) if body.scope_types else None,
        complexity_level=body.complexity_level,
        schedule_pressure=body.schedule_pressure,
        data_quality_score=body.data_quality_score,
        source_system=body.source_system,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return {"id": cp.id, "name": cp.name}


# ── Ontology ──────────────────────────────────────────────────────────────────

@router.get("/ontology/activities")
def list_canonical_activities(
    scope_family: Optional[str] = None,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    from apex.backend.models.decision_models import CanonicalActivity
    q = db.query(CanonicalActivity).filter(CanonicalActivity.is_active == True)
    if scope_family:
        q = q.filter(CanonicalActivity.scope_family == scope_family)
    activities = q.all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "division_code": a.division_code,
            "expected_unit": a.expected_unit,
            "scope_family": a.scope_family,
            "typical_cost_bucket": a.typical_cost_bucket,
            "aliases": [al.alias for al in a.aliases],
        }
        for a in activities
    ]


# ── Pricing engine trigger ────────────────────────────────────────────────────

@router.post("/estimate-runs/{run_id}/price")
def run_pricing_engine(
    run_id: str,
    body: PriceRunRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    """Run the pricing engine for all scope items in this run that have quantities.

    Deterministic — no LLM. §12.5
    """
    run = _get_run_or_404(run_id, db)
    from apex.backend.models.decision_models import ScopeItem, QuantityItem, EstimateLine
    from apex.backend.models.project import Project
    from apex.backend.services.pricing_engine import PricingEngine
    from apex.backend.services.benchmarking_engine.context import ProjectContext

    project = db.query(Project).filter(Project.id == run.project_id).first()
    ctx = ProjectContext.from_project(project)

    engine = PricingEngine(db, ctx)

    # Clear existing lines for this run before repricing
    db.query(EstimateLine).filter(EstimateLine.estimate_run_id == run_id).delete()
    db.flush()

    scope_items = db.query(ScopeItem).filter(ScopeItem.estimate_run_id == run_id).all()
    lines_created = 0

    for item in scope_items:
        if item.scope_status == "excluded":
            continue

        # Find best quantity for this scope item
        qty_row = (
            db.query(QuantityItem)
            .filter(
                QuantityItem.estimate_run_id == run_id,
                QuantityItem.scope_item_id == item.id,
                QuantityItem.quantity_confidence >= body.min_quantity_confidence,
            )
            .order_by(QuantityItem.quantity_confidence.desc())
            .first()
        )

        quantity = qty_row.quantity_value if qty_row and not qty_row.missing_flag else None
        unit = qty_row.unit if qty_row else None

        priced = engine.price_scope_item(
            canonical_name=item.canonical_name,
            division_code=item.division_code,
            quantity=quantity,
            unit=unit,
        )
        engine.persist_estimate_line(
            db=db,
            estimate_run_id=run_id,
            scope_item_id=item.id,
            benchmark_result_id=None,
            priced=priced,
        )
        lines_created += 1

    db.commit()
    return {"lines_created": lines_created, "run_id": run_id}
