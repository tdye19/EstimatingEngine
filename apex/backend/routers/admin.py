"""Admin router — user and organization management (admin-only)."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.organization import Organization
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth, require_role
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
    org_id: Optional[int] = Query(None),
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

    user.updated_at = datetime.now(timezone.utc)
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

    org.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(org)
    return APIResponse(data=OrganizationOut.model_validate(org).model_dump())


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
    org.updated_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)
