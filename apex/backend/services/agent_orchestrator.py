"""Agent orchestration service — manages the pipeline of all 7 agents.

Pipeline modes
--------------
"spec" (default)
    Normal flow: Agent 1 → 2 → 3 → 4 → 5 → 6.

"winest_import"
    WinEst file detected by Agent 1 (or pre-detected by the upload endpoint
    when the file extension is .est):

    Agent 1  runs  — parses WinEst file, outputs structured line items
    Agent 2  SKIPPED — no spec document to parse; data is already structured
    Agent 3  runs  — gap analysis on imported line items
    Agent 4  SKIPPED if quantities are already present in the import;
             otherwise runs to fill in missing takeoff quantities
    Agent 5  runs  — compares imported labor rates against historical data
    Agent 6  runs  — assembles the estimate
    Agent 7  separate (run via run_improve_agent after actuals upload)

Skipped agents are logged with the reason stored in output_summary.

WebSocket events
----------------
During run_pipeline() the orchestrator pushes real-time status updates to all
connected WebSocket clients via ws_manager.broadcast_sync().  Events:

  "pipeline_update"   — before & after each agent (status change)
  "pipeline_complete" — pipeline finished successfully
  "pipeline_error"    — pipeline stopped due to a failure
"""

import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project

logger = logging.getLogger("apex.orchestrator")

AGENT_DEFINITIONS = {
    1: ("Document Ingestion Agent",   "apex.backend.agents.agent_1_ingestion",   "run_ingestion_agent"),
    2: ("Spec Parser Agent",          "apex.backend.agents.agent_2_spec_parser", "run_spec_parser_agent"),
    3: ("Scope Gap Analysis Agent",   "apex.backend.agents.agent_3_gap_analysis","run_gap_analysis_agent"),
    4: ("Quantity Takeoff Agent",     "apex.backend.agents.agent_4_takeoff",     "run_takeoff_agent"),
    5: ("Labor Productivity Agent",   "apex.backend.agents.agent_5_labor",       "run_labor_agent"),
    6: ("Estimate Assembly Agent",    "apex.backend.agents.agent_6_assembly",    "run_assembly_agent"),
    7: ("IMPROVE Feedback Agent",     "apex.backend.agents.agent_7_improve",     "run_improve_agent"),
}


