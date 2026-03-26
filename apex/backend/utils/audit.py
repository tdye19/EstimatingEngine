"""Audit trail helper for recording data changes."""

from typing import Optional
from sqlalchemy.orm import Session
from apex.backend.models.audit_log import AuditLog


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: int,
    details: Optional[dict] = None,
) -> AuditLog:
    """Create an audit log entry.

    The record is added and flushed (but not committed) so it participates
    in the caller's transaction.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(entry)
    db.flush()
    return entry
