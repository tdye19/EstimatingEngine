"""Tests for LineItemWCAttribution (Sprint 18.4.1 Part C).

Covers the persistent takeoff-item → WorkCategory attribution service:
  - table schema
  - every takeoff item produces exactly one attribution row per run
  - tier 1 csi_exact populates work_category_id with confidence 1.0
  - unmatched items produce rows with work_category_id=NULL and match_tier="unmatched"
  - delete-then-insert idempotency (running the matcher twice = N rows, not 2N)
  - GET /api/projects/{id}/line-item-attributions response envelope + JOIN data
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from apex.backend.agents.agent_3_5_scope_matcher import run_scope_matcher_agent
from apex.backend.db.database import engine as _engine
from apex.backend.models.document import Document
from apex.backend.models.line_item_wc_attribution import LineItemWCAttribution
from apex.backend.models.project import Project
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.work_category import WorkCategory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(db_session: Session):
    """Minimal project for attribution tests."""
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Attribution Test {suffix}",
        project_number=f"LIA-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    # Document + Estimate aren't needed — Agent 3.5 now reads TakeoffItemV2
    # directly (Sprint 18.4.1 Part A).
    doc = Document(
        project_id=p.id,
        filename="dummy.pdf",
        file_path="/fake/dummy.pdf",
        file_type="pdf",
        classification="spec",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_takeoff(
    db_session: Session, project_id: int, row_number: int, **kw
) -> TakeoffItemV2:
    defaults = {
        "project_id": project_id,
        "row_number": row_number,
        "activity": f"Row {row_number}",
        "csi_code": None,
        "quantity": 1.0,
        "unit": "EA",
    }
    defaults.update(kw)
    ti = TakeoffItemV2(**defaults)
    db_session.add(ti)
    db_session.commit()
    db_session.refresh(ti)
    return ti


def _make_wc(db_session: Session, project_id: int, **kw) -> WorkCategory:
    defaults = {
        "project_id": project_id,
        "wc_number": "03",
        "title": "Structural Concrete",
        "work_included_items": [],
        "specific_notes": [],
        "related_work_by_others": [],
        "add_alternates": [],
        "allowances": [],
        "unit_prices": [],
        "referenced_spec_sections": [],
    }
    defaults.update(kw)
    wc = WorkCategory(**defaults)
    db_session.add(wc)
    db_session.commit()
    db_session.refresh(wc)
    return wc


# ---------------------------------------------------------------------------
# 1. Schema — model registered, table exists with expected columns
# ---------------------------------------------------------------------------


def test_migration_creates_table():
    """LineItemWCAttribution model is registered and its table is created
    in the shared test engine (which runs Base.metadata.create_all off the
    same metadata the alembic migration emits)."""
    inspector = inspect(_engine)
    assert "line_item_wc_attributions" in inspector.get_table_names()

    cols = {c["name"]: c for c in inspector.get_columns("line_item_wc_attributions")}
    # Required columns present
    for name in (
        "id",
        "project_id",
        "takeoff_item_id",
        "work_category_id",
        "match_tier",
        "confidence",
        "rationale",
        "source",
        "created_at",
    ):
        assert name in cols, f"Expected column {name!r} on line_item_wc_attributions"

    # Nullability contract
    assert cols["project_id"]["nullable"] is False
    assert cols["takeoff_item_id"]["nullable"] is False
    assert cols["work_category_id"]["nullable"] is True
    assert cols["match_tier"]["nullable"] is False

    # Unique constraint on (project_id, takeoff_item_id)
    uq = inspector.get_unique_constraints("line_item_wc_attributions")
    assert any(
        set(u["column_names"]) == {"project_id", "takeoff_item_id"} for u in uq
    ), f"Expected unique constraint on (project_id, takeoff_item_id), got {uq!r}"


# ---------------------------------------------------------------------------
# 2. Every takeoff item gets exactly one attribution row
# ---------------------------------------------------------------------------


def test_attribution_all_line_items_receive_a_row(db_session, project):
    """5 takeoff items + 2 WCs → exactly 5 attribution rows after the matcher runs."""
    # 2 WCs. One covers concrete (div 03), one covers electrical (div 26).
    _make_wc(
        db_session, project.id,
        wc_number="03", title="Structural Concrete",
        referenced_spec_sections=["033000"],
        work_included_items=["cast in place concrete", "slab on grade"],
    )
    _make_wc(
        db_session, project.id,
        wc_number="26", title="Electrical",
        referenced_spec_sections=["260500"],
        work_included_items=["power distribution"],
    )

    # 5 takeoff items — 2 match Div 03, 1 matches Div 26, 2 match nothing.
    _make_takeoff(db_session, project.id, 1, csi_code="03 30 00", activity="cast in place concrete slab")
    _make_takeoff(db_session, project.id, 2, csi_code="03 35 00", activity="slab on grade finish")
    _make_takeoff(db_session, project.id, 3, csi_code="26 05 00", activity="power feeder")
    _make_takeoff(db_session, project.id, 4, csi_code=None, activity="Senior Project Manager")
    _make_takeoff(db_session, project.id, 5, csi_code=None, activity="landscape irrigation sleeves")

    result = run_scope_matcher_agent(db_session, project.id)

    assert result["attributions_created"] == 5
    rows = (
        db_session.query(LineItemWCAttribution)
        .filter(LineItemWCAttribution.project_id == project.id)
        .all()
    )
    assert len(rows) == 5
    # At least one matched and at least one unmatched
    matched = [r for r in rows if r.work_category_id is not None]
    unmatched = [r for r in rows if r.work_category_id is None]
    assert len(matched) >= 1
    assert len(unmatched) >= 1
    assert all(r.match_tier == "unmatched" for r in unmatched)


# ---------------------------------------------------------------------------
# 3. CSI-exact tier produces an attribution at confidence 1.0
# ---------------------------------------------------------------------------


def test_csi_exact_attribution(db_session, project):
    """Takeoff with csi_code '315400' → normalized '315400' matches WC
    with referenced_spec_sections=['315400'] at tier csi_exact, conf 1.0."""
    wc = _make_wc(
        db_session, project.id,
        wc_number="31", title="Earthwork",
        referenced_spec_sections=["315400"],
        work_included_items=["site excavation"],
    )
    ti = _make_takeoff(
        db_session, project.id, 1,
        csi_code="31 54 00",
        activity="tunnel excavation support",
    )

    run_scope_matcher_agent(db_session, project.id)

    row = (
        db_session.query(LineItemWCAttribution)
        .filter(
            LineItemWCAttribution.project_id == project.id,
            LineItemWCAttribution.takeoff_item_id == ti.id,
        )
        .one()
    )
    assert row.match_tier == "csi_exact"
    assert row.confidence == 1.0
    assert row.work_category_id == wc.id
    assert row.source == "rule"


# ---------------------------------------------------------------------------
# 4. Unmatched line items get a NULL-WC row with match_tier="unmatched"
# ---------------------------------------------------------------------------


def test_unmatched_gets_null_wc(db_session, project):
    """Takeoff item with no CSI and no fuzzy overlap → attribution with
    work_category_id=NULL, match_tier='unmatched', confidence=0.0."""
    _make_wc(
        db_session, project.id,
        wc_number="03", title="Structural Concrete",
        referenced_spec_sections=["033000"],
        work_included_items=["cast in place concrete"],
    )
    ti = _make_takeoff(
        db_session, project.id, 1,
        csi_code=None,  # no CSI → Tier 1 skipped
        activity="xyzzy plugh frotz",  # nonsense → Tier 2 below threshold
    )

    run_scope_matcher_agent(db_session, project.id)

    row = (
        db_session.query(LineItemWCAttribution)
        .filter(
            LineItemWCAttribution.project_id == project.id,
            LineItemWCAttribution.takeoff_item_id == ti.id,
        )
        .one()
    )
    assert row.work_category_id is None
    assert row.match_tier == "unmatched"
    assert row.confidence == 0.0


# ---------------------------------------------------------------------------
# 5. Delete-then-insert idempotency
# ---------------------------------------------------------------------------


def test_delete_then_insert_idempotent(db_session, project):
    """Running the matcher twice must leave the row count stable — the
    runner deletes existing attributions before inserting fresh ones."""
    _make_wc(
        db_session, project.id,
        wc_number="03", title="Concrete",
        referenced_spec_sections=["033000"],
        work_included_items=["cast in place concrete"],
    )
    _make_takeoff(db_session, project.id, 1, csi_code="03 30 00", activity="slab on grade")
    _make_takeoff(db_session, project.id, 2, csi_code=None, activity="random widget")
    _make_takeoff(db_session, project.id, 3, csi_code=None, activity="widget two")

    run_scope_matcher_agent(db_session, project.id)
    first_count = (
        db_session.query(LineItemWCAttribution)
        .filter(LineItemWCAttribution.project_id == project.id)
        .count()
    )
    assert first_count == 3

    # Second run — exact same inputs, exact same row count expected.
    run_scope_matcher_agent(db_session, project.id)
    second_count = (
        db_session.query(LineItemWCAttribution)
        .filter(LineItemWCAttribution.project_id == project.id)
        .count()
    )
    assert second_count == 3, (
        f"Idempotency violated: {first_count} → {second_count} after 2nd matcher run"
    )


# ---------------------------------------------------------------------------
# 6. GET endpoint returns the correct envelope + JOIN data
# ---------------------------------------------------------------------------


def test_endpoint_returns_correct_envelope(
    client, auth_headers, db_session, test_project
):
    """GET /api/projects/{id}/line-item-attributions returns APIResponse
    with the Part C shape. The handler joins TakeoffItemV2 and WorkCategory
    via bulk .filter(id.in_(...)), exposing activity + wc_number/title flat."""
    wc = _make_wc(
        db_session, test_project.id,
        wc_number="03", title="Structural Concrete",
        referenced_spec_sections=["033000"],
        work_included_items=["cast in place concrete"],
    )
    ti = _make_takeoff(
        db_session, test_project.id, 1,
        csi_code="03 30 00", activity="cast in place concrete slab",
    )
    ti_unmatched = _make_takeoff(
        db_session, test_project.id, 2,
        csi_code=None, activity="xyzzy plugh frotz",
    )

    run_scope_matcher_agent(db_session, test_project.id)

    res = client.get(
        f"/api/projects/{test_project.id}/line-item-attributions",
        headers=auth_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["project_id"] == test_project.id
    assert data["total"] == 2
    assert isinstance(data["by_tier"], dict)
    assert data["by_tier"].get("csi_exact", 0) + data["by_tier"].get("unmatched", 0) == 2

    attributions = data["attributions"]
    assert len(attributions) == 2

    # Find the matched + unmatched rows by takeoff_item_id
    matched_row = next(a for a in attributions if a["takeoff_item_id"] == ti.id)
    unmatched_row = next(
        a for a in attributions if a["takeoff_item_id"] == ti_unmatched.id
    )

    # Matched row — WC context joined and flat fields populated
    assert matched_row["work_category_id"] == wc.id
    assert matched_row["work_category_wc_number"] == wc.wc_number
    assert matched_row["work_category_title"] == wc.title
    assert matched_row["takeoff_item_activity"] == "cast in place concrete slab"
    assert matched_row["match_tier"] == "csi_exact"
    assert matched_row["confidence"] == 1.0

    # Unmatched row — WC fields are None, takeoff activity still joined
    assert unmatched_row["work_category_id"] is None
    assert unmatched_row["work_category_wc_number"] is None
    assert unmatched_row["work_category_title"] is None
    assert unmatched_row["takeoff_item_activity"] == "xyzzy plugh frotz"
    assert unmatched_row["match_tier"] == "unmatched"
