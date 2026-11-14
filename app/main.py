"""
app/main.py — FastAPI application entry point for StockPilot.

Start the server:
    uvicorn app.main:app --reload

Interactive API docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
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
)

app = FastAPI(
    title="StockPilot — Retail Management Platform for Inventory Control and Sales Analytics",
    description=(
        "Smarter Stock. Better Decisions. "
        "An intelligent retail management platform featuring inventory analytics, "
        "advanced revenue analysis, demand forecasting, customer segmentation, "
        "and personalized product recommendations."
    ),
    version="3.0.0",
)

# ── Register routers ────────────────────────────────────────────────────────
app.include_router(vendor_routes.router)
app.include_router(product_routes.router)
app.include_router(analytics_routes.router)
app.include_router(revenue_routes.router)
app.include_router(inventory_routes.router)
app.include_router(inventory_routes.movement_router)
app.include_router(forecast_routes.router)
app.include_router(customer_routes.router)
app.include_router(recommendation_routes.router)
app.include_router(recommendation_routes.recommend_router)
app.include_router(report_routes.router)
app.include_router(refund_routes.router)


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "StockPilot API is running."}


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
