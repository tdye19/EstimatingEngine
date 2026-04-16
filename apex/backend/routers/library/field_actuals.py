"""Field Actuals router — upload close-out data + stats."""

import os
import tempfile

import aiofiles
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.user import User
from apex.backend.services.library.field_actuals.service import FieldActualsService
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(prefix="/api/library/field-actuals", tags=["field-actuals"], dependencies=[Depends(require_auth)])


@router.post("/upload", response_model=APIResponse)
async def upload_field_actuals(
    file: UploadFile = File(...),
    project_name: str = Form(None),
    region: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Upload a WinEst close-out export as field actuals data."""
    # Save to temp file
    suffix = os.path.splitext(file.filename or "upload")[1] or ".xlsx"
    tmp_path = os.path.join(tempfile.gettempdir(), f"apex_fa_{os.urandom(8).hex()}{suffix}")
    content = await file.read()
    async with aiofiles.open(tmp_path, "wb") as fh:
        await fh.write(content)

    try:
        svc = FieldActualsService(db)
        result = svc.ingest_file(
            filepath=tmp_path,
            filename=file.filename or "upload.xlsx",
            project_name=project_name,
            region=region,
        )
        return APIResponse(success=True, data=result, message=f"Field actuals: {result.get('status', 'done')}")
    finally:
        os.unlink(tmp_path)


@router.get("/stats", response_model=APIResponse)
def field_actuals_stats(db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Stats on loaded field actuals data."""
    svc = FieldActualsService(db)
    return APIResponse(success=True, data=svc.get_stats())


@router.get("/projects", response_model=APIResponse)
def field_actuals_projects(db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """List ingested field actuals projects."""
    svc = FieldActualsService(db)
    return APIResponse(success=True, data=svc.get_projects())
