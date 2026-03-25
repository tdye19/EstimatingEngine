"""Database engine and session configuration."""

import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = f"sqlite:///{os.path.join(_db_dir, 'apex.db')}"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logger = logging.getLogger("apex.db")


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sprint6_columns():
    """Add Sprint 6 columns to estimates table if they don't exist.

    Base.metadata.create_all() creates missing tables but does NOT add
    columns to existing tables. This guard runs ALTER TABLE when needed
    so existing databases survive the Sprint 6 upgrade without manual SQL.

    # TODO: Replace with Alembic migrations.
    """
    if not DATABASE_URL.startswith("sqlite"):
        # Postgres / other engines should use proper Alembic migrations.
        return

    new_columns = {
        "executive_summary": "TEXT",
        "variance_report_json": "TEXT",
    }
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(estimates)"))
            existing_columns = {row[1] for row in result}

            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    conn.execute(
                        text(f"ALTER TABLE estimates ADD COLUMN {col_name} {col_type}")
                    )
                    conn.commit()
                    logger.info("DB migration: added estimates.%s (%s)", col_name, col_type)
    except Exception as exc:
        logger.warning("DB migration check failed (non-fatal): %s", exc)


def _ensure_cache_columns():
    """Add prompt-caching columns to token_usage table if they don't exist.

    Same safety-net pattern as _ensure_sprint6_columns().
    # TODO: Replace with Alembic migrations.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    new_columns = {
        "cache_creation_tokens": "INTEGER DEFAULT 0",
        "cache_read_tokens": "INTEGER DEFAULT 0",
    }
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(token_usage)"))
            existing_columns = {row[1] for row in result}

            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    conn.execute(
                        text(f"ALTER TABLE token_usage ADD COLUMN {col_name} {col_type}")
                    )
                    conn.commit()
                    logger.info("DB migration: added token_usage.%s (%s)", col_name, col_type)
    except Exception as exc:
        logger.warning("DB migration check failed (non-fatal): %s", exc)


def init_db():
    from apex.backend.models import (  # noqa: F401
        user, organization, project, document, spec_section,
        gap_report, takeoff_item, labor_estimate, material_price,
        estimate, project_actual, productivity_history, agent_run_log,
        token_usage, upload_session,
    )
    Base.metadata.create_all(bind=engine)
    _ensure_sprint6_columns()
    _ensure_cache_columns()
