"""
backend/api/main.py — ShopSense Analytics Platform FastAPI Entry Point.

FastAPI Application Configuration:
  - Title: ShopSense Analytics Platform
  - Version: 1.0.0
  - Description: Production Retail Marketplace Analytics Platform

Registers:
  - Sales API (revenue & sales analytics)
  - Forecasting API (demand predictions)
  - Recommendation API (collaborative & hybrid engines)
  - Admin API (system governance & audits)
"""

from app.main import app, startup_event, shutdown_event

__all__ = ["app", "startup_event", "shutdown_event"]

if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=port)
