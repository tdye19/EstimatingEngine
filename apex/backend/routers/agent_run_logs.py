"""Read-only observability for AgentRunLog output_data (HF-20).

Surfaces per-run diagnostic info (warnings, extraction methods, counts) that
agents persist but don't return through normal pipeline responses. Created
after Sprint 18.2's enrichment phase silently no-op'd on every Division 03
section — those warnings lived in AgentRunLog.output_data but no endpoint
exposed them.

Endpoints:
  - GET /api/projects/{project_id}/agent-run-logs
  - GET /api/projects/{project_id}/agent-run-logs/{log_id}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/projects/{project_id}/agent-run-logs",
    tags=["agent-run-logs"],
    dependencies=[Depends(require_auth)],
)


def _serialize(row: AgentRunLog) -> dict:
    return {
        "id": row.id,
        "agent_number": row.agent_number,
        "agent_name": row.agent_name,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_seconds": row.duration_seconds,
        "tokens_used": row.tokens_used,
        "output_summary": row.output_summary,
        "output_data": row.output_data,
        "input_data": row.input_data,
        "error_message": row.error_message,
        "estimated_cost": row.estimated_cost,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("", response_model=APIResponse)
def list_agent_run_logs(project_id: int, db: Session = Depends(get_db)):
    """List all agent run logs for a project, newest first.

    Returns the full output_data payload so diagnostic warnings and
    sub-results (like Sprint 18.2's assembly_parameters enrichment summary)
    are inspectable without code or log-tail access.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rows = (
        db.query(AgentRunLog).filter(AgentRunLog.project_id == project_id).order_by(AgentRunLog.created_at.desc()).all()
    )
    return APIResponse(success=True, data=[_serialize(r) for r in rows])


@router.get("/{log_id}", response_model=APIResponse)
def get_agent_run_log(
    project_id: int,
    log_id: int,
    db: Session = Depends(get_db),
):
    """Fetch a single agent run log by ID, scoped to the project."""
    row = db.query(AgentRunLog).filter(AgentRunLog.id == log_id).filter(AgentRunLog.project_id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent run log not found")
    return APIResponse(success=True, data=_serialize(row))
