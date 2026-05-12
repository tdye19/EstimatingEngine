"""Smoke tests for admin_diagnostics_cli — seed-gap-findings subcommand."""

from __future__ import annotations

import uuid

import pytest

from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.project import Project
from apex.backend.scripts.admin_diagnostics_cli import seed_gap_findings


@pytest.fixture
def seed_project(db_session, test_user) -> Project:
    project = Project(
        name="CLI Seed Target",
        project_number=f"CLI-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=test_user.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture(autouse=True)
def _scrub_findings(db_session):
    db_session.query(GapFinding).delete()
    db_session.commit()
    yield


def test_seed_gap_findings_creates_five_rows(seed_project, db_session):
    result = seed_gap_findings(seed_project.id, db_session)

    assert result["seeded_count"] == 5
    assert result["project_id"] == seed_project.id
    assert result["finding_types"] == {
        "in_scope_not_estimated": 2,
        "estimated_out_of_scope": 1,
        "partial_coverage": 2,
    }
    assert result["severities"] == {"ERROR": 1, "WARNING": 2, "INFO": 2}

    rows = (
        db_session.query(GapFinding)
        .filter(GapFinding.project_id == seed_project.id)
        .all()
    )
    assert len(rows) == 5
    source_counts: dict[str, int] = {}
    for r in rows:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1
    assert source_counts == {"rule": 4, "llm": 1}


def test_seed_gap_findings_is_idempotent(seed_project, db_session):
    for _ in range(2):
        result = seed_gap_findings(seed_project.id, db_session)
        assert result["seeded_count"] == 5

    rows = (
        db_session.query(GapFinding)
        .filter(GapFinding.project_id == seed_project.id)
        .all()
    )
    assert len(rows) == 5


def test_seed_gap_findings_unknown_project_raises(db_session):
    with pytest.raises(ValueError, match="not found"):
        seed_gap_findings(999_999_999, db_session)
