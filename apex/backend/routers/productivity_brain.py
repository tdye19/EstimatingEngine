"""Productivity Brain router — bulk upload, rates, and estimate comparison."""

import os

import aiofiles
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from apex.backend.config import UPLOAD_DIR
from apex.backend.db.database import get_db
from apex.backend.services.productivity_brain.models import PBProject
from apex.backend.services.productivity_brain.service import ProductivityBrainService
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/productivity-brain",
    tags=["productivity-brain"],
    dependencies=[Depends(require_auth)],
)

PB_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "productivity_brain")


@router.post("/upload", response_model=APIResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Accept up to 50 .xlsx files, ingest each via the PB service."""
    if len(files) > 50:
        return APIResponse(success=False, error="Maximum 50 files per upload")

    os.makedirs(PB_UPLOAD_DIR, exist_ok=True)
    svc = ProductivityBrainService(db)
    results = []

    for f in files:
        if not f.filename or not f.filename.lower().endswith(".xlsx"):
            results.append({"filename": f.filename, "status": "error", "error": "Not an .xlsx file"})
            continue

        # Save directly to PB upload dir
        dest = os.path.join(PB_UPLOAD_DIR, f.filename)
        try:
            content = await f.read()
            async with aiofiles.open(dest, "wb") as fh:
                await fh.write(content)

            result = svc.ingest_file(dest, f.filename)
            results.append({"filename": f.filename, **result})
        except Exception as e:
            results.append({"filename": f.filename, "status": "error", "error": str(e)})
            if os.path.exists(dest):
                os.unlink(dest)

    return APIResponse(success=True, data=results)


@router.get("/stats", response_model=APIResponse)
def get_stats(db: Session = Depends(get_db)):
    """Summary statistics for the Productivity Brain database."""
    svc = ProductivityBrainService(db)
    stats = svc.get_stats()

    last = db.query(PBProject).order_by(PBProject.ingested_at.desc()).first()
    stats["last_ingested"] = last.ingested_at.isoformat() if last and last.ingested_at else None

    return APIResponse(success=True, data=stats)


@router.get("/rates", response_model=APIResponse)
def get_rates(
    activity: str | None = Query(None),
    wbs: str | None = Query(None),
    unit: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Averaged production rates with optional filters."""
    svc = ProductivityBrainService(db)
    rates = svc.get_rates(activity=activity, wbs=wbs, unit=unit)

    # Add spread (max - min) for each row
    for r in rates:
        if r["max_rate"] is not None and r["min_rate"] is not None:
            r["spread"] = round(r["max_rate"] - r["min_rate"], 2)
        else:
            r["spread"] = None

    return APIResponse(success=True, data=rates)


@router.post("/compare", response_model=APIResponse)
def compare_estimate(
    items: list[dict],
    db: Session = Depends(get_db),
):
    """Compare estimate line items against historical rates.

    Input: [{activity, rate, unit, csi_code}]
    Output: [{activity, estimate_rate, historical_avg, delta_pct, flag, sample_count, confidence}]
    """
    svc = ProductivityBrainService(db)

    # Normalize input keys to what the service expects
    normalized = []
    for item in items:
        normalized.append(
            {
                "activity": item.get("activity", ""),
                "production_rate": item.get("rate") or item.get("production_rate"),
                "unit": item.get("unit"),
                "csi_code": item.get("csi_code"),
            }
        )

    results = svc.compare_estimate(normalized)

    # Reshape output for frontend
    output = []
    for r in results:
        count = r.get("historical_count", 0)
        if count >= 10:
            confidence = "high"
        elif count >= 5:
            confidence = "medium"
        else:
            confidence = "low"

        output.append(
            {
                "activity": r.get("activity"),
                "estimate_rate": r.get("production_rate"),
                "historical_avg": r.get("historical_avg"),
                "delta_pct": r.get("delta_pct"),
                "flag": r.get("flag"),
                "sample_count": count,
                "confidence": confidence,
            }
        )

    return APIResponse(success=True, data=output)


@router.get("/projects", response_model=APIResponse)
def list_projects(db: Session = Depends(get_db)):
    """List all ingested Productivity Brain projects."""
    svc = ProductivityBrainService(db)
    return APIResponse(success=True, data=svc.get_projects())


@router.get("/match", response_model=APIResponse)
def match_activity(
    csi_code: str | None = Query(None),
    description: str | None = Query(None),
    unit: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Find best matching PB activity with historical rates. Used by Agent 4."""
    svc = ProductivityBrainService(db)
    match = svc.match_activity(csi_code=csi_code, description=description, unit=unit)
    if match is None:
        return APIResponse(success=True, data=None, message="No matching activity found")
    return APIResponse(success=True, data=match)
