"""
api/ — Milestone 3 API package exposing canonical route modules matching the specification.
"""
from app.routes.revenue_routes import router as revenue_router
from app.routes.forecast_routes import router as forecast_router
from app.routes.customer_routes import router as customer_router
from app.routes.recommendation_routes import router as recommendation_router

__all__ = ["revenue_router", "forecast_router", "customer_router", "recommendation_router"]
