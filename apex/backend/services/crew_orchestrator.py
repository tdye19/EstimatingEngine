"""CrewAI orchestration layer for the APEX pipeline.

This module wraps the existing APEX agent functions inside a CrewAI-compatible
task-dependency graph.  CrewAI is used for:

  • Task dependency modelling  (context= field on each Task)
  • Execution order derived from the dependency graph (topological)
  • Lifecycle callbacks that drive WebSocket status events
  • Fail-fast error propagation (stop-on-failure)

Architecture
------------
CrewAI is the orchestration layer.  The existing agent Python functions
(run_ingestion_agent, run_spec_parser_agent, …) are the workers.  Each
CrewAI Task definition wraps one agent function; the Crew determines *when*
each task may execute (dependency resolution via the context= field).

Because APEX agents are currently pure-Python, rule-based functions (no LLM
calls), the actual execution calls the Python callables directly without going
through CrewAI's LLM loop.  The CrewAI Task / Crew objects serve as the
dependency-graph data structure.  When LLM-backed agents are introduced, only
the execution engine needs to change (switch to Crew.kickoff()) — the task
definitions stay the same.

Toggle
------
Set   USE_CREWAI_ORCHESTRATOR=true   in the environment (or .env) to activate.
Default is false — the existing AgentOrchestrator is used, with zero behaviour
change.

Parallel execution (future sprint)
------------------------------------
Tasks 3 (Gap Analysis) and 4 (Quantity Takeoff) share the same upstream
dependency (Task 2 — Spec Parser) and are candidates for parallel execution:

    TASK_DEPENDENCY_GRAPH shows:
        Task 3 depends on: [Task 2]
        Task 4 depends on: [Task 2, Task 3]   ← Task 4 waits for BOTH today

    In the parallel scheme the spec-based portion of Task 4 can start as
    soon as Task 2 finishes; gap items from Task 3 are merged in afterwards.

    To enable parallel execution in a future sprint:

    Step 1 — verify DB session isolation
        Each parallel task MUST use its own SessionLocal() instance to avoid
        SQLAlchemy concurrency issues.  Do NOT share self.db between threads.

    Step 2 — split Task 4 dependencies
        Change TASK_DEPENDENCY_GRAPH[4] from [2, 3] to [2] so Task 4 can start
        alongside Task 3 right after Task 2 completes.  Add a merge step after
        both complete.

    Step 3 — switch CrewAI process mode
        # crew = Crew(
        #     agents=[agent_3_crewai, agent_4_crewai],
        #     tasks=[task_3, task_4],
        #     process=Process.hierarchical,   # ← replaces Process.sequential
        #     manager_llm=ChatOpenAI(model="gpt-4o"),  # required for hierarchical
        # )

    WARNING: Do NOT enable parallel execution until data-isolation tests
    confirm no race conditions on the shared project tables (takeoff_items,
    gap_reports, spec_sections).
"""

import importlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project

logger = logging.getLogger("apex.crew_orchestrator")

# ---------------------------------------------------------------------------
# Optional CrewAI import — graceful degradation if not installed
# ---------------------------------------------------------------------------

try:
    from crewai import Crew, Task, Process  # type: ignore

    CREWAI_AVAILABLE = True
    logger.debug("crewai imported successfully — CrewOrchestrator ready")
except ImportError:
    CREWAI_AVAILABLE = False
    logger.warning(
        "crewai package not found.  "
        "Run: pip install crewai  to enable the CrewAI orchestrator.  "
        "Requests with USE_CREWAI_ORCHESTRATOR=true will fall back to "
        "the existing sequential orchestrator."
    )
    Task = None     # type: ignore
    Process = None  # type: ignore


# ---------------------------------------------------------------------------
# Agent & task definitions
# ---------------------------------------------------------------------------

