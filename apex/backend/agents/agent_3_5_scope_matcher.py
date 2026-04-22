"""Agent 3.5 — Scope Matcher (Sprint 18.3.2).

Runs after Agent 3 (Scope Analysis) and before Agent 5 (Field Calibration).
Cross-references the estimator's takeoff line items against every
WorkCategory the CM published for the project. Emits GapFinding rows via
the scope_matcher service; this runner handles persistence, logging, and
the pipeline-contract envelope.

Findings are regenerated on every run via delete-then-insert scoped to the
project — matches the "no versioning" contract in the GapFinding model
docstring.

Agent numbering: stored as integer 35 in AgentRunLog.agent_number (the
column is Integer, not Float). API / UI display-format as "3.5". See
Sprint 18.3.2 handoff for the rationale.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.models.gap_finding import GapFinding
from apex.backend.services.scope_matcher import match_scope_to_takeoff

logger = logging.getLogger(__name__)

AGENT_NUMBER = 35  # displayed as "3.5"


def run_scope_matcher_agent(db: Session, project_id: int) -> dict:
    """Run the scope matcher for *project_id*, persist findings, return summary.

    Returns dict validated against Agent35Output contract with keys:
      status                        "completed" | "noop"
      project_id                    int
      findings_created              int
      in_scope_not_estimated_count  int
      estimated_out_of_scope_count  int
      partial_coverage_count        int
      error_count                   int
    """
    # Regenerate — delete existing findings for this project before inserting.
    db.query(GapFinding).filter(GapFinding.project_id == project_id).delete(
        synchronize_session=False
    )

    findings = match_scope_to_takeoff(project_id, db)

    for finding in findings:
        db.add(finding)
    db.commit()

    counts = {
        "in_scope_not_estimated": 0,
        "estimated_out_of_scope": 0,
        "partial_coverage": 0,
    }
    error_count = 0
    for finding in findings:
        counts[finding.finding_type] = counts.get(finding.finding_type, 0) + 1
        if finding.severity == "ERROR":
            error_count += 1

    status = "noop" if not findings else "completed"
    logger.info(
        f"Agent 3.5: project {project_id} — status={status} "
        f"findings={len(findings)} errors={error_count} "
        f"in_scope_not_estimated={counts['in_scope_not_estimated']} "
        f"estimated_out_of_scope={counts['estimated_out_of_scope']} "
        f"partial_coverage={counts['partial_coverage']}"
    )

    output = {
        "status": status,
        "project_id": project_id,
        "findings_created": len(findings),
        "in_scope_not_estimated_count": counts["in_scope_not_estimated"],
        "estimated_out_of_scope_count": counts["estimated_out_of_scope"],
        "partial_coverage_count": counts["partial_coverage"],
        "error_count": error_count,
    }
    return validate_agent_output(AGENT_NUMBER, output)
