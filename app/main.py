"""
app/main.py — FastAPI application entry point for ShopSense.

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
    title="ShopSense — Multi-Vendor E-Commerce Analytics Platform",
    description=(
        "Retail Management Platform for Inventory Control and Sales Analytics. "
        "Milestone 2: Inventory Analytics Engine, Customer Segmentation, and Recommendations."
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
    return {"status": "ok", "message": "ShopSense API is running."}
