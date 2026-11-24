"""
migrate_stage7.py — Safe, idempotent migration for Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.

Applies:
- users: creates 'users' table for credential authentication, roles (ADMIN, VENDOR, CUSTOMER), and entity links.
- refresh_tokens: creates 'refresh_tokens' table for JWT rotation, token family tracking, and reuse revocation.

Guarantees:
- Single atomic transaction block (all-or-nothing).
- 100% idempotent.
- Non-destructive (zero historical data loss, preserves all 600 transactions, 60 customers, 10 products, 5 vendors).
- Completely preserves legacy unauthenticated records without fabricating passwords.
"""

import sys
from sqlalchemy import text
from app.database import engine


def run_migration():
    print("Beginning Stage 7 schema migration...")
    dialect = engine.dialect.name
    print(f"Database dialect: {dialect}")

    with engine.begin() as conn:
        if dialect == "postgresql":
            # 1. Create users table
            print("Creating 'users' table (PostgreSQL)...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER',
                    vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
                    customer_id INTEGER REFERENCES customers(customer_id) ON DELETE SET NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    last_login_at TIMESTAMP WITHOUT TIME ZONE,
                    CONSTRAINT ck_users_role CHECK (role IN ('ADMIN', 'VENDOR', 'CUSTOMER'))
                );
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_vendor_id ON users(vendor_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_customer_id ON users(customer_id);"))

            # Ensure token_version column exists for instantaneous token invalidation
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;
            """))

            # 2. Create refresh_tokens table
            print("Creating 'refresh_tokens' table (PostgreSQL)...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash VARCHAR(64) UNIQUE NOT NULL,
                    token_family VARCHAR(36) NOT NULL,
                    jti VARCHAR(36) UNIQUE NOT NULL,
                    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
                    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    revoked_at TIMESTAMP WITHOUT TIME ZONE
                );
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family ON refresh_tokens(token_family);"))

        else:
            # SQLite fallback (used in unit test environments)
            print("Creating 'users' table (SQLite)...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER',
                    vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
                    customer_id INTEGER REFERENCES customers(customer_id) ON DELETE SET NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    is_verified BOOLEAN NOT NULL DEFAULT 0,
                    token_version INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    last_login_at TIMESTAMP
                );
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);"))

            print("Creating 'refresh_tokens' table (SQLite)...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash VARCHAR(64) UNIQUE NOT NULL,
                    token_family VARCHAR(36) NOT NULL,
                    jti VARCHAR(36) UNIQUE NOT NULL,
                    is_revoked BOOLEAN NOT NULL DEFAULT 0,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    revoked_at TIMESTAMP
                );
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);"))

        print("Stage 7 schema migration committed successfully.")


if __name__ == "__main__":
    try:
        run_migration()
        print("Migration complete!")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
