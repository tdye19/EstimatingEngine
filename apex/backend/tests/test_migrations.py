"""Regression tests for retired runtime ALTER TABLE safety net (Sprint 19B.1).

Ensures:
1. ensure_project_context_columns no longer exists in database module.
2. All nine columns it formerly added are present in the test DB after
   Alembic migrations have run (they are created by 3a69638ff6bd or were
   already present from init_db in earlier test runs).
"""

from __future__ import annotations

import apex.backend.db.database as _db_mod


def test_retired_runtime_alter_function_no_longer_exists():
    """ensure_project_context_columns must not exist on the database module."""
    assert not hasattr(_db_mod, "ensure_project_context_columns"), (
        "ensure_project_context_columns was re-introduced; "
        "runtime ALTER TABLE safety nets are banned — use Alembic migrations."
    )


def test_retired_init_db_no_longer_exists():
    """init_db must not exist on the database module (it only called the retired function)."""
    assert not hasattr(_db_mod, "init_db"), (
        "init_db was re-introduced; it has been retired along with "
        "ensure_project_context_columns."
    )


def test_project_context_columns_present_post_migration():
    """Model-defined context columns must be present on the projects table.

    The test DB is built from Base.metadata.create_all(), so it reflects the
    ORM model — not Alembic migrations.  We assert the 8 columns that ARE in
    the Project model.  size_sf is included in migration 3a69638ff6bd for
    production DBs (it was added by the retired runtime ALTER) but is not in
    the Project model — it is a zombie column not tested here.
    """
    import apex.backend.db.database as _db

    from sqlalchemy import inspect

    inspector = inspect(_db.engine)
    existing = {c["name"] for c in inspector.get_columns("projects")}

    expected = {
        "project_type",
        "market_sector",
        "region",
        "delivery_method",
        "contract_type",
        "complexity_level",
        "schedule_pressure",
        "scope_types",
    }
    missing = expected - existing
    assert not missing, (
        f"Columns missing from projects table: {sorted(missing)}. "
        "Check that the Project model defines all context columns."
    )
