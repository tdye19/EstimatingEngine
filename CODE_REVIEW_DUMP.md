# Code Review Dump

## 1. File Tree (`find apex/ -type f -name "*.py" -o -name "*.jsx" | sort`)

```
apex/__init__.py
apex/backend/__init__.py
apex/backend/agents/__init__.py
apex/backend/agents/agent_1_ingestion.py
apex/backend/agents/agent_2_spec_parser.py
apex/backend/agents/agent_3_gap_analysis.py
apex/backend/agents/agent_4_takeoff.py
apex/backend/agents/agent_5_labor.py
apex/backend/agents/agent_6_assembly.py
apex/backend/agents/agent_7_improve.py
apex/backend/agents/pipeline_contracts.py
apex/backend/agents/tools/__init__.py
apex/backend/agents/tools/assembly_tools.py
apex/backend/agents/tools/document_tools.py
apex/backend/agents/tools/domain_gap_rules.py
apex/backend/agents/tools/gap_tools.py
apex/backend/agents/tools/improve_tools.py
apex/backend/agents/tools/labor_tools.py
apex/backend/agents/tools/spec_prompts.py
apex/backend/agents/tools/spec_tools.py
apex/backend/agents/tools/takeoff_tools.py
apex/backend/alembic/env.py
apex/backend/alembic/versions/2e5ae275617d_decision_system_tables.py
apex/backend/alembic/versions/37e85ea73069_add_cache_and_sprint6_columns.py
apex/backend/alembic/versions/a1b2c3d4e5f6_sprint12_4_shadow_mode.py
apex/backend/alembic/versions/a8c0d2e4f6b7_sprint16_intelligence_report.py
apex/backend/alembic/versions/b3d5f7a9c1e2_pb_integrate_1_productivity_brain_tables.py
apex/backend/alembic/versions/c4e6a8d0f2b1_bi_ingest_1_bid_intelligence_table.py
apex/backend/alembic/versions/c9f4a8d2e1b3_sprint8_full_schema_with_estimate_library.py
apex/backend/alembic/versions/d4f7b1c9e2a5_sprint9_historical_line_items_and_document_associations.py
apex/backend/alembic/versions/d5f7b9a1c3e4_agent2_v2_spec_parameter_columns.py
apex/backend/alembic/versions/e4ae649389b5_add_estimated_cost_to_agent_run_log.py
apex/backend/alembic/versions/e5a2b7d3f1c8_sprint10_productivity_benchmark.py
apex/backend/alembic/versions/e6a8c2d4f0b3_sprint14_takeoff_v2.py
apex/backend/alembic/versions/ee412a823a92_initial_schema_sprint7.py
apex/backend/alembic/versions/f2c9d4e7b3a1_add_updated_at_to_document_models.py
apex/backend/alembic/versions/f7b9d1e3a5c6_sprint15_field_actuals.py
apex/backend/config.py
apex/backend/db/__init__.py
apex/backend/db/database.py
apex/backend/db/load_remaining_projects.py
apex/backend/db/ontology_seed.py
apex/backend/db/seed.py
apex/backend/db/seed_decision_data.py
apex/backend/main.py
apex/backend/migrate.py
apex/backend/models/__init__.py
apex/backend/models/agent_run_log.py
apex/backend/models/audit_log.py
apex/backend/models/base.py
apex/backend/models/bid_comparison.py
apex/backend/models/change_order.py
apex/backend/models/decision_models.py
apex/backend/models/document.py
apex/backend/models/document_association.py
apex/backend/models/equipment_rate.py
apex/backend/models/estimate.py
apex/backend/models/estimate_library.py
apex/backend/models/field_actuals.py
apex/backend/models/gap_report.py
apex/backend/models/historical_line_item.py
apex/backend/models/intelligence_report.py
apex/backend/models/labor_estimate.py
apex/backend/models/material_price.py
apex/backend/models/organization.py
apex/backend/models/productivity_benchmark.py
apex/backend/models/productivity_history.py
apex/backend/models/project.py
apex/backend/models/project_actual.py
apex/backend/models/spec_section.py
apex/backend/models/takeoff_item.py
apex/backend/models/takeoff_v2.py
apex/backend/models/token_usage.py
apex/backend/models/upload_chunk.py
apex/backend/models/upload_session.py
apex/backend/models/user.py
apex/backend/routers/__init__.py
apex/backend/routers/admin.py
apex/backend/routers/auth.py
apex/backend/routers/batch_import.py
apex/backend/routers/benchmarking.py
apex/backend/routers/benchmarks.py
apex/backend/routers/bid_comparison.py
apex/backend/routers/bid_intelligence.py
apex/backend/routers/change_orders.py
apex/backend/routers/decision.py
apex/backend/routers/decision_system.py
apex/backend/routers/estimate_library.py
apex/backend/routers/exports.py
apex/backend/routers/field_actuals.py
apex/backend/routers/material_prices.py
apex/backend/routers/materials.py
apex/backend/routers/notifications.py
apex/backend/routers/productivity.py
apex/backend/routers/productivity_brain.py
apex/backend/routers/projects.py
apex/backend/routers/reports.py
apex/backend/routers/test_pipeline.py
apex/backend/routers/token_usage.py
apex/backend/routers/users.py
apex/backend/routers/websocket.py
apex/backend/services/__init__.py
apex/backend/services/agent_orchestrator.py
apex/backend/services/batch_import_service.py
apex/backend/services/benchmark_engine.py
apex/backend/services/benchmarking_engine/__init__.py
apex/backend/services/benchmarking_engine/context.py
apex/backend/services/benchmarking_engine/engine.py
apex/backend/services/bid_intelligence/__init__.py
apex/backend/services/bid_intelligence/models.py
apex/backend/services/bid_intelligence/parser.py
apex/backend/services/bid_intelligence/service.py
apex/backend/services/crew_orchestrator.py
apex/backend/services/decision_assembly.py
apex/backend/services/decision_benchmark.py
apex/backend/services/decision_commercial.py
apex/backend/services/decision_pricing.py
apex/backend/services/decision_project_loader.py
apex/backend/services/decision_risk.py
apex/backend/services/email_service.py
apex/backend/services/field_actuals/__init__.py
apex/backend/services/field_actuals/service.py
apex/backend/services/line_item_normalizer.py
apex/backend/services/llm_provider.py
apex/backend/services/material_price_service.py
apex/backend/services/pricing_engine/__init__.py
apex/backend/services/pricing_engine/engine.py
apex/backend/services/productivity_brain/__init__.py
apex/backend/services/productivity_brain/models.py
apex/backend/services/productivity_brain/parser.py
apex/backend/services/productivity_brain/service.py
apex/backend/services/rate_engine/__init__.py
apex/backend/services/rate_engine/matcher.py
apex/backend/services/takeoff_parser/__init__.py
apex/backend/services/takeoff_parser/parser.py
apex/backend/services/token_tracker.py
apex/backend/services/ws_manager.py
apex/backend/tests/__init__.py
apex/backend/tests/accuracy_scorer.py
apex/backend/tests/test_parallel_agents.py
apex/backend/tests/test_pipeline.py
apex/backend/tests/test_pipeline_e2e.py
apex/backend/tests/validate_decision_system.py
apex/backend/utils/__init__.py
apex/backend/utils/async_helper.py
apex/backend/utils/audit.py
apex/backend/utils/auth.py
apex/backend/utils/csi_utils.py
apex/backend/utils/schemas.py
apex/backend/utils/upload_utils.py
apex/backend/utils/winest_parser.py
apex/frontend/src/App.jsx
apex/frontend/src/components/ChunkedUploader.jsx
apex/frontend/src/components/ErrorBoundary.jsx
apex/frontend/src/components/LLMStatus.jsx
apex/frontend/src/components/Layout.jsx
apex/frontend/src/components/PdfViewer.jsx
apex/frontend/src/components/PipelineStatus.jsx
apex/frontend/src/components/charts/BidComparisonChart.jsx
apex/frontend/src/components/charts/CostBarChart.jsx
apex/frontend/src/components/charts/EstimateCharts.jsx
apex/frontend/src/components/charts/VarianceChart.jsx
apex/frontend/src/components/tabs/AgentLogsTab.jsx
apex/frontend/src/components/tabs/BatchUploadTab.jsx
apex/frontend/src/components/tabs/BenchmarkDashboardTab.jsx
apex/frontend/src/components/tabs/BidComparisonTab.jsx
apex/frontend/src/components/tabs/BidIntelligenceTab.jsx
apex/frontend/src/components/tabs/ChangeOrderTab.jsx
apex/frontend/src/components/tabs/CostTrackingTab.jsx
apex/frontend/src/components/tabs/DecisionEstimateTab.jsx
apex/frontend/src/components/tabs/DocumentsTab.jsx
apex/frontend/src/components/tabs/EstimateLibraryTab.jsx
apex/frontend/src/components/tabs/EstimateTab.jsx
apex/frontend/src/components/tabs/EstimateVersionsTab.jsx
apex/frontend/src/components/tabs/FieldCalibrationTab.jsx
apex/frontend/src/components/tabs/GapReportTab.jsx
apex/frontend/src/components/tabs/IntelligenceReportTab.jsx
apex/frontend/src/components/tabs/LaborTab.jsx
apex/frontend/src/components/tabs/ProductivityBrainTab.jsx
apex/frontend/src/components/tabs/RateIntelligenceTab.jsx
apex/frontend/src/components/tabs/ScheduleTab.jsx
apex/frontend/src/components/tabs/ShadowComparisonTab.jsx
apex/frontend/src/components/tabs/SpecSectionsTab.jsx
apex/frontend/src/components/tabs/SubcontractorPackageTab.jsx
apex/frontend/src/components/tabs/TakeoffTab.jsx
apex/frontend/src/components/tabs/VarianceTab.jsx
apex/frontend/src/context/AuthContext.jsx
apex/frontend/src/main.jsx
apex/frontend/src/pages/AdminPage.jsx
apex/frontend/src/pages/BenchmarkingPage.jsx
apex/frontend/src/pages/ComparePage.jsx
apex/frontend/src/pages/DashboardPage.jsx
apex/frontend/src/pages/FieldActualsPage.jsx
apex/frontend/src/pages/LoginPage.jsx
apex/frontend/src/pages/MaterialsPage.jsx
apex/frontend/src/pages/ProductivityPage.jsx
apex/frontend/src/pages/ProjectDetailPage.jsx
```

