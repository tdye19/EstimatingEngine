"""HF-22 regression tests.

Three fixes wired together:
  Fix 1: Agent 3's spec-vs-takeoff except clause now calls db.rollback()
         after swallowing IntegrityError, so the shared SQLAlchemy session
         stays usable for downstream agents (3.5, 5, 6).
  Fix 2: gap_report_items.division_number is now nullable, so cross-cutting
         rule-based findings (e.g. SCOPE_CROSS_REFERENCES "takeoff includes
         X but missing Y") can persist without crashing the commit.
  Fix 3: AgentOrchestrator._force_status_update() guarantees AgentRunLog
         transitions out of "running" via a fresh session even when self.db
         is poisoned. Marker "[HF-22 forced status]" lets Railway log greps
         trace the path.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.orm import Session

from apex.backend.agents import agent_3_gap_analysis as a3
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.services.agent_orchestrator import AgentOrchestrator


@pytest.fixture
def project_with_specs(db_session: Session) -> Project:
    """Minimal project sufficient for Agent 3 to reach its spec-vs-takeoff pass."""
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"HF22 {suffix}",
        project_number=f"HF22-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()
    doc = Document(
        project_id=p.id,
        filename="specs.pdf",
        file_path="/fake/specs.pdf",
        file_type="pdf",
        classification="spec",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="03",
            section_number="03 30 00",
            title="Cast-in-Place Concrete",
            work_description="4000 psi concrete with Grade 60 rebar.",
        )
    )
    db_session.commit()
    return p


def _poison_session(session: Session) -> None:
    """Force *session* into PendingRollbackError state by attempting a commit
    that violates NOT NULL on gap_report_items (title, gap_type, severity).
    Caller MUST handle subsequent queries by rolling back first."""
    bad = GapReportItem(
        gap_report_id=99999,
        division_number=None,
        section_number=None,
        title=None,  # NOT NULL violation
        gap_type=None,
        severity=None,
    )
    session.add(bad)
    try:
        session.commit()
    except Exception:
        pass  # poisoned — exactly what the test needs


# ---------------------------------------------------------------------------
# Fix 2: division_number nullable
# ---------------------------------------------------------------------------
def test_gap_report_item_accepts_null_division_number(
    db_session: Session, project_with_specs: Project
):
    """Cross-cutting rule findings (no specific CSI division) must persist."""
    report = GapReport(
        project_id=project_with_specs.id,
        total_gaps=1,
        critical_count=1,
    )
    db_session.add(report)
    db_session.flush()

    item = GapReportItem(
        gap_report_id=report.id,
        division_number=None,
        section_number=None,
        title="Takeoff includes concrete but missing associated reinforcement",
        gap_type="spec_vs_takeoff",
        severity="critical",
    )
    db_session.add(item)
    db_session.commit()

    rt = db_session.query(GapReportItem).filter_by(id=item.id).first()
    assert rt is not None
    assert rt.division_number is None
    assert rt.section_number is None
    assert rt.title.startswith("Takeoff includes")


# ---------------------------------------------------------------------------
# Fix 1: Agent 3's bare-except now rolls back
# ---------------------------------------------------------------------------
def test_agent_3_rolls_back_on_spec_vs_takeoff_integrity_error(
    db_session: Session, project_with_specs: Project, monkeypatch
):
    """When the inline commit inside the spec-vs-takeoff block fails, Agent 3
    must catch the exception AND rollback so downstream agents in the same
    pipeline run can keep using self.db. Without HF-22 Fix 1, the next query
    on db_session would raise PendingRollbackError."""

    def _bad_gaps(db, project_id, sections):
        # Returning a gap with title=None forces the inline db.commit() at
        # the spec-vs-takeoff persistence step to raise IntegrityError
        # (title is NOT NULL). We're driving the actual code path the
        # production bug took.
        return [
            {
                "division_number": "03",
                "section_number": None,
                "title": None,
                "gap_type": "spec_vs_takeoff",
                "severity": "critical",
                "description": None,
                "recommendation": None,
            }
        ]

    monkeypatch.setattr(a3, "_spec_vs_takeoff_gaps", _bad_gaps)

    # The agent must complete cleanly — its bare-except swallows.
    result = a3.run_gap_analysis_agent(db_session, project_with_specs.id)
    assert isinstance(result, dict)
    assert "total_gaps" in result

    # The HF-22 Fix 1 invariant: db_session is usable post-call.
    # Pre-fix this raises PendingRollbackError.
    assert db_session.execute(text("SELECT 1")).scalar() == 1

    # And we can still write through it.
    db_session.add(
        SpecSection(
            project_id=project_with_specs.id,
            document_id=db_session.query(Document)
            .filter_by(project_id=project_with_specs.id)
            .first()
            .id,
            division_number="22",
            section_number="22 00 00",
            title="Plumbing",
            work_description="Fixtures.",
        )
    )
    db_session.commit()


# ---------------------------------------------------------------------------
# Fix 3: orchestrator status guarantee under poisoned session
# ---------------------------------------------------------------------------
def test_orchestrator_log_complete_routes_to_force_update_when_commit_fails(
    db_session: Session, project_with_specs: Project
):
    """When _log_complete's self.db.commit() raises (the genuinely-broken
    case that survives even the proactive rollback), the try/except routes
    to _force_status_update. The AgentRunLog row must end up status="failed"
    with [HF-22 forced status] in error_message and a non-null completed_at."""
    orch = AgentOrchestrator(db_session, project_with_specs.id)
    log = orch._log_start(agent_name="HF22 Test Agent", agent_number=999)
    log_id = log.id

    # Sanity: row starts in running state.
    assert log.status == "running"
    assert log.completed_at is None

    # Force every commit on db_session to fail. This guarantees the
    # proactive-rollback path can't save us and the inner try/except
    # routes to _force_status_update — exercising the actual safety-net.
    real_commit = db_session.commit

    def _always_fail(*args, **kwargs):
        raise RuntimeError("HF-22 test: forced commit failure")

    db_session.commit = _always_fail
    try:
        # Must not raise — the force-update path swallows.
        orch._log_complete(log, summary="should-have-completed", output_data={"x": 1})
    finally:
        db_session.commit = real_commit

    # _force_status_update writes through SessionLocal() (a separate session
    # bound to the same in-memory engine via StaticPool), so the row IS
    # persisted. Read it back via the test's own session.
    db_session.expire_all()
    fresh = db_session.query(AgentRunLog).filter_by(id=log_id).first()
    assert fresh is not None, "AgentRunLog row missing after force-update"
    assert fresh.status == "failed", (
        f"status stuck at {fresh.status!r} — force-update did not run "
        "or fresh-session write failed"
    )
    assert fresh.completed_at is not None, "completed_at not set on forced row"
    assert fresh.error_message is not None
    assert "[HF-22 forced status]" in fresh.error_message, (
        f"missing grep marker in error_message: {fresh.error_message!r}"
    )


# ---------------------------------------------------------------------------
# Fix 3 regression guard: shared self.db must remain usable after force-update
# ---------------------------------------------------------------------------
def test_force_status_update_unblocks_shared_session_for_downstream_agents(
    db_session: Session, project_with_specs: Project
):
    """After _force_status_update runs, downstream agents (3.5, 5, 6) need
    self.db to be usable. Pins the "rollback self.db before opening fresh
    session" invariant so a future refactor can't quietly drop it."""
    orch = AgentOrchestrator(db_session, project_with_specs.id)
    log = orch._log_start(agent_name="HF22 Downstream Probe", agent_number=998)
    # Capture log_id before poisoning (see comment in the previous test).
    log_id = log.id

    _poison_session(db_session)

    # Confirm test setup actually poisoned the session.
    with pytest.raises(PendingRollbackError):
        db_session.execute(text("SELECT 1")).scalar()

    orch._force_status_update(
        log_id, status="failed", error_message="downstream-probe injected"
    )

    # The HF-22 Fix 3 downstream invariant: post-force, self.db is usable
    # without the test having to call rollback() itself.
    assert db_session.execute(text("SELECT 1")).scalar() == 1
