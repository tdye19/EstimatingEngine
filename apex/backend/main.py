"""APEX Platform — FastAPI Application Entry Point."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load .env before anything else so env vars are available during import
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from apex.backend.db.database import init_db
from apex.backend.routers import auth, projects, reports, productivity
from apex.backend.routers import exports
from apex.backend.routers import token_usage as token_usage_router
from apex.backend.routers import test_pipeline as test_pipeline_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("apex")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting APEX Platform...")
    init_db()

    # Run seeder if DB is empty
    import sys
    from apex.backend.db.seed import seed_if_empty
    seed_if_empty(force="--force-seed" in sys.argv)

    # Ensure upload directory exists
    os.makedirs(os.getenv("UPLOAD_DIR", "./uploads"), exist_ok=True)

    # Clean up any stale chunked-upload temp directories from previous runs
    from apex.backend.routers.projects import cleanup_stale_upload_sessions
    cleanup_stale_upload_sessions()

    # Log active LLM provider
    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider()
        logger.info(f"LLM provider (default): {provider.provider_name} | model: {provider.model_name}")
    except Exception as e:
        logger.warning(f"LLM provider not configured: {e}")

    logger.info("APEX Platform ready.")
    yield
    logger.info("APEX Platform shutting down.")


app = FastAPI(
    title="APEX — Automated Project Estimation Exchange",
    description="AI-powered construction estimating platform for general contractors",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(reports.router)
app.include_router(productivity.router)
app.include_router(exports.router)
app.include_router(token_usage_router.router)

# Dev-only test router — only active when APEX_DEV_MODE=true
if os.getenv("APEX_DEV_MODE", "").lower() in ("true", "1", "yes"):
    app.include_router(test_pipeline_router.router)
    logger.info("Dev mode: test pipeline router mounted at /api/test")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "message": "Internal server error",
            "data": None,
        },
    )


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "apex-backend", "version": "1.0.0"}


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