## 2. apex/backend/main.py

```python
"""APEX Platform — FastAPI Application Entry Point."""

import asyncio
import os
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load .env before anything else so env vars are available during import
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from apex.backend.config import APEX_DEV_MODE, CORS_ORIGINS, GLOBAL_RATE_LIMIT, LOG_LEVEL
from apex.backend.db.database import init_db
from apex.backend.routers import auth, projects, reports, productivity
from apex.backend.routers import admin as admin_router
from apex.backend.routers import materials as materials_router
from apex.backend.routers import exports
from apex.backend.routers import token_usage as token_usage_router
from apex.backend.routers import test_pipeline as test_pipeline_router
from apex.backend.routers import websocket as ws_router
from apex.backend.routers import bid_comparison as bid_comparison_router
from apex.backend.routers import change_orders as change_orders_router
from apex.backend.routers import material_prices as material_prices_router
from apex.backend.routers import benchmarking as benchmarking_router
from apex.backend.routers import users as users_router
from apex.backend.routers import notifications as notifications_router
from apex.backend.routers import estimate_library as estimate_library_router
from apex.backend.routers import batch_import as batch_import_router
from apex.backend.routers import benchmarks as benchmarks_router
from apex.backend.routers import productivity_brain as productivity_brain_router
from apex.backend.routers import bid_intelligence as bid_intelligence_router
from apex.backend.routers import field_actuals as field_actuals_router
from apex.backend.routers import decision as decision_router
from apex.backend.routers import decision_system as decision_system_router
from apex.backend.services.ws_manager import ws_manager

# Logging — honour LOG_LEVEL env var
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("apex")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting APEX Platform...")
    # Register the running event loop so the sync orchestrator thread can
    # schedule WebSocket broadcasts via asyncio.run_coroutine_threadsafe.
    ws_manager.set_loop(asyncio.get_running_loop())
    init_db()

    # Run seeder if DB is empty
    import sys
    from apex.backend.db.seed import seed_if_empty
    seed_if_empty(force="--force-seed" in sys.argv)

    # Run decision system seeder (Christman historical data)
    try:
        from apex.backend.db.seed_decision_data import run_decision_seed
        run_decision_seed()
    except Exception as _ds_err:
        logger.warning("Decision seed skipped: %s", _ds_err)

    # Ensure upload directory exists
    os.makedirs(os.getenv("UPLOAD_DIR", "./uploads"), exist_ok=True)

    # Clean up any stale chunked-upload temp directories from previous runs
    from apex.backend.routers.projects import cleanup_stale_upload_sessions
    cleanup_stale_upload_sessions()

    # Initialise shared HTTP client pool
    from apex.backend.services.llm_provider import (
        init_http_clients,
        close_http_clients,
        get_llm_provider,
    )
    await init_http_clients()

    # Log active LLM provider
    try:
        provider = get_llm_provider()
        logger.info(f"LLM provider (default): {provider.provider_name} | model: {provider.model_name}")
    except Exception as e:
        logger.warning(f"LLM provider not configured: {e}")

    logger.info("APEX Platform ready.")
    yield
    logger.info("APEX Platform shutting down.")
    await close_http_clients()


limiter = Limiter(key_func=get_remote_address, default_limits=[GLOBAL_RATE_LIMIT])

APEX_VERSION = "0.12.0"

app = FastAPI(
    title="APEX — Automated Project Estimation Exchange",
    description="AI-powered construction estimating platform for general contractors",
    version=APEX_VERSION,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Request ID middleware ──────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# CORS — tighten methods/headers for non-dev
_cors_origins = CORS_ORIGINS
_is_dev = APEX_DEV_MODE
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"] if not _is_dev else ["*"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"] if not _is_dev else ["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(admin_router.router)
app.include_router(projects.router)
app.include_router(reports.router)
app.include_router(productivity.router)
app.include_router(exports.router)
app.include_router(materials_router.router)
app.include_router(token_usage_router.router)
app.include_router(ws_router.router)
app.include_router(bid_comparison_router.router)
app.include_router(change_orders_router.router)
app.include_router(material_prices_router.router)
app.include_router(benchmarking_router.router)
app.include_router(users_router.router)
app.include_router(notifications_router.router)
app.include_router(estimate_library_router.router)
app.include_router(batch_import_router.router)
app.include_router(benchmarks_router.router)
app.include_router(productivity_brain_router.router)
app.include_router(bid_intelligence_router.router)
app.include_router(field_actuals_router.router)
app.include_router(decision_router.router)
app.include_router(decision_system_router.router)

# Dev-only test router — only active when APEX_DEV_MODE=true
if _is_dev:
    app.include_router(test_pipeline_router.router)
    logger.info("Dev mode: test pipeline router mounted at /api/test")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled error [request_id={request_id}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "message": "Internal server error",
            "data": None,
        },
    )


@app.get("/api/health")
def health_check():
    """Health check with database connectivity verification."""
    db_ok = True
    try:
        from sqlalchemy import text
        from apex.backend.db.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "service": "apex-backend",
        "version": APEX_VERSION,
        "database": "connected" if db_ok else "unavailable",
    }


@app.get("/api/health/llm")
async def llm_health_check():
    """Check LLM provider availability per-agent. No auth required.

    Returns:
        default_provider: The resolved default provider + availability.
        agents: Per-agent config (provider, model, api_key_configured).
        providers: Live availability check for each distinct provider in use.
    """
    from apex.backend.services.llm_provider import (
        get_llm_provider,
        get_agent_provider_config,
    )

    # --- Per-agent configuration (no network calls) ---
    agent_config = get_agent_provider_config()

    # --- Default provider resolution ---
    default_info: dict = {}
    try:
        default_provider = get_llm_provider()
        default_available = await default_provider.health_check()
        default_info = {
            "provider": default_provider.provider_name,
            "model": default_provider.model_name,
            "available": default_available,
        }
    except Exception as e:
        default_info = {
            "provider": os.getenv("DEFAULT_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "ollama"),
            "model": "unknown",
            "available": False,
            "error": str(e),
        }

    # --- Live health check for each distinct provider actually in use ---
    used_providers: set[str] = set()
    for cfg in agent_config.values():
        p = cfg.get("provider", "")
        if p not in ("python", ""):
            used_providers.add(p)

    provider_health: dict = {}
    for pname in sorted(used_providers):
        try:
            from apex.backend.services.llm_provider import _build_provider, _default_model_for
            inst = _build_provider(pname, _default_model_for(pname))
            provider_health[pname] = {
                "available": await inst.health_check(),
                "api_key_configured": bool(
                    os.getenv("ANTHROPIC_API_KEY") if pname == "anthropic"
                    else os.getenv("GEMINI_API_KEY") if pname == "gemini"
                    else True
                ),
            }
        except Exception as exc:
            provider_health[pname] = {
                "available": False,
                "api_key_configured": False,
                "error": str(exc),
            }

    return {
        "default_provider": default_info,
        "agents": agent_config,
        "providers": provider_health,
    }


# ── Static file serving (production) ─────────────────────────────
# Serve the Vite-built frontend from apex/frontend/dist/ when it exists.
# This must be registered AFTER all API routes so /api/* takes priority.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    # Serve static assets (JS, CSS, images) at /assets/
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="frontend-assets")

    # SPA fallback: any non-API route returns index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = _frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
```

