"""Multi-project analytics dashboard API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.decision_models import BidOutcome
from apex.backend.models.estimate import Estimate
from apex.backend.models.project import Project
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth, require_role
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)


@router.get("/summary", response_model=APIResponse)
def dashboard_summary(db: Session = Depends(get_db)):
    """Total projects, active count, total bid volume, win rate."""
    total = db.query(func.count(Project.id)).filter(Project.is_deleted == False).scalar()  # noqa: E712
    active = (
        db.query(func.count(Project.id))
        .filter(
            Project.is_deleted == False,  # noqa: E712
            Project.status.in_(["draft", "estimating", "bid_submitted"]),
        )
        .scalar()
    )

    total_bid_volume = (
        db.query(func.coalesce(func.sum(Project.estimated_value), 0.0))
        .filter(Project.is_deleted == False)  # noqa: E712
        .scalar()
    )

    # Win rate from bid_outcomes
    total_outcomes = db.query(func.count(BidOutcome.id)).filter(BidOutcome.outcome.in_(["won", "lost"])).scalar()
    wins = db.query(func.count(BidOutcome.id)).filter(BidOutcome.outcome == "won").scalar()
    win_rate = round(wins / total_outcomes * 100, 1) if total_outcomes > 0 else None

    return APIResponse(
        success=True,
        data={
            "total_projects": total,
            "active_projects": active,
            "total_bid_volume": float(total_bid_volume),
            "win_rate": win_rate,
            "total_bids_tracked": total_outcomes,
        },
    )


@router.get("/win-loss", response_model=APIResponse)
def win_loss_analysis(
    project_type: str | None = Query(None),
    region: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Win/loss rates by project_type, with optional filters."""
    query = (
        db.query(
            Project.project_type,
            BidOutcome.outcome,
            func.count(BidOutcome.id).label("count"),
        )
        .join(BidOutcome, BidOutcome.project_id == Project.id)
        .filter(BidOutcome.outcome.in_(["won", "lost"]))
    )
    if project_type:
        query = query.filter(Project.project_type == project_type)
    if region:
        query = query.filter(Project.region == region)

    rows = query.group_by(Project.project_type, BidOutcome.outcome).all()

    # Aggregate
    by_type: dict = {}
    for ptype, outcome, count in rows:
        key = ptype or "unknown"
        entry = by_type.setdefault(key, {"won": 0, "lost": 0})
        entry[outcome] = count

    result = []
    for ptype, counts in sorted(by_type.items()):
        total = counts["won"] + counts["lost"]
        result.append(
            {
                "project_type": ptype,
                "won": counts["won"],
                "lost": counts["lost"],
                "total": total,
                "win_rate": round(counts["won"] / total * 100, 1) if total > 0 else 0,
            }
        )

    return APIResponse(success=True, data=result)


@router.get("/variance", response_model=APIResponse)
def estimate_vs_actual_variance(db: Session = Depends(get_db)):
    """Estimate vs actual variance — returns empty if no actuals data."""
    try:
        from apex.backend.models.project_actual import ProjectActual
    except ImportError:
        return APIResponse(success=True, data=[])

    rows = (
        db.query(
            Project.id,
            Project.name,
            Project.project_type,
            Project.estimated_value,
            ProjectActual.actual_total_cost,
        )
        .join(ProjectActual, ProjectActual.project_id == Project.id)
        .filter(
            Project.is_deleted == False,  # noqa: E712
            Project.estimated_value.isnot(None),
            ProjectActual.actual_total_cost.isnot(None),
        )
        .all()
    )

    result = []
    for pid, name, ptype, estimated, actual in rows:
        variance = actual - estimated
        variance_pct = round(variance / estimated * 100, 2) if estimated else None
        result.append(
            {
                "project_id": pid,
                "project_name": name,
                "project_type": ptype,
                "estimated_value": estimated,
                "actual_cost": actual,
                "variance": round(variance, 2),
                "variance_pct": variance_pct,
            }
        )

    return APIResponse(success=True, data=result)


@router.get("/estimator-metrics", response_model=APIResponse)
def estimator_metrics(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Admin-only: productivity per estimator."""
    rows = (
        db.query(
            User.id,
            User.email,
            User.full_name,
            func.count(Project.id).label("project_count"),
            func.coalesce(func.sum(Project.estimated_value), 0.0).label("total_bid_volume"),
        )
        .outerjoin(Project, Project.owner_id == User.id)
        .filter(User.is_deleted == False)  # noqa: E712
        .group_by(User.id, User.email, User.full_name)
        .all()
    )

    result = []
    for uid, email, name, proj_count, bid_vol in rows:
        # Count estimates per user
        est_count = (
            db.query(func.count(Estimate.id))
            .join(Project, Estimate.project_id == Project.id)
            .filter(Project.owner_id == uid, Estimate.is_deleted == False)  # noqa: E712
            .scalar()
        )
        result.append(
            {
                "user_id": uid,
                "email": email,
                "full_name": name,
                "project_count": proj_count,
                "estimate_count": est_count,
                "total_bid_volume": float(bid_vol),
            }
        )

    return APIResponse(success=True, data=result)
