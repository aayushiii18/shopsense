"""
create_tables.py — Run this script once to create all tables in the database.

Usage:
    python create_tables.py

It reads DATABASE_URL from the .env file and creates all tables defined
in the SQLAlchemy models if they do not already exist.
"""

from dotenv import load_dotenv
load_dotenv()

from app.database import engine, Base
# Import all models so SQLAlchemy knows about the tables before calling create_all
import app.models  # noqa: F401

if __name__ == "__main__":
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done. Tables created (or already existed):")
    for table_name in Base.metadata.tables:
        print(f"  - {table_name}")
