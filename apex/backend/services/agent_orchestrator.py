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

import asyncio
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project
from apex.backend.models.token_usage import TokenUsage

logger = logging.getLogger("apex.orchestrator")

# ---------------------------------------------------------------------------
# Project-level concurrency lock registry
# ---------------------------------------------------------------------------
_lock_registry_guard = threading.Lock()
_project_locks: dict[int, threading.Lock] = {}


def _get_project_lock(project_id: int) -> threading.Lock:
    """Return (or create) a per-project lock."""
    with _lock_registry_guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]

AGENT_DEFINITIONS = {
    1: ("Document Ingestion Agent",   "apex.backend.agents.agent_1_ingestion",   "run_ingestion_agent"),
    2: ("Spec Parser Agent",          "apex.backend.agents.agent_2_spec_parser", "run_spec_parser_agent"),
    3: ("Scope Analysis Agent",       "apex.backend.agents.agent_3_gap_analysis","run_gap_analysis_agent"),
    4: ("Rate Intelligence Agent",    "apex.backend.agents.agent_4_takeoff",     "run_takeoff_agent"),
    5: ("Field Calibration Agent",    "apex.backend.agents.agent_5_labor",       "run_labor_agent"),
    6: ("Intelligence Report Agent",  "apex.backend.agents.agent_6_assembly",    "run_assembly_agent"),
    7: ("IMPROVE Feedback Agent",     "apex.backend.agents.agent_7_improve",     "run_improve_agent"),
}

# ---------------------------------------------------------------------------
# Parallel execution helpers for Agents 3 & 4
#
# Each helper opens its own isolated DB session (via SessionLocal) so the two
# agents can execute concurrently under SQLite WAL mode without sharing a
# connection, transaction, or in-memory state.
# ---------------------------------------------------------------------------

async def _parallel_run_agent_3(project_id: int) -> dict:
    """Run Agent 3 (gap analysis) in a thread executor with an isolated DB session."""
    from apex.backend.agents.agent_3_gap_analysis import run_gap_analysis_agent
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, run_gap_analysis_agent, db, project_id)
    finally:
        db.close()


