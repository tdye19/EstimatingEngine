"""Report and data retrieval router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.gap_report import GapReport
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.estimate import Estimate
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth, get_authorized_project
from apex.backend.utils.schemas import (
    GapReportOut, TakeoffItemOut, TakeoffItemUpdate, EstimateOut,
    VarianceReportOut, ProjectActualOut, AgentRunLogOut, LaborEstimateOut,
    SpecSectionOut, APIResponse, EstimateMarkupUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["reports"], dependencies=[Depends(require_auth)])


@router.get("/{project_id}/spec-sections", response_model=APIResponse)
def get_spec_sections(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).order_by(SpecSection.section_number).all()

    def _truncate(text, limit=500):
        if not text:
            return None
        return text[:limit] + "…" if len(text) > limit else text

    data = []
    for s in sections:
        item = SpecSectionOut.model_validate(s).model_dump(mode="json")
        # Replace work_description with truncated version for list view
        item["content"] = _truncate(s.work_description)
        item["page_reference"] = None  # not stored in model
        item["status"] = "parsed"
        data.append(item)

    return APIResponse(success=True, data=data)


@router.get("/{project_id}/gap-report", response_model=APIResponse)
def get_gap_report(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    report = db.query(GapReport).filter(
        GapReport.project_id == project_id,
        GapReport.is_deleted == False,  # noqa: E712
    ).order_by(GapReport.created_at.desc()).first()

    if not report:
        return APIResponse(success=True, data=None, message="No gap report available")

    return APIResponse(
        success=True,
        data=GapReportOut.model_validate(report).model_dump(mode="json"),
    )


@router.get("/{project_id}/takeoff", response_model=APIResponse)
def get_takeoff(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    items = db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id,
        TakeoffItem.is_deleted == False,  # noqa: E712
    ).order_by(TakeoffItem.csi_code).all()

    return APIResponse(
        success=True,
        data=[TakeoffItemOut.model_validate(i).model_dump(mode="json") for i in items],
    )


@router.put("/{project_id}/takeoff/{item_id}", response_model=APIResponse)
def update_takeoff_item(
    project_id: int,
    item_id: int,
    data: TakeoffItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    item = db.query(TakeoffItem).filter(
        TakeoffItem.id == item_id,
        TakeoffItem.project_id == project_id,
        TakeoffItem.is_deleted == False,  # noqa: E712
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Takeoff item not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.is_manual_override = 1
    db.commit()
    db.refresh(item)

    return APIResponse(
        success=True,
        message="Takeoff item updated",
        data=TakeoffItemOut.model_validate(item).model_dump(mode="json"),
    )


@router.put("/{project_id}/takeoff/bulk-update", response_model=APIResponse)
def bulk_update_takeoff(
    project_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Bulk update takeoff items (e.g., mark as manual override, update notes)."""
    get_authorized_project(project_id, user, db)
    item_ids = data.get("item_ids", [])
    updates = data.get("updates", {})
    if not item_ids:
        raise HTTPException(status_code=400, detail="No item IDs provided")

    allowed_fields = {"quantity", "unit_of_measure", "notes", "description"}
    count = 0
    for item_id in item_ids:
        item = db.query(TakeoffItem).filter(
            TakeoffItem.id == item_id,
            TakeoffItem.project_id == project_id,
            TakeoffItem.is_deleted == False,  # noqa: E712
        ).first()
        if item:
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(item, field, value)
            item.is_manual_override = 1
            count += 1
    db.commit()
    return APIResponse(success=True, message=f"Updated {count} takeoff items", data={"updated": count})


