"""
app/routes/executive_routes.py — Milestone 4 Phase 2 Executive Analytics API Routes.

Endpoints:
  GET /analytics/executive/summary          Centralized Executive KPI Snapshot (ADMIN only)
  GET /analytics/executive/trends           Chronological Sales & Growth Series (ADMIN only)
  GET /analytics/executive/vendors          Vendor & Product Performance Drilldown (ADMIN only)
  GET /analytics/executive/vendor-summary   Tenant-Scoped Vendor Executive KPIs (VENDOR / ADMIN)
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_vendor_or_admin, verify_vendor_tenant
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.executive_schema import (
    ExecutiveSummaryResponse,
    ExecutiveTrendsResponse,
    ExecutiveVendorProductDrilldownResponse,
    ExecutiveVendorTenantSummaryResponse,
)
from app.services import executive_service

router = APIRouter(prefix="/analytics/executive", tags=["Executive Analytics API"])


@router.get(
    "/summary",
    response_model=ExecutiveSummaryResponse,
    summary="Centralized Executive KPI Summary (Admin Only)",
    description=(
        "Aggregates platform-wide financial KPIs (GMV, discounts, refunds, net sales, COGS-guarded gross profit), "
        "time-period comparisons, customer engagement, vendor/product leaderboards, inventory health, and monthly growth "
        "via optimized SQL aggregations. Restricted strictly to ADMIN accounts."
    ),
    responses={
        401: {"description": "Authentication credentials were not provided or are invalid."},
        403: {"description": "Administrator privileges required to access platform executive analytics."},
        422: {"description": "Invalid date range filter supplied."},
    },
    dependencies=[Depends(require_admin)],
)
def executive_summary(
    start_date: Optional[date] = Query(None, description="Inclusive start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Inclusive end date filter (YYYY-MM-DD)"),
    vendor_id: Optional[int] = Query(None, ge=1, description="Optional vendor ID drilldown filter"),
    top_n: int = Query(10, ge=1, le=100, description="Number of top vendors and products to return"),
    db: Session = Depends(get_db),
):
    """Return centralized executive KPIs for administrators with optional date-range & vendor filtering."""
    try:
        return executive_service.get_executive_summary(
            db,
            start_date=start_date,
            end_date=end_date,
            vendor_id=vendor_id,
            top_n=top_n,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/trends",
    response_model=ExecutiveTrendsResponse,
    summary="Executive Sales Trends & Period Comparisons (Admin Only)",
    description=(
        "Returns SQL-aggregated monthly or daily GMV, discounts, refunds, net sales, order volume, AOV, "
        "and chronological period-over-period growth rates alongside window comparisons. Restricted to ADMIN accounts."
    ),
    responses={
        401: {"description": "Authentication credentials were not provided or are invalid."},
        403: {"description": "Administrator privileges required."},
        422: {"description": "Invalid granularity or date range filter."},
    },
    dependencies=[Depends(require_admin)],
)
def executive_trends(
    granularity: str = Query("monthly", description="Time series granularity: 'monthly' or 'daily'"),
    start_date: Optional[date] = Query(None, description="Inclusive start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Inclusive end date filter (YYYY-MM-DD)"),
    vendor_id: Optional[int] = Query(None, ge=1, description="Optional vendor ID filter"),
    db: Session = Depends(get_db),
):
    """Return chronological executive revenue and order trends."""
    try:
        return executive_service.get_executive_trends(
            db,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            vendor_id=vendor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/vendors",
    response_model=ExecutiveVendorProductDrilldownResponse,
    summary="Executive Vendor & Product Performance Breakdown (Admin Only)",
    description=(
        "Returns paginated vendor rankings (GMV, net sales, market share, platform commission, vendor payout) "
        "and top catalog product metrics with verified cost coverage flags. Restricted to ADMIN accounts."
    ),
    responses={
        401: {"description": "Authentication credentials were not provided or are invalid."},
        403: {"description": "Administrator privileges required."},
        422: {"description": "Invalid pagination or date range filter."},
    },
    dependencies=[Depends(require_admin)],
)
def executive_vendors_drilldown(
    start_date: Optional[date] = Query(None, description="Inclusive start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Inclusive end date filter (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0, description="Pagination offset for vendor leaderboard"),
    limit: int = Query(25, ge=1, le=100, description="Maximum vendors and top products to return"),
    db: Session = Depends(get_db),
):
    """Return executive vendor benchmarking and product performance leaderboard."""
    try:
        return executive_service.get_executive_vendors_and_products(
            db,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/vendor-summary",
    response_model=ExecutiveVendorTenantSummaryResponse,
    summary="Tenant-Scoped Vendor Executive KPI Summary (Vendor / Admin)",
    description=(
        "Returns executive-grade financial, customer, product, inventory health, and growth KPIs scoped strictly "
        "to a single vendor tenant. VENDOR callers automatically receive their own store metrics and are blocked "
        "with 403 Forbidden if querying another vendor_id. CUSTOMER accounts are blocked with 403 Forbidden."
    ),
    responses={
        401: {"description": "Authentication credentials were not provided or are invalid."},
        403: {"description": "Access forbidden: role or tenant isolation check failed."},
        404: {"description": "Target vendor profile not found."},
        422: {"description": "Missing vendor_id (for ADMIN) or invalid date range."},
    },
)
def executive_vendor_tenant_summary(
    vendor_id: Optional[int] = Query(None, ge=1, description="Target vendor ID (optional for VENDOR; required for ADMIN)"),
    start_date: Optional[date] = Query(None, description="Inclusive start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Inclusive end date filter (YYYY-MM-DD)"),
    top_n: int = Query(10, ge=1, le=100, description="Maximum top store products to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_vendor_or_admin),
):
    """Return strict tenant-scoped executive KPI summary for a vendor."""
    if current_user.role == UserRole.VENDOR:
        if current_user.vendor_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vendor account is not linked to an active vendor profile.",
            )
        if vendor_id is not None:
            verify_vendor_tenant(current_user, vendor_id)
        target_vendor_id = int(current_user.vendor_id)
    else:
        if vendor_id is None:
            raise HTTPException(
                status_code=422,
                detail="vendor_id query parameter is required for ADMIN tenant lookup.",
            )
        target_vendor_id = vendor_id

    try:
        return executive_service.get_vendor_tenant_executive_summary(
            db,
            vendor_id=target_vendor_id,
            start_date=start_date,
            end_date=end_date,
            top_n=top_n,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
