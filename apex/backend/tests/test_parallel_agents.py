"""Integration test: Agents 3 & 4 parallel DB session isolation.

Verifies that Gap Analysis (Agent 3) and Quantity Takeoff (Agent 4) can run
concurrently in separate threads without deadlock, data corruption, or session
sharing violations — using SQLite in WAL mode.

Usage:
    python -m apex.backend.tests.test_parallel_agents
"""

import concurrent.futures
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Bootstrap: ensure the repo root is on sys.path when run directly
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_wal_mode(engine) -> bool:
    """Return True if the database is in WAL journal mode."""
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).fetchone()
        return result and result[0].upper() == "WAL"


def _seed_database(SessionLocal, project_id: int) -> int:
    """Insert a test project, one document, and several spec sections.

    Returns the document id created.  This simulates Agent 2 output so that
    Agents 3 and 4 have meaningful input to process.
    """
    # Import models — deferred so the test file can be imported without a live DB
    from apex.backend.models.document import Document
    from apex.backend.models.project import Project
    from apex.backend.models.spec_section import SpecSection

    db = SessionLocal()
    try:
        # Project
        project = Project(
            id=project_id,
            name="Parallel Test Project",
            project_number=f"PAR-TEST-{project_id:04d}",
            project_type="commercial",
            status="estimating",
        )
        db.add(project)
        db.flush()

        # Document (required FK for SpecSection)
        doc = Document(
            project_id=project_id,
            filename="test_spec.pdf",
            file_path="/tmp/test_spec.pdf",
            file_type="pdf",
            classification="spec",
            processing_status="completed",
        )
        db.add(doc)
        db.flush()

        # Seed spec sections — enough variety for gap analysis and takeoff
        _SECTIONS = [
            (
                "03",
                "03 30 00",
                "Cast-in-Place Concrete",
                "Provide 4,000 PSI concrete slab-on-grade, 6 inches thick, 12,000 SF. "
                "Include WWF 6x6-W2.9xW2.9 welded wire fabric reinforcement. "
                "Saw-cut control joints at 15-foot intervals.",
            ),
            (
                "05",
                "05 12 00",
                "Structural Steel Framing",
                "Wide-flange steel columns and beams per structural drawings. "
                "Total structural steel approximately 85 tons. ASTM A992 steel.",
            ),
            (
                "07",
                "07 21 00",
                "Building Insulation",
                "Provide R-19 batt insulation at all exterior walls, 8,500 SF. "
                "R-38 blown-in insulation at roof deck, 12,000 SF.",
            ),
            (
                "08",
                "08 11 13",
                "Hollow Metal Doors and Frames",
                "Provide 24 hollow metal doors, 3-0 x 7-0, 16-gauge. "
                "Hollow metal frames at all interior openings, 36 frames total.",
            ),
            (
                "09",
                "09 29 00",
                "Gypsum Board",
                "5/8-inch Type X gypsum board at all interior partitions. "
                "Approximately 28,000 SF of wall area. 3-5/8 inch metal stud framing.",
            ),
            (
                "09",
                "09 91 13",
                "Exterior Painting",
                "Two coats elastomeric paint at all exterior CMU surfaces, 4,200 SF. "
                "One primer and two finish coats interior walls, 28,000 SF.",
            ),
            (
                "26",
                "26 05 19",
                "Low-Voltage Electrical Power Conductors",
                "120/208V, 3-phase, 4-wire service. 2,000 AMP main switchboard. "
                "Provide branch circuit wiring throughout, approx 15,000 LF conduit.",
            ),
        ]

        for div, section_num, title, description in _SECTIONS:
            db.add(
                SpecSection(
                    project_id=project_id,
                    document_id=doc.id,
                    division_number=div,
                    section_number=section_num,
                    title=title,
                    work_description=description,
                    raw_text=description,
                )
            )

        db.commit()
        return doc.id

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Per-thread agent runners
# ---------------------------------------------------------------------------


