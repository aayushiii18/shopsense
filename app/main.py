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
)

app = FastAPI(
    title="StockPilot — Retail Management Platform for Inventory Control and Sales Analytics",
    description=(
        "Smarter Stock. Better Decisions. "
        "An intelligent retail management platform featuring inventory analytics, "
        "demand forecasting, customer segmentation, and personalized product recommendations."
    ),
    version="2.0.0",
)

# ── Register routers ────────────────────────────────────────────────────────
app.include_router(vendor_routes.router)
app.include_router(product_routes.router)
app.include_router(analytics_routes.router)
app.include_router(inventory_routes.router)
app.include_router(inventory_routes.movement_router)
app.include_router(customer_routes.router)
app.include_router(recommendation_routes.router)


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "StockPilot API is running."}
