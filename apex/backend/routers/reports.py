"""Report and data retrieval router."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.estimate import Estimate
from apex.backend.models.gap_report import GapReport
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.user import User
from apex.backend.utils.auth import get_authorized_project, require_auth
from apex.backend.utils.csi_utils import parse_csi_division
from apex.backend.utils.schemas import (
    AgentRunLogOut,
    APIResponse,
    EstimateMarkupUpdate,
    EstimateOut,
    EstimateVersionOut,
    GapReportOut,
    LaborEstimateOut,
    ProjectActualOut,
    SpecSectionOut,
    TakeoffItemOut,
    TakeoffItemUpdate,
    VarianceReportOut,
)

router = APIRouter(prefix="/api/projects", tags=["reports"], dependencies=[Depends(require_auth)])


@router.get("/{project_id}/intelligence-report", response_model=APIResponse)
def get_intelligence_report(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Return the latest Intelligence Report for this project."""
    get_authorized_project(project_id, user, db)
    report = (
        db.query(IntelligenceReportModel)
        .filter_by(project_id=project_id)
        .order_by(IntelligenceReportModel.version.desc())
        .first()
    )

    if not report:
        return APIResponse(
            success=True,
            data={"status": "no_report", "message": "Run the pipeline to generate an intelligence report."},
        )

    return APIResponse(
        success=True,
        data={
            "report_id": report.id,
            "version": report.version,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
            "overall_risk_level": report.overall_risk_level,
            "confidence_score": report.confidence_score,
            "takeoff_item_count": report.takeoff_item_count,
            "takeoff_total_labor": report.takeoff_total_labor,
            "takeoff_total_material": report.takeoff_total_material,
            "rate_intelligence": json.loads(report.rate_intelligence_json) if report.rate_intelligence_json else {},
            "field_calibration": json.loads(report.field_calibration_json) if report.field_calibration_json else {},
            "scope_risk": json.loads(report.scope_risk_json) if report.scope_risk_json else {},
            "comparable_projects": json.loads(report.comparable_projects_json)
            if report.comparable_projects_json
            else {},
            "spec_sections_parsed": report.spec_sections_parsed,
            "material_specs_extracted": report.material_specs_extracted,
            "executive_narrative": report.executive_narrative,
            "narrative_method": report.narrative_method,
            "pb_projects_loaded": report.pb_projects_loaded,
            "pb_activities_available": report.pb_activities_available,
        },
    )


@router.get("/{project_id}/spec-sections", response_model=APIResponse)
def get_spec_sections(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .order_by(SpecSection.section_number)
        .all()
    )

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
    report = (
        db.query(GapReport)
        .filter(
            GapReport.project_id == project_id,
            GapReport.is_deleted == False,  # noqa: E712
        )
        .order_by(GapReport.created_at.desc())
        .first()
    )

    if not report:
        return APIResponse(success=True, data=None, message="No gap report available")

    return APIResponse(
        success=True,
        data=GapReportOut.model_validate(report).model_dump(mode="json"),
    )


