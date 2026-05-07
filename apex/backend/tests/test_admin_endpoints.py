"""Tests for admin project-scoped endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apex.backend.agents import agent_3_gap_analysis as a3
from apex.backend.models.gap_report import GapReport
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.document import Document


@pytest.fixture
def admin_project(db_session, admin_user):
    project = Project(
        name=f"Admin EP Test {uuid.uuid4().hex[:6]}",
        project_number=f"AEP-{uuid.uuid4().hex[:6]}",
        project_type="commercial",
        status="draft",
        owner_id=admin_user.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


URL = "/api/admin/projects/{project_id}/agent-3/force-rule-based"


def test_force_rule_based_endpoint_requires_admin(client, auth_headers, test_project):
    """Non-admin (estimator) gets 403."""
    res = client.post(URL.format(project_id=test_project.id), headers=auth_headers)
    assert res.status_code == 403


def test_force_rule_based_endpoint_creates_new_report(client, admin_headers, db_session, admin_project):
    """Admin POST creates a new GapReport and returns the expected response shape."""
    before = db_session.query(GapReport).filter(GapReport.project_id == admin_project.id).count()

    with patch.object(a3, "run_domain_rules", return_value=[]):
        res = client.post(URL.format(project_id=admin_project.id), headers=admin_headers)

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["gap_report_id"] is not None
    assert data["analysis_method"] in {"rule_based", "rule_based_empty_fallback_to_checklist"}
    assert data["agent_run_log_id"] is not None

    db_session.expire_all()
    after = db_session.query(GapReport).filter(GapReport.project_id == admin_project.id).count()
    assert after == before + 1
