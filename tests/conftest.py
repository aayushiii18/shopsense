"""
tests/conftest.py — Pytest fixtures shared across all test modules.

Uses a SQLite in-memory database so tests do NOT require PostgreSQL.
Each test function gets a clean database (tables created fresh, dropped after).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test_shopsense.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Create all tables before each test, yield a session, then drop everything.
    This ensures test isolation — no test pollutes another's data.
    """
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient whose DB dependency is overridden to use
    the test SQLite session instead of the real PostgreSQL session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session closed by db_session fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