class AgentOrchestrator:
    def __init__(self, db: Session, project_id: int):
        self.db = db
        self.project_id = project_id

    # ------------------------------------------------------------------
    # Internal logging helpers
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

    def _log_complete(self, log: AgentRunLog, summary: str, tokens: int = 0, output_data: dict = None):
        now = datetime.now(timezone.utc)
        log.status = "completed"
        log.completed_at = now
        log.duration_seconds = (now - log.started_at).total_seconds() if log.started_at else 0
        log.tokens_used = tokens
        log.output_summary = summary
        log.output_data = output_data
        self.db.commit()

    def _log_error(self, log: AgentRunLog, error_msg: str):
        now = datetime.now(timezone.utc)
        log.status = "failed"
        log.completed_at = now
        log.duration_seconds = (now - log.started_at).total_seconds() if log.started_at else 0
        log.error_message = error_msg
        self.db.commit()

    def _log_skipped(self, agent_name: str, agent_number: int, reason: str = "") -> AgentRunLog:
        """Record a skipped agent.  *reason* is stored in output_summary."""
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

    def run_pipeline(self, document_id: int = None, pipeline_mode: str = "spec") -> dict:
        """Run agents 1-6 sequentially.

        Parameters
        ----------
        document_id : int, optional
            Specific document to process (not used by all agents, but stored
            for context).
        pipeline_mode : str
            "spec"          — standard flow, all agents 1-6 run in order.
            "winest_import" — WinEst intake flow; Agent 2 is always skipped,
                              Agent 4 is skipped when quantities are already
                              present in the imported data.

        After Agent 1 runs its output is inspected: if it reports
        pipeline_mode='winest_import', the effective mode is upgraded even if
        the caller passed "spec" (this covers the xlsx auto-detection case).

        Returns a dict with keys agent_1 … agent_6 plus pipeline_status and
        pipeline_mode.
        """
        from apex.backend.agents.pipeline_contracts import ContractViolation
        from apex.backend.services.ws_manager import ws_manager

        pipeline_id = str(uuid.uuid4())
        pipeline_start = datetime.now(timezone.utc)
        results: dict[str, dict] = {}
        pipeline_agents = [1, 2, 3, 4, 5, 6]
        failed_at: int | None = None
        effective_mode = pipeline_mode

        # In-memory agent status table used for WS broadcasts.
        # Uses agent_number / agent_name to stay consistent with the REST API.
        ws_status: dict[int, dict] = {}
        for num in pipeline_agents:
            ws_status[num] = {
                "agent_number":   num,
                "agent_name":     AGENT_DEFINITIONS[num][0],
                "status":         "pending",
                "started_at":     None,
                "duration_ms":    None,
                "error_message":  None,
                "output_summary": None,
            }
        skipped_agents: list[int] = []

        def _elapsed_ms() -> int:
            return int((datetime.now(timezone.utc) - pipeline_start).total_seconds() * 1000)

        def _broadcast(overall: str, current_agent: int | None = None) -> None:
            ws_manager.broadcast_sync(self.project_id, {
                "type":               "pipeline_update",
                "project_id":         self.project_id,
                "pipeline_id":        pipeline_id,
                "pipeline_mode":      effective_mode,
                "status":             overall,
                "current_agent":      current_agent,
                "current_agent_name": ws_status[current_agent]["agent_name"] if current_agent else None,
                "agents":             list(ws_status.values()),
                "skipped_agents":     skipped_agents,
                "total_elapsed_ms":   _elapsed_ms(),
            })

        for agent_num in pipeline_agents:
            agent_name, module_path, fn_name = AGENT_DEFINITIONS[agent_num]
            key = f"agent_{agent_num}"

            # -----------------------------------------------------------------
            # Stop-on-failure: mark remaining agents skipped
            # -----------------------------------------------------------------
            if failed_at is not None:
                skip_reason = f"Agent {failed_at} failed"
                self._log_skipped(agent_name, agent_num, reason=skip_reason)
                results[key] = {"status": "skipped", "skipped_because": skip_reason}
                ws_status[agent_num]["status"] = "skipped"
                skipped_agents.append(agent_num)
                continue

            # -----------------------------------------------------------------
            # WinEst pipeline skipping rules
            # -----------------------------------------------------------------
            if effective_mode == "winest_import":
                if agent_num == 2:
                    skip_reason = (
                        "WinEst import: data already structured — "
                        "no spec document to parse"
                    )
                    logger.info(f"Skipping Agent 2 — {skip_reason}")
                    self._log_skipped(agent_name, agent_num, reason=skip_reason)
                    results[key] = {"status": "skipped", "skipped_because": skip_reason}
                    ws_status[agent_num]["status"] = "skipped"
                    skipped_agents.append(agent_num)
                    _broadcast("running")
                    continue

                if agent_num == 4:
                    agent1_items = results.get("agent_1", {}).get("winest_line_items") or []
                    quantities_present = any(
                        item.get("quantity") is not None for item in agent1_items
                    )
                    if quantities_present:
                        skip_reason = (
                            "WinEst import: quantities already present in import data"
                        )
                        logger.info(f"Skipping Agent 4 — {skip_reason}")
                        self._log_skipped(agent_name, agent_num, reason=skip_reason)
                        results[key] = {"status": "skipped", "skipped_because": skip_reason}
                        ws_status[agent_num]["status"] = "skipped"
                        skipped_agents.append(agent_num)
                        _broadcast("running")
                        continue

            # -----------------------------------------------------------------
            # Run the agent
            # -----------------------------------------------------------------
            agent_start_time = datetime.now(timezone.utc)
            ws_status[agent_num].update({
                "status":     "running",
                "started_at": agent_start_time.isoformat(),
            })
            _broadcast("running", agent_num)

            log = self._log_start(agent_name, agent_num)
            try:
                import importlib
                module = importlib.import_module(module_path)
                agent_fn = getattr(module, fn_name)
                result = agent_fn(self.db, self.project_id)

                # After Agent 1: check if it detected a WinEst import
                if agent_num == 1 and result.get("pipeline_mode") == "winest_import":
                    if effective_mode != "winest_import":
                        logger.info(
                            "Agent 1 detected WinEst import — "
                            "switching to winest_import pipeline mode"
                        )
                    effective_mode = "winest_import"

                # Summarise result for the log
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
                ws_status[agent_num].update({
                    "status":      "completed",
                    "duration_ms": duration_ms,
                })
                _broadcast("running")

            except ContractViolation as exc:
                error_msg = f"Contract violation: {exc.detail}"
                self._log_error(log, error_msg)
                logger.error(f"Agent {agent_num} contract violation: {exc.detail}")
                results[key] = {"error": error_msg, "status": "failed"}
                failed_at = agent_num
                ws_status[agent_num].update({
                    "status":        "failed",
                    "error_message": error_msg,
                })
                _broadcast("running", agent_num)

            except Exception as exc:
                error_msg = str(exc)
                self._log_error(log, error_msg)
                logger.error(f"Agent {agent_num} failed: {exc}")
                results[key] = {"error": error_msg, "status": "failed"}
                failed_at = agent_num
                ws_status[agent_num].update({
                    "status":        "failed",
                    "error_message": error_msg,
                })
                _broadcast("running", agent_num)

        # Update project status
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
            ws_manager.broadcast_sync(self.project_id, {
                "type":             "pipeline_complete",
                "project_id":       self.project_id,
                "pipeline_id":      pipeline_id,
                "pipeline_mode":    effective_mode,
                "status":           "completed",
                "agents":           list(ws_status.values()),
                "skipped_agents":   skipped_agents,
                "total_elapsed_ms": _elapsed_ms(),
            })
        else:
            ws_manager.broadcast_sync(self.project_id, {
                "type":             "pipeline_error",
                "project_id":       self.project_id,
                "pipeline_id":      pipeline_id,
                "pipeline_mode":    effective_mode,
                "status":           "failed",
                "failed_at_agent":  failed_at,
                "agents":           list(ws_status.values()),
                "skipped_agents":   skipped_agents,
                "total_elapsed_ms": _elapsed_ms(),
            })

        return results

    # ------------------------------------------------------------------
    # Pipeline status query
    # ------------------------------------------------------------------

    def get_pipeline_status(self) -> list[dict]:
        """Return the latest status of each pipeline agent (1-6) for this project.

        For each agent number, finds the most recent AgentRunLog record and
        returns a status dict.  Agents with no log record are reported as
        "pending".
        """
        from sqlalchemy import func

        # Latest log id per agent_number
        subq = (
            self.db.query(
                AgentRunLog.agent_number,
                func.max(AgentRunLog.id).label("max_id"),
            )
            .filter(AgentRunLog.project_id == self.project_id)
            .group_by(AgentRunLog.agent_number)
            .subquery()
        )

        latest_logs = (
            self.db.query(AgentRunLog)
            .join(subq, AgentRunLog.id == subq.c.max_id)
            .all()
        )

        log_by_num = {log.agent_number: log for log in latest_logs}

        statuses = []
        for agent_num in range(1, 7):
            agent_name = AGENT_DEFINITIONS[agent_num][0]
            log = log_by_num.get(agent_num)

            if log is None:
                statuses.append({
                    "agent_number":   agent_num,
                    "agent_name":     agent_name,
                    "status":         "pending",
                    "started_at":     None,
                    "completed_at":   None,
                    "duration_seconds": None,
                    "error_message":  None,
                    "output_summary": None,
                })
            else:
                statuses.append({
                    "agent_number":   agent_num,
                    "agent_name":     agent_name,
                    "status":         log.status,
                    "started_at":     log.started_at.isoformat() if log.started_at else None,
                    "completed_at":   log.completed_at.isoformat() if log.completed_at else None,
                    "duration_seconds": log.duration_seconds,
                    "error_message":  log.error_message,
                    "output_summary": log.output_summary,
                })

        return statuses

    # ------------------------------------------------------------------
    # Single-agent run (used by the per-agent run UI)
    # ------------------------------------------------------------------

    def run_single_agent(self, agent_number: int) -> dict:
        """Run a single agent by number (1-7)."""
        if agent_number not in AGENT_DEFINITIONS:
            raise ValueError(f"Invalid agent_number {agent_number}: must be 1-7")

        agent_name, module_path, fn_name = AGENT_DEFINITIONS[agent_number]
        import importlib
        module = importlib.import_module(module_path)
        agent_fn = getattr(module, fn_name)

        log = self._log_start(agent_name, agent_number)
        try:
            result = agent_fn(self.db, self.project_id)
            summary = str(result.get(list(result.keys())[0], "")) if result else "Done"
            self._log_complete(log, summary, output_data=result)
            return {
                "agent_number":     agent_number,
                "agent_name":       agent_name,
                "output":           result,
                "duration_seconds": log.duration_seconds,
            }
        except Exception as exc:
            self._log_error(log, str(exc))
            logger.error(f"Agent {agent_number} failed: {exc}")
            raise

    # ------------------------------------------------------------------
    # Improve agent (Agent 7)
    # ------------------------------------------------------------------

    def run_improve_agent(self) -> dict:
        """Run Agent 7 independently after actuals upload."""
        from apex.backend.agents.agent_7_improve import run_improve_agent

        log7 = self._log_start("IMPROVE Feedback Agent", 7)
        try:
            r7 = run_improve_agent(self.db, self.project_id)
            self._log_complete(log7, f"Processed {r7.get('actuals_processed', 0)} actuals", output_data=r7)
            return r7
        except Exception as exc:
            self._log_error(log7, str(exc))
            logger.error(f"Agent 7 failed: {exc}")
            return {"error": str(exc)}
