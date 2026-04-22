"""GapFinding persistence helpers (Sprint 18.3.1).

Agent 3.5 regenerates findings on every run via delete-then-insert scoped
to a project. These helpers keep the "delete prior, insert current" contract
in one place so both the agent and its tests use identical code paths.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from apex.backend.models.gap_finding import GapFinding


def delete_project_findings(db: Session, project_id: int) -> int:
    """Remove every GapFinding for a project. Returns the number deleted.

    Called at the start of each Agent 3.5 run. Commits the delete so the
    subsequent inserts happen in a clean state.
    """
    deleted = (
        db.query(GapFinding)
        .filter(GapFinding.project_id == project_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def create_finding(
    db: Session,
    *,
    project_id: int,
    finding_type: str,
    match_tier: str,
    confidence: float,
    rationale: str,
    source: str,
    work_category_id: int | None = None,
    estimate_line_id: int | None = None,
    spec_section_ref: str | None = None,
) -> GapFinding:
    """Insert one GapFinding row and return the persisted instance.

    Does not commit — callers typically batch many findings per Agent 3.5 run
    and commit once at the end.
    """
    row = GapFinding(
        project_id=project_id,
        finding_type=finding_type,
        match_tier=match_tier,
        confidence=confidence,
        rationale=rationale,
        source=source,
        work_category_id=work_category_id,
        estimate_line_id=estimate_line_id,
        spec_section_ref=spec_section_ref,
    )
    db.add(row)
    db.flush()
    return row


def list_findings(
    db: Session,
    project_id: int,
    finding_type: str | None = None,
) -> list[GapFinding]:
    """Read helper for API endpoints and tests. Orders by created_at asc."""
    q = db.query(GapFinding).filter(GapFinding.project_id == project_id)
    if finding_type is not None:
        q = q.filter(GapFinding.finding_type == finding_type)
    return q.order_by(GapFinding.created_at.asc(), GapFinding.id.asc()).all()
