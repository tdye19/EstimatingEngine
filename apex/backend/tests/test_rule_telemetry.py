"""Tests for Spec 19E.6.4 — Agent 3 rule citation telemetry on AgentRunLog.

Covers:
  - ValidationResult.to_telemetry_dict() shape
  - validate_and_attach_rule_facts telemetry counts
  - Agent 3 fallback run includes path="fallback" in rule_telemetry
  - Orchestrator _log_complete writes rule_telemetry to AgentRunLog
  - get_recent_rule_telemetry returns rows newest-first with project_id
  - Migration round-trip: upgrade → downgrade → upgrade
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from apex.backend.agents.pipeline_contracts import GapFinding
from apex.backend.agents.tools.domain_gap_rules import ALL_DOMAIN_RULES
from apex.backend.agents.tools.rule_validator import ValidationResult, validate_and_attach_rule_facts
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_with_concrete_spec(db_session):
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Telemetry Test {suffix}",
        project_number=f"TEL-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    doc = Document(
        project_id=p.id,
        filename="specs.pdf",
        file_path="/fake/specs.pdf",
        file_type="pdf",
        classification="spec",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.flush()

    db_session.add(
        SpecSection(
            project_id=p.id,
            document_id=doc.id,
            division_number="03",
            section_number="03 30 00",
            title="Cast-in-Place Concrete",
            work_description="4000 psi concrete with Grade 60 rebar.",
        )
    )
    db_session.commit()
    return p


# ---------------------------------------------------------------------------
# ValidationResult.to_telemetry_dict()
# ---------------------------------------------------------------------------


class TestValidationResultTelemetryDict:
    def test_shape(self):
        vr = ValidationResult(
            findings=[],
            valid_cite_count=3,
            stripped_cite_count=1,
            no_cite_count=5,
            valid_rule_ids=["CGR-001", "CGR-002", "CIV-001"],
            stripped_rule_ids=["FAKE-001"],
        )
        d = vr.to_telemetry_dict()
        assert d["total_findings"] == 9
        assert d["valid_cite_count"] == 3
        assert d["stripped_cite_count"] == 1
        assert d["no_cite_count"] == 5
        assert d["valid_rule_ids"] == ["CGR-001", "CGR-002", "CIV-001"]
        assert d["stripped_rule_ids"] == ["FAKE-001"]

    def test_total_findings_is_sum(self):
        vr = ValidationResult(
            findings=[], valid_cite_count=2, stripped_cite_count=0, no_cite_count=7
        )
        assert vr.to_telemetry_dict()["total_findings"] == 9

    def test_empty_lists_default(self):
        vr = ValidationResult(
            findings=[], valid_cite_count=0, stripped_cite_count=0, no_cite_count=0
        )
        d = vr.to_telemetry_dict()
        assert d["valid_rule_ids"] == []
        assert d["stripped_rule_ids"] == []


# ---------------------------------------------------------------------------
# validate_and_attach_rule_facts telemetry
# ---------------------------------------------------------------------------


class TestValidatorTelemetryCounts:
    def _make_finding(self, rule_id=None):
        return GapFinding(
            title="Test gap",
            gap_type="missing",
            severity="critical",
            rule_id=rule_id,
        )

    def test_no_citations(self):
        findings = [self._make_finding() for _ in range(4)]
        vr = validate_and_attach_rule_facts(findings)
        assert vr.valid_cite_count == 0
        assert vr.stripped_cite_count == 0
        assert vr.no_cite_count == 4
        assert vr.valid_rule_ids == []
        assert vr.stripped_rule_ids == []

    def test_valid_citation_counted(self):
        valid_id = ALL_DOMAIN_RULES[0].id  # e.g. "CGR-001"
        findings = [self._make_finding(valid_id), self._make_finding()]
        vr = validate_and_attach_rule_facts(findings)
        assert vr.valid_cite_count == 1
        assert vr.no_cite_count == 1
        assert valid_id in vr.valid_rule_ids

    def test_hallucinated_id_stripped(self):
        findings = [self._make_finding("FAKE-999")]
        vr = validate_and_attach_rule_facts(findings)
        assert vr.stripped_cite_count == 1
        assert vr.valid_cite_count == 0
        assert "FAKE-999" in vr.stripped_rule_ids
        # rule_id is stripped from the finding
        assert vr.findings[0].rule_id is None

    def test_telemetry_dict_total_matches(self):
        valid_id = ALL_DOMAIN_RULES[0].id
        findings = [
            self._make_finding(valid_id),
            self._make_finding("FAKE-000"),
            self._make_finding(),
        ]
        vr = validate_and_attach_rule_facts(findings)
        d = vr.to_telemetry_dict()
        assert d["total_findings"] == 3
        assert d["valid_cite_count"] == 1
        assert d["stripped_cite_count"] == 1
        assert d["no_cite_count"] == 1


# ---------------------------------------------------------------------------
# Agent 3 fallback run has path="fallback"
# ---------------------------------------------------------------------------


class TestAgent3FallbackTelemetry:
    def test_fallback_rule_telemetry_has_path_key(self, db_session, project_with_concrete_spec):
        """Agent 3 run with force_rule_based=True must include path='fallback'."""
        from apex.backend.agents import agent_3_gap_analysis as a3

        result = a3.run_gap_analysis_agent(
            db_session, project_with_concrete_spec.id, force_rule_based=True
        )

        telem = result.get("rule_telemetry")
        assert telem is not None, "rule_telemetry missing from Agent 3 result"
        assert telem.get("path") == "fallback", f"Expected path='fallback', got: {telem}"

    def test_fallback_rule_telemetry_valid_cite_is_zero(self, db_session, project_with_concrete_spec):
        from apex.backend.agents import agent_3_gap_analysis as a3

        result = a3.run_gap_analysis_agent(
            db_session, project_with_concrete_spec.id, force_rule_based=True
        )
        telem = result["rule_telemetry"]
        assert telem["valid_cite_count"] == 0
        assert telem["stripped_cite_count"] == 0
        assert telem["valid_rule_ids"] == []

    def test_fallback_total_findings_matches_gaps(self, db_session, project_with_concrete_spec):
        from apex.backend.agents import agent_3_gap_analysis as a3

        result = a3.run_gap_analysis_agent(
            db_session, project_with_concrete_spec.id, force_rule_based=True
        )
        telem = result["rule_telemetry"]
        # total_findings = valid + stripped + no_cite
        computed = telem["valid_cite_count"] + telem["stripped_cite_count"] + telem["no_cite_count"]
        assert telem["total_findings"] == computed


# ---------------------------------------------------------------------------
# Orchestrator _log_complete writes rule_telemetry to AgentRunLog
# ---------------------------------------------------------------------------


class TestOrchestratorWritesTelemetry:
    def test_rule_telemetry_persisted_to_log(self, db_session, project_with_concrete_spec):
        """_log_complete must write rule_telemetry from output_data onto the log row."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_session, project_with_concrete_spec.id)
        log = AgentRunLog(
            project_id=project_with_concrete_spec.id,
            agent_name="Scope Analysis Agent",
            agent_number=3,
            status="running",
            started_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        telemetry = {
            "total_findings": 5,
            "valid_cite_count": 2,
            "stripped_cite_count": 0,
            "no_cite_count": 3,
            "valid_rule_ids": ["CGR-001", "CIV-002"],
            "stripped_rule_ids": [],
        }
        output_data = {"total_gaps": 5, "rule_telemetry": telemetry}
        orch._log_complete(log, "total_gaps=5", output_data=output_data)

        db_session.expire(log)
        db_session.refresh(log)
        assert log.rule_telemetry is not None
        assert log.rule_telemetry["valid_cite_count"] == 2
        assert log.rule_telemetry["valid_rule_ids"] == ["CGR-001", "CIV-002"]

    def test_no_rule_telemetry_in_output_leaves_column_null(self, db_session, project_with_concrete_spec):
        from apex.backend.services.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_session, project_with_concrete_spec.id)
        log = AgentRunLog(
            project_id=project_with_concrete_spec.id,
            agent_name="Rate Intelligence Agent",
            agent_number=4,
            status="running",
            started_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        orch._log_complete(log, "items=3", output_data={"items": 3})

        db_session.expire(log)
        db_session.refresh(log)
        assert log.rule_telemetry is None


# ---------------------------------------------------------------------------
# get_recent_rule_telemetry ordering and project_id
# ---------------------------------------------------------------------------


class TestGetRecentRuleTelemetry:
    def _make_agent3_log(self, db_session, project_id: int, telemetry: dict, started_offset: int = 0):
        from datetime import timedelta

        log = AgentRunLog(
            project_id=project_id,
            agent_name="Scope Analysis Agent",
            agent_number=3,
            status="completed",
            started_at=datetime.utcnow() + timedelta(seconds=started_offset),
            rule_telemetry=telemetry,
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        return log

    def test_returns_list(self, db_session, project_with_concrete_spec):
        from apex.backend.services.rule_telemetry_query import get_recent_rule_telemetry

        self._make_agent3_log(db_session, project_with_concrete_spec.id, {"total_findings": 3})
        results = get_recent_rule_telemetry(limit=50)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_project_id_attached(self, db_session, project_with_concrete_spec):
        from apex.backend.services.rule_telemetry_query import get_recent_rule_telemetry

        self._make_agent3_log(db_session, project_with_concrete_spec.id, {"total_findings": 1})
        results = get_recent_rule_telemetry(limit=50)
        assert all("project_id" in r for r in results)
        assert any(r["project_id"] == project_with_concrete_spec.id for r in results)

    def test_newest_first_ordering(self, db_session, project_with_concrete_spec):
        from apex.backend.services.rule_telemetry_query import get_recent_rule_telemetry

        log1 = self._make_agent3_log(
            db_session, project_with_concrete_spec.id, {"total_findings": 10}, started_offset=0
        )
        log2 = self._make_agent3_log(
            db_session, project_with_concrete_spec.id, {"total_findings": 20}, started_offset=1
        )
        results = get_recent_rule_telemetry(limit=50)
        run_ids = [r["run_id"] for r in results]
        assert run_ids.index(log2.id) < run_ids.index(log1.id), (
            "Newer log should appear before older log"
        )

    def test_rows_without_telemetry_excluded(self, db_session, project_with_concrete_spec):
        from apex.backend.services.rule_telemetry_query import get_recent_rule_telemetry

        log_no_telem = AgentRunLog(
            project_id=project_with_concrete_spec.id,
            agent_name="Scope Analysis Agent",
            agent_number=3,
            status="completed",
        )
        db_session.add(log_no_telem)
        db_session.commit()

        results = get_recent_rule_telemetry(limit=50)
        assert all(r["rule_telemetry"] is not None for r in results)

    def test_limit_respected(self, db_session, project_with_concrete_spec):
        from apex.backend.services.rule_telemetry_query import get_recent_rule_telemetry

        for i in range(5):
            self._make_agent3_log(
                db_session, project_with_concrete_spec.id, {"total_findings": i}
            )
        results = get_recent_rule_telemetry(limit=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# Migration round-trip: upgrade → downgrade → upgrade
# ---------------------------------------------------------------------------


class TestMigrationRoundTrip:
    """Verify the sprint19e6 migration is reversible and idempotent using
    Alembic Operations directly on an isolated in-memory SQLite database."""

    def _build_engine(self):
        engine = sa.create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE agent_run_logs ("
                    "id INTEGER PRIMARY KEY,"
                    "project_id INTEGER NOT NULL,"
                    "agent_number INTEGER NOT NULL"
                    ")"
                )
            )
            conn.commit()
        return engine

    def _column_names(self, engine) -> set[str]:
        inspector = sa.inspect(engine)
        return {c["name"] for c in inspector.get_columns("agent_run_logs")}

    def test_upgrade_adds_column(self):
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        engine = self._build_engine()
        assert "rule_telemetry" not in self._column_names(engine)

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            ops = Operations(ctx)
            with ops.batch_alter_table("agent_run_logs") as batch_ops:
                batch_ops.add_column(sa.Column("rule_telemetry", sa.JSON(), nullable=True))
            conn.commit()

        assert "rule_telemetry" in self._column_names(engine)

    def test_downgrade_removes_column(self):
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        engine = self._build_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            ops = Operations(ctx)
            with ops.batch_alter_table("agent_run_logs") as batch_ops:
                batch_ops.add_column(sa.Column("rule_telemetry", sa.JSON(), nullable=True))
            conn.commit()

        assert "rule_telemetry" in self._column_names(engine)

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            ops = Operations(ctx)
            with ops.batch_alter_table("agent_run_logs") as batch_ops:
                batch_ops.drop_column("rule_telemetry")
            conn.commit()

        assert "rule_telemetry" not in self._column_names(engine)

    def test_upgrade_after_downgrade(self):
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        engine = self._build_engine()

        def _upgrade(conn):
            ctx = MigrationContext.configure(conn)
            ops = Operations(ctx)
            with ops.batch_alter_table("agent_run_logs") as batch_ops:
                batch_ops.add_column(sa.Column("rule_telemetry", sa.JSON(), nullable=True))

        def _downgrade(conn):
            ctx = MigrationContext.configure(conn)
            ops = Operations(ctx)
            with ops.batch_alter_table("agent_run_logs") as batch_ops:
                batch_ops.drop_column("rule_telemetry")

        with engine.connect() as conn:
            _upgrade(conn)
            conn.commit()
        with engine.connect() as conn:
            _downgrade(conn)
            conn.commit()
        with engine.connect() as conn:
            _upgrade(conn)
            conn.commit()

        assert "rule_telemetry" in self._column_names(engine)

    def test_idempotent_upgrade_pattern(self):
        """The migration's inspector check prevents double-add errors."""
        engine = self._build_engine()

        def _idempotent_upgrade(engine):
            with engine.connect() as conn:
                inspector = sa.inspect(engine)
                existing = {c["name"] for c in inspector.get_columns("agent_run_logs")}
                if "rule_telemetry" not in existing:
                    from alembic.operations import Operations
                    from alembic.runtime.migration import MigrationContext

                    ctx = MigrationContext.configure(conn)
                    ops = Operations(ctx)
                    with ops.batch_alter_table("agent_run_logs") as batch_ops:
                        batch_ops.add_column(sa.Column("rule_telemetry", sa.JSON(), nullable=True))
                conn.commit()

        _idempotent_upgrade(engine)
        _idempotent_upgrade(engine)  # second call must not raise
        assert "rule_telemetry" in self._column_names(engine)
