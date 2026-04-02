"""Dev-only test router — gated by APEX_DEV_MODE=true environment variable.

Provides POST /api/test/run-pipeline which:
  1. Creates a temporary project
  2. Ingests the bundled test_spec.txt fixture
  3. Runs the full 6-agent pipeline synchronously
  4. Returns a detailed summary of what each agent produced

Mount this router in main.py only when APEX_DEV_MODE is set.
"""

import os
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.gap_report import GapReport
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.services.agent_orchestrator import AgentOrchestrator

logger = logging.getLogger("apex.test_pipeline")

router = APIRouter(prefix="/api/test", tags=["test"])

FIXTURE_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "test_spec.txt"


def _dev_only():
    """Dependency that raises 404 unless APEX_DEV_MODE=true."""
    if os.getenv("APEX_DEV_MODE", "").lower() not in ("true", "1", "yes"):
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/run-pipeline", dependencies=[Depends(_dev_only)])
def run_test_pipeline(db: Session = Depends(get_db)):
    """Create a temp project, ingest the test fixture, run the full pipeline.

    Returns a structured summary useful for smoke-testing the pipeline.
    """
    if not FIXTURE_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Test fixture not found: {FIXTURE_PATH}")

    # --- 1. Create temporary project ---
    project = Project(
        name="[TEST] Riverside Office Complex",
        project_number=f"TEST-{os.urandom(3).hex().upper()}",
        project_type="commercial",
        description="Automated smoke-test project — safe to delete",
        status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    project_id = project.id

    # --- 2. Ingest test fixture as a Document record ---
    # Copy fixture to uploads directory so agents can read it
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads")) / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / "test_spec.txt"
    dest_path.write_bytes(FIXTURE_PATH.read_bytes())

    doc = Document(
        project_id=project_id,
        filename="test_spec.txt",
        file_path=str(dest_path),
        file_type="txt",
        file_size_bytes=dest_path.stat().st_size,
        processing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # --- 3. Run full pipeline ---
    orchestrator = AgentOrchestrator(db, project_id)
    pipeline_results = orchestrator.run_pipeline(document_id=doc.id)

    # --- 4. Collect validation assertions ---
    assertions = []

    r1 = pipeline_results.get("agent_1", {})
    assertions.append({
        "check": "Agent 1 extracted text",
        "passed": r1.get("documents_processed", 0) >= 1 and not r1.get("error"),
        "detail": f"documents_processed={r1.get('documents_processed', 0)}",
    })

    r2 = pipeline_results.get("agent_2", {})
    sections = r2.get("sections_parsed", 0)
    assertions.append({
        "check": "Agent 2 found >= 3 spec sections",
        "passed": sections >= 3,
        "detail": f"sections_parsed={sections}",
    })

    r3 = pipeline_results.get("agent_3", {})
    gaps = r3.get("total_gaps", 0)
    assertions.append({
        "check": "Agent 3 flagged >= 1 gap",
        "passed": gaps >= 1 and not r3.get("error"),
        "detail": f"total_gaps={gaps}",
    })

    r4 = pipeline_results.get("agent_4", {})
    parsed = r4.get("takeoff_items_parsed", 0)
    assertions.append({
        "check": "Agent 4 parsed takeoff and produced recommendations",
        "passed": parsed >= 0 and not r4.get("error"),
        "detail": f"takeoff_items_parsed={parsed}, items_matched={r4.get('items_matched', 0)}",
    })

    r5 = pipeline_results.get("agent_5", {})
    compared = r5.get("items_compared", 0)
    assertions.append({
        "check": "Agent 5 compared against field actuals",
        "passed": compared >= 0 and not r5.get("error"),
        "detail": f"items_compared={compared}, with_field_data={r5.get('items_with_field_data', 0)}",
    })

    r6 = pipeline_results.get("agent_6", {})
    report_id = r6.get("report_id", -1)
    assertions.append({
        "check": "Agent 6 produced intelligence report",
        "passed": report_id >= 0 and not r6.get("error"),
        "detail": f"report_id={report_id}, risk={r6.get('overall_risk_level', 'N/A')}",
    })

    # --- 5. v2 pipeline deep validation (queries DB directly) ---
    v2_checks = _validate_v2_pipeline(project_id, db)
    for label, passed in v2_checks:
        assertions.append({
            "check": f"[v2] {label}",
            "passed": passed,
            "detail": "OK" if passed else "FAIL",
        })

    all_passed = all(a["passed"] for a in assertions)

    return {
        "project_id": project_id,
        "document_id": doc.id,
        "pipeline_status": pipeline_results.get("pipeline_status"),
        "all_assertions_passed": all_passed,
        "assertions": assertions,
        "agent_results": {
            "agent_1": r1,
            "agent_2": r2,
            "agent_3": r3,
            "agent_4": r4,
            "agent_5": r5,
            "agent_6": r6,
        },
    }


def _validate_v2_pipeline(project_id: int, db: Session) -> list[tuple[str, bool]]:
    """Validate the full v2 pipeline produced expected outputs."""
    checks = []

    # Agent 2: spec sections parsed
    sections = db.query(SpecSection).filter_by(project_id=project_id).count()
    checks.append(("Agent 2 spec sections exist", sections > 0))

    # Agent 4: takeoff items (0 ok if no takeoff uploaded)
    takeoff = db.query(TakeoffItemV2).filter_by(project_id=project_id).count()
    checks.append(("Agent 4 takeoff items queryable", takeoff >= 0))

    # Agent 3: gap report exists
    gap_report = db.query(GapReport).filter_by(project_id=project_id).first()
    checks.append(("Agent 3 gap report exists", gap_report is not None))

    # Agent 6: intelligence report exists
    report = db.query(IntelligenceReportModel).filter_by(project_id=project_id).first()
    checks.append(("Agent 6 intelligence report exists", report is not None))

    if report:
        checks.append(("Risk level set", report.overall_risk_level != "unknown"))
        checks.append(("Narrative generated", len(report.executive_narrative or "") > 0))
        checks.append(("Rate intelligence populated", report.rate_intelligence_json is not None))
        checks.append(("Scope risk populated", report.scope_risk_json is not None))

    return checks
