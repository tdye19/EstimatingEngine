"""Database engine and session configuration."""

import logging
import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = f"sqlite:///{os.path.join(_db_dir, 'apex.db')}"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

# Enable WAL mode for SQLite to allow concurrent reads alongside a single writer,
# which is a prerequisite for safe parallel agent execution (Agents 3 & 4).
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_wal_mode(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

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


# Schema migrations handled by Alembic — run: alembic upgrade head
def init_db():
    from apex.backend.models import (  # noqa: F401
        user, organization, project, document, spec_section,
        gap_report, takeoff_item, labor_estimate, material_price,
        estimate, project_actual, productivity_history, agent_run_log,
        token_usage, upload_session, upload_chunk,
        bid_comparison, change_order,
    )
    Base.metadata.create_all(bind=engine)