## 3. apex/backend/models/__init__.py

```python
from apex.backend.models.user import User
from apex.backend.models.organization import Organization
from apex.backend.models.project import Project
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.productivity_history import ProductivityHistory
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.upload_session import UploadSession
from apex.backend.models.upload_chunk import UploadChunk
from apex.backend.models.token_usage import TokenUsage
from apex.backend.models.bid_comparison import BidComparison
from apex.backend.models.equipment_rate import EquipmentRate
from apex.backend.models.change_order import ChangeOrder
from apex.backend.models.audit_log import AuditLog
from apex.backend.models.estimate_library import EstimateLibraryEntry, EstimateLibraryTag
from apex.backend.models.historical_line_item import HistoricalLineItem
from apex.backend.models.document_association import DocumentGroup, DocumentAssociation
from apex.backend.models.productivity_benchmark import ProductivityBenchmark
from apex.backend.services.productivity_brain.models import PBProject, PBLineItem
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.field_actuals import FieldActualsProject, FieldActualsLineItem
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.services.bid_intelligence.models import BIEstimate
from apex.backend.models.decision_models import (
    ComparableProject,
    HistoricalRateObservation,
    CanonicalActivity,
    ActivityAlias,
    EstimateRun,
    SourceReference,
    ScopeItem,
    ScopeItemEvidence,
    QuantityItem,
    BenchmarkResult,
    EstimateLine,
    CostBreakdownBucket,
    RiskItem,
    EscalationInput,
    ScheduleScenario,
    EstimatorOverride,
    BidOutcome,
    FieldActual,
)

__all__ = [
    "User", "Organization", "Project", "Document", "SpecSection",
    "GapReport", "GapReportItem", "TakeoffItem", "LaborEstimate",
    "MaterialPrice", "Estimate", "EstimateLineItem", "ProjectActual",
    "ProductivityHistory", "AgentRunLog",
    "UploadSession", "UploadChunk", "TokenUsage", "BidComparison", "EquipmentRate", "ChangeOrder", "AuditLog",
    "EstimateLibraryEntry", "EstimateLibraryTag",
    "HistoricalLineItem",
    "DocumentGroup", "DocumentAssociation",
    "ProductivityBenchmark",
    "PBProject", "PBLineItem",
    "BIEstimate",
    "TakeoffItemV2",
    "FieldActualsProject", "FieldActualsLineItem",
    "IntelligenceReportModel",
    # Decision system models
    "ComparableProject", "HistoricalRateObservation", "CanonicalActivity",
    "ActivityAlias", "EstimateRun", "SourceReference", "ScopeItem",
    "ScopeItemEvidence", "QuantityItem", "BenchmarkResult", "EstimateLine",
    "CostBreakdownBucket", "RiskItem", "EscalationInput", "ScheduleScenario",
    "EstimatorOverride", "BidOutcome", "FieldActual",
]
```

## 4. apex/backend/services/agent_orchestrator.py

```python
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
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.project import Project
from apex.backend.models.token_usage import TokenUsage

logger = logging.getLogger("apex.orchestrator")

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
```

## 5. apex/backend/agents/agent_4_takeoff.py (first 150 lines)

> Note: The requested file `agent_4_rate_engine.py` does not exist. The actual Agent 4 file is `agent_4_takeoff.py`.

```python
"""Agent 4 — Rate Recommendation Engine (v2)

Takes the estimator's uploaded takeoff (WinEst .xlsx or CSV) and matches
each line item against Productivity Brain historical data. Produces rate
recommendations with deviation flags.

NO LLM. NO QUANTITY GENERATION. ALL MATH IS DETERMINISTIC PYTHON.

Inputs:
  - Uploaded takeoff file(s) on the project (detected by classification)
  - Productivity Brain data in the database

Outputs:
  - TakeoffItemV2 rows saved to DB with rate recommendations
  - Agent4Output contract

Flow:
  1. Find uploaded takeoff document(s) for this project
  2. Parse using takeoff_parser
  3. Match against PB using rate_engine
  4. Save TakeoffItemV2 rows with recommendations
  5. Return Agent4Output
"""

import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.models.document import Document
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.services.takeoff_parser.parser import parse_takeoff
from apex.backend.services.rate_engine.matcher import RateMatchingEngine

logger = logging.getLogger("apex.agent.takeoff")


# ---------------------------------------------------------------------------
# Main agent entry point (v2)
# ---------------------------------------------------------------------------

def run_takeoff_agent(db: Session, project_id: int) -> dict:
    """Match estimator takeoff against Productivity Brain historical rates.

    1. Find the most recent takeoff/xlsx/csv document for this project.
    2. Parse it into TakeoffLineItem list via takeoff_parser.
    3. Match against PB data via RateMatchingEngine.
    4. Save TakeoffItemV2 rows (clean slate per run).
    5. Return validated Agent4Output.
    """
    # ── Step 1: Find takeoff document ────────────────────────────────────
    doc = _find_takeoff_document(db, project_id)

    if doc is None:
        logger.info(
            "Agent 4: no takeoff file found for project %d — returning empty output",
            project_id,
        )
        return validate_agent_output(4, {
            "takeoff_items_parsed": 0,
            "items_matched": 0,
            "items_unmatched": 0,
            "recommendations": [],
            "flags_summary": {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0},
            "parse_format": None,
            "overall_optimism_score": None,
        })

    # ── Step 2: Parse takeoff file ───────────────────────────────────────
    logger.info("Agent 4: parsing takeoff file %s (doc_id=%d)", doc.filename, doc.id)
    items, fmt = parse_takeoff(doc.file_path)
    logger.info("Agent 4: parsed %d line items (format=%s)", len(items), fmt)

    if not items:
        logger.warning("Agent 4: parser returned 0 items from %s", doc.filename)
        return validate_agent_output(4, {
            "takeoff_items_parsed": 0,
            "items_matched": 0,
            "items_unmatched": 0,
            "recommendations": [],
            "flags_summary": {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0},
            "parse_format": fmt,
            "overall_optimism_score": None,
        })

    # ── Step 3: Match against PB historical data ─────────────────────────
    engine = RateMatchingEngine(db)
    recommendations = engine.match_all(items)
    optimism = engine.compute_optimism_score(recommendations)
    flags = engine.flags_summary(recommendations)

    items_matched = sum(1 for r in recommendations if r.flag not in ("NO_DATA",))
    items_unmatched = sum(1 for r in recommendations if r.flag == "NO_DATA")

    logger.info(
        "Agent 4: %d matched, %d unmatched, optimism=%.2f%%",
        items_matched,
        items_unmatched,
        optimism if optimism is not None else 0.0,
    )

    # ── Step 4: Save TakeoffItemV2 rows (clean slate) ────────────────────
    db.query(TakeoffItemV2).filter(
        TakeoffItemV2.project_id == project_id,
    ).delete(synchronize_session="fetch")

    for rec in recommendations:
        row = TakeoffItemV2(
            project_id=project_id,
            row_number=rec.line_item_row,
            wbs_area=rec.wbs_area,
            activity=rec.activity,
            quantity=rec.estimator_rate,  # estimator's production rate stored as reference
            unit=rec.unit,
            crew=rec.crew,
            production_rate=rec.estimator_rate,
            labor_cost_per_unit=rec.labor_cost_per_unit,
            material_cost_per_unit=rec.material_cost_per_unit,
            historical_avg_rate=rec.historical_avg_rate,
            historical_min_rate=rec.historical_min_rate,
            historical_max_rate=rec.historical_max_rate,
            sample_count=rec.sample_count,
            confidence=rec.confidence,
            delta_pct=rec.delta_pct,
            flag=rec.flag,
            matching_projects=json.dumps(rec.matching_projects) if rec.matching_projects else None,
        )
        db.add(row)

    db.commit()
    logger.info("Agent 4: saved %d TakeoffItemV2 rows for project %d", len(recommendations), project_id)

    # ── Step 5: Return validated output ──────────────────────────────────
    return validate_agent_output(4, {
        "takeoff_items_parsed": len(items),
        "items_matched": items_matched,
        "items_unmatched": items_unmatched,
        "recommendations": [r.model_dump() for r in recommendations],
        "flags_summary": flags,
        "parse_format": fmt,
        "overall_optimism_score": optimism,
    })


def _find_takeoff_document(db: Session, project_id: int) -> Optional[Document]:
    """Find the most recent takeoff document for a project.
```