@router.get("/{project_id}/takeoff", response_model=APIResponse)
def get_takeoff(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    items = (
        db.query(TakeoffItem)
        .filter(
            TakeoffItem.project_id == project_id,
            TakeoffItem.is_deleted == False,  # noqa: E712
        )
        .order_by(TakeoffItem.csi_code)
        .all()
    )

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
    item = (
        db.query(TakeoffItem)
        .filter(
            TakeoffItem.id == item_id,
            TakeoffItem.project_id == project_id,
            TakeoffItem.is_deleted == False,  # noqa: E712
        )
        .first()
    )
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
        item = (
            db.query(TakeoffItem)
            .filter(
                TakeoffItem.id == item_id,
                TakeoffItem.project_id == project_id,
                TakeoffItem.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        if item:
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(item, field, value)
            item.is_manual_override = 1
            count += 1
    db.commit()
    return APIResponse(success=True, message=f"Updated {count} takeoff items", data={"updated": count})


@router.get("/{project_id}/rate-intelligence", response_model=APIResponse)
def get_rate_intelligence(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Return Agent 4 v2 rate recommendations for this project."""
    import json as _json

    from apex.backend.models.takeoff_v2 import TakeoffItemV2

    get_authorized_project(project_id, user, db)
    rows = (
        db.query(TakeoffItemV2)
        .filter(
            TakeoffItemV2.project_id == project_id,
        )
        .order_by(TakeoffItemV2.row_number)
        .all()
    )

    recommendations = []
    flags_count = {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0, "NEEDS_RATE": 0}
    deltas = []

    for r in rows:
        flag = r.flag or "NO_DATA"
        flags_count[flag] = flags_count.get(flag, 0) + 1

        try:
            projects = _json.loads(r.matching_projects) if r.matching_projects else []
        except (ValueError, TypeError):
            projects = []

        if r.delta_pct is not None and flag != "NO_DATA":
            deltas.append(r.delta_pct)

        recommendations.append(
            {
                "line_item_row": r.row_number,
                "activity": r.activity,
                "unit": r.unit,
                "crew": r.crew,
                "wbs_area": r.wbs_area,
                "estimator_rate": r.production_rate,
                "historical_avg_rate": r.historical_avg_rate,
                "historical_min_rate": r.historical_min_rate,
                "historical_max_rate": r.historical_max_rate,
                "historical_spread": None,
                "sample_count": r.sample_count or 0,
                "confidence": r.confidence or "none",
                "delta_pct": r.delta_pct,
                "flag": flag,
                "matching_projects": projects,
                "labor_cost_per_unit": r.labor_cost_per_unit,
                "material_cost_per_unit": r.material_cost_per_unit,
            }
        )

    items_matched = sum(1 for r in recommendations if r["flag"] != "NO_DATA")
    optimism = round(sum(deltas) / len(deltas), 2) if deltas else None

    return APIResponse(
        success=True,
        data={
            "takeoff_items_parsed": len(rows),
            "items_matched": items_matched,
            "items_unmatched": len(rows) - items_matched,
            "recommendations": recommendations,
            "flags_summary": flags_count,
            "overall_optimism_score": optimism,
            "parse_format": None,
        },
    )


@router.get("/{project_id}/field-calibration", response_model=APIResponse)
def get_field_calibration(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Return Agent 5 v2 field actuals comparisons for this project."""
    from apex.backend.models.takeoff_v2 import TakeoffItemV2
    from apex.backend.services.field_actuals.service import FieldActualsService

    get_authorized_project(project_id, user, db)

    rows = (
        db.query(TakeoffItemV2)
        .filter(
            TakeoffItemV2.project_id == project_id,
        )
        .order_by(TakeoffItemV2.row_number)
        .all()
    )

    if not rows:
        return APIResponse(
            success=True,
            data={
                "items_compared": 0,
                "items_with_field_data": 0,
                "items_without_field_data": 0,
                "comparisons": [],
                "avg_calibration_factor": None,
                "calibration_summary": {"optimistic": 0, "conservative": 0, "aligned": 0, "no_data": 0},
            },
        )

    fa_service = FieldActualsService(db)
    comparisons = []
    cal_factors = []
    dir_counts = {"optimistic": 0, "conservative": 0, "aligned": 0, "no_data": 0}

    for row in rows:
        est_rate = row.production_rate
        est_avg = row.historical_avg_rate
        field_match = fa_service.match_field_data(activity=row.activity, unit=row.unit)

        if field_match and field_match["avg_rate"]:
            field_avg = field_match["avg_rate"]
            est_to_field = round(((est_avg - field_avg) / field_avg) * 100, 2) if est_avg and est_avg > 0 else None
            entered_to_field = (
                round(((est_rate - field_avg) / field_avg) * 100, 2) if est_rate and est_rate > 0 else None
            )
            cal_factor = round(field_avg / est_avg, 4) if est_avg and est_avg > 0 else None

            direction = "no_data"
            if cal_factor is not None:
                cal_factors.append(cal_factor)
                direction = "optimistic" if cal_factor < 0.90 else "conservative" if cal_factor > 1.10 else "aligned"

            dir_counts[direction] += 1
            comparisons.append(
                {
                    "line_item_row": row.row_number,
                    "activity": row.activity,
                    "unit": row.unit,
                    "estimator_rate": est_rate,
                    "estimating_avg_rate": est_avg,
                    "field_avg_rate": field_avg,
                    "field_sample_count": field_match["sample_count"],
                    "estimating_to_field_delta_pct": est_to_field,
                    "entered_to_field_delta_pct": entered_to_field,
                    "calibration_factor": cal_factor,
                    "calibration_direction": direction,
                    "recommendation": "",
                    "field_projects": field_match["projects"],
                }
            )
        else:
            dir_counts["no_data"] += 1
            comparisons.append(
                {
                    "line_item_row": row.row_number,
                    "activity": row.activity,
                    "unit": row.unit,
                    "estimator_rate": est_rate,
                    "estimating_avg_rate": est_avg,
                    "field_avg_rate": None,
                    "field_sample_count": 0,
                    "estimating_to_field_delta_pct": None,
                    "entered_to_field_delta_pct": None,
                    "calibration_factor": None,
                    "calibration_direction": "no_data",
                    "recommendation": "No field actuals available for this activity.",
                    "field_projects": [],
                }
            )

    avg_cal = round(sum(cal_factors) / len(cal_factors), 4) if cal_factors else None

    return APIResponse(
        success=True,
        data={
            "items_compared": len(comparisons),
            "items_with_field_data": sum(1 for c in comparisons if c["calibration_direction"] != "no_data"),
            "items_without_field_data": sum(1 for c in comparisons if c["calibration_direction"] == "no_data"),
            "comparisons": comparisons,
            "avg_calibration_factor": avg_cal,
            "calibration_summary": dir_counts,
        },
    )


@router.get("/{project_id}/labor-estimates", response_model=APIResponse)
def get_labor_estimates(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    items = (
        db.query(LaborEstimate)
        .filter(
            LaborEstimate.project_id == project_id,
            LaborEstimate.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    return APIResponse(
        success=True,
        data=[LaborEstimateOut.model_validate(i).model_dump(mode="json") for i in items],
    )


@router.get("/{project_id}/estimate", response_model=APIResponse)
def get_estimate(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
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

    return APIResponse(
        success=True,
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )


@router.get("/{project_id}/estimates", response_model=APIResponse)
def list_estimate_versions(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    estimates = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .all()
    )

    data = []
    for e in estimates:
        data.append(
            {
                "id": e.id,
                "version": e.version,
                "status": e.status,
                "total_bid_amount": e.total_bid_amount,
                "total_direct_cost": e.total_direct_cost,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )
    return APIResponse(success=True, data=data)


@router.get("/{project_id}/estimates/{version}", response_model=APIResponse)
def get_estimate_by_version(
    project_id: int, version: int, db: Session = Depends(get_db), user: User = Depends(require_auth)
):
    get_authorized_project(project_id, user, db)
    estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.version == version,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail=f"Estimate version {version} not found")
    return APIResponse(
        success=True,
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )


@router.get("/{project_id}/variance", response_model=APIResponse)
def get_variance_report(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    actuals = (
        db.query(ProjectActual)
        .filter(
            ProjectActual.project_id == project_id,
            ProjectActual.is_deleted == False,  # noqa: E712
        )
        .all()
    )

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
        div = parse_csi_division(a.csi_code)
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


@router.get("/{project_id}/estimate/versions", response_model=APIResponse)
def list_estimate_versions_legacy(project_id: int, db: Session = Depends(get_db)):
    """List all saved estimate versions for a project (newest first)."""
    versions = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data=[EstimateVersionOut.model_validate(e).model_dump(mode="json") for e in versions],
    )


@router.get("/{project_id}/estimate/versions/{version_num}", response_model=APIResponse)
def get_estimate_version(project_id: int, version_num: int, db: Session = Depends(get_db)):
    """Get a specific estimate version."""
    estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.version == version_num,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail=f"Version {version_num} not found")
    return APIResponse(
        success=True,
        data=EstimateOut.model_validate(estimate).model_dump(mode="json"),
    )


@router.post("/{project_id}/estimate/snapshot", response_model=APIResponse)
def snapshot_estimate(project_id: int, db: Session = Depends(get_db)):
    """Create a new versioned snapshot of the current estimate (increments version number)."""
    from apex.backend.models.estimate import EstimateLineItem

    current = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="No estimate to snapshot")

    next_version = current.version + 1

    # Deep-copy the estimate record
    snapshot = Estimate(
        project_id=project_id,
        version=next_version,
        status="draft",
        total_direct_cost=current.total_direct_cost,
        total_labor_cost=current.total_labor_cost,
        total_material_cost=current.total_material_cost,
        total_subcontractor_cost=current.total_subcontractor_cost,
        gc_markup_pct=current.gc_markup_pct,
        gc_markup_amount=current.gc_markup_amount,
        overhead_pct=current.overhead_pct,
        overhead_amount=current.overhead_amount,
        profit_pct=current.profit_pct,
        profit_amount=current.profit_amount,
        contingency_pct=current.contingency_pct,
        contingency_amount=current.contingency_amount,
        total_bid_amount=current.total_bid_amount,
        exclusions=current.exclusions,
        assumptions=current.assumptions,
        alternates=current.alternates,
        bid_bond_required=current.bid_bond_required,
        executive_summary=current.executive_summary,
    )
    db.add(snapshot)
    db.flush()

    # Copy line items
    for li in current.line_items:
        new_li = EstimateLineItem(
            estimate_id=snapshot.id,
            division_number=li.division_number,
            csi_code=li.csi_code,
            description=li.description,
            quantity=li.quantity,
            unit_of_measure=li.unit_of_measure,
            labor_cost=li.labor_cost,
            material_cost=li.material_cost,
            equipment_cost=li.equipment_cost,
            subcontractor_cost=li.subcontractor_cost,
            total_cost=li.total_cost,
            unit_cost=li.unit_cost,
            notes=li.notes,
        )
        db.add(new_li)

    db.commit()
    db.refresh(snapshot)
    return APIResponse(
        success=True,
        message=f"Estimate snapshot created as version {next_version}",
        data=EstimateVersionOut.model_validate(snapshot).model_dump(mode="json"),
    )


@router.get("/{project_id}/agent-logs", response_model=APIResponse)
def get_agent_logs(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    logs = (
        db.query(AgentRunLog)
        .filter(
            AgentRunLog.project_id == project_id,
            AgentRunLog.is_deleted == False,  # noqa: E712
        )
        .order_by(AgentRunLog.agent_number, AgentRunLog.created_at.desc())
        .all()
    )

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
    estimate = (
        db.query(Estimate)
        .filter(
            Estimate.id == estimate_id,
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .first()
    )
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
