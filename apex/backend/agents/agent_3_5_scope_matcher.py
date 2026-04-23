"""Agent 3.5 — Scope Matcher (Sprint 18.3.2, extended 18.4.1 Part C).

Runs after Agent 3 (Scope Analysis) and before Agent 5 (Field Calibration).
Cross-references the estimator's takeoff items against every
WorkCategory the CM published for the project. Emits two parallel outputs
via the scope_matcher service:

  - GapFinding rows (risk surface for the gap UI / Intelligence Report)
  - LineItemWCAttribution rows (per-WC pricing roll-up foundation)

This runner handles persistence for both, delete-then-insert scoped to the
project — matches the "no versioning" contract in the GapFinding and
LineItemWCAttribution model docstrings.

Agent numbering: stored as integer 35 in AgentRunLog.agent_number (the
column is Integer, not Float). API / UI display-format as "3.5". See
Sprint 18.3.2 handoff for the rationale.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.line_item_wc_attribution import LineItemWCAttribution
from apex.backend.services.scope_matcher import match_scope_to_takeoff

logger = logging.getLogger(__name__)

AGENT_NUMBER = 35  # displayed as "3.5"


def run_scope_matcher_agent(db: Session, project_id: int) -> dict:
    """Run the scope matcher for *project_id*, persist findings and
    attributions, return a validated Agent35Output dict.

    Output keys:
      status                        "completed" | "noop"
      project_id                    int
      findings_created              int
      in_scope_not_estimated_count  int
      estimated_out_of_scope_count  int
      partial_coverage_count        int
      error_count                   int
      attributions_created          int
      attributions_by_tier          dict[str, int]
      attributions_unmatched        int
    """
    # Regenerate — delete existing findings and attributions for this project
    # before inserting fresh rows. Matches GapFinding's contract (no versioning).
    db.query(GapFinding).filter(GapFinding.project_id == project_id).delete(
        synchronize_session=False
    )
    db.query(LineItemWCAttribution).filter(
        LineItemWCAttribution.project_id == project_id
    ).delete(synchronize_session=False)

    findings, attributions = match_scope_to_takeoff(project_id, db)

    for finding in findings:
        db.add(finding)
    for attribution in attributions:
        db.add(attribution)
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

    attributions_by_tier: dict[str, int] = {}
    for attribution in attributions:
        attributions_by_tier[attribution.match_tier] = (
            attributions_by_tier.get(attribution.match_tier, 0) + 1
        )
    attributions_unmatched = attributions_by_tier.get("unmatched", 0)

    # status="completed" when there's ANY output to report (findings or
    # attributions). "noop" only when both are empty (e.g. no WCs yet).
    status = "noop" if not findings and not attributions else "completed"
    logger.info(
        f"Agent 3.5: project {project_id} — status={status} "
        f"findings={len(findings)} errors={error_count} "
        f"in_scope_not_estimated={counts['in_scope_not_estimated']} "
        f"estimated_out_of_scope={counts['estimated_out_of_scope']} "
        f"partial_coverage={counts['partial_coverage']} "
        f"attributions={len(attributions)} unmatched={attributions_unmatched} "
        f"by_tier={attributions_by_tier}"
    )

    output = {
        "status": status,
        "project_id": project_id,
        "findings_created": len(findings),
        "in_scope_not_estimated_count": counts["in_scope_not_estimated"],
        "estimated_out_of_scope_count": counts["estimated_out_of_scope"],
        "partial_coverage_count": counts["partial_coverage"],
        "error_count": error_count,
        "attributions_created": len(attributions),
        "attributions_by_tier": attributions_by_tier,
        "attributions_unmatched": attributions_unmatched,
    }
    return validate_agent_output(AGENT_NUMBER, output)
