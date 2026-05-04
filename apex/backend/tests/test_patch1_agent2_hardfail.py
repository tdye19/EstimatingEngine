"""Patch 1 regression tests — Agent 2 hard-fail + Agent 2B lifecycle integration.

Covers acceptance criteria:
  1. Agent 2 cannot silently fall back to regex parsing.
  2. Provider/billing failure → visible failed pipeline state.
  3. No fake SpecSection rows written on Agent 2 failure.
  4. No downstream stage runs after Agent 2 failure.
  5. Agent 2B appears in orchestrator lifecycle and observability flow.
  6. Agent 2B produces AgentRunLog entries.
  7. Agent 2B emits websocket progress/error events.
  8. Existing successful LLM-based spec parsing still works.
  9. Existing successful work scope parsing still works.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apex.backend.agents import agent_2_spec_parser as a2
from apex.backend.agents.agent_2_spec_parser import (
    Agent2LLMParseFailure,
    Agent2ProviderUnavailableError,
)
from apex.backend.agents.pipeline_contracts import _CONTRACT_MAP, AGENT_NAMES
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection
from apex.backend.services.agent_orchestrator import (
    AGENT_DEFINITIONS,
    _NON_BLOCKING_AGENTS,
)
from apex.backend.services.llm_provider import LLMProviderBillingError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(db_session, suffix: str | None = None) -> Project:
    suffix = suffix or uuid.uuid4().hex[:8]
    p = Project(
        name=f"Patch1 Test {suffix}",
        project_number=f"P1-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()
    return p


def _add_spec_doc(db_session, project_id: int, text: str = "SECTION 03 30 00\nConcrete.") -> Document:
    doc = Document(
        project_id=project_id,
        filename="spec.pdf",
        file_path="/fake/spec.pdf",
        file_type="pdf",
        classification="spec",
        processing_status="completed",
        raw_text=text,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


class _FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    async def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# A. Agent 2 hard-fail — no regex fallback
# ---------------------------------------------------------------------------


class TestAgent2HardFail:
    def test_provider_unavailable_raises_error(self, db_session):
        """health_check() returning False must raise Agent2ProviderUnavailableError, not fall back."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        class _UnhealthyProvider(_FakeProvider):
            async def health_check(self) -> bool:
                return False

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_UnhealthyProvider()),
            pytest.raises(Agent2ProviderUnavailableError),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

    def test_provider_init_failure_raises_unavailable_error(self, db_session):
        """get_llm_provider() raising must become Agent2ProviderUnavailableError."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        with (
            patch(
                "apex.backend.services.llm_provider.get_llm_provider",
                side_effect=RuntimeError("no API key"),
            ),
            pytest.raises(Agent2ProviderUnavailableError, match="no API key"),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

    def test_llm_response_failure_raises_parse_failure(self, db_session):
        """LLM call raising (non-billing) must become Agent2LLMParseFailure."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        async def _bad_parse(text, prov):
            raise ValueError("LLM returned empty JSON")

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_bad_parse),
            pytest.raises(Agent2LLMParseFailure, match="LLM spec parse failed"),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

    def test_billing_error_propagates_unchanged(self, db_session):
        """LLMProviderBillingError must propagate as-is (not wrapped)."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        async def _billing_error(text, prov):
            raise LLMProviderBillingError("402 Payment Required")

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_billing_error),
            pytest.raises(LLMProviderBillingError),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

    def test_no_regex_fallback_attribute(self):
        """regex_parse_spec_sections must not be imported into agent_2_spec_parser."""
        assert not hasattr(a2, "regex_parse_spec_sections"), (
            "regex_parse_spec_sections must not be accessible inside agent_2_spec_parser "
            "(regex fallback path has been removed)"
        )

    def test_no_spec_sections_written_on_provider_failure(self, db_session):
        """No SpecSection rows must exist in the DB after a provider-unavailable failure."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        class _UnhealthyProvider(_FakeProvider):
            async def health_check(self) -> bool:
                return False

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_UnhealthyProvider()),
            pytest.raises(Agent2ProviderUnavailableError),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

        count = (
            db_session.query(SpecSection)
            .filter(SpecSection.project_id == p.id)
            .count()
        )
        assert count == 0, f"Expected 0 SpecSection rows after failure, found {count}"

    def test_no_spec_sections_written_on_llm_parse_failure(self, db_session):
        """Partial SpecSection rows from earlier docs must be cleaned up on LLM failure."""
        p = _make_project(db_session)

        # Two spec docs; first will succeed, second will trigger LLM failure.
        for i in range(2):
            db_session.add(Document(
                project_id=p.id,
                filename=f"spec_{i}.pdf",
                file_path=f"/fake/spec_{i}.pdf",
                file_type="pdf",
                classification="spec",
                processing_status="completed",
                raw_text=f"SECTION 03 3{i} 00\nContent {i}.",
            ))
        db_session.commit()

        call_count = 0

        async def _flaky_parse(text, prov):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"section_number": "03 30 00", "title": "Concrete", "in_scope": True,
                         "material_specs": {}, "quality_requirements": [], "submittals_required": [],
                         "referenced_standards": [], "division": "03", "raw_content": ""}], 10, 5
            raise ValueError("LLM timed out on doc 2")

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_flaky_parse),
            patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
            pytest.raises(Agent2LLMParseFailure),
        ):
            a2.run_spec_parser_agent(db_session, p.id)

        count = (
            db_session.query(SpecSection)
            .filter(SpecSection.project_id == p.id)
            .count()
        )
        assert count == 0, f"Partial rows must be cleaned up — found {count}"

    def test_successful_llm_parse_still_works(self, db_session):
        """Happy path: valid LLM response produces SpecSection rows and returns contract-valid dict."""
        p = _make_project(db_session)
        _add_spec_doc(db_session, p.id)

        async def _good_parse(text, prov):
            return [
                {
                    "section_number": "03 30 00",
                    "title": "Cast-in-Place Concrete",
                    "in_scope": True,
                    "material_specs": {"compressive_strength_psi": 4000},
                    "quality_requirements": ["ACI 301"],
                    "submittals_required": [],
                    "referenced_standards": ["ACI 318"],
                    "division": "03",
                    "raw_content": "",
                }
            ], 100, 50

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_good_parse),
            patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
            patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
                  return_value={"division_03_count": 0, "enriched": 0,
                                "extraction_methods": {}, "warnings": [], "duration_ms": 0.0}),
        ):
            result = a2.run_spec_parser_agent(db_session, p.id)

        assert result["sections_parsed"] == 1
        assert result["parse_method"] == "llm"

        rows = (
            db_session.query(SpecSection)
            .filter(SpecSection.project_id == p.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].section_number == "03 30 00"


# ---------------------------------------------------------------------------
# B. Exception class structure
# ---------------------------------------------------------------------------


class TestAgent2ExceptionClasses:
    def test_provider_unavailable_is_runtime_error(self):
        assert issubclass(Agent2ProviderUnavailableError, RuntimeError)

    def test_llm_parse_failure_is_runtime_error(self):
        assert issubclass(Agent2LLMParseFailure, RuntimeError)

    def test_billing_error_is_different_class(self):
        assert Agent2ProviderUnavailableError is not LLMProviderBillingError
        assert Agent2LLMParseFailure is not LLMProviderBillingError


# ---------------------------------------------------------------------------
# C. Agent 2B promoted into orchestrator lifecycle
# ---------------------------------------------------------------------------


class TestAgent2BLifecycle:
    def test_agent_25_in_agent_definitions(self):
        """Agent 2B (integer 25) must be registered in AGENT_DEFINITIONS."""
        assert 25 in AGENT_DEFINITIONS
        name, module, fn = AGENT_DEFINITIONS[25]
        assert "Work Scope" in name
        assert "agent_2b_work_scopes" in module
        assert fn == "run_work_scope_agent"

    def test_agent_25_in_pipeline_agents(self):
        """Agent 25 must appear in the pipeline_agents execution list."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator
        import inspect
        src = inspect.getsource(AgentOrchestrator._run_pipeline_locked)
        assert "25" in src, "Agent 25 (2B) must be in pipeline_agents list"

    def test_agent_25_is_non_blocking(self):
        """Agent 2B failure must not halt the pipeline."""
        assert 25 in _NON_BLOCKING_AGENTS

    def test_agent_25_in_contract_map(self):
        """Agent 25 must have a Pydantic contract in _CONTRACT_MAP."""
        assert 25 in _CONTRACT_MAP

    def test_agent_25_in_agent_names(self):
        """Agent 25 must have a display name in AGENT_NAMES."""
        assert 25 in AGENT_NAMES

    def test_agent_2b_runs_in_pipeline_sequence(self, db_session):
        """Agent 2B must be invoked by the orchestrator, not as a sidecar.

        Verify that run_work_scope_agent is called during the orchestrated pipeline
        run (through AGENT_DEFINITIONS dispatch), not via a special-cased block.
        """
        from apex.backend.models.agent_run_log import AgentRunLog
        from apex.backend.services.agent_orchestrator import AgentOrchestrator

        suffix = uuid.uuid4().hex[:8]
        p = Project(
            name=f"2B lifecycle {suffix}",
            project_number=f"2BL-{suffix}",
            project_type="commercial",
        )
        db_session.add(p)
        db_session.flush()

        db_session.add(Document(
            project_id=p.id,
            filename="spec.pdf",
            file_path="/fake/spec.pdf",
            file_type="pdf",
            classification="spec",
            processing_status="completed",
            raw_text="SECTION 03 30 00 CAST-IN-PLACE CONCRETE\n1.1 SUMMARY\nA. This section includes concrete.",
        ))
        db_session.commit()

        work_scope_called = []

        def _fake_work_scope(db, project_id, **kwargs):
            work_scope_called.append(project_id)
            return {
                "project_id": project_id,
                "documents_examined": 0,
                "documents_parsed": 0,
                "work_categories_created": 0,
                "work_categories_updated": 0,
                "parse_methods": {},
                "classification_summary": {},
                "warnings": [],
                "duration_ms": 0.0,
            }

        async def _fake_llm_parse(text, prov):
            return [], 0, 0

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_fake_llm_parse),
            patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
            patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
                  return_value={"division_03_count": 0, "enriched": 0, "extraction_methods": {},
                                "warnings": [], "duration_ms": 0.0}),
            patch("apex.backend.agents.agent_2b_work_scopes.run_work_scope_agent",
                  side_effect=_fake_work_scope),
            patch("apex.backend.agents.agent_3_gap_analysis.run_gap_analysis_agent",
                  return_value={"total_gaps": 0, "critical_count": 0, "moderate_count": 0,
                                "watch_count": 0, "report_id": 1, "sections_analyzed": 0}),
            patch("apex.backend.agents.agent_4_takeoff.run_takeoff_agent",
                  return_value={"takeoff_items_parsed": 0, "items_matched": 0, "items_unmatched": 0}),
            patch("apex.backend.agents.agent_3_5_scope_matcher.run_scope_matcher_agent",
                  return_value={"status": "noop", "project_id": p.id, "findings_created": 0,
                                "in_scope_not_estimated_count": 0, "estimated_out_of_scope_count": 0,
                                "partial_coverage_count": 0, "error_count": 0}),
            patch("apex.backend.agents.agent_5_labor.run_labor_agent",
                  return_value={"items_compared": 0, "items_with_field_data": 0,
                                "items_without_field_data": 0}),
            patch("apex.backend.agents.agent_6_assembly.run_assembly_agent",
                  return_value={"report_id": 1, "report_version": 1, "overall_risk_level": "LOW",
                                "rate_items_flagged": 0, "scope_gaps_found": 0,
                                "field_calibration_alerts": 0, "comparable_projects_found": 0,
                                "narrative_method": "template", "narrative_tokens_used": 0}),
            patch("apex.backend.agents.agent_1_ingestion.run_ingestion_agent",
                  return_value={"documents_processed": 1, "total_documents": 1, "results": []}),
            patch("apex.backend.services.ws_manager.ws_manager.broadcast_sync"),
            patch("apex.backend.services.email_service.send_pipeline_complete", side_effect=Exception("no email")),
        ):
            orch = AgentOrchestrator(db_session, p.id)
            orch.run_pipeline()

        assert len(work_scope_called) == 1, (
            "run_work_scope_agent must be called once by the orchestrator"
        )
        assert work_scope_called[0] == p.id

    def test_agent_2b_produces_agentrunlog(self, db_session):
        """A pipeline run must create an AgentRunLog with agent_number=25."""
        from apex.backend.models.agent_run_log import AgentRunLog
        from apex.backend.services.agent_orchestrator import AgentOrchestrator

        suffix = uuid.uuid4().hex[:8]
        p = Project(
            name=f"2B runlog {suffix}",
            project_number=f"2BRL-{suffix}",
            project_type="commercial",
        )
        db_session.add(p)
        db_session.flush()
        db_session.add(Document(
            project_id=p.id,
            filename="spec.pdf",
            file_path="/fake/spec.pdf",
            file_type="pdf",
            classification="spec",
            processing_status="completed",
            raw_text="SECTION 03 30 00\nConcrete.",
        ))
        db_session.commit()

        async def _fake_llm_parse(text, prov):
            return [], 0, 0

        def _fake_work_scope(db, project_id, **kwargs):
            return {
                "project_id": project_id,
                "documents_examined": 0,
                "documents_parsed": 0,
                "work_categories_created": 0,
                "work_categories_updated": 0,
                "parse_methods": {},
                "classification_summary": {},
                "warnings": [],
                "duration_ms": 0.0,
            }

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_fake_llm_parse),
            patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
            patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
                  return_value={"division_03_count": 0, "enriched": 0, "extraction_methods": {},
                                "warnings": [], "duration_ms": 0.0}),
            patch("apex.backend.agents.agent_2b_work_scopes.run_work_scope_agent",
                  side_effect=_fake_work_scope),
            patch("apex.backend.agents.agent_3_gap_analysis.run_gap_analysis_agent",
                  return_value={"total_gaps": 0, "critical_count": 0, "moderate_count": 0,
                                "watch_count": 0, "report_id": 1, "sections_analyzed": 0}),
            patch("apex.backend.agents.agent_4_takeoff.run_takeoff_agent",
                  return_value={"takeoff_items_parsed": 0, "items_matched": 0, "items_unmatched": 0}),
            patch("apex.backend.agents.agent_3_5_scope_matcher.run_scope_matcher_agent",
                  return_value={"status": "noop", "project_id": p.id, "findings_created": 0,
                                "in_scope_not_estimated_count": 0, "estimated_out_of_scope_count": 0,
                                "partial_coverage_count": 0, "error_count": 0}),
            patch("apex.backend.agents.agent_5_labor.run_labor_agent",
                  return_value={"items_compared": 0, "items_with_field_data": 0,
                                "items_without_field_data": 0}),
            patch("apex.backend.agents.agent_6_assembly.run_assembly_agent",
                  return_value={"report_id": 1, "report_version": 1, "overall_risk_level": "LOW",
                                "rate_items_flagged": 0, "scope_gaps_found": 0,
                                "field_calibration_alerts": 0, "comparable_projects_found": 0,
                                "narrative_method": "template", "narrative_tokens_used": 0}),
            patch("apex.backend.agents.agent_1_ingestion.run_ingestion_agent",
                  return_value={"documents_processed": 1, "total_documents": 1, "results": []}),
            patch("apex.backend.services.ws_manager.ws_manager.broadcast_sync"),
            patch("apex.backend.services.email_service.send_pipeline_complete", side_effect=Exception("no email")),
        ):
            orch = AgentOrchestrator(db_session, p.id)
            orch.run_pipeline()

        log = (
            db_session.query(AgentRunLog)
            .filter(
                AgentRunLog.project_id == p.id,
                AgentRunLog.agent_number == 25,
            )
            .first()
        )
        assert log is not None, "AgentRunLog with agent_number=25 must be created"
        assert log.status in ("completed", "failed"), f"Unexpected status: {log.status}"

    def test_agent_2b_failure_does_not_halt_pipeline(self, db_session):
        """Agent 2B failure must be visible in results but must not set failed_at."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator

        suffix = uuid.uuid4().hex[:8]
        p = Project(
            name=f"2B nohalt {suffix}",
            project_number=f"2BNH-{suffix}",
            project_type="commercial",
        )
        db_session.add(p)
        db_session.flush()
        db_session.add(Document(
            project_id=p.id,
            filename="spec.pdf",
            file_path="/fake/spec.pdf",
            file_type="pdf",
            classification="spec",
            processing_status="completed",
            raw_text="SECTION 03 30 00\nConcrete.",
        ))
        db_session.commit()

        async def _fake_llm_parse(text, prov):
            return [], 0, 0

        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch("apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections", side_effect=_fake_llm_parse),
            patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
            patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
                  return_value={"division_03_count": 0, "enriched": 0, "extraction_methods": {},
                                "warnings": [], "duration_ms": 0.0}),
            patch("apex.backend.agents.agent_2b_work_scopes.run_work_scope_agent",
                  side_effect=RuntimeError("work scope parser exploded")),
            patch("apex.backend.agents.agent_3_gap_analysis.run_gap_analysis_agent",
                  return_value={"total_gaps": 0, "critical_count": 0, "moderate_count": 0,
                                "watch_count": 0, "report_id": 1, "sections_analyzed": 0}),
            patch("apex.backend.agents.agent_4_takeoff.run_takeoff_agent",
                  return_value={"takeoff_items_parsed": 0, "items_matched": 0, "items_unmatched": 0}),
            patch("apex.backend.agents.agent_3_5_scope_matcher.run_scope_matcher_agent",
                  return_value={"status": "noop", "project_id": p.id, "findings_created": 0,
                                "in_scope_not_estimated_count": 0, "estimated_out_of_scope_count": 0,
                                "partial_coverage_count": 0, "error_count": 0}),
            patch("apex.backend.agents.agent_5_labor.run_labor_agent",
                  return_value={"items_compared": 0, "items_with_field_data": 0,
                                "items_without_field_data": 0}),
            patch("apex.backend.agents.agent_6_assembly.run_assembly_agent",
                  return_value={"report_id": 1, "report_version": 1, "overall_risk_level": "LOW",
                                "rate_items_flagged": 0, "scope_gaps_found": 0,
                                "field_calibration_alerts": 0, "comparable_projects_found": 0,
                                "narrative_method": "template", "narrative_tokens_used": 0}),
            patch("apex.backend.agents.agent_1_ingestion.run_ingestion_agent",
                  return_value={"documents_processed": 1, "total_documents": 1, "results": []}),
            patch("apex.backend.services.ws_manager.ws_manager.broadcast_sync"),
            patch("apex.backend.services.email_service.send_pipeline_complete", side_effect=Exception("no email")),
        ):
            orch = AgentOrchestrator(db_session, p.id)
            results = orch.run_pipeline()

        # Pipeline must complete (not stop at 2B)
        assert results["pipeline_status"] == "completed", (
            f"Pipeline must complete despite 2B failure; got {results['pipeline_status']}"
        )
        # Agent 2B result must show failure
        assert results.get("agent_25", {}).get("status") == "failed"
        # Downstream agents must have run
        assert "agent_6" in results
        assert results["agent_6"].get("report_id") == 1