## 6. apex/backend/services/productivity_brain/service.py (first 150 lines)

```python
"""Business logic layer for Productivity Brain."""

from difflib import SequenceMatcher

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.services.productivity_brain.models import PBProject, PBLineItem
from apex.backend.services.productivity_brain.parser import (
    compute_file_hash, detect_format,
    parse_26col, parse_21col, parse_averaged_rates,
)

_PARSERS = {
    "26col_civil": parse_26col,
    "21col_estimate": parse_21col,
    "averaged_rates": parse_averaged_rates,
}


class ProductivityBrainService:
    def __init__(self, db: Session):
        self.db = db

    # ── Ingestion ──

    def ingest_file(self, filepath: str, filename: str) -> dict:
        """Ingest a single file. Returns summary dict."""
        fhash = compute_file_hash(filepath)

        # Dedup by hash
        existing = self.db.query(PBProject).filter_by(file_hash=fhash).first()
        if existing:
            return {
                "status": "skipped",
                "reason": "duplicate",
                "project_id": existing.id,
                "name": existing.name,
            }

        fmt = detect_format(filepath)
        if fmt == "unknown":
            return {"status": "error", "reason": f"unknown format: {filename}"}

        parser = _PARSERS[fmt]
        rows = parser(filepath)

        project = PBProject(
            name=filename,
            source_file=filename,
            file_hash=fhash,
            format_type=fmt,
            project_count=1 if fmt != "averaged_rates" else self._count_projects(rows),
            total_line_items=len(rows),
        )
        self.db.add(project)
        self.db.flush()  # get project.id

        for row in rows:
            item = PBLineItem(project_id=project.id, **row)
            self.db.add(item)

        self.db.commit()

        return {
            "status": "ingested",
            "project_id": project.id,
            "name": project.name,
            "format": fmt,
            "line_items": len(rows),
        }

    def batch_ingest(self, filepaths: list[tuple[str, str]]) -> list[dict]:
        """Ingest multiple files. Each tuple is (filepath, filename)."""
        return [self.ingest_file(fp, fn) for fp, fn in filepaths]

    # ── Querying ──

    def get_rates(
        self,
        activity: str | None = None,
        wbs: str | None = None,
        unit: str | None = None,
    ) -> list[dict]:
        """Averaged rates grouped by activity+unit. All math is deterministic Python."""
        q = self.db.query(
            PBLineItem.activity,
            PBLineItem.unit,
            func.count(PBLineItem.id).label("occurrences"),
            func.count(func.distinct(PBLineItem.project_id)).label("project_count"),
            func.avg(PBLineItem.production_rate).label("avg_rate"),
            func.min(PBLineItem.production_rate).label("min_rate"),
            func.max(PBLineItem.production_rate).label("max_rate"),
            func.avg(PBLineItem.labor_cost_per_unit).label("avg_labor_cost"),
            func.avg(PBLineItem.material_cost_per_unit).label("avg_material_cost"),
        ).filter(
            PBLineItem.production_rate.isnot(None),
        )

        if activity:
            q = q.filter(PBLineItem.activity.ilike(f"%{activity}%"))
        if wbs:
            q = q.filter(PBLineItem.wbs_area.ilike(f"%{wbs}%"))
        if unit:
            q = q.filter(PBLineItem.unit == unit)

        q = q.group_by(PBLineItem.activity, PBLineItem.unit)
        q = q.order_by(PBLineItem.activity)

        return [
            {
                "activity": r.activity,
                "unit": r.unit,
                "occurrences": r.occurrences,
                "project_count": r.project_count,
                "avg_rate": round(r.avg_rate, 2) if r.avg_rate else None,
                "min_rate": round(r.min_rate, 2) if r.min_rate else None,
                "max_rate": round(r.max_rate, 2) if r.max_rate else None,
                "avg_labor_cost_per_unit": round(r.avg_labor_cost, 2) if r.avg_labor_cost else None,
                "avg_material_cost_per_unit": round(r.avg_material_cost, 2) if r.avg_material_cost else None,
            }
            for r in q.all()
        ]

    def compare_estimate(self, estimate_items: list[dict]) -> list[dict]:
        """Compare line items against historical averages.

        Each input dict needs: activity, production_rate.
        Returns items with historical_avg, delta_pct, flag.
        All percentages computed in deterministic Python.
        """
        results = []
        for item in estimate_items:
            activity = item.get("activity", "")
            current_rate = item.get("production_rate")

            hist = self.db.query(
                func.avg(PBLineItem.production_rate).label("avg"),
                func.count(PBLineItem.id).label("cnt"),
            ).filter(
                PBLineItem.activity == activity,
                PBLineItem.production_rate.isnot(None),
            ).first()

            if hist and hist.cnt > 0 and current_rate:
                avg = round(hist.avg, 2)
                delta_pct = round(((avg - current_rate) / current_rate) * 100, 1) if current_rate != 0 else 0.0

                if abs(delta_pct) < 5:
                    flag = "OK"
```

## 7. apex/backend/services/llm_provider.py

