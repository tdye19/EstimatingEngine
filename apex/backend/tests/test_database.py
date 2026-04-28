"""Tests for database helper utilities."""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text

from apex.backend.db.database import ensure_project_context_columns


def test_ensure_project_context_columns_adds_missing_columns(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    metadata = MetaData()
    Table(
        "projects",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(255)),
    )
    metadata.create_all(engine)

    ensure_project_context_columns(engine)

    with engine.connect() as conn:
        cols = {row["name"] for row in conn.execute(text("PRAGMA table_info(projects)")).mappings()}

    assert "project_type" in cols
    assert "market_sector" in cols
    assert "scope_types" in cols

    # Re-running the migration should be idempotent and not raise.
    ensure_project_context_columns(engine)


def test_ensure_project_context_columns_skips_missing_table(tmp_path):
    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    # Should not raise when the projects table does not exist.
    ensure_project_context_columns(engine)