# Mirrors agent_orchestrator.AGENT_DEFINITIONS — kept in sync intentionally
# so this module is self-contained and doesn't cross-import from the old one.
AGENT_DEFINITIONS = {
    1: ("Document Ingestion Agent",  "apex.backend.agents.agent_1_ingestion",    "run_ingestion_agent"),
    2: ("Spec Parser Agent",         "apex.backend.agents.agent_2_spec_parser",  "run_spec_parser_agent"),
    3: ("Scope Gap Analysis Agent",  "apex.backend.agents.agent_3_gap_analysis", "run_gap_analysis_agent"),
    4: ("Quantity Takeoff Agent",    "apex.backend.agents.agent_4_takeoff",       "run_takeoff_agent"),
    5: ("Labor Productivity Agent",  "apex.backend.agents.agent_5_labor",         "run_labor_agent"),
    6: ("Estimate Assembly Agent",   "apex.backend.agents.agent_6_assembly",      "run_assembly_agent"),
    7: ("IMPROVE Feedback Agent",    "apex.backend.agents.agent_7_improve",       "run_improve_agent"),
}

# Canonical APEX pipeline dependency graph.
#
#   Agent 1  — no deps        runs first
#   Agent 2  — needs [1]      spec parsing needs ingestion output
#   Agent 3  — needs [2]      gap analysis needs parsed spec
#   Agent 4  — needs [2, 3]   takeoff needs spec + gap items
#   Agent 5  — needs [4]      labor needs takeoff quantities
#   Agent 6  — needs [4, 5]   assembly needs takeoff + labor rates
#   Agent 7  — needs [6]      IMPROVE runs separately after actuals
#
TASK_DEPENDENCY_GRAPH: dict[int, list[int]] = {
    1: [],
    2: [1],
    3: [2],
    4: [2, 3],
    5: [4],
    6: [4, 5],
    7: [6],
}

