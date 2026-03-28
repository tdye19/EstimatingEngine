"""Estimate Library router — searchable archive of completed estimates."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.estimate import Estimate
from apex.backend.models.estimate_library import EstimateLibraryEntry, EstimateLibraryTag
from apex.backend.models.project import Project
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse
from apex.backend.models.user import User

# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class LibraryEntryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    building_type: Optional[str] = None
    square_footage: Optional[float] = None
    total_cost: float
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_zip: Optional[str] = None
    bid_date: Optional[date] = None
    status: Optional[str] = "completed"
    bid_result: Optional[str] = None
    csi_divisions: Optional[dict] = None
    line_item_count: Optional[int] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = "manual"
    original_file_path: Optional[str] = None
    notes: Optional[str] = None
    is_template: Optional[bool] = False
    project_id: Optional[int] = None
    estimate_id: Optional[int] = None


class LibraryEntryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_type: Optional[str] = None
    building_type: Optional[str] = None
    square_footage: Optional[float] = None
    total_cost: Optional[float] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_zip: Optional[str] = None
    bid_date: Optional[date] = None
    status: Optional[str] = None
    bid_result: Optional[str] = None
    csi_divisions: Optional[dict] = None
    line_item_count: Optional[int] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    original_file_path: Optional[str] = None
    notes: Optional[str] = None
    is_template: Optional[bool] = None


class LibraryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: Optional[int]
    estimate_id: Optional[int]
    name: str
    description: Optional[str]
    project_type: Optional[str]
    building_type: Optional[str]
    square_footage: Optional[float]
    total_cost: float
    cost_per_sqft: Optional[float]
    location_city: Optional[str]
    location_state: Optional[str]
    location_zip: Optional[str]
    bid_date: Optional[date]
    status: str
    bid_result: Optional[str]
    csi_divisions_json: Optional[str]
    line_item_count: Optional[int]
    tags: Optional[str]
    source: str
    original_file_path: Optional[str]
    notes: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    is_template: bool
    organization_id: Optional[int]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _entry_to_dict(entry: EstimateLibraryEntry) -> dict:
    """Serialize an entry to a plain dict, parsing csi_divisions_json."""
    d = LibraryEntryOut.model_validate(entry).model_dump()
    # Replace raw JSON string with parsed object for API consumers
    raw = d.pop("csi_divisions_json", None)
    d["csi_divisions"] = json.loads(raw) if raw else {}
    # Normalize tag list from library_tags relationship
    d["tag_list"] = [t.tag for t in entry.library_tags]
    return d


def _apply_tags(db: Session, entry: EstimateLibraryEntry, tags: List[str]) -> None:
    """Replace the normalized tag rows for an entry."""
    db.query(EstimateLibraryTag).filter(EstimateLibraryTag.entry_id == entry.id).delete()
    seen: set[str] = set()
    for raw in tags:
        t = raw.strip().lower()
        if t and t not in seen:
            seen.add(t)
            db.add(EstimateLibraryTag(entry_id=entry.id, tag=t))


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/api/estimate-library",
    tags=["estimate-library"],
    dependencies=[Depends(require_auth)],
)


# GET /stats/summary — must come BEFORE /{entry_id}
@router.get("/stats/summary", response_model=APIResponse)
def stats_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Aggregate statistics across the library."""
    entries = (
        db.query(EstimateLibraryEntry)
        .filter(
            EstimateLibraryEntry.is_deleted == False,  # noqa: E712
            EstimateLibraryEntry.organization_id == current_user.organization_id,
        )
        .all()
    )

    total = len(entries)

    # cost/sqft by project_type
    type_buckets: dict[str, list[float]] = {}
    for e in entries:
        if e.project_type and e.cost_per_sqft:
            type_buckets.setdefault(e.project_type, []).append(e.cost_per_sqft)

    avg_cost_per_sqft_by_type = {
        pt: round(sum(vals) / len(vals), 2)
        for pt, vals in type_buckets.items()
    }

    # cost/sqft by state
    state_buckets: dict[str, list[float]] = {}
    for e in entries:
        if e.location_state and e.cost_per_sqft:
            state_buckets.setdefault(e.location_state, []).append(e.cost_per_sqft)

    avg_cost_per_sqft_by_state = {
        st: round(sum(vals) / len(vals), 2)
        for st, vals in state_buckets.items()
    }

    # Win/loss ratio by project_type
    wl_buckets: dict[str, dict[str, int]] = {}
    for e in entries:
        if e.project_type and e.bid_result in ("won", "lost"):
            bucket = wl_buckets.setdefault(e.project_type, {"won": 0, "lost": 0})
            bucket[e.bid_result] += 1

    win_loss_by_type = {}
    for pt, counts in wl_buckets.items():
        total_bids = counts["won"] + counts["lost"]
        win_loss_by_type[pt] = {
            "won": counts["won"],
            "lost": counts["lost"],
            "win_rate": round(counts["won"] / total_bids, 4) if total_bids else None,
        }

    return APIResponse(
        success=True,
        data={
            "total_entries": total,
            "avg_cost_per_sqft_by_project_type": avg_cost_per_sqft_by_type,
            "avg_cost_per_sqft_by_state": avg_cost_per_sqft_by_state,
            "win_loss_by_project_type": win_loss_by_type,
        },
    )