```python
"""LLM Provider abstraction layer.

Supports Ollama (local), Anthropic Claude API, OpenRouter (Anthropic Messages API
for Claude models, OpenAI Chat Completions API for non-Claude models like Gemini),
and Google Gemini API via a unified interface.  Provider selection uses a three-level fallback chain:

  1. Per-agent env vars  → AGENT_{N}_PROVIDER / AGENT_{N}_MODEL
     (or AGENT_{N}_{SUFFIX}_PROVIDER for sub-roles like AGENT_6_SUMMARY)
  2. Default env vars    → DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL
  3. Legacy env var      → LLM_PROVIDER (backwards-compatible)
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("apex.llm_provider")

# ---------------------------------------------------------------------------
# Shared HTTP client pool
# ---------------------------------------------------------------------------

_clients: dict = {}
_health_cache: dict = {}
_health_cache_ttl = 60  # seconds


async def init_http_clients() -> None:
    """Create shared httpx clients. Call on app startup."""
    _clients["anthropic"] = httpx.AsyncClient(
        base_url="https://api.anthropic.com",
        timeout=httpx.Timeout(300.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    _clients["google"] = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com",
        timeout=httpx.Timeout(300.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    _clients["openrouter"] = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        timeout=httpx.Timeout(300.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


async def close_http_clients() -> None:
    """Close all shared httpx clients. Call on app shutdown."""
    for client in _clients.values():
        try:
            await client.aclose()
        except (RuntimeError, httpx.TransportError):
            logger.debug("Client already closed during shutdown (expected)")
    _clients.clear()


def get_http_client(provider: str) -> httpx.AsyncClient:
    return _clients.get(provider)

# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    content: str            # The text response
    model: str              # Which model was used
    provider: str           # "ollama", "anthropic", or "gemini"
    input_tokens: int       # Token usage (0 if unavailable)
    output_tokens: int      # Token usage (0 if unavailable)
    duration_ms: float      # Wall clock time for the call
    cache_creation_input_tokens: int = 0  # Anthropic: tokens written to cache
    cache_read_input_tokens: int = 0      # Anthropic: tokens read from cache
    finish_reason: str = ""               # "STOP", "MAX_TOKENS", etc.


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a prompt and get a text response."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._model = model or os.getenv("OLLAMA_MODEL", "llama3.2")

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000
        content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="ollama",
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            duration_ms=duration_ms,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
    ):
        self._api_key = api_key
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._base_url = "https://api.anthropic.com/v1"

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._base_url}/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        start = time.monotonic()
        _pooled = get_http_client("anthropic")
        if _pooled is not None:
            resp = await _pooled.post("/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        else:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000
        content = data["content"][0]["text"]
        usage = data.get("usage", {})

        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        if cache_read > 0:
            logger.info("Cache HIT: %d tokens read from cache", cache_read)
        elif cache_creation > 0:
            logger.info("Cache CREATED: %d tokens written to cache", cache_creation)
        else:
            logger.info("Cache MISS: no cache interaction (model=%s)", self._model)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="anthropic",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=duration_ms,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

    async def health_check(self) -> bool:
        """Check if Anthropic API is reachable with the configured key."""
        cached = _health_cache.get("anthropic")
        if cached:
            ts, result = cached
            if time.monotonic() - ts < _health_cache_ttl:
                return result
        try:
            url = f"{self._base_url}/messages"
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self._model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            _pooled = get_http_client("anthropic")
            if _pooled is not None:
                resp = await _pooled.post("/v1/messages", json=payload, headers=headers)
                is_healthy = resp.status_code == 200
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    is_healthy = resp.status_code == 200
            _health_cache["anthropic"] = (time.monotonic(), is_healthy)
            return is_healthy
        except Exception:
            _health_cache["anthropic"] = (time.monotonic(), False)
            return False


# ---------------------------------------------------------------------------
# OpenRouter (Anthropic-compatible proxy)
# ---------------------------------------------------------------------------

class OpenRouterProvider(AnthropicProvider):
    """Route requests through OpenRouter.

    Uses Anthropic Messages API (/messages) for Claude models (with prompt
    caching) and OpenAI Chat Completions API (/chat/completions) for all
    other models (Gemini, Llama, etc.).
    """

    def __init__(self, api_key: str, model: Optional[str] = None):
        super().__init__(api_key=api_key.strip(), model=model)
        self._base_url = "https://openrouter.ai/api/v1"
        logger.info("OpenRouter API key loaded: %d chars", len(self._api_key))

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def _is_anthropic_model(self) -> bool:
        """Return True if the model should use Anthropic Messages API format."""
        model_lower = self._model.lower()
        return "claude" in model_lower or "anthropic" in model_lower

    # -- Override complete() to pick the right API format ------------------

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self._is_anthropic_model():
            return await self._complete_messages(
                system_prompt, user_prompt, temperature, max_tokens,
            )
        return await self._complete_chat(
            system_prompt, user_prompt, temperature, max_tokens,
        )

    # -- Anthropic Messages API path (Claude models) -----------------------

    async def _complete_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Anthropic Messages format — used for Claude models via OpenRouter."""
        logger.info("OpenRouter: using messages format for model %s", self._model)
        url = f"{self._base_url}/messages"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
            "HTTP-Referer": "https://github.com/tdye19/EstimatingEngine",
            "X-Title": "APEX Estimating Engine",
        }
        logger.debug(
            "OpenRouter auth header present: %s, key prefix: %s...",
            bool(headers.get("Authorization")),
            self._api_key[:8],
        )
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        start = time.monotonic()
        _pooled = get_http_client("openrouter")
        if _pooled is not None:
            try:
                resp = await _pooled.post("/messages", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.TransportError, RuntimeError) as exc:
                logger.warning(
                    "OpenRouter pooled client error (%s) — creating fresh client for this request",
                    exc,
                )
                fresh = httpx.AsyncClient(timeout=300.0)
                try:
                    resp = await fresh.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                finally:
                    await fresh.aclose()
        else:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000
        content = data["content"][0]["text"]
        usage = data.get("usage", {})

        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        if cache_read > 0:
            logger.info("Cache HIT: %d tokens read from cache (openrouter)", cache_read)
        elif cache_creation > 0:
            logger.info("Cache CREATED: %d tokens written to cache (openrouter)", cache_creation)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="openrouter",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=duration_ms,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

    # -- OpenAI Chat Completions API path (Gemini, Llama, etc.) ------------

    async def _complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """OpenAI Chat Completions format — used for non-Claude models via OpenRouter."""
        logger.info("OpenRouter: using chat/completions format for model %s", self._model)
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/tdye19/EstimatingEngine",
            "X-Title": "APEX Estimating Engine",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        start = time.monotonic()
        _pooled = get_http_client("openrouter")
        if _pooled is not None:
            try:
                resp = await _pooled.post("/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.TransportError, RuntimeError) as exc:
                logger.warning(
                    "OpenRouter pooled client error (%s) — creating fresh client for this request",
                    exc,
                )
                fresh = httpx.AsyncClient(timeout=300.0)
                try:
                    resp = await fresh.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                finally:
                    await fresh.aclose()
        else:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000

        # OpenAI Chat Completions response format
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"OpenRouter chat/completions returned no choices: {data}")
        content = choices[0]["message"]["content"]
        finish_reason = choices[0].get("finish_reason", "unknown")

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="openrouter",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            finish_reason=finish_reason,
        )

    async def health_check(self) -> bool:
        """Ping OpenRouter models endpoint (public, no auth required)."""
        cached = _health_cache.get("openrouter")
        if cached:
            ts, result = cached
            if time.monotonic() - ts < _health_cache_ttl:
                return result
        try:
            _pooled = get_http_client("openrouter")
            if _pooled is not None:
                try:
                    resp = await _pooled.get("/models")
                    is_healthy = resp.status_code == 200
                except (httpx.TransportError, RuntimeError):
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get("https://openrouter.ai/api/v1/models")
                        is_healthy = resp.status_code == 200
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get("https://openrouter.ai/api/v1/models")
                    is_healthy = resp.status_code == 200
            _health_cache["openrouter"] = (time.monotonic(), is_healthy)
            return is_healthy
        except Exception:
            _health_cache["openrouter"] = (time.monotonic(), False)
            return False


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini via REST API (generateContent endpoint).

    Docs: https://ai.google.dev/api/generate-content
    Auth: API key passed as query param ?key={GEMINI_API_KEY}
    """

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
    ):
        self._api_key = api_key
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._BASE_URL}/{self._model}:generateContent"
        params = {"key": self._api_key}
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        start = time.monotonic()
        _pooled = get_http_client("google")
        if _pooled is not None:
            try:
                resp = await _pooled.post(
                    f"/v1beta/models/{self._model}:generateContent",
                    json=payload,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.TransportError, RuntimeError) as exc:
                logger.warning(
                    "Gemini pooled client transport closed — creating fresh client for this request"
                )
                fresh = httpx.AsyncClient(timeout=300.0)
                try:
                    resp = await fresh.post(url, json=payload, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                finally:
                    await fresh.aclose()
        else:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, params=params)
                resp.raise_for_status()
                data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000

        # Extract text from first candidate
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates: {data}")
        content = candidates[0]["content"]["parts"][0]["text"]
        finish_reason = candidates[0].get("finishReason", "unknown")

        # Token usage
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="gemini",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            finish_reason=finish_reason,
        )

    async def health_check(self) -> bool:
        """Ping the model list endpoint to verify key validity."""
        cached = _health_cache.get("gemini")
        if cached:
            ts, result = cached
            if time.monotonic() - ts < _health_cache_ttl:
                return result
        try:
            url = f"{self._BASE_URL}/{self._model}:generateContent"
            params = {"key": self._api_key}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5},
            }
            _pooled = get_http_client("google")
            if _pooled is not None:
                resp = await _pooled.post(
                    f"/v1beta/models/{self._model}:generateContent",
                    json=payload,
                    params=params,
                )
                is_healthy = resp.status_code == 200
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload, params=params)
                    is_healthy = resp.status_code == 200
            _health_cache["gemini"] = (time.monotonic(), is_healthy)
            return is_healthy
        except Exception:
            _health_cache["gemini"] = (time.monotonic(), False)
            return False


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build_provider(provider_name: str, model: Optional[str]) -> LLMProvider:
    """Instantiate a provider by name, injecting the correct API key."""
    name = provider_name.lower()
    if name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when provider=anthropic")
        return AnthropicProvider(api_key=api_key, model=model)
    elif name == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required when provider=openrouter")
        return OpenRouterProvider(api_key=api_key, model=model)
    elif name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when provider=gemini")
        return GeminiProvider(api_key=api_key, model=model)
    elif name == "ollama":
        return OllamaProvider(model=model)
    else:
        raise ValueError(f"Unknown LLM provider: '{provider_name}'. Valid: anthropic, openrouter, gemini, ollama")


# ---------------------------------------------------------------------------
# Public factory — three-level fallback chain
# ---------------------------------------------------------------------------

def get_llm_provider(
    agent_number: Optional[int] = None,
    suffix: Optional[str] = None,
) -> LLMProvider:
    """Return the configured LLM provider using a three-level fallback chain.

    Level 1 — Per-agent config (most specific):
        AGENT_{N}_PROVIDER / AGENT_{N}_MODEL
        or AGENT_{N}_{SUFFIX}_PROVIDER / AGENT_{N}_{SUFFIX}_MODEL
        when suffix is provided (e.g. suffix="SUMMARY" for Agent 6).

    Level 2 — Default config:
        DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL

    Level 3 — Legacy backwards-compatible config:
        LLM_PROVIDER  (defaults to "ollama" if unset)

    Args:
        agent_number: Optional agent number (1-7). When provided, checks for
                      per-agent env vars before falling back.
        suffix:       Optional sub-role suffix, e.g. "SUMMARY" for the
                      AGENT_6_SUMMARY_PROVIDER / AGENT_6_SUMMARY_MODEL pair.
    """

    # --- Level 1: per-agent ---
    if agent_number is not None:
        if suffix:
            env_prefix = f"AGENT_{agent_number}_{suffix.upper()}"
        else:
            env_prefix = f"AGENT_{agent_number}"

        agent_provider = os.getenv(f"{env_prefix}_PROVIDER")
        agent_model = os.getenv(f"{env_prefix}_MODEL")

        if agent_provider:
            logger.debug(
                "Agent %d%s → provider=%s model=%s (per-agent config)",
                agent_number,
                f"/{suffix}" if suffix else "",
                agent_provider,
                agent_model or "(default for provider)",
            )
            return _build_provider(agent_provider, agent_model)

    # --- Level 2: default ---
    default_provider = os.getenv("DEFAULT_LLM_PROVIDER")
    default_model = os.getenv("DEFAULT_LLM_MODEL")
    if default_provider:
        logger.debug(
            "Agent %s → provider=%s model=%s (DEFAULT_LLM_PROVIDER)",
            agent_number or "?",
            default_provider,
            default_model or "(default for provider)",
        )
        return _build_provider(default_provider, default_model)

    # --- Level 3: legacy ---
    legacy_provider = os.getenv("LLM_PROVIDER", "ollama")
    logger.debug(
        "Agent %s → provider=%s (LLM_PROVIDER legacy fallback)",
        agent_number or "?",
        legacy_provider,
    )
    return _build_provider(legacy_provider, None)


# ---------------------------------------------------------------------------
# Introspection helpers (used by /api/health/llm)
# ---------------------------------------------------------------------------

# Canonical agent roster for health reporting.
# Each entry: (agent_number, suffix_or_None, label, description)
AGENT_PROVIDER_ROSTER = [
    (1,  None,      "agent_1_ingestion",          "Document Ingestion (Python only)"),
    (2,  None,      "agent_2_spec_parser",         "Spec Parser"),
    (3,  None,      "agent_3_scope_analysis",      "Scope Analysis"),
    (4,  None,      "agent_4_rate_intelligence",   "Rate Intelligence (Python only)"),
    (5,  None,      "agent_5_field_calibration",   "Field Calibration (Python only)"),
    (6,  "SUMMARY", "agent_6_intelligence_report", "Intelligence Report — Executive Narrative"),
    (7,  None,      "agent_7_improve",             "IMPROVE Feedback"),
]


def get_agent_provider_config() -> dict:
    """Return a dict describing each agent's resolved provider config.

    Does NOT instantiate providers or make network calls — purely reads env vars.
    Used by the /api/health/llm endpoint.
    """
    result = {}

    for agent_number, suffix, label, description in AGENT_PROVIDER_ROSTER:
        # Agent 1 is always pure Python
        if agent_number == 1:
            result[label] = {
                "description": description,
                "provider": "python",
                "model": None,
                "source": "hardcoded",
                "api_key_configured": True,
            }
            continue

        if suffix:
            env_prefix = f"AGENT_{agent_number}_{suffix}"
        else:
            env_prefix = f"AGENT_{agent_number}"

        agent_provider = os.getenv(f"{env_prefix}_PROVIDER")
        agent_model = os.getenv(f"{env_prefix}_MODEL")

        if agent_provider:
            source = f"{env_prefix}_PROVIDER"
            provider = agent_provider.lower()
            model = agent_model
        else:
            default_provider = os.getenv("DEFAULT_LLM_PROVIDER")
            if default_provider:
                source = "DEFAULT_LLM_PROVIDER"
                provider = default_provider.lower()
                model = os.getenv("DEFAULT_LLM_MODEL")
            else:
                source = "LLM_PROVIDER (legacy)"
                provider = os.getenv("LLM_PROVIDER", "ollama").lower()
                model = None

        # Determine if the required API key is present
        api_key_configured = _api_key_is_set(provider)

        result[label] = {
            "description": description,
            "provider": provider,
            "model": model or _default_model_for(provider),
            "source": source,
            "api_key_configured": api_key_configured,
        }

    return result


def _api_key_is_set(provider: str) -> bool:
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    elif provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    elif provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    else:  # ollama / python
        return True


def _default_model_for(provider: str) -> str:
    defaults = {
        "anthropic": "claude-sonnet-4-6",
        "openrouter": "claude-sonnet-4-6",
        "gemini": "gemini-2.5-flash",
        "ollama": "llama3.2",
    }
    return defaults.get(provider, "unknown")
```

