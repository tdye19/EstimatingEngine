"""Export profiles router — per-organization export branding and defaults."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.export_profile import ExportProfile
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth

log = logging.getLogger(__name__)

router = APIRouter(tags=["export-profiles"], dependencies=[Depends(require_auth)])


class ExportProfileOut(BaseModel):
    class Config:
        from_attributes = True

    id: int
    organization_id: int
    logo_url: str | None = None
    header_text: str | None = None
    default_sections_json: str | None = None
    include_assumptions: bool
    include_exclusions: bool
    group_by: str


class ExportProfileUpsert(BaseModel):
    logo_url: str | None = None
    header_text: str | None = None
    default_sections_json: str | None = None
    include_assumptions: bool = True
    include_exclusions: bool = True
    group_by: str = "trade"


@router.get("/api/export-profile", response_model=ExportProfileOut)
def get_export_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    profile = (
        db.query(ExportProfile)
        .filter(
            ExportProfile.organization_id == current_user.organization_id,
            ExportProfile.is_deleted.is_(False),
        )
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="No export profile found")
    return profile


@router.put("/api/export-profile", response_model=ExportProfileOut)
def upsert_export_profile(
    body: ExportProfileUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    profile = (
        db.query(ExportProfile)
        .filter(
            ExportProfile.organization_id == current_user.organization_id,
            ExportProfile.is_deleted.is_(False),
        )
        .first()
    )

    if profile:
        for field, value in body.model_dump().items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(UTC)
    else:
        profile = ExportProfile(
            organization_id=current_user.organization_id,
            **body.model_dump(),
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return profile
