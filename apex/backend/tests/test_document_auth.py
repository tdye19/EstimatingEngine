"""Tests for document auth migration: query-param token → signed blob URL."""

import os
import time
import tempfile

import pytest

from apex.backend.models.document import Document
from apex.backend.utils.auth import (
    BLOB_TOKEN_TTL_SECONDS,
    create_access_token,
    create_blob_token,
    verify_blob_token,
)
from fastapi import HTTPException


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def test_document(db_session, test_project):
    """Create a real temp file and a Document row for it."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake content")
        tmp_path = f.name

    doc = Document(
        project_id=test_project.id,
        filename="test.pdf",
        file_path=tmp_path,
        file_type="pdf",
        file_size_bytes=20,
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    yield doc
    os.unlink(tmp_path)


# ── signed-url endpoint tests ─────────────────────────────────────────────────

class TestSignedUrlEndpoint:
    def test_signed_url_endpoint_returns_short_lived_token(self, client, auth_headers, test_project, test_document):
        res = client.post(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/signed-url",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "signed_url" in data
        assert "expires_at" in data
        assert f"blob_token=" in data["signed_url"]
        assert f"/projects/{test_project.id}/documents/{test_document.id}/file" in data["signed_url"]

    def test_doc_endpoint_requires_authorization_header(self, client, test_project, test_document):
        """Signed-url endpoint rejects requests with no auth."""
        res = client.post(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/signed-url",
        )
        assert res.status_code == 401

    def test_signed_url_endpoint_rejects_wrong_user(self, client, test_project, test_document, db_session):
        """A user who doesn't own the project cannot get a signed URL."""
        from apex.backend.models.user import User
        from apex.backend.utils.auth import hash_password
        import uuid

        stranger = User(
            email=f"stranger-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pass123"),
            full_name="Stranger",
            role="estimator",
        )
        db_session.add(stranger)
        db_session.commit()
        db_session.refresh(stranger)

        token = create_access_token({"sub": str(stranger.id), "email": stranger.email})
        res = client.post(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/signed-url",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403


# ── file endpoint tests ───────────────────────────────────────────────────────

class TestDocumentFileEndpoint:
    def test_doc_endpoint_rejects_query_param_token(self, client, test_project, test_document, test_user):
        """Regression: old JWT query-param token must be rejected (blob_token required)."""
        jwt_token = create_access_token({"sub": str(test_user.id), "email": test_user.email})
        res = client.get(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/file?token={jwt_token}",
        )
        # blob_token query param is required; token= is unknown — expect 422 (missing required param)
        assert res.status_code == 422

    def test_file_endpoint_accepts_valid_blob_token(self, client, test_project, test_document):
        blob_token = create_blob_token(test_document.id)
        res = client.get(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/file?blob_token={blob_token}",
        )
        assert res.status_code == 200

    def test_file_endpoint_rejects_tampered_blob_token(self, client, test_project, test_document):
        res = client.get(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/file?blob_token=not.a.real.token",
        )
        assert res.status_code == 401

    def test_file_endpoint_rejects_mismatched_doc_id(self, client, test_project, test_document):
        """A valid blob token for doc 999 must not grant access to a different doc_id in the URL."""
        blob_token = create_blob_token(999)
        res = client.get(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/file?blob_token={blob_token}",
        )
        assert res.status_code == 401

    def test_signed_blob_token_expires_after_ttl(self, client, test_project, test_document):
        """An expired blob token must be rejected with 401."""
        # Create a token that expired 1 second ago
        expired_token = create_blob_token(test_document.id, ttl_seconds=-1)
        res = client.get(
            f"/api/projects/{test_project.id}/documents/{test_document.id}/file?blob_token={expired_token}",
        )
        assert res.status_code == 401


# ── verify_blob_token unit tests ──────────────────────────────────────────────

class TestVerifyBlobToken:
    def test_valid_blob_token_returns_doc_id(self):
        token = create_blob_token(42)
        assert verify_blob_token(token) == 42

    def test_expired_blob_token_raises_401(self):
        expired = create_blob_token(42, ttl_seconds=-1)
        with pytest.raises(HTTPException) as exc:
            verify_blob_token(expired)
        assert exc.value.status_code == 401

    def test_user_jwt_rejected_as_blob_token(self):
        """A regular user JWT must not pass as a blob token (wrong type claim)."""
        user_jwt = create_access_token({"sub": "1", "email": "x@example.com"})
        with pytest.raises(HTTPException) as exc:
            verify_blob_token(user_jwt)
        assert exc.value.status_code == 401
