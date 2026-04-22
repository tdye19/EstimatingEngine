"""Tests for the admin schema-repair endpoint that backfills
bid_outcomes.estimate_run_id on drifted Railway SQLite databases.

Covers:
  * feature flag gating (404 when APEX_ENABLE_SCHEMA_REPAIR unset)
  * role enforcement (403 for non-admin with flag on)
  * cold ALTER path: column missing → column added, both PRAGMA lists returned
  * idempotency: column already present → no-op, both lists equal, altered=False
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

URL = "/api/admin/diagnostics/repair-bid-outcomes-column"
FLAG_ENV = "APEX_ENABLE_SCHEMA_REPAIR"


@pytest.fixture
def repair_flag_on(monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")


@pytest.fixture
def repair_flag_off(monkeypatch):
    monkeypatch.delenv(FLAG_ENV, raising=False)


def _drop_estimate_run_id_column(db_session) -> None:
    """Simulate Railway drift: drop bid_outcomes and recreate without
    estimate_run_id. DDL auto-commits on SQLite, so this persists across
    the session rollback performed at fixture teardown.
    """
    db_session.execute(text("DROP TABLE IF EXISTS bid_outcomes"))
    db_session.execute(
        text(
            """
            CREATE TABLE bid_outcomes (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                outcome VARCHAR(20),
                final_bid_submitted FLOAT,
                winning_bid_value FLOAT,
                delta_to_winner FLOAT,
                notes TEXT,
                recorded_at DATETIME
            )
            """
        )
    )
    db_session.commit()


def _pragma_column_names(db_session, table: str) -> list[str]:
    return [r[1] for r in db_session.execute(text(f"PRAGMA table_info({table})")).fetchall()]


def test_flag_off_returns_404_even_with_admin(client, admin_headers, repair_flag_off):
    res = client.post(URL, headers=admin_headers)
    assert res.status_code == 404


def test_non_admin_with_flag_on_returns_403(client, auth_headers, repair_flag_on):
    res = client.post(URL, headers=auth_headers)
    assert res.status_code == 403


def test_repair_adds_missing_column_and_reports_before_after(
    client, admin_headers, repair_flag_on, db_session
):
    _drop_estimate_run_id_column(db_session)
    columns_before = _pragma_column_names(db_session, "bid_outcomes")
    assert "estimate_run_id" not in columns_before

    res = client.post(URL, headers=admin_headers)
    assert res.status_code == 200

    body = res.json()
    assert body["altered"] is True
    assert "estimate_run_id" not in body["columns_before"]
    assert "estimate_run_id" in body["columns_after"]
    assert set(body["columns_before"]) | {"estimate_run_id"} == set(body["columns_after"])

    # And the underlying table is actually altered.
    assert "estimate_run_id" in _pragma_column_names(db_session, "bid_outcomes")


def test_repair_is_idempotent_when_column_already_present(
    client, admin_headers, repair_flag_on, db_session
):
    # Ensure the column is present (it will be, from Base.metadata.create_all
    # in conftest — but a prior test in this module may have left it in any
    # state, so force-verify before calling).
    cols = _pragma_column_names(db_session, "bid_outcomes")
    if "estimate_run_id" not in cols:
        db_session.execute(
            text(
                "ALTER TABLE bid_outcomes "
                "ADD COLUMN estimate_run_id VARCHAR(36) REFERENCES estimate_runs(id)"
            )
        )
        db_session.commit()

    res = client.post(URL, headers=admin_headers)
    assert res.status_code == 200

    body = res.json()
    assert body["altered"] is False
    assert "estimate_run_id" in body["columns_before"]
    assert body["columns_before"] == body["columns_after"]
