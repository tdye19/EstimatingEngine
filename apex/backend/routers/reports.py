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
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    GapReportOut, TakeoffItemOut, TakeoffItemUpdate, EstimateOut,
    VarianceReportOut, ProjectActualOut, AgentRunLogOut, LaborEstimateOut,
    APIResponse,
)

router = APIRouter(prefix="/api/projects", tags=["reports"], dependencies=[Depends(require_auth)])


@router.get("/{project_id}/gap-report", response_model=APIResponse)
def get_gap_report(project_id: int, db: Session = Depends(get_db)):
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
def get_takeoff(project_id: int, db: Session = Depends(get_db)):
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
):
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


@router.get("/{project_id}/labor-estimates", response_model=APIResponse)
def get_labor_estimates(project_id: int, db: Session = Depends(get_db)):
    items = db.query(LaborEstimate).filter(
        LaborEstimate.project_id == project_id,
        LaborEstimate.is_deleted == False,  # noqa: E712
    ).all()
    return APIResponse(
        success=True,
        data=[LaborEstimateOut.model_validate(i).model_dump(mode="json") for i in items],
    )


@router.get("/{project_id}/estimate", response_model=APIResponse)
def get_estimate(project_id: int, db: Session = Depends(get_db)):
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


@router.get("/{project_id}/variance", response_model=APIResponse)
def get_variance_report(project_id: int, db: Session = Depends(get_db)):
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
def get_agent_logs(project_id: int, db: Session = Depends(get_db)):
    logs = db.query(AgentRunLog).filter(
        AgentRunLog.project_id == project_id,
        AgentRunLog.is_deleted == False,  # noqa: E712
    ).order_by(AgentRunLog.agent_number, AgentRunLog.created_at.desc()).all()

    return APIResponse(
        success=True,
        data=[AgentRunLogOut.model_validate(log).model_dump(mode="json") for log in logs],
    )
