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

    # Log active LLM provider
    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider()
        logger.info(f"LLM provider: {provider.provider_name} | model: {provider.model_name}")
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
    """Check LLM provider availability. No auth required."""
    try:
        from apex.backend.services.llm_provider import get_llm_provider
        provider = get_llm_provider()
        available = await provider.health_check()
        return {
            "provider": provider.provider_name,
            "model": provider.model_name,
            "available": available,
        }
    except Exception as e:
        return {
            "provider": os.getenv("LLM_PROVIDER", "ollama"),
            "model": "unknown",
            "available": False,
            "error": str(e),
        }
