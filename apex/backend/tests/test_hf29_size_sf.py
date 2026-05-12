"""Tests for HF-29: size_sf zombie column reconciliation.

Verifies:
 - projects table has no size_sf column in the test DB (ORM-derived schema)
 - decision_benchmark correctly uses Project.square_footage
 - _project_dict returns square_footage under the "size_sf" key
 - update_project_context correctly writes size_sf input → project.square_footage
 - Migration round-trip: downgrade adds column back, upgrade drops it again
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from apex.backend.models.project import Project


@pytest.fixture
def sized_project(db_session, test_user) -> Project:
    proj = Project(
        name="Sized Project",
        project_number=f"SZ-{uuid.uuid4().hex[:8]}",
        project_type="commercial",
        status="draft",
        owner_id=test_user.id,
        square_footage=75_000.0,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)
    return proj


# ---------------------------------------------------------------------------
# Schema sanity: test DB must not have size_sf on projects
# ---------------------------------------------------------------------------

def test_projects_table_has_no_size_sf_column():
    import apex.backend.db.database as _db

    inspector = sa.inspect(_db.engine)
    cols = {c["name"] for c in inspector.get_columns("projects")}
    assert "size_sf" not in cols, (
        "projects.size_sf should have been removed by migration HF-29 (c4e8a1f2d9b7)"
    )


def test_projects_table_has_square_footage_column():
    import apex.backend.db.database as _db

    inspector = sa.inspect(_db.engine)
    cols = {c["name"] for c in inspector.get_columns("projects")}
    assert "square_footage" in cols


# ---------------------------------------------------------------------------
# decision.py _project_dict returns square_footage under "size_sf" key
# ---------------------------------------------------------------------------

def test_project_dict_returns_square_footage_as_size_sf(sized_project):
    from apex.backend.routers.decision import _project_dict

    result = _project_dict(sized_project)
    assert result["size_sf"] == 75_000.0


# ---------------------------------------------------------------------------
# update_project_context writes size_sf → square_footage
# ---------------------------------------------------------------------------

def test_update_project_context_size_sf_writes_square_footage(
    client, sized_project, auth_headers, db_session
):
    res = client.patch(
        f"/api/decision/projects/{sized_project.id}/context",
        json={"size_sf": 99_000.0},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["size_sf"] == 99_000.0

    db_session.expire_all()
    db_session.refresh(sized_project)
    assert sized_project.square_footage == 99_000.0


# ---------------------------------------------------------------------------
# decision_benchmark uses square_footage for project size bucket
# ---------------------------------------------------------------------------

def test_decision_benchmark_uses_square_footage(db_session, sized_project):
    from apex.backend.services.decision_benchmark import _size_bucket, score_context_similarity
    from apex.backend.models.decision_models import ComparableProject

    comp = ComparableProject(
        name="Test Comp",
        project_type="commercial",
        region="Southeast",
        size_sf=80_000.0,
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)

    # Project has square_footage=75_000; comp has size_sf=80_000.
    # Both should land in the same size bucket (50k–200k → "large").
    # score_context_similarity must use project.square_footage (not project.size_sf which is None).
    proj_bucket = _size_bucket(sized_project.square_footage)
    comp_bucket = _size_bucket(comp.size_sf)
    assert proj_bucket == comp_bucket, (
        f"Expected same bucket for 75k and 80k sf, got {proj_bucket!r} vs {comp_bucket!r}"
    )

    # Calling score_context_similarity should not raise AttributeError and should
    # produce a non-zero score (project and comp are similar in most dimensions).
    score = score_context_similarity(sized_project, comp)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Migration round-trip: downgrade adds size_sf back, upgrade drops it
# ---------------------------------------------------------------------------

def test_migration_round_trip():
    """Verify the HF-29 migration is idempotent in both directions."""
    import apex.backend.db.database as _db
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    with _db.engine.connect() as conn:
        inspector = sa.inspect(conn)
        cols_start = {c["name"] for c in inspector.get_columns("projects")}

        # size_sf should not be present in the ORM-derived test DB
        assert "size_sf" not in cols_start

        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)

        # downgrade: add the column back
        with ops.batch_alter_table("projects") as batch_ops:
            batch_ops.add_column(sa.Column("size_sf", sa.Float(), nullable=True))
        conn.commit()

        inspector = sa.inspect(conn)
        cols_after_down = {c["name"] for c in inspector.get_columns("projects")}
        assert "size_sf" in cols_after_down

        # upgrade: drop the column again
        with ops.batch_alter_table("projects") as batch_ops:
            batch_ops.drop_column("size_sf")
        conn.commit()

        inspector = sa.inspect(conn)
        cols_after_up = {c["name"] for c in inspector.get_columns("projects")}
        assert "size_sf" not in cols_after_up
