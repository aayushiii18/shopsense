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


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shopsense_dev.db")

# connect_args only needed for SQLite (thread-safety)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

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
