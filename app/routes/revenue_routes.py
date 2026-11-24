"""
routes/revenue_routes.py — FastAPI endpoints for Advanced Revenue Analysis, Profit Margins,
Category & Regional Breakdowns, and Multi-Vendor Settlements.

Endpoints:
  GET  /analytics/revenue               Total gross merchandise value (GMV)
  GET  /analytics/vendor-performance    Vendor-wise revenue aggregation
  GET  /analytics/revenue/growth        Chronological MoM revenue growth rates
  GET  /analytics/revenue/benchmarking  Vendor benchmarking, ranking & market share
  GET  /analytics/revenue/profit-margins Audited gross profit & COGS coverage %
  GET  /analytics/revenue/by-category   Category revenue breakdown
  GET  /analytics/revenue/by-region     Regional customer revenue breakdown
  GET  /analytics/vendors/payouts       Multi-vendor settlement sheet (Loopback-Guarded)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import revenue_service
from app.schemas.revenue_schema import (
    TotalRevenueResponse,
    VendorPerformanceItem,
    RevenueGrowthResponse,
    VendorBenchmarkResponse,
    ProfitMarginResponse,
    CategoryRevenueResponse,
    RegionalRevenueResponse,
    VendorSettlementResponse,
)
from app.core.dependencies import require_vendor_or_admin
from app.models.user import User, UserRole

router = APIRouter(tags=["Revenue & Vendor Analytics"])


@router.get(
    "/analytics/revenue",
    response_model=TotalRevenueResponse,
    summary="Total Gross Merchandise Value (GMV)",
)
def revenue_analysis(db: Session = Depends(get_db)):
    """Returns total revenue / GMV across all recorded marketplace transactions."""
    return revenue_service.get_total_revenue(db)


@router.get(
    "/analytics/vendor-performance",
    response_model=List[VendorPerformanceItem],
    summary="Vendor Sales Performance Aggregation",
)
def vendor_performance(db: Session = Depends(get_db)):
    """Returns total revenue and units sold grouped by vendor."""
    return revenue_service.get_vendor_performance(db)


@router.get(
    "/analytics/revenue/growth",
    response_model=RevenueGrowthResponse,
    summary="Month-over-Month (MoM) Revenue Growth Analytics",
)
def revenue_growth(db: Session = Depends(get_db)):
    """Returns chronological monthly revenue breakdown with Month-over-Month (MoM) growth percentages."""
    return revenue_service.get_monthly_revenue_growth(db)


@router.get(
    "/analytics/revenue/benchmarking",
    response_model=VendorBenchmarkResponse,
    summary="Marketplace Vendor Revenue Benchmarking & Market Share",
)
def vendor_benchmarking(db: Session = Depends(get_db)):
    """Returns ranked vendor benchmarking with total revenue, units sold, order count, and market share."""
    return revenue_service.get_vendor_benchmarking(db)


@router.get(
    "/analytics/revenue/profit-margins",
    response_model=ProfitMarginResponse,
    summary="Gross Profit & COGS Coverage Analysis",
)
def profit_margin_analysis(db: Session = Depends(get_db)):
    """
    Computes audited Gross Profit and COGS Coverage % according to formal accounting rules:
      - Excludes uncosted legacy items from actual profit calculations.
      - Accurately reports coverage % to prevent data fabrication.
    """
    return revenue_service.get_profit_margins(db)


@router.get(
    "/analytics/revenue/by-category",
    response_model=CategoryRevenueResponse,
    summary="Revenue Breakdown by Category",
)
def revenue_by_category(db: Session = Depends(get_db)):
    """Returns merchandise sales breakdown grouped by product category."""
    return revenue_service.get_revenue_by_category(db)


@router.get(
    "/analytics/revenue/by-region",
    response_model=RegionalRevenueResponse,
    summary="Revenue Breakdown by Region",
)
def revenue_by_region(db: Session = Depends(get_db)):
    """Returns sales breakdown grouped by customer geographical region."""
    return revenue_service.get_revenue_by_region(db)


@router.get(
    "/analytics/vendors/payouts",
    response_model=VendorSettlementResponse,
    summary="Vendor Settlement Sheet & Payouts (Role-Protected)",
)
def vendor_settlement_sheet(
    vendor_id: Optional[int] = Query(None, description="Optional vendor ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_vendor_or_admin),
):
    """
    Returns auditable settlement ledger for vendors with net sales, commissions, and payable balances.
    - ADMIN: full visibility across all vendors, or filtered by vendor_id.
    - VENDOR: strictly tenant-isolated to own vendor_id. Requests for other vendors fail with 403 Forbidden.
    """
    if current_user.role == UserRole.VENDOR:
        if vendor_id is not None and vendor_id != current_user.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You cannot view settlement data for another vendor.",
            )
        target_vendor_id = current_user.vendor_id
    else:
        target_vendor_id = vendor_id

    return revenue_service.get_vendor_settlements(db, vendor_id=target_vendor_id)