# GET /compare — must come BEFORE /{entry_id}
@router.get("/compare", response_model=APIResponse)
def compare_entries(
    ids: str = Query(..., description="Comma-separated list of 2–5 entry IDs"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Return 2–5 library entries side-by-side for comparison."""
    raw_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if len(raw_ids) < 2 or len(raw_ids) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide between 2 and 5 entry IDs.",
        )
    try:
        entry_ids = [int(i) for i in raw_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="IDs must be integers.")

    entries = (
        db.query(EstimateLibraryEntry)
        .filter(
            EstimateLibraryEntry.id.in_(entry_ids),
            EstimateLibraryEntry.is_deleted == False,  # noqa: E712
            EstimateLibraryEntry.organization_id == current_user.organization_id,
        )
        .all()
    )

    found_ids = {e.id for e in entries}
    missing = set(entry_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"Entries not found: {sorted(missing)}")

    # Return in the requested order
    id_to_entry = {e.id: e for e in entries}
    return APIResponse(
        success=True,
        data={"entries": [_entry_to_dict(id_to_entry[i]) for i in entry_ids]},
    )


# GET /
@router.get("/", response_model=APIResponse)
def list_entries(
    project_type: Optional[str] = Query(None),
    building_type: Optional[str] = Query(None),
    min_cost: Optional[float] = Query(None),
    max_cost: Optional[float] = Query(None),
    min_sqft: Optional[float] = Query(None),
    max_sqft: Optional[float] = Query(None),
    status: Optional[str] = Query(None),
    bid_result: Optional[str] = Query(None),
    location_state: Optional[str] = Query(None),
    tag: Optional[str] = Query(None, description="Filter by a single tag (exact match)"),
    search: Optional[str] = Query(None, description="Full-text search across name, description, tags"),
    is_template: Optional[bool] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List library entries with optional filters and pagination."""
    q = db.query(EstimateLibraryEntry).filter(
        EstimateLibraryEntry.is_deleted == False  # noqa: E712
    )

    if project_type:
        q = q.filter(EstimateLibraryEntry.project_type == project_type)
    if building_type:
        q = q.filter(EstimateLibraryEntry.building_type == building_type)
    if min_cost is not None:
        q = q.filter(EstimateLibraryEntry.total_cost >= min_cost)
    if max_cost is not None:
        q = q.filter(EstimateLibraryEntry.total_cost <= max_cost)
    if min_sqft is not None:
        q = q.filter(EstimateLibraryEntry.square_footage >= min_sqft)
    if max_sqft is not None:
        q = q.filter(EstimateLibraryEntry.square_footage <= max_sqft)
    if status:
        q = q.filter(EstimateLibraryEntry.status == status)
    if bid_result:
        q = q.filter(EstimateLibraryEntry.bid_result == bid_result)
    if location_state:
        q = q.filter(EstimateLibraryEntry.location_state == location_state)
    if is_template is not None:
        q = q.filter(EstimateLibraryEntry.is_template == is_template)

    if tag:
        # Join to tag table for normalized tag filtering
        q = q.join(EstimateLibraryTag).filter(
            EstimateLibraryTag.tag == tag.strip().lower()
        )

    if search:
        like = f"%{search}%"
        q = q.filter(
            EstimateLibraryEntry.name.ilike(like)
            | EstimateLibraryEntry.description.ilike(like)
            | EstimateLibraryEntry.tags.ilike(like)
        )

    total = q.count()

    # Sorting
    sort_col = getattr(EstimateLibraryEntry, sort_by, None)
    if sort_col is None:
        sort_col = EstimateLibraryEntry.created_at
    if sort_order.lower() == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    entries = q.offset(skip).limit(limit).all()

    return APIResponse(
        success=True,
        data={
            "total": total,
            "skip": skip,
            "limit": limit,
            "entries": [_entry_to_dict(e) for e in entries],
        },
    )


# GET /{entry_id}
@router.get("/{entry_id}", response_model=APIResponse)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    """Retrieve a single library entry by ID."""
    entry = db.query(EstimateLibraryEntry).filter(
        EstimateLibraryEntry.id == entry_id,
        EstimateLibraryEntry.is_deleted == False,  # noqa: E712
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")
    return APIResponse(success=True, data=_entry_to_dict(entry))


# POST /
@router.post("/", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: LibraryEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Manually create a new library entry."""
    entry = EstimateLibraryEntry(
        project_id=body.project_id,
        estimate_id=body.estimate_id,
        name=body.name,
        description=body.description,
        project_type=body.project_type,
        building_type=body.building_type,
        square_footage=body.square_footage,
        total_cost=body.total_cost,
        location_city=body.location_city,
        location_state=body.location_state,
        location_zip=body.location_zip,
        bid_date=body.bid_date,
        status=body.status or "completed",
        bid_result=body.bid_result,
        line_item_count=body.line_item_count,
        tags=",".join(body.tags) if body.tags else None,
        source=body.source or "manual",
        original_file_path=body.original_file_path,
        notes=body.notes,
        created_by=current_user.id,
        organization_id=current_user.organization_id,
        is_template=body.is_template or False,
    )
    if body.csi_divisions:
        entry.set_csi_divisions(body.csi_divisions)
    entry.recalculate_cost_per_sqft()

    db.add(entry)
    db.flush()  # get entry.id before adding tags

    if body.tags:
        _apply_tags(db, entry, body.tags)

    db.commit()
    db.refresh(entry)
    return APIResponse(
        success=True,
        message="Library entry created",
        data=_entry_to_dict(entry),
    )


# POST /from-project/{project_id}
@router.post(
    "/from-project/{project_id}",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_from_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Auto-create a library entry from a project's latest completed estimate."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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
        raise HTTPException(
            status_code=404,
            detail="No estimate found for this project",
        )

    # Build CSI division breakdown from line items
    csi_divisions: dict[str, float] = {}
    for li in estimate.line_items or []:
        div = li.division_number or "00"
        csi_divisions[div] = csi_divisions.get(div, 0.0) + (li.total_cost or 0.0)

    entry = EstimateLibraryEntry(
        project_id=project_id,
        estimate_id=estimate.id,
        name=f"{project.name} — v{estimate.version}",
        description=estimate.executive_summary,
        project_type=project.project_type,
        square_footage=project.square_footage,
        total_cost=estimate.total_bid_amount or 0.0,
        location_city=None,
        location_state=None,
        location_zip=None,
        bid_date=date.fromisoformat(project.bid_date) if project.bid_date else None,
        status="completed",
        line_item_count=len(estimate.line_items) if estimate.line_items else 0,
        source="pipeline",
        created_by=current_user.id,
        organization_id=current_user.organization_id,
        is_template=False,
    )
    if csi_divisions:
        entry.set_csi_divisions(csi_divisions)
    entry.recalculate_cost_per_sqft()

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return APIResponse(
        success=True,
        message="Library entry created from project pipeline data",
        data=_entry_to_dict(entry),
    )


# PUT /{entry_id}
@router.put("/{entry_id}", response_model=APIResponse)
def update_entry(
    entry_id: int,
    body: LibraryEntryUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing library entry."""
    entry = db.query(EstimateLibraryEntry).filter(
        EstimateLibraryEntry.id == entry_id,
        EstimateLibraryEntry.is_deleted == False,  # noqa: E712
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")

    update_fields = body.model_dump(exclude_none=True, exclude={"csi_divisions", "tags"})
    for field, value in update_fields.items():
        setattr(entry, field, value)

    if body.csi_divisions is not None:
        entry.set_csi_divisions(body.csi_divisions)

    if body.tags is not None:
        entry.tags = ",".join(body.tags)
        _apply_tags(db, entry, body.tags)

    entry.recalculate_cost_per_sqft()

    db.commit()
    db.refresh(entry)
    return APIResponse(
        success=True,
        message="Library entry updated",
        data=_entry_to_dict(entry),
    )


# DELETE /{entry_id}
@router.delete("/{entry_id}", response_model=APIResponse)
def delete_entry(
    entry_id: int,
    hard: bool = Query(False, description="Permanently delete the record"),
    db: Session = Depends(get_db),
):
    """Soft-delete (archive) or hard-delete a library entry."""
    entry = db.query(EstimateLibraryEntry).filter(
        EstimateLibraryEntry.id == entry_id,
        EstimateLibraryEntry.is_deleted == False,  # noqa: E712
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")

    if hard:
        db.delete(entry)
        db.commit()
        return APIResponse(success=True, message="Library entry permanently deleted")
    else:
        entry.is_deleted = True
        entry.status = "archived"
        db.commit()
        return APIResponse(success=True, message="Library entry archived")
