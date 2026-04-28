"""Tests for auth environment edge cases."""

import os
import subprocess
import sys


def test_auth_requires_jwt_secret_in_production(monkeypatch):
    monkeypatch.setenv("APEX_DEV_MODE", "false")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; os.environ['APEX_DEV_MODE']='false'; os.environ.pop('JWT_SECRET_KEY', None); from apex.backend.utils import auth",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "JWT_SECRET_KEY environment variable is required" in result.stderr


def test_auth_dev_mode_uses_default_key():
    from apex.backend.utils import auth

    assert auth.SECRET_KEY == "apex-dev-secret-DO-NOT-USE-IN-PRODUCTION"
