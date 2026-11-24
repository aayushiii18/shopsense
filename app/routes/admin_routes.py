"""
routes/admin_routes.py — FastAPI endpoints for Platform Administration & System Governance.

GET /admin/overview   Comprehensive system health, entity counts & revenue summary
GET /admin/stats      Administrative breakdown of roles, statuses & model readiness
GET /admin/health     Detailed administrative health diagnostics
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.core.dependencies import require_admin
from backend.config import get_settings

router = APIRouter(
    prefix="/admin",
    tags=["Admin API"],
    dependencies=[Depends(require_admin)],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class AdminOverviewResponse(BaseModel):
    system_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Platform version")
    status: str = Field("operational", description="System operational state")
    database_connected: bool = Field(True, description="Database connectivity status")
    total_users: int = Field(..., description="Total registered platform users")
    total_vendors: int = Field(..., description="Total vendor accounts")
    total_products: int = Field(..., description="Total active catalog products")
    total_customers: int = Field(..., description="Total registered customer profiles")
    total_transactions: int = Field(..., description="Total completed transactions")
    total_gmv: float = Field(..., description="Total marketplace gross merchandise value")


class AdminStatsResponse(BaseModel):
    users_by_role: Dict[str, int] = Field(..., description="User count partitioned by role")
    vendors_by_status: Dict[str, int] = Field(..., description="Vendor count by lifecycle status")
    products_count: int = Field(..., description="Active catalog products")
    customers_count: int = Field(..., description="Customer registry count")
    total_gmv: float = Field(..., description="Platform gross merchandise value")
    forecast_model_path: str = Field(..., description="Path to active demand forecasting model")
    recommender_model_path: str = Field(..., description="Path to recommendation model")


class AdminHealthResponse(BaseModel):
    status: str = Field("healthy", description="Operational health status")
    database: str = Field("connected", description="Database connection health")
    version: str = Field("1.0.0", description="Active platform version")
    project_name: str = Field("ShopSense", description="Application name")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Platform Administrative Overview",
)
def admin_overview(db: Session = Depends(get_db)):
    """
    Returns platform-wide operational KPIs and entity counts.
    Requires ADMIN privileges.
    """
    settings = get_settings()

    total_users = db.query(func.count(User.id)).scalar() or 0
    total_vendors = db.query(func.count(Vendor.id)).scalar() or 0
    total_products = db.query(func.count(Product.id)).scalar() or 0
    total_customers = db.query(func.count(Customer.customer_id)).scalar() or 0
    total_txns = db.query(func.count(Transaction.transaction_id)).scalar() or 0
    total_gmv = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0

    return {
        "system_name": settings.project_name,
        "version": settings.version,
        "status": "operational",
        "database_connected": True,
        "total_users": int(total_users),
        "total_vendors": int(total_vendors),
        "total_products": int(total_products),
        "total_customers": int(total_customers),
        "total_transactions": int(total_txns),
        "total_gmv": round(float(total_gmv), 2),
    }


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    summary="Administrative System Statistics",
)
def admin_stats(db: Session = Depends(get_db)):
    """
    Returns detailed role distributions, vendor statuses, and ML model configuration.
    Requires ADMIN privileges.
    """
    settings = get_settings()

    # User role distribution
    user_roles = (
        db.query(User.role, func.count(User.id))
        .group_by(User.role)
        .all()
    )
    role_map = {r[0].value if hasattr(r[0], "value") else str(r[0]): r[1] for r in user_roles}

    # Vendor status distribution
    vendor_statuses = (
        db.query(Vendor.status, func.count(Vendor.id))
        .group_by(Vendor.status)
        .all()
    )
    status_map = {str(s[0]): s[1] for s in vendor_statuses}

    products_count = db.query(func.count(Product.id)).scalar() or 0
    customers_count = db.query(func.count(Customer.customer_id)).scalar() or 0
    total_gmv = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0

    return {
        "users_by_role": role_map,
        "vendors_by_status": status_map,
        "products_count": int(products_count),
        "customers_count": int(customers_count),
        "total_gmv": round(float(total_gmv), 2),
        "forecast_model_path": settings.forecast_model_path,
        "recommender_model_path": settings.recommender_model_path,
    }


@router.get(
    "/health",
    response_model=AdminHealthResponse,
    summary="Administrative System Health Diagnostics",
)
def admin_health(db: Session = Depends(get_db)):
    """
    Health diagnostic verification including database roundtrip and system metadata.
    Requires ADMIN privileges.
    """
    settings = get_settings()
    # Check DB roundtrip
    db.execute(func.now())
    return {
        "status": "healthy",
        "database": "connected",
        "version": settings.version,
        "project_name": settings.project_name,
    }
