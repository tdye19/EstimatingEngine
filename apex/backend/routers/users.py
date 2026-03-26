"""Users management router — admin-only CRUD for user accounts and roles."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from apex.backend.db.database import get_db
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth, require_role, hash_password
from apex.backend.utils.schemas import APIResponse, UserOut

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_auth)])

VALID_ROLES = {"admin", "estimator", "viewer"}


class UserRoleUpdate(BaseModel):
    role: str


class UserCreateAdmin(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "estimator"
    organization_id: Optional[int] = None


@router.get("", response_model=APIResponse, dependencies=[Depends(require_role("admin"))])
def list_users(db: Session = Depends(get_db)):
    """Admin: list all users."""
    users = db.query(User).filter(User.is_deleted == False).all()  # noqa: E712
    return APIResponse(
        success=True,
        data=[UserOut.model_validate(u).model_dump(mode="json") for u in users],
    )


@router.get("/me", response_model=APIResponse)
def get_me(current_user: User = Depends(require_auth)):
    """Return the current authenticated user's profile."""
    return APIResponse(
        success=True,
        data=UserOut.model_validate(current_user).model_dump(mode="json"),
    )


@router.put("/{user_id}/role", response_model=APIResponse, dependencies=[Depends(require_role("admin"))])
def update_user_role(user_id: int, data: UserRoleUpdate, db: Session = Depends(get_db)):
    """Admin: change a user's role."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = data.role
    db.commit()
    db.refresh(user)
    return APIResponse(
        success=True,
        message=f"Role updated to '{data.role}'",
        data=UserOut.model_validate(user).model_dump(mode="json"),
    )


@router.delete("/{user_id}", response_model=APIResponse, dependencies=[Depends(require_role("admin"))])
def deactivate_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_auth)):
    """Admin: soft-delete (deactivate) a user account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_deleted = True
    db.commit()
    return APIResponse(success=True, message="User deactivated")
