"""Agent orchestration service — manages the pipeline of all 7 agents."""

import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project

logger = logging.getLogger("apex.orchestrator")


class AgentOrchestrator:
    def __init__(self, db: Session, project_id: int):
        self.db = db
        self.project_id = project_id

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
        log.status = "error"
        log.completed_at = now
        log.duration_seconds = (now - log.started_at).total_seconds() if log.started_at else 0
        log.error_message = error_msg
        self.db.commit()

    def run_pipeline(self) -> dict:
        """Run the full agent pipeline sequentially with parallel steps where applicable."""
        from apex.backend.agents.agent_1_ingestion import run_ingestion_agent
        from apex.backend.agents.agent_2_spec_parser import run_spec_parser_agent
        from apex.backend.agents.agent_3_gap_analysis import run_gap_analysis_agent
        from apex.backend.agents.agent_4_takeoff import run_takeoff_agent
        from apex.backend.agents.agent_5_labor import run_labor_agent
        from apex.backend.agents.agent_6_assembly import run_assembly_agent

        results = {}

        # Step 1: Document Ingestion
        log1 = self._log_start("Document Ingestion Agent", 1)
        try:
            r1 = run_ingestion_agent(self.db, self.project_id)
            self._log_complete(log1, f"Ingested {r1.get('documents_processed', 0)} documents", output_data=r1)
            results["agent_1"] = r1
        except Exception as e:
            self._log_error(log1, str(e))
            logger.error(f"Agent 1 failed: {e}")
            results["agent_1"] = {"error": str(e)}

        # Step 2: Spec Parser
        log2 = self._log_start("Spec Parser Agent", 2)
        try:
            r2 = run_spec_parser_agent(self.db, self.project_id)
            self._log_complete(log2, f"Parsed {r2.get('sections_parsed', 0)} spec sections", output_data=r2)
            results["agent_2"] = r2
        except Exception as e:
            self._log_error(log2, str(e))
            logger.error(f"Agent 2 failed: {e}")
            results["agent_2"] = {"error": str(e)}

        # Step 3: Gap Analysis and Takeoff in parallel (run sequentially here for SQLite compatibility)
        log3 = self._log_start("Scope Gap Analysis Agent", 3)
        try:
            r3 = run_gap_analysis_agent(self.db, self.project_id)
            self._log_complete(log3, f"Found {r3.get('total_gaps', 0)} scope gaps", output_data=r3)
            results["agent_3"] = r3
        except Exception as e:
            self._log_error(log3, str(e))
            logger.error(f"Agent 3 failed: {e}")
            results["agent_3"] = {"error": str(e)}

        log4 = self._log_start("Quantity Takeoff Agent", 4)
        try:
            r4 = run_takeoff_agent(self.db, self.project_id)
            self._log_complete(log4, f"Generated {r4.get('items_created', 0)} takeoff items", output_data=r4)
            results["agent_4"] = r4
        except Exception as e:
            self._log_error(log4, str(e))
            logger.error(f"Agent 4 failed: {e}")
            results["agent_4"] = {"error": str(e)}

        # Step 4: Labor Productivity
        log5 = self._log_start("Labor Productivity Agent", 5)
        try:
            r5 = run_labor_agent(self.db, self.project_id)
            self._log_complete(log5, f"Estimated {r5.get('estimates_created', 0)} labor items", output_data=r5)
            results["agent_5"] = r5
        except Exception as e:
            self._log_error(log5, str(e))
            logger.error(f"Agent 5 failed: {e}")
            results["agent_5"] = {"error": str(e)}

        # Step 5: Estimate Assembly
        log6 = self._log_start("Estimate Assembly Agent", 6)
        try:
            r6 = run_assembly_agent(self.db, self.project_id)
            self._log_complete(log6, f"Assembled estimate v{r6.get('version', 1)}", output_data=r6)
            results["agent_6"] = r6
        except Exception as e:
            self._log_error(log6, str(e))
            logger.error(f"Agent 6 failed: {e}")
            results["agent_6"] = {"error": str(e)}

        # Update project status
        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if project:
            project.status = "estimating"
            self.db.commit()

        return results

    def run_improve_agent(self) -> dict:
        """Run Agent 7 independently after actuals upload."""
        from apex.backend.agents.agent_7_improve import run_improve_agent

        log7 = self._log_start("IMPROVE Feedback Agent", 7)
        try:
            r7 = run_improve_agent(self.db, self.project_id)
            self._log_complete(log7, f"Processed {r7.get('actuals_processed', 0)} actuals", output_data=r7)
            return r7
        except Exception as e:
            self._log_error(log7, str(e))
            logger.error(f"Agent 7 failed: {e}")
            return {"error": str(e)}
