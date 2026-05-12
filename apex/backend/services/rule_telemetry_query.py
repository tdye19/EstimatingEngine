"""Query helper for Agent 3 rule citation telemetry (Spec 19E.6.4).

For Tucker's internal review when deciding whether Direction B is justified
post-pilot.  Read-only — no writes, no side effects.
"""

from __future__ import annotations

from apex.backend.db.database import SessionLocal
from apex.backend.models.agent_run_log import AgentRunLog


def get_recent_rule_telemetry(limit: int = 50) -> list[dict]:
    """Returns the most recent N Agent 3 rule_telemetry payloads,
       newest first, with project_id and run timestamp attached."""
    db = SessionLocal()
    try:
        rows = (
            db.query(AgentRunLog)
            .filter(
                AgentRunLog.agent_number == 3,
                AgentRunLog.rule_telemetry.isnot(None),
            )
            .order_by(AgentRunLog.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "project_id": row.project_id,
                "run_id": row.id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "rule_telemetry": row.rule_telemetry,
            }
            for row in rows
        ]
    finally:
        db.close()
