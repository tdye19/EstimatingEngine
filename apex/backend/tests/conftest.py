"""Shared pytest fixtures for APEX backend tests."""

import os

# Set env vars BEFORE any app imports
os.environ["APEX_DEV_MODE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from apex.backend.db.database import Base, get_db
from apex.backend.main import app
from apex.backend.models.project import Project
from apex.backend.models.user import User
from apex.backend.utils.auth import create_access_token, hash_password

# Use a shared in-memory SQLite engine via StaticPool so both the app
# lifespan (seed, init_db) and the tests share the same database.
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Monkey-patch the app's engine and session factory to use our test engine
import apex.backend.db.database as _db_mod

_db_mod.engine = _test_engine
_db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


# Enable WAL-like listener for test engine
@event.listens_for(_test_engine, "connect")
def _set_wal(dbapi_conn, rec):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# Create all tables
Base.metadata.create_all(bind=_test_engine)


@pytest.fixture(scope="session")
def test_engine():
    yield _test_engine
    _test_engine.dispose()


@pytest.fixture
def db_session():
    """Session for direct DB manipulation in tests."""
    session = _db_mod.SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with db override."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """Create a test estimator user."""
    import uuid

    user = User(
        email=f"testuser-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test User",
        role="estimator",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """Create an admin user."""
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("adminpass123"),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """JWT Bearer headers for test_user."""
    token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user):
    """JWT Bearer headers for admin_user."""
    token = create_access_token(data={"sub": str(admin_user.id), "email": admin_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_project(db_session, test_user):
    """Create a test project owned by test_user."""
    project = Project(
        name="Test Project",
        project_number="TP-001",
        owner_id=test_user.id,
        status="draft",
        project_type="commercial",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def mock_llm_response():
    """Factory for mock LLM responses."""

    def _make(content="mock response", model="test-model", provider="test"):
        from apex.backend.services.llm_provider import LLMResponse

        return LLMResponse(
            content=content,
            model=model,
            provider=provider,
            input_tokens=100,
            output_tokens=50,
            duration_ms=500.0,
        )

    return _make
