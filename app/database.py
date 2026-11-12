"""
database.py — SQLAlchemy engine + session factory.

Reads DATABASE_URL from the environment (via .env).
The TEST_DATABASE_URL override is used by tests (see tests/conftest.py).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()  # loads .env if present


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stockpilot_dev.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# connect_args only needed for SQLite (thread-safety)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

_engine_kwargs = {
    "connect_args": _connect_args,
    "pool_pre_ping": True,
}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 30
    _engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency that yields a database session and
    ensures it is closed after each request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