def _run_agent3(SessionLocal, project_id: int) -> tuple[dict, float, Exception | None]:
    """Run Agent 3 (gap analysis) with its own DB session.  Returns (result, elapsed, error)."""
    from apex.backend.agents.agent_3_gap_analysis import run_gap_analysis_agent

    db = SessionLocal()
    t0 = time.perf_counter()
    error = None
    result = {}
    try:
        result = run_gap_analysis_agent(db, project_id)
    except Exception as exc:
        error = exc
    finally:
        db.close()
    elapsed = time.perf_counter() - t0
    return result, elapsed, error


def _run_agent4(SessionLocal, project_id: int) -> tuple[dict, float, Exception | None]:
    """Run Agent 4 (quantity takeoff) with its own DB session.  Returns (result, elapsed, error)."""
    from apex.backend.agents.agent_4_takeoff import run_takeoff_agent

    db = SessionLocal()
    t0 = time.perf_counter()
    error = None
    result = {}
    try:
        result = run_takeoff_agent(db, project_id)
    except Exception as exc:
        error = exc
    finally:
        db.close()
    elapsed = time.perf_counter() - t0
    return result, elapsed, error


# ---------------------------------------------------------------------------
# Verification queries
# ---------------------------------------------------------------------------


def _count_gap_reports(SessionLocal, project_id: int) -> tuple[int, int]:
    """Return (report_count, item_count) for the project."""
    from apex.backend.models.gap_report import GapReport, GapReportItem

    db = SessionLocal()
    try:
        reports = db.query(GapReport).filter(GapReport.project_id == project_id).count()
        items = db.query(GapReportItem).join(GapReport).filter(GapReport.project_id == project_id).count()
        return reports, items
    finally:
        db.close()


def _count_takeoff_items(SessionLocal, project_id: int) -> int:
    """Return number of takeoff items written for the project."""
    from apex.backend.models.takeoff_item import TakeoffItem

    db = SessionLocal()
    try:
        return db.query(TakeoffItem).filter(TakeoffItem.project_id == project_id).count()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------


