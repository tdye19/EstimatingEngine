"""JWT authentication utilities."""

import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.user import User

_jwt_secret = os.getenv("JWT_SECRET_KEY", "")
if not _jwt_secret:
    if os.getenv("APEX_DEV_MODE", "").lower() in ("true", "1", "yes"):
        _jwt_secret = "apex-dev-secret-DO-NOT-USE-IN-PRODUCTION"
    else:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required. "
            "Set it to a strong random string (e.g. 64+ hex chars). "
            "For local development, set APEX_DEV_MODE=true to use a default key."
        )
SECRET_KEY = _jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        user_id: int = int(sub)
    except (JWTError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()  # noqa: E712
    return user


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user_id: int = int(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()  # noqa: E712
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*roles: str) -> Callable:
    """Return a FastAPI dependency that enforces role-based access.

    Usage::

        @router.get("/admin-only")
        def admin_endpoint(user: User = Depends(require_role("admin"))):
            ...
    """

    def _dependency(user: User = Depends(require_auth)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency


def get_authorized_project(project_id: int, user: User, db: Session):
    """Fetch a project and verify the current user owns it.

    Raises 404 if not found, 403 if the user doesn't own the project.
    """
    from apex.backend.models.project import Project

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Admin users can access any project within their organization
    if user.role == "admin":
        if (
            user.organization_id is not None
            and project.organization_id is not None
            and project.organization_id == user.organization_id
        ):
            return project
    if project.owner_id is not None and project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this project")
    return project