async def _parallel_run_agent_4(project_id: int) -> dict:
    """Run Agent 4 (quantity takeoff) in a thread executor with an isolated DB session."""
    from apex.backend.agents.agent_4_takeoff import run_takeoff_agent
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, run_takeoff_agent, db, project_id)
    finally:
        db.close()


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
            started_at=datetime.utcnow(),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def _log_complete(self, log: AgentRunLog, summary: str, tokens: int = 0, output_data: dict = None):
        now = datetime.utcnow()
        log.status = "completed"
        log.completed_at = now
        log.duration_seconds = (datetime.utcnow() - log.started_at).total_seconds() if log.started_at else 0
        log.tokens_used = tokens
        log.output_summary = summary
        log.output_data = output_data

        if tokens == 0 and log.started_at is not None:
            usage_records = (
                self.db.query(TokenUsage)
                .filter(
                    TokenUsage.project_id == self.project_id,
                    TokenUsage.agent_number == log.agent_number,
                    TokenUsage.created_at >= log.started_at,
                )
                .all()
            )
            count = len(usage_records)
            if count > 0:
                total_tokens = sum(r.input_tokens + r.output_tokens for r in usage_records)
                log.tokens_used = total_tokens
                logger.info(
                    "Agent %d token usage: %d tokens (auto-filled from %d TokenUsage records)",
                    log.agent_number, total_tokens, count,
                )

        self.db.commit()

    def _log_error(self, log: AgentRunLog, error_msg: str):
        now = datetime.utcnow()
        log.status = "failed"
        log.completed_at = now
        log.duration_seconds = (datetime.utcnow() - log.started_at).total_seconds() if log.started_at else 0
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

        project_lock = _get_project_lock(self.project_id)
        if not project_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail=f"Pipeline already running for project {self.project_id}",
            )

        try:
            return self._run_pipeline_locked(document_id, pipeline_mode)
        finally:
            project_lock.release()

    def _run_pipeline_locked(self, document_id: int = None, pipeline_mode: str = "spec") -> dict:
        """Internal pipeline execution — called while holding the project lock."""
        from apex.backend.agents.pipeline_contracts import ContractViolation
        from apex.backend.services.ws_manager import ws_manager

        pipeline_id = str(uuid.uuid4())
        pipeline_start = datetime.utcnow()
        results: dict[str, dict] = {}
        # v2 order: Agent 4 runs before Agent 3 so takeoff data is available
        # for spec-vs-takeoff cross-reference analysis
        pipeline_agents = [1, 2, 4, 3, 5, 6]
        failed_at: int | None = None
        effective_mode = pipeline_mode

        # Mark project as running
        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if project and project.status not in ("estimating",):
            project.status = "estimating"
            self.db.commit()

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
            return int((datetime.utcnow() - pipeline_start).total_seconds() * 1000)

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
            agent_start_time = datetime.utcnow()
            ws_status[agent_num].update({
                "status":     "running",
                "started_at": agent_start_time.isoformat(),
            })
            _broadcast("running", agent_num)

            log = self._log_start(agent_name, agent_num)
            max_retries = int(os.getenv("AGENT_MAX_RETRIES", "1")) if agent_num >= 2 else 0
            last_error = None

            for attempt in range(1 + max_retries):
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
                        "takeoff_items_parsed", "items_compared", "items_created", "estimates_created", "estimate_id",
                        "report_id", "overall_risk_level",
                    )
                    summary = next(
                        (f"{k}={result[k]}" for k in summary_keys if k in result),
                        str(result)[:200],
                    )
                    if attempt > 0:
                        summary = f"[retry {attempt}] {summary}"
                    self._log_complete(log, summary, output_data=result)
                    results[key] = result

                    duration_ms = int(
                        (datetime.utcnow() - agent_start_time).total_seconds() * 1000
                    )
                    ws_status[agent_num].update({
                        "status":      "completed",
                        "duration_ms": duration_ms,
                    })
                    _broadcast("running")
                    last_error = None
                    break  # success

                except ContractViolation as exc:
                    last_error = f"Contract violation: {exc.detail}"
                    if attempt < max_retries:
                        logger.warning(
                            "Agent %d contract violation (attempt %d/%d), retrying: %s",
                            agent_num, attempt + 1, 1 + max_retries, exc.detail,
                        )
                        continue
                    # Final attempt failed
                    self._log_error(log, last_error)
                    logger.error(f"Agent {agent_num} contract violation: {exc.detail}")

                except Exception as exc:
                    last_error = str(exc)
                    if attempt < max_retries:
                        logger.warning(
                            "Agent %d failed (attempt %d/%d), retrying: %s",
                            agent_num, attempt + 1, 1 + max_retries, exc,
                        )
                        continue
                    # Final attempt failed
                    self._log_error(log, last_error)
                    logger.error(f"Agent {agent_num} failed: {exc}")

            if last_error is not None:
                results[key] = {"error": last_error, "status": "failed"}
                failed_at = agent_num
                ws_status[agent_num].update({
                    "status":        "failed",
                    "error_message": last_error,
                })
                _broadcast("running", agent_num)

        # Update project status
        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if project:
            if failed_at is None:
                project.status = "estimating"
            else:
                project.status = "failed"
                logger.error(
                    "Pipeline failed at Agent %d for project %d",
                    failed_at, self.project_id,
                )
            self.db.commit()

        pipeline_final_status = (
            "completed" if failed_at is None else f"stopped_at_agent_{failed_at}"
        )
        results["pipeline_status"] = pipeline_final_status
        results["pipeline_mode"] = effective_mode

        # Send email notification
        try:
            from apex.backend.services.email_service import send_pipeline_complete
            project = self.db.query(Project).filter(Project.id == self.project_id).first()
            if project and project.owner:
                success = failed_at is None
                error_msg = None
                if not success:
                    # Find first failed agent
                    for k, v in results.items():
                        if isinstance(v, dict) and v.get("status") == "failed":
                            error_msg = v.get("error", "Unknown error")
                            break
                send_pipeline_complete(
                    to=project.owner.email,
                    project_name=project.name,
                    project_number=project.project_number,
                    success=success,
                    error_msg=error_msg,
                )
        except Exception as e:
            logger.warning(f"Failed to send pipeline notification: {e}")

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
            # Email notification — fire-and-forget (errors logged, never raised)
            try:
                self._notify_pipeline_complete(results)
            except Exception as _e:
                logger.warning("Email notification failed: %s", _e)
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
    # Email notification helpers
    # ------------------------------------------------------------------

    def _notify_pipeline_complete(self, results: dict):
        """Send pipeline-complete email to the project owner (if NOTIFICATIONS_ENABLED)."""
        import os
        if os.getenv("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
            return

        from apex.backend.services.email_service import notify_pipeline_complete
        from apex.backend.models.estimate import Estimate
        from apex.backend.models.user import User

        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if not project:
            return

        estimate = (
            self.db.query(Estimate)
            .filter(Estimate.project_id == self.project_id, Estimate.is_deleted == False)  # noqa: E712
            .order_by(Estimate.version.desc())
            .first()
        )

        recipient = None
        if project.owner_id:
            owner = self.db.query(User).filter(User.id == project.owner_id).first()
            if owner and owner.email:
                recipient = owner.email

        notify_email = os.getenv("NOTIFICATION_EMAIL", recipient)
        if not notify_email:
            return

        notify_pipeline_complete(
            to=notify_email,
            project_name=project.name,
            project_number=project.project_number,
            total_bid=estimate.total_bid_amount if estimate else None,
        )

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
