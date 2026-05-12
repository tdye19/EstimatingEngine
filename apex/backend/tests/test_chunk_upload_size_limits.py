"""Tests for chunk upload size enforcement (Spec 19C.2).

Tests:
 - Chunk equal to CHUNK_SIZE accepted
 - Chunk one byte over CHUNK_SIZE rejected with 413, session aborted
 - Cumulative exceeding declared total_size rejected with 413
 - Upload initiation with total_size > MAX_UPLOAD_SIZE rejected with 413
 - After rejection, subsequent chunk attempt returns 404
 - No orphan files/DB rows after rejection
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apex.backend.config import CHUNK_SIZE, MAX_UPLOAD_SIZE, SESSION_TTL, UPLOAD_DIR
from apex.backend.models.project import Project
from apex.backend.models.upload_session import UploadSession


@pytest.fixture
def upload_project(db_session, test_user) -> Project:
    project = Project(
        name="Chunk Limit Test",
        project_number=f"CLT-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=test_user.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _make_session(db_session, project_id: int, file_size: int, tmp_path: Path) -> UploadSession:
    """Insert an UploadSession directly, bypassing the init endpoint."""
    upload_id = str(uuid.uuid4())
    import math

    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    temp_dir = str(tmp_path / upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    session = UploadSession(
        upload_id=upload_id,
        project_id=project_id,
        filename="test.pdf",
        file_size=file_size,
        content_type="application/pdf",
        total_chunks=total_chunks,
        next_chunk=0,
        bytes_received=0,
        temp_dir=temp_dir,
        expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_TTL),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def _chunk_url(project_id: int, upload_id: str) -> str:
    return f"/api/projects/{project_id}/documents/upload/{upload_id}/chunk"


# ---------------------------------------------------------------------------
# Test: init endpoint rejects total_size > MAX_UPLOAD_SIZE with 413
# ---------------------------------------------------------------------------

def test_init_rejects_oversized_file(client, upload_project, auth_headers):
    too_large = MAX_UPLOAD_SIZE + 1
    res = client.post(
        f"/api/projects/{upload_project.id}/documents/upload/init",
        json={"filename": "huge.pdf", "file_size": too_large, "content_type": "application/pdf"},
        headers=auth_headers,
    )
    assert res.status_code == 413


def test_init_accepts_max_size_file(client, upload_project, auth_headers):
    res = client.post(
        f"/api/projects/{upload_project.id}/documents/upload/init",
        json={"filename": "ok.pdf", "file_size": MAX_UPLOAD_SIZE, "content_type": "application/pdf"},
        headers=auth_headers,
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Test: per-chunk size enforcement
# ---------------------------------------------------------------------------

def test_chunk_equal_to_chunk_size_accepted(client, upload_project, db_session, tmp_path, auth_headers):
    file_size = CHUNK_SIZE
    session = _make_session(db_session, upload_project.id, file_size, tmp_path)
    exact_chunk = b"x" * CHUNK_SIZE

    res = client.post(
        _chunk_url(upload_project.id, session.upload_id),
        params={"chunk_number": 0},
        files={"chunk": ("test.pdf", exact_chunk, "application/pdf")},
        headers=auth_headers,
    )
    assert res.status_code == 200


def test_chunk_one_byte_over_chunk_size_rejected_413(
    client, upload_project, db_session, tmp_path, auth_headers
):
    file_size = CHUNK_SIZE + 100
    session = _make_session(db_session, upload_project.id, file_size, tmp_path)
    oversized = b"x" * (CHUNK_SIZE + 1)

    res = client.post(
        _chunk_url(upload_project.id, session.upload_id),
        params={"chunk_number": 0},
        files={"chunk": ("test.pdf", oversized, "application/pdf")},
        headers=auth_headers,
    )
    assert res.status_code == 413
    assert "exceeds maximum" in res.json()["detail"]

    # Session must be deleted after abort
    db_session.expire_all()
    aborted = (
        db_session.query(UploadSession)
        .filter(UploadSession.upload_id == session.upload_id)
        .first()
    )
    assert aborted is None

    # Temp dir must be cleaned up
    assert not os.path.isdir(session.temp_dir)


def test_oversized_chunk_subsequent_request_returns_404(
    client, upload_project, db_session, tmp_path, auth_headers
):
    file_size = CHUNK_SIZE + 100
    session = _make_session(db_session, upload_project.id, file_size, tmp_path)
    oversized = b"x" * (CHUNK_SIZE + 1)

    # First chunk aborts the session
    client.post(
        _chunk_url(upload_project.id, session.upload_id),
        params={"chunk_number": 0},
        files={"chunk": ("test.pdf", oversized, "application/pdf")},
        headers=auth_headers,
    )

    # Second attempt on same upload_id returns 404 (session deleted)
    res = client.post(
        _chunk_url(upload_project.id, session.upload_id),
        params={"chunk_number": 0},
        files={"chunk": ("test.pdf", b"retry", "application/pdf")},
        headers=auth_headers,
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Test: cumulative bytes enforcement
# ---------------------------------------------------------------------------

def test_cumulative_exceeding_declared_size_rejected_413(
    client, upload_project, db_session, tmp_path, auth_headers
):
    # Declare 10 bytes, then try to send 11
    file_size = 10
    session = _make_session(db_session, upload_project.id, file_size, tmp_path)

    res = client.post(
        _chunk_url(upload_project.id, session.upload_id),
        params={"chunk_number": 0},
        files={"chunk": ("test.pdf", b"x" * 11, "application/pdf")},
        headers=auth_headers,
    )
    assert res.status_code == 413
    assert "declared file size" in res.json()["detail"]

    # Session aborted
    db_session.expire_all()
    assert (
        db_session.query(UploadSession)
        .filter(UploadSession.upload_id == session.upload_id)
        .first()
    ) is None

    # Temp dir cleaned up
    assert not os.path.isdir(session.temp_dir)
