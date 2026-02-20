"""Database engine and session configuration."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./apex.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from apex.backend.models import (  # noqa: F401
        user, organization, project, document, spec_section,
        gap_report, takeoff_item, labor_estimate, material_price,
        estimate, project_actual, productivity_history, agent_run_log,
    )
    Base.metadata.create_all(bind=engine)
