"""
docker_entrypoint.py — ShopSense container initialization and lifecycle manager.

Stage 8: Docker, Containerization, CI/CD & Final System Integration.

Responsibilities:
1. Wait for database connectivity with retry backoff.
2. Ensure database schema exists idempotently (never drops or modifies data).
3. Run Stage 7 schema migration checks (users, refresh_tokens, token_version).
4. If fresh database (0 vendors): seed baseline demonstration catalog.
5. If existing database: preserve 100% of historical records.
6. Bootstrap administrative account idempotently.
7. Initialize daily sales mart aggregates if empty.
8. Execute target application process.
"""

import os
import sys
import time
import logging
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [docker-entrypoint] %(message)s",
)
logger = logging.getLogger("docker_entrypoint")


def wait_for_database(max_retries: int = 30, delay_seconds: int = 2) -> bool:
    """Poll database until connection succeeds or retries exhausted."""
    from app.database import engine
    logger.info("Verifying database connectivity...")
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
            logger.info("Database connection established successfully.")
            return True
        except Exception as e:
            logger.warning(
                "Database unavailable (attempt %d/%d): %s. Retrying in %ds...",
                attempt,
                max_retries,
                e,
                delay_seconds,
            )
            time.sleep(delay_seconds)

    logger.error("Failed to connect to database after %d attempts. Exiting.", max_retries)
    sys.exit(1)


def initialize_database():
    """Ensure all schema tables, migrations, and baseline data exist safely."""
    from app.database import engine, Base, SessionLocal
    import app.models  # Registers all 16 models
    from migrate_stage7 import run_migration as run_stage7_migration
    from migrate_vendor_onboarding import run_migration as run_vendor_onboarding_migration
    from app.models.vendor import Vendor
    from app.models.etl import DailySalesMart
    from bootstrap_admin import bootstrap_admin_user

    # 1. Safe, non-destructive table creation
    logger.info("Verifying database tables (create_all)...")
    Base.metadata.create_all(bind=engine)
    logger.info("Base tables verified.")

    # 2. Stage 7 & Vendor Onboarding migration checks
    logger.info("Executing Stage 7 migration check...")
    try:
        run_stage7_migration()
        run_vendor_onboarding_migration()
        logger.info("Stage 7 and vendor onboarding migrations verified.")
    except Exception as e:
        logger.warning("Migration check returned: %s", e)

    # 3. Check existing data / fresh database initialization
    db = SessionLocal()
    try:
        vendor_count = db.query(Vendor).count()
        if vendor_count == 0:
            logger.info("Fresh database detected (0 vendors). Seeding baseline demonstration dataset...")
            import seed_data
            seed_data.seed_vendors(db)
            seed_data.seed_products(db)
            seed_data.seed_inventory(db)
            seed_data.seed_customers(db)
            seed_data.seed_transactions(db)
            seed_data.seed_stock_movements(db)
            seed_data.seed_customer_interactions(db)
            logger.info("Baseline catalog seeded successfully.")
        else:
            logger.info(
                "Existing database detected (%d vendors). Preserving all historical business records.",
                vendor_count,
            )

        # 4. Check daily sales mart
        try:
            mart_count = db.query(DailySalesMart).count()
            if mart_count == 0:
                logger.info("Daily sales mart is empty. Building analytical aggregates...")
                from app.services.etl import refresh_daily_sales_mart
                refresh_daily_sales_mart(db=db, full_rebuild=True)
                logger.info("Daily sales mart initialized.")
            else:
                logger.info("Daily sales mart contains %d records.", mart_count)
        except Exception as e:
            logger.warning("Daily sales mart check returned: %s", e)

        # 5. Bootstrap administrator user
        admin_email = os.getenv("ADMIN_EMAIL", "admin@shopsense.internal").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "AdminSecure123!")
        logger.info("Verifying administrative account for '%s'...", admin_email)
        try:
            bootstrap_admin_user(email=admin_email, password=admin_password, force=False, db=db)
        except Exception as e:
            logger.warning("Admin bootstrap notice: %s", e)

    finally:
        db.close()


def main():
    wait_for_database()
    initialize_database()

    # If arguments passed, execute them replacing current process
    if len(sys.argv) > 1:
        cmd = sys.argv[1:]
        logger.info("Executing application command: %s", " ".join(cmd))
        os.execvp(cmd[0], cmd)
    else:
        logger.info("No command specified. Launching default FastAPI Uvicorn server...")
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
