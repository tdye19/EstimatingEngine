"""Bid comparison router — upload competitor bids or historical actuals and
overlay them against the current estimate to spot over/under pricing."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.bid_comparison import BidComparison, BidComparisonItem
from apex.backend.models.estimate import Estimate
from apex.backend.models.project import Project
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    APIResponse,
    BidComparisonCreate,
    BidComparisonOut,
)

router = APIRouter(
    prefix="/api/projects",
    tags=["bid-comparison"],
    dependencies=[Depends(require_auth)],
)


def _get_project_or_404(project_id: int, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ── CRUD ──────────────────────────────────────────────────────────────────────


@router.get("/{project_id}/bid-comparisons", response_model=APIResponse)
def list_comparisons(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    comps = (
        db.query(BidComparison)
        .filter(
            BidComparison.project_id == project_id,
            BidComparison.is_deleted == False,  # noqa: E712
        )
        .order_by(BidComparison.created_at.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data=[BidComparisonOut.model_validate(c).model_dump(mode="json") for c in comps],
    )


@router.post("/{project_id}/bid-comparisons", response_model=APIResponse)
def create_comparison(
    project_id: int,
    data: BidComparisonCreate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    comp = BidComparison(
        project_id=project_id,
        name=data.name,
        source_type=data.source_type,
        bid_date=data.bid_date,
        total_bid_amount=data.total_bid_amount,
        notes=data.notes,
    )
    db.add(comp)
    db.flush()  # get comp.id before adding items

    for item_data in data.items:
        item = BidComparisonItem(
            comparison_id=comp.id,
            **item_data.model_dump(),
        )
        db.add(item)

    db.commit()
    db.refresh(comp)
    return APIResponse(
        success=True,
        message="Comparison created",
        data=BidComparisonOut.model_validate(comp).model_dump(mode="json"),
    )


@router.delete("/{project_id}/bid-comparisons/{comparison_id}", response_model=APIResponse)
def delete_comparison(
    project_id: int,
    comparison_id: int,
    db: Session = Depends(get_db),
):
    comp = (
        db.query(BidComparison)
        .filter(
            BidComparison.id == comparison_id,
            BidComparison.project_id == project_id,
            BidComparison.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    comp.is_deleted = True
    db.commit()
    return APIResponse(success=True, message="Deleted")


# ── Overlay endpoint — merge estimate + all comparisons ───────────────────────


@router.get("/{project_id}/bid-comparisons/overlay", response_model=APIResponse)
def get_overlay(project_id: int, db: Session = Depends(get_db)):
    """Return the current estimate's division costs alongside all active comparisons,
    structured for chart rendering."""
    _get_project_or_404(project_id, db)

    estimate = (
        db.query(Estimate)
        .filter(
            Estimate.project_id == project_id,
            Estimate.is_deleted == False,  # noqa: E712
        )
        .order_by(Estimate.version.desc())
        .first()
    )

    # Build estimate division totals from line items
    estimate_by_div: dict[str, float] = {}
    if estimate and estimate.line_items:
        for li in estimate.line_items:
            div = li.division_number or "00"
            estimate_by_div[div] = estimate_by_div.get(div, 0.0) + (li.total_cost or 0.0)

    comps = (
        db.query(BidComparison)
        .filter(
            BidComparison.project_id == project_id,
            BidComparison.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    # All unique divisions across estimate + comparisons
    all_divs: set[str] = set(estimate_by_div.keys())
    comp_data = []
    for comp in comps:
        by_div: dict[str, float] = {}
        for item in comp.items:
            div = item.division_number or "00"
            by_div[div] = by_div.get(div, 0.0) + (item.amount or 0.0)
        all_divs.update(by_div.keys())
        comp_data.append(
            {
                "id": comp.id,
                "name": comp.name,
                "source_type": comp.source_type,
                "total_bid_amount": comp.total_bid_amount,
                "by_division": by_div,
            }
        )

    sorted_divs = sorted(all_divs)

    # Chart-ready rows: one object per division with a column per dataset
    rows = []
    for div in sorted_divs:
        row: dict = {"division": div, "apex_estimate": estimate_by_div.get(div, 0.0)}
        for cd in comp_data:
            row[cd["name"]] = cd["by_division"].get(div, 0.0)
        rows.append(row)

    return APIResponse(
        success=True,
        data={
            "divisions": sorted_divs,
            "apex_total": estimate.total_bid_amount if estimate else 0.0,
            "comparisons": comp_data,
            "chart_rows": rows,
        },
    )
