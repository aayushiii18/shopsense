"""
migrate_vendor_onboarding.py — Idempotent schema migration for Vendor Onboarding Stage A.

Safely adds the optional `owner_name` column to the `vendors` table while preserving
100% of existing historical vendors, products, customers, transactions, inventory, and users.
Supports both PostgreSQL and SQLite dialects.
"""

from sqlalchemy import text
from app.database import engine


def run_migration():
    """Apply idempotent vendor onboarding schema updates."""
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("""
                ALTER TABLE vendors
                ADD COLUMN IF NOT EXISTS owner_name VARCHAR(150);
            """))
        else:
            # SQLite compatibility: inspect pragma table_info
            rows = conn.execute(text("PRAGMA table_info(vendors)")).fetchall()
            col_names = {r[1] for r in rows}
            if "owner_name" not in col_names and rows:
                conn.execute(text("ALTER TABLE vendors ADD COLUMN owner_name VARCHAR(150);"))


if __name__ == "__main__":
    print(f"Running vendor onboarding migration on dialect={engine.dialect.name}...")
    run_migration()
    print("Migration completed successfully without data loss.")
