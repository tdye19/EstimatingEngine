"""Authentication router."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from apex.backend.db.database import get_db
from apex.backend.config import AUTH_LOGIN_RATE_LIMIT, AUTH_REGISTER_RATE_LIMIT
from apex.backend.models.user import User
from apex.backend.utils.auth import hash_password, verify_password, create_access_token
from apex.backend.utils.schemas import (
    UserCreate, UserOut, LoginRequest, TokenResponse, APIResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=APIResponse)
@limiter.limit(AUTH_REGISTER_RATE_LIMIT)
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        organization_id=data.organization_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return APIResponse(
        success=True,
        message="User registered successfully",
        data=UserOut.model_validate(user).model_dump(),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_LOGIN_RATE_LIMIT)
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == data.email,
        User.is_deleted == False,  # noqa: E712
    ).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )
