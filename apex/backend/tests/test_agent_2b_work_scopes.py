"""Tests for Agent 2B - Work Scope Parser orchestration (Sprint 18.1.3)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from apex.backend.agents.agent_2b_work_scopes import run_work_scope_agent
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.work_category import WorkCategory


@pytest.fixture
def sample_project(db_session: Session):
    """Create a project with two docs: one work scope, one pure spec.

    project_number is UUID-suffixed so tests against the shared in-memory
    SQLite DB (conftest.py uses StaticPool) don't collide.
    """
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Test Project {suffix}",
        project_number=f"TP-18.1.3-{suffix}",
        project_type="commercial",
        status="draft",
    )
    db_session.add(p)
    db_session.flush()

    d1 = Document(
        project_id=p.id,
        filename="Volume 2 - Work Scopes.pdf",
        file_path="/fake/path1",
        file_type="pdf",
        classification="spec",
        raw_text=(
            "WC 01 - Concrete Work\n"
            "Work Included:\n"
            "- Formwork\n"
            "- Rebar\n"
            "\n"
            "WC 02 - Steel Work\n"
            "Work Included:\n"
            "- Erection\n"
        ),
        processing_status="completed",
    )
    d2 = Document(
        project_id=p.id,
        filename="Specs - Division 03.pdf",
        file_path="/fake/path2",
        file_type="pdf",
        classification="spec",
        raw_text="Section 03 30 00. Cast-in-place concrete shall be...",
        processing_status="completed",
    )
    db_session.add_all([d1, d2])
    db_session.commit()
    return p


def test_creates_work_categories_from_work_scope_doc(db_session, sample_project):
    """Classifier-driven: work scope doc parsed, pure spec doc skipped."""
    output = run_work_scope_agent(db_session, sample_project.id, use_llm=False)

    assert output["work_categories_created"] == 2
    assert output["work_categories_updated"] == 0
    assert output["documents_examined"] == 2
    assert output["documents_parsed"] == 1
    assert output["classification_summary"]["no_work_scope"] == 1

    wcs = (
        db_session.query(WorkCategory)
        .filter(WorkCategory.project_id == sample_project.id)
        .order_by(WorkCategory.wc_number)
        .all()
    )
    assert [w.wc_number for w in wcs] == ["WC 01", "WC 02"]
    # source_document_id should point at the work-scope doc, not the spec doc
    ws_doc = (
        db_session.query(Document)
        .filter(Document.filename == "Volume 2 - Work Scopes.pdf")
        .first()
    )
    assert all(w.source_document_id == ws_doc.id for w in wcs)


def test_upsert_behavior_on_rerun(db_session, sample_project):
    """Second run updates existing rows instead of creating duplicates."""
    run_work_scope_agent(db_session, sample_project.id, use_llm=False)
    output2 = run_work_scope_agent(db_session, sample_project.id, use_llm=False)

    assert output2["work_categories_created"] == 0
    assert output2["work_categories_updated"] == 2

    count = (
        db_session.query(WorkCategory)
        .filter(WorkCategory.project_id == sample_project.id)
        .count()
    )
    assert count == 2  # unique constraint held


def test_empty_document_raw_text_produces_warning(db_session, sample_project):
    """Documents with empty raw_text are skipped with a warning."""
    empty_doc = Document(
        project_id=sample_project.id,
        filename="empty.pdf",
        file_path="/fake/empty",
        file_type="pdf",
        classification="other",
        raw_text="",
        processing_status="completed",
    )
    db_session.add(empty_doc)
    db_session.commit()

    output = run_work_scope_agent(db_session, sample_project.id, use_llm=False)
    assert any(
        "empty.pdf" in w and "empty raw_text" in w for w in output["warnings"]
    )


def test_agent_2b_propagates_unexpected_errors(db_session, sample_project):
    """Parser exceptions propagate; orchestrator catches them, not the agent.

    This test pins the contract: the agent itself raises so developers can
    debug. The orchestrator's try/except keeps downstream agents running.
    Don't double-wrap exceptions — they're signal, not noise.
    """
    with patch(
        "apex.backend.agents.agent_2b_work_scopes.parse_work_scopes",
        side_effect=RuntimeError("parser exploded"),
    ):
        with pytest.raises(RuntimeError, match="parser exploded"):
            run_work_scope_agent(db_session, sample_project.id, use_llm=False)
