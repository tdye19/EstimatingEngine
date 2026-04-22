"""Admin diagnostics router — one-shot maintenance endpoints.

Each endpoint is independently gated by its own feature-flag env var so
the surface is invisible (returns 404) unless an operator has explicitly
turned it on for the duration of a maintenance window.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.user import User
from apex.backend.scripts.cleanup_orphan_projects import run_cleanup
from apex.backend.utils.auth import require_role

router = APIRouter(prefix="/api/admin/diagnostics", tags=["admin-diagnostics"])

_CLEANUP_FLAG_ENV = "APEX_ENABLE_CLEANUP_RUN"
_REPAIR_FLAG_ENV = "APEX_ENABLE_SCHEMA_REPAIR"
_FLAG_ON = "1"
_CONFIRM_TOKEN = "YES_DELETE"

_admin = require_role("admin")


def _require_cleanup_flag_enabled() -> None:
    """Hide the cleanup endpoint unless APEX_ENABLE_CLEANUP_RUN=1.

    Declared as the first dependency so it resolves before auth and the
    surface looks non-existent to any caller when the flag is off.
    """
    if os.environ.get(_CLEANUP_FLAG_ENV, "") != _FLAG_ON:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _require_repair_flag_enabled() -> None:
    """Hide the schema-repair endpoint unless APEX_ENABLE_SCHEMA_REPAIR=1."""
    if os.environ.get(_REPAIR_FLAG_ENV, "") != _FLAG_ON:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("/run-orphan-cleanup")
def run_orphan_cleanup(
    dry_run: bool = Query(True),
    confirm: str | None = Query(None),
    _flag: None = Depends(_require_cleanup_flag_enabled),
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


def _bid_outcomes_column_names(db: Session) -> list[str]:
    """Return column names for bid_outcomes per SQLite PRAGMA table_info.

    Railway runs SQLite; PRAGMA is the right primitive here. The second
    field of each PRAGMA row is the column name.
    """
    rows = db.execute(text("PRAGMA table_info(bid_outcomes)")).fetchall()
    return [r[1] for r in rows]


@router.post("/repair-bid-outcomes-column")
def repair_bid_outcomes_column(
    _flag: None = Depends(_require_repair_flag_enabled),
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Idempotent one-shot: add bid_outcomes.estimate_run_id if it's missing.

    Response includes columns_before and columns_after (PRAGMA-derived
    name lists) so a single curl call returns proof that the ALTER
    succeeded. When the column is already present, both lists are equal
    and `altered` is false.
    """
    columns_before = _bid_outcomes_column_names(db)
    if "estimate_run_id" in columns_before:
        return {
            "altered": False,
            "columns_before": columns_before,
            "columns_after": list(columns_before),
        }

    db.execute(
        text(
            "ALTER TABLE bid_outcomes "
            "ADD COLUMN estimate_run_id VARCHAR(36) REFERENCES estimate_runs(id)"
        )
    )
    db.commit()

    columns_after = _bid_outcomes_column_names(db)
    return {
        "altered": True,
        "columns_before": columns_before,
        "columns_after": columns_after,
    }
