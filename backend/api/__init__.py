"""
backend/api/ — API package for ShopSense Analytics Platform.

Exposes canonical routers for Sales API, Forecasting API, Recommendation API, and Admin API.
"""

from app.routes.revenue_routes import router as sales_revenue_router
from app.routes.analytics_routes import router as sales_analytics_router
from app.routes.forecast_routes import router as forecasting_router
from app.routes.recommendation_routes import (
    router as recommendation_router,
    recommend_router as single_recommendation_router,
)
from app.routes.admin_routes import router as admin_router
from app.main import app

__all__ = [
    "app",
    "sales_revenue_router",
    "sales_analytics_router",
    "forecasting_router",
    "recommendation_router",
    "single_recommendation_router",
    "admin_router",
]