## 8. apex/backend/routers/projects.py (first 150 lines)

```python
"""Project management router."""

import math
import os
import shutil
import time
import uuid
from pathlib import Path
import csv
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, BackgroundTasks, Query
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.project import Project
from apex.backend.models.document import Document
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.upload_session import UploadSession
from apex.backend.models.upload_chunk import UploadChunk
from apex.backend.models.user import User
from apex.backend.services.crew_orchestrator import get_orchestrator
from apex.backend.utils.auth import require_auth, get_authorized_project, get_current_user, SECRET_KEY, ALGORITHM
from apex.backend.utils.schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut, DocumentOut, APIResponse,
    PipelineStatusOut, AgentStepStatus, ChunkedUploadInitRequest,
    ShadowComparisonOut,
)

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_auth)])

from slowapi import Limiter
from slowapi.util import get_remote_address
from apex.backend.config import (
    UPLOAD_DIR, CHUNK_SIZE, SESSION_TTL, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS,
    PIPELINE_RATE_LIMIT,
)
_limiter = Limiter(key_func=get_remote_address)
from apex.backend.utils.upload_utils import get_chunk_path, assemble_chunks, cleanup_chunks

def cleanup_stale_upload_sessions() -> None:
    """Remove upload sessions and temp dirs older than SESSION_TTL. Call on startup."""
    now = datetime.utcnow()
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    try:
        expired_sessions = (
            db.query(UploadSession)
            .filter(UploadSession.expires_at < now)
            .all()
        )
        for session in expired_sessions:
            cleanup_chunks(session.upload_id)
            db.delete(session)
        db.commit()
    finally:
        db.close()

    # Also remove old tmp dirs on disk from previous server runs.
    tmp_root = os.path.join(UPLOAD_DIR, "tmp")
    if os.path.isdir(tmp_root):
        for entry in os.scandir(tmp_root):
            if entry.is_dir():
                age = time.time() - entry.stat().st_mtime
                if age > SESSION_TTL:
                    shutil.rmtree(entry.path, ignore_errors=True)


def _generate_project_number(db: Session) -> str:
    year = datetime.now().year
    prefix = f"PRJ-{year}-"
    from sqlalchemy import func
    max_num = (
        db.query(func.max(Project.project_number))
        .filter(Project.project_number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num:
        last_seq = int(max_num.replace(prefix, ""))
    else:
        last_seq = 0
    return f"{prefix}{last_seq + 1:03d}"


@router.post("", response_model=APIResponse)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    project_number = data.project_number or _generate_project_number(db)

    existing = db.query(Project).filter(Project.project_number == project_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project number already exists")

    mode = data.mode if data.mode in ("shadow", "production") else "shadow"
    project = Project(
        name=data.name,
        project_number=project_number,
        project_type=data.project_type,
        mode=mode,
        description=data.description,
        location=data.location,
        square_footage=data.square_footage,
        estimated_value=data.estimated_value,
        bid_date=data.bid_date,
        owner_id=user.id,
        organization_id=user.organization_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return APIResponse(
        success=True,
        message="Project created",
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.get("", response_model=APIResponse)
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    query = db.query(Project).filter(
        Project.is_deleted == False,  # noqa: E712
        Project.owner_id == user.id,
    ).order_by(Project.id.desc())
    total = query.count()
    projects = query.offset(skip).limit(min(limit, 200)).all()
    return APIResponse(
        success=True,
        data=[ProjectOut.model_validate(p).model_dump(mode="json") for p in projects],
        message=f"{total} projects total",
    )


@router.get("/{project_id}", response_model=APIResponse)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    project = get_authorized_project(project_id, user, db)
    return APIResponse(
        success=True,
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.put("/{project_id}", response_model=APIResponse)
```

