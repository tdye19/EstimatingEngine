"""Tests for the admin orphan-cleanup HTTP endpoint.

Covers:
  * feature flag gating (404 when off)
  * auth (401) and role (403) enforcement
  * dry_run=true happy path
  * real-run confirm-token requirement (400)
  * real-run with correct confirm → projects + children removed
"""

from __future__ import annotations

import uuid

import pytest

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.work_category import WorkCategory

URL = "/api/admin/diagnostics/run-orphan-cleanup"
FLAG_ENV = "APEX_ENABLE_CLEANUP_RUN"


@pytest.fixture(autouse=True)
def _scrub_projects(db_session):
    """Shared in-memory engine persists commits across tests; reset state."""
    for Model in (SpecSection, Document, WorkCategory, AgentRunLog):
        db_session.query(Model).delete()
    db_session.query(Project).delete()
    db_session.commit()
    yield


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.delenv(FLAG_ENV, raising=False)


def _seed_soft_deleted_with_children(db_session, owner_id: int) -> int:
    proj = Project(
        name="to-delete",
        project_number=f"DEL-{uuid.uuid4().hex[:6]}",
        project_type="commercial",
        status="draft",
        owner_id=owner_id,
        is_deleted=True,
    )
    db_session.add(proj)
    db_session.flush()
    doc = Document(
        project_id=proj.id,
        filename="x.pdf",
        file_path="/tmp/x.pdf",
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
        title="s",
    ))
    db_session.commit()
    return proj.id


class TestFlagGating:
    def test_flag_off_returns_404_even_with_admin(self, client, admin_headers, flag_off):
        res = client.post(URL, headers=admin_headers)
        assert res.status_code == 404

    def test_flag_off_returns_404_unauthenticated(self, client, flag_off):
        res = client.post(URL)
        assert res.status_code == 404


class TestAuth:
    def test_unauthenticated_returns_401(self, client, flag_on):
        res = client.post(URL)
        assert res.status_code == 401

    def test_non_admin_returns_403(self, client, auth_headers, flag_on):
        res = client.post(URL, headers=auth_headers)
        assert res.status_code == 403


class TestDryRun:
    def test_dry_run_true_returns_report_and_writes_nothing(
        self, client, admin_headers, flag_on, db_session, admin_user
    ):
        project_id = _seed_soft_deleted_with_children(db_session, admin_user.id)

        res = client.post(f"{URL}?dry_run=true", headers=admin_headers)
        assert res.status_code == 200

        body = res.json()
        assert body["dry_run"] is True
        assert body["projects_deleted"] == 0
        assert project_id in body["soft_deleted_project_ids"]
        assert body["per_table_rowcounts_before"].get("documents") == 1
        assert body["aborted_with"] is None

        # Nothing actually deleted
        db_session.expire_all()
        assert db_session.query(Project).filter(Project.id == project_id).count() == 1


class TestRealRun:
    def test_real_run_without_confirm_returns_400(self, client, admin_headers, flag_on):
        res = client.post(f"{URL}?dry_run=false", headers=admin_headers)
        assert res.status_code == 400
        assert "YES_DELETE" in res.json()["detail"]

    def test_real_run_with_wrong_confirm_returns_400(self, client, admin_headers, flag_on):
        res = client.post(f"{URL}?dry_run=false&confirm=YES", headers=admin_headers)
        assert res.status_code == 400

    def test_real_run_with_confirm_deletes_projects(
        self, client, admin_headers, flag_on, db_session, admin_user
    ):
        project_id = _seed_soft_deleted_with_children(db_session, admin_user.id)

        res = client.post(
            f"{URL}?dry_run=false&confirm=YES_DELETE", headers=admin_headers
        )
        assert res.status_code == 200

        body = res.json()
        assert body["dry_run"] is False
        assert body["projects_deleted"] == 1
        assert project_id in body["soft_deleted_project_ids"]
        assert body["aborted_with"] is None

        db_session.expire_all()
        assert db_session.query(Project).filter(Project.id == project_id).count() == 0
        assert db_session.query(Document).filter(Document.project_id == project_id).count() == 0
        assert db_session.query(SpecSection).filter(SpecSection.project_id == project_id).count() == 0
