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
