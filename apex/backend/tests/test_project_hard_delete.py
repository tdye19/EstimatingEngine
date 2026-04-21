"""Tests for the hard-delete fix on DELETE /api/projects/{id}.

Before this commit the handler flipped `project.is_deleted = True` and
committed — the row and every child table survived. Post-fix the handler
calls `db.delete(project)` so the ORM cascade (cascade="all, delete-orphan"
on every Project.* relationship) removes the project and all its child
rows in one transaction.
"""

from __future__ import annotations

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.work_category import WorkCategory


def _seed_project_with_children(db_session, owner_id: int, label: str = "T1") -> int:
    """Create a project with one child row in each of the tables the test
    exercises. Returns the new project.id. `label` disambiguates the
    UNIQUE project_number when callers seed multiple projects in one test."""
    import uuid

    proj = Project(
        name=f"Target-{label}",
        project_number=f"HD-{label}-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=owner_id,
    )
    db_session.add(proj)
    db_session.flush()

    doc = Document(
        project_id=proj.id,
        filename="spec.pdf",
        file_path="/tmp/spec.pdf",
        file_type="pdf",
        classification="spec",
    )
    db_session.add(doc)
    db_session.flush()

    db_session.add(SpecSection(
        project_id=proj.id,
        document_id=doc.id,
        division_number="03",
        section_number="03 30 00",
        title="Cast-in-Place Concrete",
    ))
    db_session.add(WorkCategory(
        project_id=proj.id,
        wc_number="WC-01",
        title="Concrete work",
    ))
    db_session.add(AgentRunLog(
        project_id=proj.id,
        agent_name="agent_2_spec_parser",
        agent_number=2,
        status="completed",
    ))
    db_session.add(TakeoffItemV2(
        project_id=proj.id,
        row_number=1,
        activity="Form wall",
    ))
    db_session.commit()
    return proj.id


def _child_counts(db_session, project_id: int) -> dict[str, int]:
    return {
        "project": db_session.query(Project).filter(Project.id == project_id).count(),
        "documents": db_session.query(Document).filter(Document.project_id == project_id).count(),
        "spec_sections": db_session.query(SpecSection).filter(SpecSection.project_id == project_id).count(),
        "work_categories": db_session.query(WorkCategory).filter(WorkCategory.project_id == project_id).count(),
        "agent_run_logs": db_session.query(AgentRunLog).filter(AgentRunLog.project_id == project_id).count(),
        "takeoff_items_v2": db_session.query(TakeoffItemV2).filter(TakeoffItemV2.project_id == project_id).count(),
    }


def test_delete_removes_project_and_all_children(client, auth_headers, db_session, test_user):
    project_id = _seed_project_with_children(db_session, owner_id=test_user.id)

    # Pre-delete: all present
    pre = _child_counts(db_session, project_id)
    assert pre == {
        "project": 1,
        "documents": 1,
        "spec_sections": 1,
        "work_categories": 1,
        "agent_run_logs": 1,
        "takeoff_items_v2": 1,
    }

    res = client.delete(f"/api/projects/{project_id}", headers=auth_headers)
    assert res.status_code == 204

    # Post-delete: everything gone
    db_session.expire_all()
    post = _child_counts(db_session, project_id)
    assert post == {
        "project": 0,
        "documents": 0,
        "spec_sections": 0,
        "work_categories": 0,
        "agent_run_logs": 0,
        "takeoff_items_v2": 0,
    }


def test_delete_returns_204_preserving_api_contract(client, auth_headers, db_session, test_user):
    """The pre-fix handler returned 204. The contract is unchanged."""
    import uuid

    proj = Project(
        name="Empty",
        project_number=f"HD-EMPTY-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=test_user.id,
    )
    db_session.add(proj)
    db_session.commit()
    pid = proj.id

    res = client.delete(f"/api/projects/{pid}", headers=auth_headers)
    assert res.status_code == 204
    assert res.content == b""


def test_delete_does_not_touch_other_projects(client, auth_headers, db_session, test_user):
    """Deleting one project must leave another user-owned project's
    children untouched. Regression guard against cascade-query scoping bugs."""
    keep_id = _seed_project_with_children(db_session, owner_id=test_user.id, label="KEEP")
    doomed_id = _seed_project_with_children(db_session, owner_id=test_user.id, label="DOOM")

    res = client.delete(f"/api/projects/{doomed_id}", headers=auth_headers)
    assert res.status_code == 204

    db_session.expire_all()
    keep_counts = _child_counts(db_session, keep_id)
    doomed_counts = _child_counts(db_session, doomed_id)
    assert all(v == 1 for v in keep_counts.values())
    assert all(v == 0 for v in doomed_counts.values())