## 9. apex/backend/agents/pipeline_contracts.py

```python
"""Pipeline data contracts — Pydantic models for each agent's validated output.

Each agent validates its return dict against these contracts before returning.
If validation fails, a ContractViolation is raised with the agent name and details.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ContractViolation(Exception):
    """Raised when an agent's output fails contract validation."""

    def __init__(self, agent_name: str, detail: str):
        self.agent_name = agent_name
        self.detail = detail
        super().__init__(f"Contract violation in {agent_name}: {detail}")


# ---------------------------------------------------------------------------
# Agent 1 — Document Ingestion
# ---------------------------------------------------------------------------

class Agent1DocResult(BaseModel):
    document_id: int
    filename: str
    status: str
    classification: Optional[str] = None
    pages: Optional[int] = None
    chars: Optional[int] = None
    error: Optional[str] = None
    winest_format: Optional[str] = None   # "est_native" | "xlsx_format1" | "xlsx_format2" | None


class Agent1Output(BaseModel):
    documents_processed: int = Field(ge=0)
    total_documents: int = Field(ge=0)
    results: list[Agent1DocResult] = []
    pipeline_mode: Optional[str] = None         # "spec" or "winest_import"
    winest_line_items: Optional[list] = None     # populated when pipeline_mode == "winest_import"


# ---------------------------------------------------------------------------
# Agent 2 — Spec Parser (v2: parameter extraction, no quantities)
# ---------------------------------------------------------------------------

class SpecParameter(BaseModel):
    """A single spec section with extracted material parameters."""
    division: str                                       # CSI division e.g. "03"
    section_number: str                                 # full CSI e.g. "03 30 00"
    section_title: str
    in_scope: bool = True
    material_specs: dict = Field(default_factory=dict)  # division-specific params
    quality_requirements: list[str] = []
    submittals_required: list[str] = []
    referenced_standards: list[str] = []                # ACI, ASTM, CRSI codes


class Agent2ParsedOutput(BaseModel):
    """Schema for LLM response across all chunks (merged)."""
    sections: list[SpecParameter] = []
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    spec_date: Optional[str] = None


class Agent2DocResult(BaseModel):
    document_id: int
    filename: str
    sections_found: int = Field(ge=0)
    parse_method: str
    status: str
    error: Optional[str] = None


class Agent2Output(BaseModel):
    sections_parsed: int = Field(ge=0)
    documents_processed: int = Field(ge=0)
    parse_method: str
    results: list[Agent2DocResult] = []


# ---------------------------------------------------------------------------
# Agent 3 — Gap Analysis
# ---------------------------------------------------------------------------

class Agent3Output(BaseModel):
    total_gaps: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    moderate_count: int = Field(ge=0)
    watch_count: int = Field(ge=0)
    overall_score: Optional[float] = None
    report_id: int
    sections_analyzed: int = Field(ge=0)
    spec_vs_takeoff_gaps: int = 0   # count of spec-vs-takeoff cross-reference gaps


# ---------------------------------------------------------------------------
# Agent 4 — Rate Recommendation Engine (v2)
# ---------------------------------------------------------------------------

# DEPRECATED — v1 only
class Agent4SectionResult_V1(BaseModel):
    section_id: Optional[int] = None   # None for gap-derived items with no matching section
    section_number: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    drawings: Optional[list] = None
    source: Optional[str] = None       # "specified" or "estimated" (LLM path only)
    error: Optional[str] = None


class TakeoffLineItem(BaseModel):
    """Single line item parsed from estimator's uploaded takeoff."""
    row_number: int
    wbs_area: Optional[str] = None
    activity: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    crew: Optional[str] = None
    production_rate: Optional[float] = None
    labor_cost_per_unit: Optional[float] = None
    material_cost_per_unit: Optional[float] = None
    csi_code: Optional[str] = None


class RateRecommendation(BaseModel):
    """Rate intelligence for a single takeoff line item."""
    line_item_row: int
    activity: str
    unit: Optional[str] = None
    crew: Optional[str] = None
    estimator_rate: Optional[float] = None
    historical_avg_rate: Optional[float] = None
    historical_min_rate: Optional[float] = None
    historical_max_rate: Optional[float] = None
    historical_spread: Optional[float] = None
    sample_count: int = 0
    confidence: str = "none"  # "high" (n>=10), "medium" (5-9), "low" (1-4), "none" (0)
    delta_pct: Optional[float] = None  # positive = optimistic vs history, negative = conservative
    flag: str = "NO_DATA"  # "OK" (<5%), "REVIEW" (5-20%), "UPDATE" (>20%), "NO_DATA", "NEEDS_RATE"
    matching_projects: list[str] = []
    labor_cost_per_unit: Optional[float] = None
    material_cost_per_unit: Optional[float] = None
    wbs_area: Optional[str] = None


class Agent4Output(BaseModel):
    """Agent 4 v2 — Rate Recommendation Engine output."""
    takeoff_items_parsed: int = Field(ge=0)
    items_matched: int = Field(ge=0)
    items_unmatched: int = Field(ge=0)
    recommendations: list[RateRecommendation] = []
    flags_summary: dict = {}  # {"OK": N, "REVIEW": N, "UPDATE": N, "NO_DATA": N, "NEEDS_RATE": N}
    parse_format: Optional[str] = None  # "26col", "21col", "csv", "manual"
    overall_optimism_score: Optional[float] = None  # avg delta across all matched items


# ---------------------------------------------------------------------------
# Agent 5 — Field Actuals Comparison Layer (v2)
# ---------------------------------------------------------------------------

# DEPRECATED — v1 only
class Agent5ItemResult_V1(BaseModel):
    takeoff_item_id: int
    csi_code: str
    quantity: Optional[float] = None
    rate: Optional[float] = None
    crew_type: Optional[str] = None
    labor_hours: Optional[float] = None
    labor_cost: Optional[float] = None
    confidence: Optional[float] = None
    match_confidence: Optional[str] = None
    matched_productivity_id: Optional[int] = None
    notes: Optional[str] = None
    error: Optional[str] = None
    source: Optional[str] = None


# DEPRECATED — v1 only
class Agent5Output_V1(BaseModel):
    estimates_created: int = Field(ge=0)
    total_labor_cost: float = Field(ge=0)
    total_labor_hours: float = Field(ge=0)
    items_processed: int = Field(ge=0)
    results: list[Agent5ItemResult_V1] = []
    labor_method: Optional[str] = None
    tokens_used: Optional[int] = None
    benchmark_coverage: Optional[float] = None


class FieldActualsComparison(BaseModel):
    """Three-way comparison for a single takeoff line item."""
    line_item_row: int
    activity: str
    unit: Optional[str] = None
    # The three rates
    estimator_rate: Optional[float] = None       # what this estimator entered
    estimating_avg_rate: Optional[float] = None   # what estimators historically enter (from PB)
    field_avg_rate: Optional[float] = None        # what crews actually produce
    # Comparison metrics
    field_sample_count: int = 0
    estimating_to_field_delta_pct: Optional[float] = None
    entered_to_field_delta_pct: Optional[float] = None
    calibration_factor: Optional[float] = None    # field_avg / estimating_avg
    calibration_direction: str = "no_data"        # "optimistic", "conservative", "aligned", "no_data"
    recommendation: str = ""                       # human-readable guidance
    field_projects: list[str] = []                 # which completed projects inform this


class Agent5Output(BaseModel):
    """Agent 5 v2 — Field Actuals Comparison output."""
    items_compared: int = Field(ge=0)
    items_with_field_data: int = Field(ge=0)
    items_without_field_data: int = Field(ge=0)
    comparisons: list[FieldActualsComparison] = []
    avg_calibration_factor: Optional[float] = None
    calibration_summary: dict = {}  # {"optimistic": N, "conservative": N, "aligned": N, "no_data": N}


# ---------------------------------------------------------------------------
# Agent 6 — Intelligence Report Assembly (v2)
# ---------------------------------------------------------------------------

# DEPRECATED — v1 only
class Agent6Output_V1(BaseModel):
    estimate_id: int
    version: int = Field(ge=1)
    total_direct_cost: float = Field(ge=0)
    total_bid_amount: float = Field(ge=0)
    line_items_count: int = Field(ge=0)
    divisions_covered: list[str] = []
    bid_bond_required: bool = False
    executive_summary: Optional[str] = None
    summary_method: Optional[str] = None
    summary_tokens_used: Optional[int] = None


class RateIntelligenceSummary(BaseModel):
    """Aggregated rate intelligence from Agent 4."""
    total_items: int = 0
    items_ok: int = 0           # <5% deviation
    items_review: int = 0       # 5-20% deviation
    items_update: int = 0       # >20% deviation
    items_no_match: int = 0     # no PB data
    items_needs_rate: int = 0   # PB match but no estimator rate (.est uploads)
    avg_deviation_pct: Optional[float] = None
    optimism_score: Optional[float] = None
    top_deviations: list[dict] = []         # top 5 items by absolute deviation


class FieldCalibrationSummary(BaseModel):
    """Aggregated field calibration from Agent 5."""
    items_with_field_data: int = 0
    items_without_field_data: int = 0
    avg_calibration_factor: Optional[float] = None
    optimistic_count: int = 0
    conservative_count: int = 0
    aligned_count: int = 0
    critical_alerts: list[dict] = []   # items with cal_factor < 0.80 or > 1.20


class ScopeRiskSummary(BaseModel):
    """Aggregated scope risk from Agent 3."""
    total_gaps: int = 0
    critical_gaps: int = 0
    watch_gaps: int = 0
    spec_vs_takeoff_gaps: int = 0
    missing_divisions: list[str] = []
    top_risks: list[dict] = []          # top 5 gaps by severity


class ComparableProjectSummary(BaseModel):
    """Comparable projects from Bid Intelligence."""
    comparable_count: int = 0
    avg_bid_amount: Optional[float] = None
    avg_cost_per_cy: Optional[float] = None
    avg_production_mh_per_cy: Optional[float] = None
    company_hit_rate: Optional[float] = None
    comparables: list[dict] = []        # top 5 most similar projects


class IntelligenceReport(BaseModel):
    """Agent 6 v2 — full intelligence report output."""
    project_id: int
    report_version: int = 1
    generated_at: str = ""

    # Estimator's numbers (from takeoff)
    takeoff_item_count: int = 0
    takeoff_total_labor: Optional[float] = None
    takeoff_total_material: Optional[float] = None

    # Intelligence sections
    rate_intelligence: RateIntelligenceSummary = RateIntelligenceSummary()
    field_calibration: FieldCalibrationSummary = FieldCalibrationSummary()
    scope_risk: ScopeRiskSummary = ScopeRiskSummary()
    comparable_projects: ComparableProjectSummary = ComparableProjectSummary()

    # Spec intelligence
    spec_sections_parsed: int = 0
    material_specs_extracted: int = 0

    # Overall assessment
    overall_risk_level: str = "unknown"    # "low", "moderate", "high", "critical"
    confidence_score: Optional[float] = None  # 0-100 based on data coverage
    executive_narrative: str = ""           # LLM-generated or template
    narrative_method: str = "template"      # "llm" or "template"

    # PB coverage
    pb_projects_loaded: int = 0
    pb_activities_available: int = 0

    # Token tracking
    narrative_tokens_used: int = 0


class Agent6Output(BaseModel):
    """Agent 6 v2 — Intelligence Report output for pipeline contract."""
    report_id: int = Field(ge=0)
    report_version: int = Field(ge=1)
    overall_risk_level: str = ""
    confidence_score: Optional[float] = None
    rate_items_flagged: int = Field(ge=0, default=0)
    scope_gaps_found: int = Field(ge=0, default=0)
    field_calibration_alerts: int = Field(ge=0, default=0)
    comparable_projects_found: int = Field(ge=0, default=0)
    narrative_method: str = "template"
    narrative_tokens_used: int = Field(ge=0, default=0)


# ---------------------------------------------------------------------------
# Agent 7 — IMPROVE Feedback
# ---------------------------------------------------------------------------

class Agent7VarianceItem(BaseModel):
    """Single line-item variance as returned by the LLM (Pydantic-validated)."""

    line_item: str
    estimated_rate: float
    historical_actual_rate: float
    variance_pct: float
    likely_cause: str
    recommendation: str
    confidence: Literal["high", "medium", "low"]

    @field_validator("confidence", mode="before")
    @classmethod
    def _norm_confidence(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("estimated_rate", "historical_actual_rate", "variance_pct", mode="before")
    @classmethod
    def _to_float(cls, v) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        return float(str(v).replace(",", "").strip())


class Agent7Output(BaseModel):
    actuals_processed: int = Field(ge=0)
    variances_calculated: int = Field(ge=0)
    productivity_updates: int = Field(ge=0)
    accuracy_score: float
    total_estimated_cost: float
    total_actual_cost: float
    overall_variance_pct: float
    variance_method: Optional[str] = None   # "llm" or "statistical"
    variance_tokens_used: Optional[int] = None
    variance_items: list[Agent7VarianceItem] = []
    message: Optional[str] = None           # informational note (e.g. no actuals found)


# ---------------------------------------------------------------------------
# Validation helpers — called by each agent before returning
# ---------------------------------------------------------------------------

_CONTRACT_MAP: dict[int, type[BaseModel]] = {
    1: Agent1Output,
    2: Agent2Output,
    3: Agent3Output,
    4: Agent4Output,
    5: Agent5Output,
    6: Agent6Output,
    7: Agent7Output,
}

AGENT_NAMES = {
    1: "Document Ingestion Agent",
    2: "Spec Parser Agent",
    3: "Scope Analysis Agent",
    4: "Rate Intelligence Agent",
    5: "Field Calibration Agent",
    6: "Intelligence Report Agent",
    7: "IMPROVE Feedback Agent",
}


def validate_agent_output(agent_number: int, output: dict) -> dict:
    """Validate *output* dict against the contract for *agent_number*.

    Returns the original dict unchanged if valid.
    Raises ContractViolation if validation fails.
    """
    contract_cls = _CONTRACT_MAP.get(agent_number)
    if contract_cls is None:
        return output

    agent_name = AGENT_NAMES.get(agent_number, f"Agent {agent_number}")
    try:
        contract_cls.model_validate(output)
    except Exception as exc:
        raise ContractViolation(agent_name, str(exc)) from exc

    return output
```

