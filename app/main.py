"""
app/main.py — FastAPI application entry point for ShopSense Analytics Platform.

Start the server:
    uvicorn app.main:app --reload

Interactive API docs: http://127.0.0.1:8000/docs
"""

from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import health_service
from app.routes import (
    vendor_routes,
    product_routes,
    analytics_routes,
    inventory_routes,
    customer_routes,
    recommendation_routes,
    revenue_routes,
    forecast_routes,
    report_routes,
    refund_routes,
    offer_routes,
    catalog_routes,
    etl_routes,
    auth_routes,
    admin_routes,
    executive_routes,
)
from backend.config import get_settings

settings = get_settings()

openapi_tags = [
    {
        "name": "Sales API",
        "description": "Sales, GMV, category, regional, and vendor revenue analytics endpoints.",
    },
    {
        "name": "Forecasting API",
        "description": "Inventory demand forecasting and stock requirement prediction endpoints.",
    },
    {
        "name": "Recommendation API",
        "description": "Personalized collaborative filtering, content-based, and cold-start product recommendations.",
    },
    {
        "name": "Admin API",
        "description": "Administrative endpoints for platform overview, system metrics, and governance.",
    },
    {
        "name": "Executive Analytics API",
        "description": "Role-restricted executive KPIs, period comparisons, SQL-aggregated trends, and vendor/product drilldowns.",
    },
]

app = FastAPI(
    title="ShopSense Analytics Platform",
    description="Production Retail Marketplace Analytics Platform",
    version=settings.version if settings.version == "1.0.0" else "1.0.0",
    openapi_tags=openapi_tags,
)

# ── Register routers ────────────────────────────────────────────────────────
# Sales API & Executive Analytics routers
app.include_router(revenue_routes.router)
app.include_router(analytics_routes.router)
app.include_router(executive_routes.router)

# Forecasting API routers
app.include_router(forecast_routes.router)
app.include_router(inventory_routes.router)
app.include_router(inventory_routes.movement_router)

# Recommendation API routers
app.include_router(recommendation_routes.router)
app.include_router(recommendation_routes.recommend_router)

# Admin API & Security routers
app.include_router(admin_routes.router)
app.include_router(auth_routes.router)
app.include_router(etl_routes.router)

# Core domain & auxiliary routers
app.include_router(vendor_routes.router)
app.include_router(product_routes.router)
app.include_router(customer_routes.router)
app.include_router(report_routes.router)
app.include_router(refund_routes.router)
app.include_router(offer_routes.router)
app.include_router(catalog_routes.router)


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "ShopSense API is running."}


@app.get("/health/live", tags=["Health"], summary="Liveness Probe")
def liveness_probe():
    """
    Lightweight process liveness probe (does not query downstream dependencies).
    Returns 200 UP whenever the FastAPI server process is responsive.
    """
    return {
        "status": "UP",
        "service": settings.project_name,
        "version": settings.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/ready", tags=["Health"], summary="Readiness Probe")
def readiness_probe(db: Session = Depends(get_db)):
    """
    Service readiness probe verifying core database connectivity.
    Returns 200 READY if operational or 503 Service Unavailable if database is unreachable.
    For detailed component diagnostics, administrators should query GET /admin/health.
    """
    db_check = health_service.check_database_health(db)
    if db_check["status"] == "UNAVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "NOT_READY",
                "database": "UNAVAILABLE",
                "timestamp": db_check["last_checked"],
            },
        )
    return {
        "status": "READY",
        "database": db_check["status"],
        "timestamp": db_check["last_checked"],
    }


@app.on_event("startup")
def startup_event():
    """Starts APScheduler background scheduler on FastAPI startup if enabled."""
    import os
    import sys
    if os.getenv("DISABLE_BACKGROUND_SCHEDULER", "false").lower() in ("1", "true", "yes"):
        return
    if os.getenv("ENABLE_AUTO_SCHEDULER", "true").lower() in ("1", "true", "yes"):
        if "pytest" not in sys.modules:
            from app.scheduler import start_scheduler
            start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    """Safely shuts down APScheduler background scheduler on FastAPI shutdown."""
    from app.scheduler import stop_scheduler
    stop_scheduler()


if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
