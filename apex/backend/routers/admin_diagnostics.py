"""Admin diagnostics router — one-shot maintenance endpoints.

Gated by the APEX_ENABLE_CLEANUP_RUN env var so the surface is invisible
(returns 404) unless an operator has explicitly turned it on for the
duration of a maintenance window.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.user import User
from apex.backend.scripts.cleanup_orphan_projects import run_cleanup
from apex.backend.utils.auth import require_role

router = APIRouter(prefix="/api/admin/diagnostics", tags=["admin-diagnostics"])

_FLAG_ENV = "APEX_ENABLE_CLEANUP_RUN"
_FLAG_ON = "1"
_CONFIRM_TOKEN = "YES_DELETE"

_admin = require_role("admin")


def _require_flag_enabled() -> None:
    """Hide the endpoint unless the operator has set the feature flag.

    Declared as the first dependency so it resolves before auth and the
    surface looks non-existent to any caller when the flag is off.
    """
    if os.environ.get(_FLAG_ENV, "") != _FLAG_ON:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("/run-orphan-cleanup")
def run_orphan_cleanup(
    dry_run: bool = Query(True),
    confirm: str | None = Query(None),
    _flag: None = Depends(_require_flag_enabled),
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> dict:
    if not dry_run and confirm != _CONFIRM_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Real run requires confirm={_CONFIRM_TOKEN}",
        )

    report = run_cleanup(db, dry_run=dry_run)
    return report.as_dict()
