"""APEX Platform — FastAPI Application Entry Point."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
