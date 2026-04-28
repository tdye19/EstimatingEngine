# APEX Backend Architecture

This document summarizes the backend architecture for the EstimatingEngine APEX platform.

## Overview

The backend is implemented in `apex/backend/` using FastAPI, SQLAlchemy, and SQLite/PostgreSQL.

Key responsibilities:
- API routing and middleware in `main.py`
- environment and runtime configuration in `config.py`
- database engine and session management in `db/database.py`
- schema migrations via Alembic in `alembic/`
- agent orchestration and fallback logic in `agents/`
- retrieval and embedding in `retrieval/`
- reusable services and business logic in `services/`
- robust testing in `tests/`

## App Entry Point (`main.py`)

`apex/backend/main.py` initializes the FastAPI app and applies:
- CORS middleware using `CORS_ORIGINS`
- global rate limiting using `slowapi`
- a static file mount for production assets
- `init_db()` on startup to ensure schema additions are applied
- dev-only routers when `APEX_DEV_MODE=true`

## Configuration (`config.py`)

Configuration is centralized in `apex/backend/config.py`.

Patterns:
- environment variables are read once at import time
- default values are defined in one place
- dev mode is toggled by `APEX_DEV_MODE`
- fallback values support local development without external secrets

Important runtime flags:
- `JWT_SECRET_KEY` / `APEX_DEV_MODE`
- `OPENAI_API_KEY` for retrieval embeddings
- `CORS_ORIGINS`
- `GLOBAL_RATE_LIMIT`

## Database Layer (`db/database.py`)

The database layer provides:
- engine creation for SQLite or PostgreSQL
- session factory via `SessionLocal`
- async-safe SQLite WAL mode for concurrent reads/writes
- schema migration helper `ensure_project_context_columns()`

New optimization:
- `ensure_project_context_columns()` now inspects the existing `projects` table and adds only missing columns.
- This avoids repeated failed `ALTER TABLE` statements and is compatible with both SQLite and PostgreSQL.

## Agent and Retrieval Patterns

Agents live under `apex/backend/agents/` and generally follow this pattern:
- pure Python core logic where possible
- LLM-assisted behavior only when configured and available
- deterministic math and rule-based fallbacks for safety

The retrieval subsystem is implemented in `apex/backend/retrieval/`:
- `embedder.py` handles OpenAI embeddings
- `pipeline.py` indexes project specs in batches
- `retriever.py` performs semantic search and formats results
- graceful fallback is used when `OPENAI_API_KEY` is missing

## Testing Strategy

Tests live under `apex/backend/tests/`.

Important patterns:
- `tests/conftest.py` sets `APEX_DEV_MODE=true` for safe startup
- an in-memory SQLite engine is used for fast, isolated test execution
- `FastAPI` dependencies are overridden for `TestClient`
- regression and edge-case tests cover environment states, agent behavior, and DB helpers

## Developer Notes

- Use `PYTHONPATH=. alembic -c apex/backend/alembic.ini upgrade head` to apply migrations.
- Set `APEX_DEV_MODE=true` for local development when `JWT_SECRET_KEY` is not provided.
- If `OPENAI_API_KEY` is not configured, retrieval indexing and search are skipped safely.
- Add new API routes under `routers/`, business logic under `services/`, and retrieval helpers under `retrieval/`.
