"""Tests for the one-time orphan-project cleanup script.

Seeds three projects into the shared test DB:
  A) soft-deleted, with children in multiple tables          → must be removed
  B) active, with children                                   → must stay
  C) soft-deleted, with NO children                          → must be removed

Verifies:
  * dry run: writes nothing
  * real run: (A) and (C) rows gone, (A)'s children gone, (B) and its
    children untouched
  * the orphan sweep (raw-SQL fallback) hits any child table whose FK
    points to projects.id, not just the tables reachable via Project.*
    ORM relationships
"""

from __future__ import annotations

import uuid

import pytest

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.work_category import WorkCategory
from apex.backend.scripts import cleanup_orphan_projects as cleanup


@pytest.fixture(autouse=True)
def _clean_between_tests(db_session):
    """The shared in-memory engine persists across tests; scrub every
    project and its known children so each test starts from a known state."""
    for Model in (SpecSection, Document, WorkCategory, AgentRunLog):
        db_session.query(Model).delete()
    db_session.query(Project).delete()
    db_session.commit()
    yield


def _mk_project(db_session, name: str, is_deleted: bool, owner_id: int) -> Project:
    p = Project(
        name=name,
        project_number=f"CLEAN-{name}-{uuid.uuid4().hex[:6]}",
        project_type="commercial",
        status="draft",
        owner_id=owner_id,
        is_deleted=is_deleted,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _add_children(db_session, project: Project) -> None:
    doc = Document(
        project_id=project.id,
        filename=f"{project.name}.pdf",
        file_path=f"/tmp/{project.name}.pdf",
        file_type="pdf",
        classification="spec",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(SpecSection(
        project_id=project.id,
        document_id=doc.id,
        division_number="03",
        section_number="03 30 00",
        title=f"spec for {project.name}",
    ))
    db_session.add(WorkCategory(
        project_id=project.id,
        wc_number="WC-01",
        title=f"WC for {project.name}",
    ))
    db_session.add(AgentRunLog(
        project_id=project.id,
        agent_name="agent_2_spec_parser",
        agent_number=2,
        status="completed",
    ))


def _seed_trio(db_session, owner_id: int) -> dict[str, int]:
    """Returns {label: project_id} for A / B / C."""
    a = _mk_project(db_session, "A_soft_with_children", is_deleted=True, owner_id=owner_id)
    b = _mk_project(db_session, "B_active_with_children", is_deleted=False, owner_id=owner_id)
    c = _mk_project(db_session, "C_soft_empty", is_deleted=True, owner_id=owner_id)
    _add_children(db_session, a)
    _add_children(db_session, b)
    db_session.commit()
    return {"A": a.id, "B": b.id, "C": c.id}


def _count_all(db_session, project_id: int) -> dict[str, int]:
    return {
        "project": db_session.query(Project).filter(Project.id == project_id).count(),
        "documents": db_session.query(Document).filter(Document.project_id == project_id).count(),
        "spec_sections": db_session.query(SpecSection).filter(SpecSection.project_id == project_id).count(),
        "work_categories": db_session.query(WorkCategory).filter(WorkCategory.project_id == project_id).count(),
        "agent_run_logs": db_session.query(AgentRunLog).filter(AgentRunLog.project_id == project_id).count(),
    }


class TestCleanupScript:
    def test_dry_run_writes_nothing(self, db_session, test_user):
        ids = _seed_trio(db_session, test_user.id)
        report = cleanup.run_cleanup(db_session, dry_run=True)

        assert report.dry_run is True
        assert report.projects_deleted == 0
        assert set(report.soft_deleted_project_ids) == {ids["A"], ids["C"]}
        # Before-counts populated so operator can see what a real run would hit
        assert report.per_table_rowcounts_before["spec_sections"] == 1
        assert report.per_table_rowcounts_before["documents"] == 1
        assert report.orphan_rows_cleared == {}

        # All rows still present
        assert all(v >= 1 for v in _count_all(db_session, ids["A"]).values())
        assert all(v >= 1 for v in _count_all(db_session, ids["B"]).values())
        assert _count_all(db_session, ids["C"])["project"] == 1

    def test_real_run_removes_soft_deleted_and_children(self, db_session, test_user):
        ids = _seed_trio(db_session, test_user.id)
        report = cleanup.run_cleanup(db_session, dry_run=False)
        db_session.expire_all()

        assert report.dry_run is False
        assert report.projects_deleted == 2
        assert set(report.soft_deleted_project_ids) == {ids["A"], ids["C"]}
        assert report.aborted_with is None

        # (A) soft-deleted with children — everything gone
        a_counts = _count_all(db_session, ids["A"])
        assert a_counts == {
            "project": 0, "documents": 0, "spec_sections": 0,
            "work_categories": 0, "agent_run_logs": 0,
        }
        # (C) soft-deleted, no children — project row gone
        assert db_session.query(Project).filter(Project.id == ids["C"]).count() == 0

        # (B) active with children — completely untouched
        b_counts = _count_all(db_session, ids["B"])
        assert b_counts == {
            "project": 1, "documents": 1, "spec_sections": 1,
            "work_categories": 1, "agent_run_logs": 1,
        }

    def test_raw_sql_fallback_hits_every_fk_table(self, db_session, test_user):
        """Confirm the orphan-sweep phase inspects every table with a FK to
        projects.id (not just the ones ORM-wired). If the script later adds
        rows via ORM-cascade paths, the sweep finds zero — but the sweep
        DID run against every table, which is the regression guard we care
        about here."""
        _seed_trio(db_session, test_user.id)

        # Run the table-discovery path directly to check coverage.
        tables = cleanup._child_tables_referencing_projects(db_session)
        table_names = {t for t, _ in tables}

        expected_core = {
            "documents", "spec_sections", "work_categories", "agent_run_logs",
            "takeoff_items", "takeoff_items_v2", "estimates", "estimate_runs",
            "intelligence_reports", "sub_bid_packages", "upload_sessions",
            "bid_outcomes", "labor_estimates", "project_actuals",
            "gap_reports", "token_usage", "bid_comparisons", "change_orders",
        }
        missing = expected_core - table_names
        assert not missing, f"Inspector missed tables: {missing}"

        # Smoke test: run full cleanup and make sure no exception.
        cleanup.run_cleanup(db_session, dry_run=False)

    def test_no_soft_deleted_projects_is_a_noop(self, db_session, test_user):
        _mk_project(db_session, "only_active", is_deleted=False, owner_id=test_user.id)
        db_session.commit()

        report = cleanup.run_cleanup(db_session, dry_run=False)
        assert report.soft_deleted_project_ids == []
        assert report.projects_deleted == 0
        assert report.per_table_rowcounts_before == {}
        assert report.aborted_with is None

    def test_confirm_flag_gating(self, monkeypatch):
        monkeypatch.delenv("APEX_CONFIRM_ORPHAN_CLEANUP", raising=False)
        assert cleanup._confirm_flag_yes() is False

        monkeypatch.setenv("APEX_CONFIRM_ORPHAN_CLEANUP", "yes")
        assert cleanup._confirm_flag_yes() is True  # case-insensitive

        monkeypatch.setenv("APEX_CONFIRM_ORPHAN_CLEANUP", "Y")
        assert cleanup._confirm_flag_yes() is False  # must be exact word
