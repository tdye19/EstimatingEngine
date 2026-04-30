"""Integration tests for orchestrator billing error handling (Sprint 18 backlog #5).

Verifies that LLMProviderBillingError from any agent:
  - sets project.status to "failed_billing"
  - does NOT call downstream agents
  - broadcasts a pipeline_error WS message with status="failed_billing"
  - re-raises so the caller knows the pipeline halted
"""

import os

os.environ.setdefault("APEX_DEV_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from apex.backend.models.project import Project
from apex.backend.services.agent_orchestrator import AgentOrchestrator
from apex.backend.services.llm_provider import LLMProviderBillingError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BILLING_EXC = LLMProviderBillingError(
    "OpenRouter 402 Payment Required — account balance exhausted."
)

_AGENT_1_OK = {"documents_processed": 1, "pipeline_mode": "spec"}


def _agent_patches(agent2_side_effect=_BILLING_EXC):
    """Return a list of patch objects covering all pipeline agents."""
    return [
        patch(
            "apex.backend.agents.agent_1_ingestion.run_ingestion_agent",
            return_value=_AGENT_1_OK,
        ),
        patch(
            "apex.backend.agents.agent_2_spec_parser.run_spec_parser_agent",
            side_effect=agent2_side_effect,
        ),
        patch("apex.backend.agents.agent_3_gap_analysis.run_gap_analysis_agent"),
        patch("apex.backend.agents.agent_4_takeoff.run_takeoff_agent"),
        patch("apex.backend.agents.agent_3_5_scope_matcher.run_scope_matcher_agent"),
        patch("apex.backend.agents.agent_5_labor.run_labor_agent"),
        patch("apex.backend.agents.agent_6_assembly.run_assembly_agent"),
        patch("apex.backend.services.ws_manager.ws_manager.broadcast_sync"),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_billing_error_halts_pipeline(db_session, test_project):
    """Agent 2 billing error → project failed_billing, Agent 3 not called, WS broadcast."""
    with ExitStack() as stack:
        patches = _agent_patches()
        mocks = [stack.enter_context(p) for p in patches]

        mock_a3 = mocks[2]   # agent_3_gap_analysis
        mock_ws = mocks[7]   # ws_manager.broadcast_sync

        orchestrator = AgentOrchestrator(db_session, test_project.id)

        with pytest.raises(LLMProviderBillingError):
            orchestrator.run_pipeline()

    # Agent 3 must NOT have been called
    mock_a3.assert_not_called()

    # Project status must be "failed_billing"
    project = db_session.query(Project).filter(Project.id == test_project.id).first()
    assert project.status == "failed_billing", (
        f"Expected 'failed_billing', got {project.status!r}"
    )

    # At least one WS broadcast must carry status="failed_billing"
    billing_broadcasts = [
        call
        for call in mock_ws.call_args_list
        if (
            len(call[0]) > 1
            and isinstance(call[0][1], dict)
            and call[0][1].get("status") == "failed_billing"
        )
    ]
    assert billing_broadcasts, (
        "Expected at least one ws_manager.broadcast_sync call with status='failed_billing'"
    )

    msg_payload = billing_broadcasts[0][0][1]
    assert msg_payload.get("type") == "pipeline_error"
    human_msg = msg_payload.get("message", "")
    assert "billing" in human_msg.lower() or "OpenRouter" in human_msg, (
        f"Expected billing/OpenRouter in message, got: {human_msg!r}"
    )


def test_billing_error_re_raises_to_caller(db_session, test_project):
    """run_pipeline() propagates LLMProviderBillingError to its caller."""
    with ExitStack() as stack:
        for p in _agent_patches():
            stack.enter_context(p)

        orchestrator = AgentOrchestrator(db_session, test_project.id)

        with pytest.raises(LLMProviderBillingError):
            orchestrator.run_pipeline()
        # If we reach here without raising, the test fails via pytest.raises


def test_billing_error_does_not_call_agents_after_failed_agent(db_session, test_project):
    """No agent after the billing-failed one is invoked."""
    with ExitStack() as stack:
        patches = _agent_patches()
        mocks = [stack.enter_context(p) for p in patches]

        mock_a3  = mocks[2]   # gap_analysis (runs after agent 2 in pipeline order)
        mock_a4  = mocks[3]   # takeoff
        mock_a35 = mocks[4]   # scope_matcher
        mock_a5  = mocks[5]   # labor
        mock_a6  = mocks[6]   # assembly

        orchestrator = AgentOrchestrator(db_session, test_project.id)

        with pytest.raises(LLMProviderBillingError):
            orchestrator.run_pipeline()

    for mock, name in [
        (mock_a3,  "agent_3"),
        (mock_a4,  "agent_4"),
        (mock_a35, "agent_3_5"),
        (mock_a5,  "agent_5"),
        (mock_a6,  "agent_6"),
    ]:
        mock.assert_not_called(), f"{name} should not have been called after billing error"
