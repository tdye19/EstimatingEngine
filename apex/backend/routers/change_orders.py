"""Change order router — create, update, and track scope changes after initial estimate."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.change_order import ChangeOrder
from apex.backend.models.project import Project
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    APIResponse,
    ChangeOrderCreate,
    ChangeOrderOut,
    ChangeOrderUpdate,
)

router = APIRouter(
    prefix="/api/projects",
    tags=["change-orders"],
    dependencies=[Depends(require_auth)],
)


def _get_project_or_404(project_id: int, db: Session) -> Project:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _next_co_number(project_id: int, db: Session) -> str:
    count = db.query(ChangeOrder).filter(
        ChangeOrder.project_id == project_id,
    ).count()
    return f"CO-{count + 1:03d}"


@router.get("/{project_id}/change-orders", response_model=APIResponse)
def list_change_orders(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    orders = (
        db.query(ChangeOrder)
        .filter(
            ChangeOrder.project_id == project_id,
            ChangeOrder.is_deleted == False,  # noqa: E712
        )
        .order_by(ChangeOrder.created_at.asc())
        .all()
    )
    return APIResponse(
        success=True,
        data=[ChangeOrderOut.model_validate(co).model_dump(mode="json") for co in orders],
    )


@router.post("/{project_id}/change-orders", response_model=APIResponse)
def create_change_order(
    project_id: int,
    data: ChangeOrderCreate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    co = ChangeOrder(
        project_id=project_id,
        co_number=_next_co_number(project_id, db),
        title=data.title,
        description=data.description,
        csi_code=data.csi_code,
        change_type=data.change_type,
        requested_by=data.requested_by,
        cost_impact=data.cost_impact,
        schedule_impact_days=data.schedule_impact_days,
        status=data.status,
    )
    db.add(co)
    db.commit()
    db.refresh(co)
    return APIResponse(
        success=True,
        message=f"Change order {co.co_number} created",
        data=ChangeOrderOut.model_validate(co).model_dump(mode="json"),
    )


@router.put("/{project_id}/change-orders/{co_id}", response_model=APIResponse)
def update_change_order(
    project_id: int,
    co_id: int,
    data: ChangeOrderUpdate,
    db: Session = Depends(get_db),
):
    co = db.query(ChangeOrder).filter(
        ChangeOrder.id == co_id,
        ChangeOrder.project_id == project_id,
        ChangeOrder.is_deleted == False,  # noqa: E712
    ).first()
    if not co:
        raise HTTPException(status_code=404, detail="Change order not found")

    updates = data.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(co, field, value)

    # Auto-stamp approval time when status transitions to approved
    if data.status == "approved" and co.approved_at is None:
        co.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(co)
    return APIResponse(
        success=True,
        message="Change order updated",
        data=ChangeOrderOut.model_validate(co).model_dump(mode="json"),
    )


@router.delete("/{project_id}/change-orders/{co_id}", response_model=APIResponse)
def delete_change_order(
    project_id: int,
    co_id: int,
    db: Session = Depends(get_db),
):
    co = db.query(ChangeOrder).filter(
        ChangeOrder.id == co_id,
        ChangeOrder.project_id == project_id,
        ChangeOrder.is_deleted == False,  # noqa: E712
    ).first()
    if not co:
        raise HTTPException(status_code=404, detail="Change order not found")
    co.is_deleted = True
    db.commit()
    return APIResponse(success=True, message="Change order deleted")


@router.get("/{project_id}/change-orders/summary", response_model=APIResponse)
def change_order_summary(project_id: int, db: Session = Depends(get_db)):
    """Return aggregate cost and schedule impact by status."""
    _get_project_or_404(project_id, db)
    orders = db.query(ChangeOrder).filter(
        ChangeOrder.project_id == project_id,
        ChangeOrder.is_deleted == False,  # noqa: E712
    ).all()

    total_approved_cost = sum(co.cost_impact for co in orders if co.status == "approved")
    total_pending_cost = sum(co.cost_impact for co in orders if co.status == "pending")
    total_schedule_impact = sum(
        co.schedule_impact_days for co in orders if co.status == "approved"
    )

    by_status: dict = {}
    for co in orders:
        by_status.setdefault(co.status, 0)
        by_status[co.status] += 1

    return APIResponse(
        success=True,
        data={
            "total_orders": len(orders),
            "by_status": by_status,
            "total_approved_cost": total_approved_cost,
            "total_pending_cost": total_pending_cost,
            "total_schedule_impact_days": total_schedule_impact,
        },
    )
