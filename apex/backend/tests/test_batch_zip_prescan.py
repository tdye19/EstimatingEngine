"""Tests for batch ZIP pre-scan (Spec 19C.3).

Tests call pre_scan_zip() directly for unit coverage plus HTTP-level
integration tests to verify fail-closed behavior (no extraction, no DB rows).
All ZIPs are constructed via zipfile stdlib — no external test data.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from apex.backend.routers.batch_import import pre_scan_zip

# Small limits used by unit tests so we don't need multi-GB files.
_LIMITS = dict(
    max_uncompressed_bytes=10_000,
    max_files=5,
    max_per_file_bytes=5_000,
    allowed_extensions=frozenset({".pdf", ".docx", ".xlsx", ".est", ".csv"}),
)


def _make_zip(files: dict[str, bytes], compression: int = zipfile.ZIP_STORED) -> bytes:
    """Build a ZIP in memory. files maps filename → content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _write_tmp(data: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.write(fd, data)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_zip_accepted(tmp_path):
    zip_path = _write_tmp(_make_zip({"a.pdf": b"data", "b.csv": b"col1,col2"}))
    try:
        pre_scan_zip(zip_path, **_LIMITS)  # must not raise
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# File count limit
# ---------------------------------------------------------------------------

def test_file_count_exceeds_max_rejected(tmp_path):
    files = {f"file{i}.pdf": b"x" for i in range(6)}  # 6 > max_files=5
    zip_path = _write_tmp(_make_zip(files))
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "maximum" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# Cumulative uncompressed size limit
# ---------------------------------------------------------------------------

def test_cumulative_uncompressed_exceeds_max_rejected(tmp_path):
    # 3 files × 4000 bytes each = 12000 > max_uncompressed_bytes=10000
    files = {f"f{i}.pdf": b"x" * 4000 for i in range(3)}
    zip_path = _write_tmp(_make_zip(files))
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "total uncompressed" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# Per-file size limit
# ---------------------------------------------------------------------------

def test_single_file_exceeds_per_file_max_rejected(tmp_path):
    # One file of 6000 bytes > max_per_file_bytes=5000
    zip_path = _write_tmp(_make_zip({"big.pdf": b"x" * 6000}))
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "per-file maximum" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# Extension whitelist
# ---------------------------------------------------------------------------

def test_disallowed_extension_rejected(tmp_path):
    zip_path = _write_tmp(_make_zip({"malware.exe": b"MZ\x90\x00"}))
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "disallowed extension" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# Zip-bomb: compression ratio > 100:1
# ---------------------------------------------------------------------------

def test_zip_bomb_ratio_rejected(tmp_path):
    # 100 KB of repeated bytes compresses to ~100 bytes with DEFLATE → ratio ~1000:1
    compressible = b"A" * 102_400
    zip_path = _write_tmp(
        _make_zip({"bomb.pdf": compressible}, compression=zipfile.ZIP_DEFLATED)
    )
    try:
        with zipfile.ZipFile(zip_path) as zf:
            entry = zf.infolist()[0]
            # Verify ratio > 100 so the test is meaningful
            assert entry.compress_size > 0
            assert entry.file_size / entry.compress_size > 100, (
                f"Expected ratio > 100, got {entry.file_size / entry.compress_size:.1f}"
            )

        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(
                zip_path,
                max_uncompressed_bytes=10 * 1024 * 1024,  # 10 MB — won't trip total limit
                max_files=5,
                max_per_file_bytes=10 * 1024 * 1024,  # 10 MB — won't trip per-file limit
                allowed_extensions=frozenset({".pdf"}),
            )
        assert exc_info.value.status_code == 400
        assert "zip-bomb" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------

def test_path_traversal_dotdot_rejected(tmp_path):
    zip_path = _write_tmp(_make_zip({"../../etc/passwd": b"root:x:0:0:"}))
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


def test_path_traversal_absolute_rejected(tmp_path):
    # Manually craft a ZIP with an absolute path entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("/etc/passwd")
        zf.writestr(info, b"root:x:0:0:")
    zip_path = _write_tmp(buf.getvalue())
    try:
        with pytest.raises(HTTPException) as exc_info:
            pre_scan_zip(zip_path, **_LIMITS)
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()
    finally:
        os.unlink(zip_path)


# ---------------------------------------------------------------------------
# HTTP integration: rejected ZIP produces no extraction artifacts
# ---------------------------------------------------------------------------

def test_http_rejected_zip_leaves_no_artifacts(client, auth_headers, db_session):
    """A ZIP that fails pre-scan must not extract any files or create DB rows."""
    from apex.backend.models.document_association import DocumentGroup

    group_count_before = db_session.query(DocumentGroup).count()

    # Build a ZIP with a disallowed extension
    zip_bytes = _make_zip({"virus.exe": b"MZ"})
    res = client.post(
        "/api/batch-import/upload-zip",
        files={"file": ("test.zip", zip_bytes, "application/zip")},
        headers=auth_headers,
    )
    assert res.status_code == 400

    # No new DocumentGroup rows
    group_count_after = db_session.query(DocumentGroup).count()
    assert group_count_after == group_count_before