## 10. apex/backend/alembic/env.py

```python
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so apex.backend.* imports work whether
# alembic is invoked from apex/backend/ or from the project root.
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))  # apex/backend/alembic/
_backend = os.path.dirname(_here)                    # apex/backend/
_repo_root = os.path.dirname(os.path.dirname(_backend))  # project root
for _p in (_repo_root, _backend):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Import Base (defined in database.py) and ALL models so autogenerate sees
# every table.
# ---------------------------------------------------------------------------
from apex.backend.db.database import Base, DATABASE_URL  # noqa: E402

from apex.backend.models import (  # noqa: F401, E402
    agent_run_log,
    audit_log,
    bid_comparison,
    change_order,
    document,
    equipment_rate,
    estimate,
    estimate_library,
    gap_report,
    labor_estimate,
    material_price,
    organization,
    productivity_history,
    project,
    project_actual,
    spec_section,
    takeoff_item,
    token_usage,
    upload_chunk,
    upload_session,
    user,
)
from apex.backend.models.historical_line_item import HistoricalLineItem  # noqa: F401, E402
from apex.backend.models.document_association import DocumentAssociation, DocumentGroup  # noqa: F401, E402
from apex.backend.services.productivity_brain.models import PBProject, PBLineItem  # noqa: F401, E402
from apex.backend.services.bid_intelligence.models import BIEstimate  # noqa: F401, E402
from apex.backend.models.takeoff_v2 import TakeoffItemV2  # noqa: F401, E402
from apex.backend.models.field_actuals import FieldActualsProject, FieldActualsLineItem  # noqa: F401, E402
from apex.backend.models.intelligence_report import IntelligenceReportModel  # noqa: F401, E402
from apex.backend.models.decision_models import (  # noqa: F401, E402
    ComparableProject, HistoricalRateObservation, CanonicalActivity,
    ActivityAlias, EstimateLine, CostBreakdownBucket, RiskItem,
    EscalationInput, EstimatorOverride, BidOutcome, FieldActual,
)

# ---------------------------------------------------------------------------
# Alembic Config
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from the same source database.py uses so they stay
# consistent.  The value in alembic.ini acts as a fallback only.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to real DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```
