"""Admin router — user and organization management (admin-only)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.organization import Organization
from apex.backend.models.user import User
from apex.backend.utils.auth import require_role
from apex.backend.utils.schemas import (
    APIResponse,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_admin = require_role("admin")


# ── Users ────────────────────────────────────────────────────────────


@router.get("/users", response_model=APIResponse)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    org_id: int | None = Query(None),
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.is_deleted == False)  # noqa: E712
    if org_id is not None:
        query = query.filter(User.organization_id == org_id)
    users = query.offset(skip).limit(limit).all()
    return APIResponse(data=[UserOut.model_validate(u).model_dump() for u in users])


@router.put("/users/{user_id}", response_model=APIResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "is_active":
            user.is_deleted = not value
        else:
            setattr(user, field, value)

    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return APIResponse(data=UserOut.model_validate(user).model_dump())


# ── Organizations ────────────────────────────────────────────────────


@router.get("/organizations", response_model=APIResponse)
def list_organizations(
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    orgs = db.query(Organization).filter(Organization.is_deleted == False).all()  # noqa: E712
    return APIResponse(data=[OrganizationOut.model_validate(o).model_dump() for o in orgs])


@router.post("/organizations", response_model=APIResponse, status_code=201)
def create_organization(
    body: OrganizationCreate,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    org = Organization(**body.model_dump())
    db.add(org)
    db.commit()
    db.refresh(org)
    return APIResponse(data=OrganizationOut.model_validate(org).model_dump())


@router.put("/organizations/{org_id}", response_model=APIResponse)
def update_organization(
    org_id: int,
    body: OrganizationUpdate,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_deleted == False).first()  # noqa: E712
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)

    org.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(org)
    return APIResponse(data=OrganizationOut.model_validate(org).model_dump())


@router.post("/projects/{project_id}/agent-3/force-rule-based")
def force_rule_based_gap_analysis(
    project_id: int,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    """Re-run Agent 3 with force_rule_based=True for empirical rule validation.

    Creates a new GapReport row alongside the existing LLM report. The LLM
    report is untouched. The AgentRunLog entry is tagged " (force_rule_based)"
    so it is distinguishable from normal pipeline runs.
    """
    from apex.backend.agents.agent_3_gap_analysis import run_gap_analysis_agent
    from apex.backend.models.agent_run_log import AgentRunLog
    from apex.backend.models.gap_report import GapReport
    from apex.backend.models.project import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    log = AgentRunLog(
        project_id=project_id,
        agent_name="Scope Analysis Agent (force_rule_based)",
        agent_number=3,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        result = run_gap_analysis_agent(db, project_id, force_rule_based=True)
        log.status = "completed"
        log.completed_at = datetime.utcnow()
        log.duration_seconds = (log.completed_at - log.started_at).total_seconds()
        log.output_summary = f"force_rule_based: {result.get('total_gaps', 0)} gaps"
        log.output_data = result
        db.commit()
    except Exception as exc:
        log.status = "failed"
        log.completed_at = datetime.utcnow()
        log.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))

    gap_report_id = result.get("report_id")
    report = db.query(GapReport).filter(GapReport.id == gap_report_id).first()

    return APIResponse(
        data={
            "gap_report_id": gap_report_id,
            "analysis_method": (report.metadata_json or {}).get("analysis_method") if report else None,
            "total_gaps": result.get("total_gaps"),
            "critical_count": result.get("critical_count"),
            "moderate_count": result.get("moderate_count"),
            "watch_count": result.get("watch_count"),
            "overall_score": result.get("overall_score"),
            "sections_analyzed": result.get("sections_analyzed"),
            "agent_run_log_id": log.id,
        }
    )


@router.delete("/organizations/{org_id}", status_code=204)
def delete_organization(
    org_id: int,
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_deleted == False).first()  # noqa: E712
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.is_deleted = True
    org.updated_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