# Agents included in the main pipeline run (Agent 7 runs independently)
PIPELINE_AGENTS: list[int] = [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# ApexTask wrapper
# ---------------------------------------------------------------------------

@dataclass
class ApexTask:
    """Pairs an APEX agent definition with a CrewAI Task object.

    The crewai_task field holds the CrewAI Task instance — used for its
    context= dependency graph — but actual execution calls agent_fn directly
    via call_agent().  This keeps CrewAI as an orchestration data layer
    without requiring an LLM for each step.
    """

    agent_number: int
    agent_name: str
    module_path: str
    fn_name: str
    crewai_task: object = field(default=None, repr=False)  # crewai.Task or None

    def call_agent(self, db: Session, project_id: int) -> dict:
        """Execute the wrapped agent function and return its result dict."""
        module = importlib.import_module(self.module_path)
        agent_fn = getattr(module, self.fn_name)
        return agent_fn(db, project_id)


def _build_apex_tasks(active_agents: list[int]) -> dict[int, "ApexTask"]:
    """Create ApexTask instances, optionally wiring CrewAI Task dependencies.

    Parameters
    ----------
    active_agents:
        Ordered list of agent numbers to include in this pipeline run.
        Agents absent from this list (e.g. skipped by pipeline_mode) are
        excluded from the dependency context so their downstream tasks are
        not blocked.

    Returns
    -------
    dict mapping agent_number → ApexTask for each active agent.
    """
    apex_tasks: dict[int, ApexTask] = {}
    active_set = set(active_agents)

    # First pass — create ApexTask shells (no crewai_task yet)
    for num in active_agents:
        agent_name, module_path, fn_name = AGENT_DEFINITIONS[num]
        apex_tasks[num] = ApexTask(
            agent_number=num,
            agent_name=agent_name,
            module_path=module_path,
            fn_name=fn_name,
        )

    if not CREWAI_AVAILABLE:
        return apex_tasks

    # Second pass — build CrewAI Task objects with context= wiring.
    # If Task construction fails (e.g. API change between CrewAI versions)
    # we log and continue — execution is driven by call_agent(), not crewai_task.
    crewai_tasks: dict[int, object] = {}  # agent_number → crewai.Task
    for num in active_agents:
        deps = TASK_DEPENDENCY_GRAPH.get(num, [])
        # Only wire dependencies that are actually active in this run
        context = [crewai_tasks[d] for d in deps if d in crewai_tasks and d in active_set]
        agent_name = AGENT_DEFINITIONS[num][0]
        try:
            crewai_tasks[num] = Task(
                description=(
                    f"APEX Pipeline — {agent_name} (Agent {num}). "
                    f"Execute the agent function and return structured results."
                ),
                expected_output=f"Dict containing Agent {num} processing results.",
                # agent= is intentionally omitted: we execute Python callables
                # directly without an LLM agent.  Assign an Agent instance here
                # when LLM-backed execution is introduced in a future sprint.
                context=context if context else None,
            )
        except Exception as exc:
            logger.debug(
                "CrewAI Task creation for Agent %d skipped: %s", num, exc
            )
            crewai_tasks[num] = None

        apex_tasks[num].crewai_task = crewai_tasks[num]

    return apex_tasks


# ---------------------------------------------------------------------------
# CrewOrchestrator
# ---------------------------------------------------------------------------

class CrewOrchestrator:
    """Pipeline orchestrator backed by the CrewAI task-dependency model.

    Mirrors the public interface of AgentOrchestrator so it is a drop-in
    replacement via the get_orchestrator() factory.

    Key differences from AgentOrchestrator
    ---------------------------------------
    • Execution order is derived from TASK_DEPENDENCY_GRAPH, not hard-coded
      if/else agent-number logic.
    • Lifecycle callbacks (before/after each task) emit WebSocket events in
      the same format as the existing orchestrator.
    • Parallel execution can be unlocked in a future sprint — see module
      docstring for the three-step migration guide.
    """

    def __init__(self, db: Session, project_id: int) -> None:
        self.db = db
        self.project_id = project_id

    # ------------------------------------------------------------------
    # DB logging helpers — identical to AgentOrchestrator
    # ------------------------------------------------------------------

    def _log_start(self, agent_name: str, agent_number: int) -> AgentRunLog:
        log = AgentRunLog(
            project_id=self.project_id,
            agent_name=agent_name,
            agent_number=agent_number,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def _log_complete(
        self,
        log: AgentRunLog,
        summary: str,
        tokens: int = 0,
        output_data: Optional[dict] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        log.status = "completed"
        log.completed_at = now
        log.duration_seconds = (now - log.started_at).total_seconds() if log.started_at else 0
        log.tokens_used = tokens
        log.output_summary = summary
        log.output_data = output_data
        self.db.commit()

    def _log_error(self, log: AgentRunLog, error_msg: str) -> None:
        now = datetime.now(timezone.utc)
        log.status = "failed"
        log.completed_at = now
        log.duration_seconds = (now - log.started_at).total_seconds() if log.started_at else 0
        log.error_message = error_msg
        self.db.commit()

    def _log_skipped(
        self, agent_name: str, agent_number: int, reason: str = ""
    ) -> AgentRunLog:
        log = AgentRunLog(
            project_id=self.project_id,
            agent_name=agent_name,
            agent_number=agent_number,
            status="skipped",
            started_at=None,
        )
        if reason:
            log.output_summary = reason
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        document_id: Optional[int] = None,
        pipeline_mode: str = "spec",
    ) -> dict:
        """Run agents 1-6 via the CrewAI dependency graph.

        Interface is identical to AgentOrchestrator.run_pipeline() so callers
        need no changes.
        """
        from apex.backend.agents.pipeline_contracts import ContractViolation
        from apex.backend.services.ws_manager import ws_manager

        pipeline_id = str(uuid.uuid4())
        pipeline_start = datetime.now(timezone.utc)
        results: dict[str, dict] = {}
        failed_at: Optional[int] = None
        effective_mode = pipeline_mode

        def _elapsed_ms() -> int:
            return int((datetime.now(timezone.utc) - pipeline_start).total_seconds() * 1000)

        # -----------------------------------------------------------------
        # Determine agents to skip before building the task graph
        # -----------------------------------------------------------------
        pre_skips: dict[int, str] = {}  # agent_num → reason
        if effective_mode == "winest_import":
            pre_skips[2] = (
                "WinEst import: data already structured — "
                "no spec document to parse"
            )

        # Active agents (those not already known-skipped)
        active_agents = [n for n in PIPELINE_AGENTS if n not in pre_skips]

        # Build CrewAI-backed ApexTask graph for active agents
        apex_tasks = _build_apex_tasks(active_agents)

        # Instantiate Crew as the dependency-graph data structure.
        # Execution is currently driven by the Python for-loop below,
        # not Crew.kickoff(). Switch to kickoff() in a future sprint
        # when parallel execution is enabled.
        if CREWAI_AVAILABLE:
            crewai_task_list = [
                t.crewai_task for t in apex_tasks.values()
                if t.crewai_task is not None
            ]
            if crewai_task_list:
                self._crew = Crew(
                    agents=[],
                    tasks=crewai_task_list,
                    process=Process.sequential,
                    verbose=False,
                )

        # -----------------------------------------------------------------
        # WS status table (same shape as AgentOrchestrator)
        # -----------------------------------------------------------------
        ws_status: dict[int, dict] = {
            num: {
                "agent_number":   num,
                "agent_name":     AGENT_DEFINITIONS[num][0],
                "status":         "pending",
                "started_at":     None,
                "duration_ms":    None,
                "error_message":  None,
                "output_summary": None,
            }
            for num in PIPELINE_AGENTS
        }
        skipped_agents: list[int] = []

        def _broadcast(overall: str, current_agent: Optional[int] = None) -> None:
            """Emit a pipeline_update WebSocket event.

            This is the CrewAI task callback integration point:
              • Before task execution  → called with status="running", current_agent=N
              • After task completion  → called with status="running", current_agent=None
              • On task failure        → called with status="running", current_agent=N
            Final pipeline_complete / pipeline_error events are emitted separately.
            """
            ws_manager.broadcast_sync(
                self.project_id,
                {
                    "type":               "pipeline_update",
                    "project_id":         self.project_id,
                    "pipeline_id":        pipeline_id,
                    "pipeline_mode":      effective_mode,
                    "status":             overall,
                    "current_agent":      current_agent,
                    "current_agent_name": (
                        ws_status[current_agent]["agent_name"] if current_agent else None
                    ),
                    "agents":             list(ws_status.values()),
                    "skipped_agents":     skipped_agents,
                    "total_elapsed_ms":   _elapsed_ms(),
                },
            )

        # -----------------------------------------------------------------
        # Log pre-determined skips (e.g. Agent 2 in winest_import mode)
        # -----------------------------------------------------------------
        for agent_num, reason in pre_skips.items():
            agent_name = AGENT_DEFINITIONS[agent_num][0]
            logger.info("CrewOrchestrator: skipping Agent %d — %s", agent_num, reason)
            self._log_skipped(agent_name, agent_num, reason=reason)
            results[f"agent_{agent_num}"] = {"status": "skipped", "skipped_because": reason}
            ws_status[agent_num]["status"] = "skipped"
            skipped_agents.append(agent_num)

        # -----------------------------------------------------------------
        # Execute tasks in dependency order (Process.sequential equivalent)
        #
        # PIPELINE_AGENTS is already in topological order [1, 2, 3, 4, 5, 6].
        # The CrewAI Task.context= fields encode the dependency graph so that
        # future parallel modes can respect them automatically.
        # -----------------------------------------------------------------
        for agent_num in PIPELINE_AGENTS:
            agent_name = AGENT_DEFINITIONS[agent_num][0]
            key = f"agent_{agent_num}"

            # Already handled above (pre-determined skip)
            if agent_num in pre_skips:
                continue

            # Stop-on-failure: mark remaining agents as skipped
            if failed_at is not None:
                skip_reason = f"Agent {failed_at} failed"
                self._log_skipped(agent_name, agent_num, reason=skip_reason)
                results[key] = {"status": "skipped", "skipped_because": skip_reason}
                ws_status[agent_num]["status"] = "skipped"
                skipped_agents.append(agent_num)
                continue

            # WinEst Agent 4: conditional skip when quantities are already present
            if effective_mode == "winest_import" and agent_num == 4:
                agent1_items = results.get("agent_1", {}).get("winest_line_items") or []
                quantities_present = any(
                    item.get("quantity") is not None for item in agent1_items
                )
                if quantities_present:
                    skip_reason = (
                        "WinEst import: quantities already present in import data"
                    )
                    logger.info(
                        "CrewOrchestrator: skipping Agent 4 — %s", skip_reason
                    )
                    self._log_skipped(agent_name, agent_num, reason=skip_reason)
                    results[key] = {"status": "skipped", "skipped_because": skip_reason}
                    ws_status[agent_num]["status"] = "skipped"
                    skipped_agents.append(agent_num)
                    _broadcast("running")
                    continue

            # -----------------------------------------------------------
            # Task lifecycle — BEFORE execution → broadcast "running"
            # (CrewAI callback integration point)
            # -----------------------------------------------------------
            agent_start_time = datetime.now(timezone.utc)
            ws_status[agent_num].update(
                {"status": "running", "started_at": agent_start_time.isoformat()}
            )
            _broadcast("running", agent_num)
            log = self._log_start(agent_name, agent_num)

            try:
                apex_task = apex_tasks[agent_num]
                result = apex_task.call_agent(self.db, self.project_id)

                # After Agent 1: check for WinEst auto-detection
                if agent_num == 1 and result.get("pipeline_mode") == "winest_import":
                    if effective_mode != "winest_import":
                        logger.info(
                            "CrewOrchestrator: Agent 1 detected WinEst import — "
                            "switching to winest_import pipeline mode"
                        )
                    effective_mode = "winest_import"

                summary_keys = (
                    "documents_processed", "sections_parsed", "total_gaps",
                    "items_created", "estimates_created", "estimate_id",
                )
                summary = next(
                    (f"{k}={result[k]}" for k in summary_keys if k in result),
                    str(result)[:200],
                )
                self._log_complete(log, summary, output_data=result)
                results[key] = result

                duration_ms = int(
                    (datetime.now(timezone.utc) - agent_start_time).total_seconds() * 1000
                )
                ws_status[agent_num].update(
                    {"status": "completed", "duration_ms": duration_ms}
                )
                # Task lifecycle — AFTER execution → broadcast "complete"
                _broadcast("running")

            except ContractViolation as exc:
                error_msg = f"Contract violation: {exc.detail}"
                self._log_error(log, error_msg)
                logger.error(
                    "CrewOrchestrator: Agent %d contract violation: %s",
                    agent_num, exc.detail,
                )
                results[key] = {"error": error_msg, "status": "failed"}
                failed_at = agent_num
                ws_status[agent_num].update(
                    {"status": "failed", "error_message": error_msg}
                )
                # Task lifecycle — ON FAILURE → broadcast "failed"
                _broadcast("running", agent_num)

            except Exception as exc:
                error_msg = str(exc)
                self._log_error(log, error_msg)
                logger.error("CrewOrchestrator: Agent %d failed: %s", agent_num, exc)
                results[key] = {"error": error_msg, "status": "failed"}
                failed_at = agent_num
                ws_status[agent_num].update(
                    {"status": "failed", "error_message": error_msg}
                )
                # Task lifecycle — ON FAILURE → broadcast "failed"
                _broadcast("running", agent_num)

        # -----------------------------------------------------------------
        # Update project status
        # -----------------------------------------------------------------
        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if project:
            project.status = "estimating" if failed_at is None else project.status
            self.db.commit()

        pipeline_final_status = (
            "completed" if failed_at is None else f"stopped_at_agent_{failed_at}"
        )
        results["pipeline_status"] = pipeline_final_status
        results["pipeline_mode"] = effective_mode

        # Final WebSocket event
        if failed_at is None:
            ws_manager.broadcast_sync(
                self.project_id,
                {
                    "type":             "pipeline_complete",
                    "project_id":       self.project_id,
                    "pipeline_id":      pipeline_id,
                    "pipeline_mode":    effective_mode,
                    "status":           "completed",
                    "agents":           list(ws_status.values()),
                    "skipped_agents":   skipped_agents,
                    "total_elapsed_ms": _elapsed_ms(),
                },
            )
        else:
            ws_manager.broadcast_sync(
                self.project_id,
                {
                    "type":             "pipeline_error",
                    "project_id":       self.project_id,
                    "pipeline_id":      pipeline_id,
                    "pipeline_mode":    effective_mode,
                    "status":           "failed",
                    "failed_at_agent":  failed_at,
                    "agents":           list(ws_status.values()),
                    "skipped_agents":   skipped_agents,
                    "total_elapsed_ms": _elapsed_ms(),
                },
            )

        return results

    # ------------------------------------------------------------------
    # Status / single-agent / improve — delegate to AgentOrchestrator
    # ------------------------------------------------------------------

    def get_pipeline_status(self) -> list[dict]:
        """Delegate to AgentOrchestrator (reads same AgentRunLog table)."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator
        return AgentOrchestrator(self.db, self.project_id).get_pipeline_status()

    def run_single_agent(self, agent_number: int) -> dict:
        """Delegate to AgentOrchestrator (unchanged behaviour)."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator
        return AgentOrchestrator(self.db, self.project_id).run_single_agent(agent_number)

    def run_improve_agent(self) -> dict:
        """Delegate to AgentOrchestrator (unchanged behaviour)."""
        from apex.backend.services.agent_orchestrator import AgentOrchestrator
        return AgentOrchestrator(self.db, self.project_id).run_improve_agent()


# ---------------------------------------------------------------------------
# Factory function — the primary integration point for callers
# ---------------------------------------------------------------------------

def get_orchestrator(db: Session, project_id: int):
    """Return the appropriate orchestrator based on the toggle env var.

    USE_CREWAI_ORCHESTRATOR=true  → CrewOrchestrator (requires crewai installed)
    USE_CREWAI_ORCHESTRATOR=false → AgentOrchestrator (default; no behaviour change)

    Fallback behaviour
    ------------------
    If  USE_CREWAI_ORCHESTRATOR=true  but crewai is not installed, or if
    CrewOrchestrator instantiation raises for any reason, a warning is logged
    and the function returns an AgentOrchestrator so the pipeline never
    hard-fails due to an orchestration-layer issue.

    Usage
    -----
    Replace every::

        orchestrator = AgentOrchestrator(db, project_id)

    with::

        orchestrator = get_orchestrator(db, project_id)

    The returned object has the same public interface regardless of which
    implementation is active.
    """
    from apex.backend.services.agent_orchestrator import AgentOrchestrator

    use_crewai = os.getenv("USE_CREWAI_ORCHESTRATOR", "false").strip().lower() == "true"

    if use_crewai:
        if not CREWAI_AVAILABLE:
            logger.warning(
                "USE_CREWAI_ORCHESTRATOR=true but crewai is not installed. "
                "Run: pip install crewai  "
                "Falling back to AgentOrchestrator."
            )
        else:
            try:
                orchestrator = CrewOrchestrator(db, project_id)
                logger.debug(
                    "get_orchestrator: using CrewOrchestrator for project %d",
                    project_id,
                )
                return orchestrator
            except Exception as exc:
                logger.warning(
                    "CrewOrchestrator instantiation failed (%s); "
                    "falling back to AgentOrchestrator.",
                    exc,
                )

    return AgentOrchestrator(db, project_id)