def run_test() -> bool:
    """Execute the parallel session-isolation test.  Returns True on pass."""

    # ------------------------------------------------------------------
    # 1. Create a temporary SQLite database (isolated from apex.db)
    # ------------------------------------------------------------------
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    db_url = f"sqlite:///{db_path}"

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Enable WAL mode on every new connection
    @event.listens_for(test_engine, "connect")
    def _set_wal(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # ------------------------------------------------------------------
    # 2. Create schema
    # ------------------------------------------------------------------
    import apex.backend.models.agent_run_log  # noqa: F401
    import apex.backend.models.document  # noqa: F401
    import apex.backend.models.estimate  # noqa: F401
    import apex.backend.models.gap_report  # noqa: F401
    import apex.backend.models.labor_estimate  # noqa: F401
    import apex.backend.models.material_price  # noqa: F401
    import apex.backend.models.organization  # noqa: F401
    import apex.backend.models.productivity_history  # noqa: F401
    import apex.backend.models.project  # noqa: F401
    import apex.backend.models.project_actual  # noqa: F401
    import apex.backend.models.spec_section  # noqa: F401
    import apex.backend.models.takeoff_item  # noqa: F401
    import apex.backend.models.token_usage  # noqa: F401
    import apex.backend.models.upload_chunk  # noqa: F401
    import apex.backend.models.upload_session  # noqa: F401

    # Import all models so their metadata is registered on Base
    import apex.backend.models.user  # noqa: F401
    from apex.backend.db.database import Base

    Base.metadata.create_all(bind=test_engine)

    # ------------------------------------------------------------------
    # 3. Confirm WAL mode is active
    # ------------------------------------------------------------------
    wal_enabled = _check_wal_mode(test_engine)

    # ------------------------------------------------------------------
    # 4. Seed test data (simulates Agent 2 output)
    # ------------------------------------------------------------------
    PROJECT_ID = 1
    _seed_database(TestSessionLocal, PROJECT_ID)

    # ------------------------------------------------------------------
    # 5. Run Agents 3 and 4 in parallel threads (30-second timeout)
    # ------------------------------------------------------------------
    TIMEOUT_SECONDS = 30

    a3_result = a4_result = {}
    a3_elapsed = a4_elapsed = 0.0
    a3_error = a4_error = None
    deadlock_detected = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut3 = pool.submit(_run_agent3, TestSessionLocal, PROJECT_ID)
        fut4 = pool.submit(_run_agent4, TestSessionLocal, PROJECT_ID)

        try:
            a3_result, a3_elapsed, a3_error = fut3.result(timeout=TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            deadlock_detected = True
            a3_error = TimeoutError(f"Agent 3 timed out after {TIMEOUT_SECONDS}s — possible deadlock")

        try:
            a4_result, a4_elapsed, a4_error = fut4.result(timeout=TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            deadlock_detected = True
            a4_error = TimeoutError(f"Agent 4 timed out after {TIMEOUT_SECONDS}s — possible deadlock")

    # ------------------------------------------------------------------
    # 6. Verify DB writes
    # ------------------------------------------------------------------
    gap_reports, gap_items = _count_gap_reports(TestSessionLocal, PROJECT_ID)
    takeoff_items = _count_takeoff_items(TestSessionLocal, PROJECT_ID)

    # ------------------------------------------------------------------
    # 7. Print results
    # ------------------------------------------------------------------
    print()
    print("Parallel Agent Test")
    print("─" * 45)

    # Agent 3
    if a3_error is None:
        print(f"  Agent 3: \u2705 completed in {a3_elapsed:.1f}s — {gap_items} gap items written")
    else:
        print(f"  Agent 3: \u274c FAILED in {a3_elapsed:.1f}s")
        print(f"           Error: {a3_error}")
        tb = "".join(traceback.format_exception(type(a3_error), a3_error, a3_error.__traceback__))
        print(f"           {tb.strip()}")
        if "database is locked" in str(a3_error).lower() or "deadlock" in str(a3_error).lower():
            print("           Suggestion: fix is ENGINE-LEVEL — consider connection pooling or serialised write queue")
        elif "session" in str(a3_error).lower() or "transaction" in str(a3_error).lower():
            print(
                "           Suggestion: fix is SESSION-LEVEL — ensure each thread creates "
                "its own SessionLocal() and never shares sessions across threads"
            )

    # Agent 4
    if a4_error is None:
        print(f"  Agent 4: \u2705 completed in {a4_elapsed:.1f}s — {takeoff_items} takeoff items written")
    else:
        print(f"  Agent 4: \u274c FAILED in {a4_elapsed:.1f}s")
        print(f"           Error: {a4_error}")
        tb = "".join(traceback.format_exception(type(a4_error), a4_error, a4_error.__traceback__))
        print(f"           {tb.strip()}")
        if "database is locked" in str(a4_error).lower() or "deadlock" in str(a4_error).lower():
            print("           Suggestion: fix is ENGINE-LEVEL — consider connection pooling or serialised write queue")
        elif "session" in str(a4_error).lower() or "transaction" in str(a4_error).lower():
            print(
                "           Suggestion: fix is SESSION-LEVEL — ensure each thread creates "
                "its own SessionLocal() and never shares sessions across threads"
            )

    # Session isolation
    if not deadlock_detected and a3_error is None and a4_error is None:
        print("  Session isolation: \u2705 No conflicts")
    else:
        print("  Session isolation: \u274c Conflicts detected")

    # WAL mode
    print(f"  WAL mode: {'✅ Enabled' if wal_enabled else '❌ Not enabled'}")

    # ------------------------------------------------------------------
    # 8. Cleanup temp DB
    # ------------------------------------------------------------------
    test_engine.dispose()
    try:
        os.unlink(db_path)
        # SQLite WAL mode may leave -wal and -shm sidecar files
        for suffix in ("-wal", "-shm"):
            sidecar = db_path + suffix
            if os.path.exists(sidecar):
                os.unlink(sidecar)
    except OSError:
        pass

    passed = a3_error is None and a4_error is None and not deadlock_detected
    return passed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    passed = run_test()
    sys.exit(0 if passed else 1)
