"""HF-21 (Sprint 18.3.0) — SpecSection cross-document dedup regression tests.

Covers:
- Unique constraint on (project_id, section_number) at the model level.
- Upsert semantics in Agent 2's loader: longest-content-wins,
  shorter-content is idempotent no-op, different CSI codes do not collide.
- The migration's data-cleanup SQL on a populated DB seeded with duplicates.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apex.backend.agents.agent_2_spec_parser import _upsert_spec_section
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_scaffold(db: Session, tag: str) -> tuple[Project, Document]:
    """Minimal Project + Document to satisfy NOT NULL FKs."""
    suffix = uuid.uuid4().hex[:8]
    project = Project(
        name=f"Dedup {tag}",
        project_number=f"DEDUP-{tag}-{suffix}",
        project_type="commercial",
    )
    db.add(project)
    db.flush()

    doc = Document(
        project_id=project.id,
        filename=f"{tag}.pdf",
        file_path=f"/fake/{tag}.pdf",
        file_type="pdf",
        classification="spec",
        raw_text="test",
        processing_status="completed",
    )
    db.add(doc)
    db.flush()
    return project, doc


def _section_payload(section_number: str, work_desc: str) -> dict:
    """A minimal Agent 2 extracted-section dict shaped like _parse_document output."""
    return {
        "section_number": section_number,
        "division_number": section_number.split()[0] if " " in section_number else "03",
        "title": f"Section {section_number}",
        "in_scope": True,
        "material_specs": {"work_description_override": work_desc},
        "quality_requirements": [],
        "submittals_required": [],
        "referenced_standards": [],
        "raw_content": "",
    }


def _upsert(db: Session, project_id: int, doc_id: int, section_number: str, work_desc: str) -> str:
    return _upsert_spec_section(
        db,
        project_id=project_id,
        doc_id=doc_id,
        section_data=_section_payload(section_number, work_desc),
        division_number="03",
        work_desc=work_desc,
        keywords=[],
        standards=[],
        submittals=[],
        raw_content="",
    )


# ---------------------------------------------------------------------------
# Model-level constraint
# ---------------------------------------------------------------------------


def test_unique_constraint_blocks_raw_duplicate_insert(db_session: Session):
    """HF-21: the ORM-level UniqueConstraint prevents two rows with the same
    (project_id, section_number) from being persisted, independent of the
    upsert helper."""
    project, doc = _build_scaffold(db_session, "U1")

    first = SpecSection(
        project_id=project.id,
        document_id=doc.id,
        division_number="03",
        section_number="03 30 00",
        title="Cast-in-Place Concrete",
        work_description="short",
    )
    db_session.add(first)
    db_session.commit()

    duplicate = SpecSection(
        project_id=project.id,
        document_id=doc.id,
        division_number="03",
        section_number="03 30 00",
        title="Cast-in-Place Concrete",
        work_description="also short",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Upsert semantics — Agent 2 loader
# ---------------------------------------------------------------------------


def test_reparse_same_section_produces_one_row(db_session: Session):
    """Re-running the upsert for the same (project, section_number) with
    identical content does not create a second row."""
    project, doc = _build_scaffold(db_session, "R1")

    outcome_1 = _upsert(db_session, project.id, doc.id, "03 30 00", "concrete 4000 psi")
    db_session.commit()
    outcome_2 = _upsert(db_session, project.id, doc.id, "03 30 00", "concrete 4000 psi")
    db_session.commit()

    rows = db_session.query(SpecSection).filter_by(project_id=project.id).all()
    assert len(rows) == 1
    assert outcome_1 == "new"
    assert outcome_2 == "skipped"


def test_longer_work_description_replaces_shorter(db_session: Session):
    """Upsert keeps the longest work_description seen across passes."""
    project, doc = _build_scaffold(db_session, "R2")

    _upsert(db_session, project.id, doc.id, "03 30 00", "short spec")
    db_session.commit()
    longer = "full Part 1 + Part 2 content from a later chunk — much more detail"
    outcome = _upsert(db_session, project.id, doc.id, "03 30 00", longer)
    db_session.commit()

    rows = db_session.query(SpecSection).filter_by(project_id=project.id).all()
    assert len(rows) == 1
    assert rows[0].work_description == longer
    assert outcome == "replaced"


def test_shorter_work_description_does_not_overwrite_longer(db_session: Session):
    """Idempotent no-op when incoming content is shorter than the stored row."""
    project, doc = _build_scaffold(db_session, "R3")

    long_text = "A" * 500
    _upsert(db_session, project.id, doc.id, "03 30 00", long_text)
    db_session.commit()
    outcome = _upsert(db_session, project.id, doc.id, "03 30 00", "short")
    db_session.commit()

    rows = db_session.query(SpecSection).filter_by(project_id=project.id).all()
    assert len(rows) == 1
    assert rows[0].work_description == long_text
    assert outcome == "skipped"


def test_different_csi_codes_do_not_collide(db_session: Session):
    """Constraint is scoped to (project_id, section_number) — distinct CSI codes
    in the same project produce distinct rows."""
    project, doc = _build_scaffold(db_session, "R4")

    _upsert(db_session, project.id, doc.id, "03 30 00", "concrete")
    _upsert(db_session, project.id, doc.id, "05 12 00", "steel")
    db_session.commit()

    rows = (
        db_session.query(SpecSection)
        .filter_by(project_id=project.id)
        .order_by(SpecSection.section_number)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].section_number == "03 30 00"
    assert rows[1].section_number == "05 12 00"


def test_same_csi_different_projects_do_not_collide(db_session: Session):
    """Constraint is scoped per-project — same CSI across projects is allowed."""
    project_a, doc_a = _build_scaffold(db_session, "R5A")
    project_b, doc_b = _build_scaffold(db_session, "R5B")

    _upsert(db_session, project_a.id, doc_a.id, "03 30 00", "project A concrete")
    _upsert(db_session, project_b.id, doc_b.id, "03 30 00", "project B concrete")
    db_session.commit()

    a_rows = db_session.query(SpecSection).filter_by(project_id=project_a.id).all()
    b_rows = db_session.query(SpecSection).filter_by(project_id=project_b.id).all()
    assert len(a_rows) == 1
    assert len(b_rows) == 1


# ---------------------------------------------------------------------------
# Migration data-cleanup SQL
# ---------------------------------------------------------------------------


def _load_migration_sql() -> str:
    """Import the migration module by path and return its _DEDUP_SQL constant."""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "b7d2c1e9f8a4_sprint18_3_0_spec_section_dedup.py"
    )
    spec = importlib.util.spec_from_file_location("_hf21_mig", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._DEDUP_SQL


def test_migration_cleanup_collapses_triplicates_keeping_longest(tmp_path):
    """Migration path — seed 3 duplicate rows, run the migration's dedup SQL,
    assert exactly 1 row remains and it has the longest work_description.

    Uses an isolated engine with a schema that does NOT yet have the unique
    constraint, mirroring the pre-migration state on production DBs where
    HF-21 cleanup must run BEFORE the ALTER.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'dedup.db'}")

    ddl = """
    CREATE TABLE spec_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        section_number TEXT NOT NULL,
        work_description TEXT
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))
        # Seed three rows for the same (project_id=1, section_number='03 30 00').
        # Winner must be id=2 — longest work_description. Intentionally not in
        # id order so the test exercises the ROW_NUMBER ordering, not insertion
        # order.
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (1, 1, '03 30 00', 'short')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (2, 1, '03 30 00', :long)"
            ),
            {"long": "B" * 800},
        )
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (3, 1, '03 30 00', 'medium length description')"
            )
        )
        # Control row on a different CSI — must survive untouched.
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (4, 1, '05 12 00', 'steel')"
            )
        )

    with engine.begin() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM spec_sections")).scalar()

    assert before == 4

    with engine.begin() as conn:
        conn.execute(text(_load_migration_sql()))

    with engine.begin() as conn:
        after_rows = conn.execute(
            text(
                "SELECT id, section_number, work_description "
                "FROM spec_sections ORDER BY section_number"
            )
        ).fetchall()

    assert len(after_rows) == 2  # 1 winner for 03 30 00 + control row 05 12 00
    winner = [r for r in after_rows if r.section_number == "03 30 00"][0]
    assert winner.id == 2  # longest work_description
    assert len(winner.work_description) == 800


def test_migration_cleanup_prefers_non_null_over_null(tmp_path):
    """Rows with non-null work_description win over NULL even if NULL row has lower id."""
    engine = create_engine(f"sqlite:///{tmp_path / 'dedup_null.db'}")

    ddl = """
    CREATE TABLE spec_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        section_number TEXT NOT NULL,
        work_description TEXT
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (1, 7, '03 30 00', NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO spec_sections (id, project_id, section_number, work_description) "
                "VALUES (2, 7, '03 30 00', 'has content')"
            )
        )

    with engine.begin() as conn:
        conn.execute(text(_load_migration_sql()))

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, work_description FROM spec_sections")
        ).fetchall()

    assert len(rows) == 1
    assert rows[0].id == 2  # non-null beat NULL despite higher id
