"""Tests for the admin seed-test-gap-findings HTTP endpoint.

TEMPORARY — Sprint 18.3.3.1 validation maintenance window. Remove via
follow-up chore PR after summit validation (same teardown pattern as
PR #82 for the PR #79 / PR #80 diagnostics).

Covers:
  * feature flag gating (404 when off)
  * happy path (200, 5 rows, exact finding_type + severity distribution)
  * idempotence (two invocations → still exactly 5 rows, not 10)
  * unknown project_id → 404
"""

from __future__ import annotations

import uuid

import pytest

from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.project import Project

URL_TEMPLATE = "/api/admin/diagnostics/seed-test-gap-findings/{project_id}"
FLAG_ENV = "APEX_ENABLE_SEED_GAP_FINDINGS"


@pytest.fixture(autouse=True)
def _scrub_findings(db_session):
    """Shared in-memory engine persists commits across tests; reset state."""
    db_session.query(GapFinding).delete()
    db_session.commit()
    yield


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.delenv(FLAG_ENV, raising=False)


@pytest.fixture
def seed_project(db_session, test_user) -> Project:
    """A freshly created project to target with the seed endpoint."""
    project = Project(
        name="Seed Target",
        project_number=f"SEED-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=test_user.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def test_seed_endpoint_flag_disabled_returns_403(
    client, admin_headers, flag_off, seed_project
):
    """Flag name retained from spec; actual status is 404 per PR #79
    invisibility pattern (see Sprint 18.3.3.1-VALIDATE Amendment 1, #1)."""
    res = client.post(URL_TEMPLATE.format(project_id=seed_project.id), headers=admin_headers)
    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


def test_seed_endpoint_flag_enabled_seeds_five_rows(
    client, admin_headers, flag_on, seed_project, db_session
):
    res = client.post(URL_TEMPLATE.format(project_id=seed_project.id), headers=admin_headers)
    assert res.status_code == 200

    body = res.json()
    assert body["project_id"] == seed_project.id
    assert body["seeded_count"] == 5
    assert body["finding_types"] == {
        "in_scope_not_estimated": 2,
        "estimated_out_of_scope": 1,
        "partial_coverage": 2,
    }
    assert body["severities"] == {"ERROR": 1, "WARNING": 2, "INFO": 2}

    rows = (
        db_session.query(GapFinding)
        .filter(GapFinding.project_id == seed_project.id)
        .all()
    )
    assert len(rows) == 5

    finding_type_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for r in rows:
        finding_type_counts[r.finding_type] = finding_type_counts.get(r.finding_type, 0) + 1
        severity_counts[r.severity] = severity_counts.get(r.severity, 0) + 1
        source_counts[r.source] = source_counts.get(r.source, 0) + 1

    assert finding_type_counts == {
        "in_scope_not_estimated": 2,
        "estimated_out_of_scope": 1,
        "partial_coverage": 2,
    }
    assert severity_counts == {"ERROR": 1, "WARNING": 2, "INFO": 2}
    # 4 rule / 1 llm per Amendment 1 resolution #3.
    assert source_counts == {"rule": 4, "llm": 1}


def test_seed_endpoint_is_idempotent(
    client, admin_headers, flag_on, seed_project, db_session
):
    for _ in range(2):
        res = client.post(URL_TEMPLATE.format(project_id=seed_project.id), headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["seeded_count"] == 5

    # After two invocations, still exactly 5 rows — delete-then-insert
    # matches Agent 3.5's per-project regeneration contract.
    rows = (
        db_session.query(GapFinding)
        .filter(GapFinding.project_id == seed_project.id)
        .all()
    )
    assert len(rows) == 5


def test_seed_endpoint_unknown_project_returns_404(
    client, admin_headers, flag_on, db_session
):
    unknown_id = 999_999_999
    assert db_session.query(Project).filter(Project.id == unknown_id).first() is None

    res = client.post(URL_TEMPLATE.format(project_id=unknown_id), headers=admin_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == f"Project {unknown_id} not found"

    # No rows seeded for the nonexistent project.
    assert (
        db_session.query(GapFinding).filter(GapFinding.project_id == unknown_id).count() == 0
    )