@router.get("/{project_id}/labor-estimates", response_model=APIResponse)
def get_labor_estimates(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    items = db.query(LaborEstimate).filter(
        LaborEstimate.project_id == project_id,
        LaborEstimate.is_deleted == False,  # noqa: E712
    ).all()
    return APIResponse(
        success=True,
        data=[LaborEstimateOut.model_validate(i).model_dump(mode="json") for i in items],
    )


@router.get("/{project_id}/estimate", response_model=APIResponse)
def get_estimate(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    estimate = db.query(Estimate).filter(
        Estimate.project_id == project_id,
        Estimate.is_deleted == False,  # noqa: E712
    ).order_by(Estimate.version.desc()).first()

    if not estimate:
        return APIResponse(success=True, data=None, message="No estimate available")

    return APIResponse(
        success=True,
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )


@router.get("/{project_id}/estimates", response_model=APIResponse)
def list_estimate_versions(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    estimates = db.query(Estimate).filter(
        Estimate.project_id == project_id,
        Estimate.is_deleted == False,  # noqa: E712
    ).order_by(Estimate.version.desc()).all()

    data = []
    for e in estimates:
        data.append({
            "id": e.id,
            "version": e.version,
            "status": e.status,
            "total_bid_amount": e.total_bid_amount,
            "total_direct_cost": e.total_direct_cost,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return APIResponse(success=True, data=data)


@router.get("/{project_id}/estimates/{version}", response_model=APIResponse)
def get_estimate_by_version(project_id: int, version: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    estimate = db.query(Estimate).filter(
        Estimate.project_id == project_id,
        Estimate.version == version,
        Estimate.is_deleted == False,  # noqa: E712
    ).first()
    if not estimate:
        raise HTTPException(status_code=404, detail=f"Estimate version {version} not found")
    return APIResponse(
        success=True,
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )


@router.get("/{project_id}/variance", response_model=APIResponse)
def get_variance_report(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    actuals = db.query(ProjectActual).filter(
        ProjectActual.project_id == project_id,
        ProjectActual.is_deleted == False,  # noqa: E712
    ).all()

    if not actuals:
        return APIResponse(success=True, data=None, message="No actuals data available")

    items = [ProjectActualOut.model_validate(a).model_dump(mode="json") for a in actuals]

    total_est = sum(a.estimated_cost or 0 for a in actuals)
    total_act = sum(a.actual_cost or 0 for a in actuals)
    overall_var = ((total_act - total_est) / total_est * 100) if total_est > 0 else 0
    accuracy = max(0, 100 - abs(overall_var))

    # Group by division
    by_division = {}
    for a in actuals:
        div = a.csi_code[:2].strip() if a.csi_code else "00"
        if div not in by_division:
            by_division[div] = {"estimated": 0, "actual": 0, "variance": 0}
        by_division[div]["estimated"] += a.estimated_cost or 0
        by_division[div]["actual"] += a.actual_cost or 0
        by_division[div]["variance"] += a.variance_cost or 0

    report = VarianceReportOut(
        project_id=project_id,
        total_items=len(actuals),
        overall_variance_pct=round(overall_var, 2),
        accuracy_score=round(accuracy, 1),
        items=items,
        by_division=by_division,
    )

    return APIResponse(success=True, data=report.model_dump(mode="json"))


@router.get("/{project_id}/agent-logs", response_model=APIResponse)
def get_agent_logs(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    logs = db.query(AgentRunLog).filter(
        AgentRunLog.project_id == project_id,
        AgentRunLog.is_deleted == False,  # noqa: E712
    ).order_by(AgentRunLog.agent_number, AgentRunLog.created_at.desc()).all()

    return APIResponse(
        success=True,
        data=[AgentRunLogOut.model_validate(log).model_dump(mode="json") for log in logs],
    )


@router.put("/{project_id}/estimate/{estimate_id}/markups", response_model=APIResponse)
def update_estimate_markups(
    project_id: int,
    estimate_id: int,
    data: EstimateMarkupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    estimate = db.query(Estimate).filter(
        Estimate.id == estimate_id,
        Estimate.project_id == project_id,
        Estimate.is_deleted == False,  # noqa: E712
    ).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(estimate, field, value)

    # Recalculate amounts from direct cost
    estimate.gc_markup_amount = estimate.total_direct_cost * (estimate.gc_markup_pct / 100)
    estimate.overhead_amount = estimate.total_direct_cost * (estimate.overhead_pct / 100)
    estimate.profit_amount = estimate.total_direct_cost * (estimate.profit_pct / 100)
    estimate.contingency_amount = estimate.total_direct_cost * (estimate.contingency_pct / 100)
    estimate.total_bid_amount = (
        estimate.total_direct_cost
        + estimate.gc_markup_amount
        + estimate.overhead_amount
        + estimate.profit_amount
        + estimate.contingency_amount
    )

    db.commit()
    db.refresh(estimate)

    return APIResponse(
        success=True,
        message="Estimate markups updated",
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )
