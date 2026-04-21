"""GapFinding model + repo tests (Sprint 18.3.1).

Covers:
- Round-trip insert and read for all three finding_type values.
- CASCADE on project delete; SET NULL on work_category delete.
- delete_project_findings scoping — only the target project is cleared.

FK-behavior tests use an isolated engine with PRAGMA foreign_keys = ON
because conftest's shared engine does not enable SQLite FK enforcement
by default (most tests don't depend on it).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from apex.backend.agents.pipeline_contracts import GapFindingOut
from apex.backend.db.database import Base
from apex.backend.models.document import Document
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.project import Project
from apex.backend.models.work_category import WorkCategory
from apex.backend.services.gap_finding_repo import (
    create_finding,
    delete_project_findings,
    list_findings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fk_session() -> Session:
    """Isolated SQLite session with foreign_keys pragma ON.

    conftest's shared engine doesn't enable FK enforcement, so the
    CASCADE / SET NULL tests need their own engine to observe real DB
    behavior. We build the full ORM schema via Base.metadata.create_all.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, rec):  # pragma: no cover - driver callback
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _scaffold_project(db: Session, tag: str) -> Project:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"GF {tag}",
        project_number=f"GF-{tag}-{suffix}",
        project_type="commercial",
    )
    db.add(p)
    db.flush()
    return p


def _scaffold_work_category(db: Session, project: Project, wc_number: str) -> WorkCategory:
    wc = WorkCategory(
        project_id=project.id,
        wc_number=wc_number,
        title=f"Category {wc_number}",
        work_included_items=[],
        specific_notes=[],
        related_work_by_others=[],
        add_alternates=[],
        allowances=[],
        unit_prices=[],
        referenced_spec_sections=[],
    )
    db.add(wc)
    db.flush()
    return wc


def _scaffold_estimate_line(db: Session, project: Project, csi_code: str) -> EstimateLineItem:
    est = Estimate(project_id=project.id, version=1, status="draft")
    db.add(est)
    db.flush()

    line = EstimateLineItem(
        estimate_id=est.id,
        division_number=csi_code.split()[0] if " " in csi_code else csi_code[:2],
        csi_code=csi_code,
        description="line",
        quantity=1.0,
        unit_of_measure="EA",
    )
    db.add(line)
    db.flush()
    return line


# ---------------------------------------------------------------------------
# Round-trip insert / read
# ---------------------------------------------------------------------------


def test_round_trip_in_scope_not_estimated(db_session: Session):
    project = _scaffold_project(db_session, "A")
    wc = _scaffold_work_category(db_session, project, "05")

    finding = create_finding(
        db_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        match_tier="csi_exact",
        confidence=0.95,
        rationale="WC 05 references 03 30 00 but no EstimateLineItem covers it",
        source="rule",
        work_category_id=wc.id,
        spec_section_ref="03 30 00",
    )
    db_session.commit()

    loaded = db_session.query(GapFinding).filter_by(id=finding.id).one()
    assert loaded.finding_type == "in_scope_not_estimated"
    assert loaded.match_tier == "csi_exact"
    assert loaded.confidence == pytest.approx(0.95)
    assert loaded.work_category_id == wc.id
    assert loaded.spec_section_ref == "03 30 00"
    assert loaded.source == "rule"
    assert isinstance(loaded.created_at, datetime)

    # Pydantic round-trip through from_attributes.
    out = GapFindingOut.model_validate(loaded)
    assert out.finding_type == "in_scope_not_estimated"
    assert out.confidence == pytest.approx(0.95)


def test_round_trip_estimated_out_of_scope(db_session: Session):
    project = _scaffold_project(db_session, "B")
    line = _scaffold_estimate_line(db_session, project, "09 91 00")

    finding = create_finding(
        db_session,
        project_id=project.id,
        finding_type="estimated_out_of_scope",
        match_tier="spec_section_fuzzy",
        confidence=0.72,
        rationale="EstimateLineItem 09 91 00 has no matching WorkCategory scope",
        source="rule",
        estimate_line_id=line.id,
    )
    db_session.commit()

    loaded = db_session.query(GapFinding).filter_by(id=finding.id).one()
    assert loaded.finding_type == "estimated_out_of_scope"
    assert loaded.match_tier == "spec_section_fuzzy"
    assert loaded.estimate_line_id == line.id
    assert loaded.work_category_id is None


def test_round_trip_partial_coverage_llm_source(db_session: Session):
    project = _scaffold_project(db_session, "C")
    wc = _scaffold_work_category(db_session, project, "12")
    line = _scaffold_estimate_line(db_session, project, "12 36 00")

    finding = create_finding(
        db_session,
        project_id=project.id,
        finding_type="partial_coverage",
        match_tier="llm_semantic",
        confidence=0.55,
        rationale="Scope mentions countertops; estimate covers only solid-surface sub-type",
        source="llm",
        work_category_id=wc.id,
        estimate_line_id=line.id,
        spec_section_ref="12 36 00",
    )
    db_session.commit()

    loaded = db_session.query(GapFinding).filter_by(id=finding.id).one()
    assert loaded.finding_type == "partial_coverage"
    assert loaded.match_tier == "llm_semantic"
    assert loaded.source == "llm"


# ---------------------------------------------------------------------------
# FK behavior (isolated engine with foreign_keys pragma)
# ---------------------------------------------------------------------------


def test_cascade_delete_removes_findings_when_project_deleted(fk_session: Session):
    project = _scaffold_project(fk_session, "Cas")
    create_finding(
        fk_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        match_tier="csi_exact",
        confidence=0.9,
        rationale="r",
        source="rule",
        spec_section_ref="03 30 00",
    )
    fk_session.commit()
    assert fk_session.query(GapFinding).count() == 1

    fk_session.delete(project)
    fk_session.commit()

    assert fk_session.query(GapFinding).count() == 0


def test_work_category_delete_sets_fk_null_keeps_finding(fk_session: Session):
    project = _scaffold_project(fk_session, "Nul")
    wc = _scaffold_work_category(fk_session, project, "07")
    finding = create_finding(
        fk_session,
        project_id=project.id,
        finding_type="in_scope_not_estimated",
        match_tier="csi_exact",
        confidence=0.8,
        rationale="r",
        source="rule",
        work_category_id=wc.id,
    )
    fk_session.commit()

    fk_session.delete(wc)
    fk_session.commit()

    reloaded = fk_session.query(GapFinding).filter_by(id=finding.id).one()
    assert reloaded.work_category_id is None
    assert reloaded.finding_type == "in_scope_not_estimated"


# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------


def test_delete_project_findings_scoped_to_target(db_session: Session):
    a = _scaffold_project(db_session, "DP-A")
    b = _scaffold_project(db_session, "DP-B")

    for p in (a, b):
        for i in range(3):
            create_finding(
                db_session,
                project_id=p.id,
                finding_type="in_scope_not_estimated",
                match_tier="csi_exact",
                confidence=0.9 - i * 0.1,
                rationale=f"r{i}",
                source="rule",
            )
    db_session.commit()

    assert db_session.query(GapFinding).filter_by(project_id=a.id).count() == 3
    assert db_session.query(GapFinding).filter_by(project_id=b.id).count() == 3

    deleted = delete_project_findings(db_session, a.id)

    assert deleted == 3
    assert db_session.query(GapFinding).filter_by(project_id=a.id).count() == 0
    # Project B untouched — scoping contract.
    assert db_session.query(GapFinding).filter_by(project_id=b.id).count() == 3


def test_list_findings_filters_by_type(db_session: Session):
    p = _scaffold_project(db_session, "LF")
    create_finding(
        db_session,
        project_id=p.id,
        finding_type="in_scope_not_estimated",
        match_tier="csi_exact",
        confidence=0.9,
        rationale="a",
        source="rule",
    )
    create_finding(
        db_session,
        project_id=p.id,
        finding_type="estimated_out_of_scope",
        match_tier="csi_exact",
        confidence=0.8,
        rationale="b",
        source="rule",
    )
    create_finding(
        db_session,
        project_id=p.id,
        finding_type="partial_coverage",
        match_tier="llm_semantic",
        confidence=0.5,
        rationale="c",
        source="llm",
    )
    db_session.commit()

    all_findings = list_findings(db_session, p.id)
    assert len(all_findings) == 3

    oos_only = list_findings(db_session, p.id, finding_type="estimated_out_of_scope")
    assert len(oos_only) == 1
    assert oos_only[0].rationale == "b"

    partial_only = list_findings(db_session, p.id, finding_type="partial_coverage")
    assert len(partial_only) == 1
    assert partial_only[0].source == "llm"


def test_composite_index_exists():
    """Smoke test — the (project_id, finding_type) index is registered in metadata."""
    idx_names = {ix.name for ix in GapFinding.__table__.indexes}
    assert "ix_gap_findings_project_finding_type" in idx_names
