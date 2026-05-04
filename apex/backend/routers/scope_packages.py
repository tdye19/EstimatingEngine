"""Scope package router — /api/projects/:id/scope-packages."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.scope_package import ScopePackage
from apex.backend.models.user import User
from apex.backend.utils.auth import get_authorized_project, require_auth
from apex.backend.utils.schemas import ScopePackageCreate, ScopePackageOut, ScopePackageUpdate

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects",
    tags=["scope-packages"],
    dependencies=[Depends(require_auth)],
)


@router.post("/{project_id}/scope-packages", response_model=ScopePackageOut, status_code=201)
def create_scope_package(
    project_id: int,
    body: ScopePackageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    pkg = ScopePackage(project_id=project_id, **body.model_dump())
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.get("/{project_id}/scope-packages", response_model=list[ScopePackageOut])
def list_scope_packages(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    return (
        db.query(ScopePackage)
        .filter(ScopePackage.project_id == project_id, ScopePackage.is_deleted.is_(False))
        .order_by(ScopePackage.id)
        .all()
    )


@router.patch("/{project_id}/scope-packages/{pkg_id}", response_model=ScopePackageOut)
def update_scope_package(
    project_id: int,
    pkg_id: int,
    body: ScopePackageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    pkg = (
        db.query(ScopePackage)
        .filter(ScopePackage.id == pkg_id, ScopePackage.project_id == project_id, ScopePackage.is_deleted.is_(False))
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Scope package not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(pkg, field, value)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/{project_id}/scope-packages/{pkg_id}", status_code=204)
def delete_scope_package(
    project_id: int,
    pkg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)
    pkg = (
        db.query(ScopePackage)
        .filter(ScopePackage.id == pkg_id, ScopePackage.project_id == project_id, ScopePackage.is_deleted.is_(False))
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Scope package not found")
    pkg.is_deleted = True
    db.commit()
