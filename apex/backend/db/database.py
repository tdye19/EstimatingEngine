"""Database engine and session configuration."""

import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = f"sqlite:///{os.path.join(_db_dir, 'apex.db')}"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

connect_args = {}
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    engine_kwargs = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": 1800,
        "pool_pre_ping": True,
        "pool_timeout": 30,
    }

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False, **engine_kwargs)

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


# Schema migrations handled by Alembic — see apex/backend/alembic/versions/
# Run: PYTHONPATH=. alembic -c apex/backend/alembic.ini upgrade head
