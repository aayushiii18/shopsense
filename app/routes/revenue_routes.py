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

from typing import List
from fastapi import APIRouter, Depends
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
from app.core.security import verify_loopback_only

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
    summary="Vendor Settlement Sheet & Payouts (Loopback-Guarded)",
    dependencies=[Depends(verify_loopback_only)],
)
def vendor_settlement_sheet(db: Session = Depends(get_db)):
    """
    Returns auditable settlement ledger for all vendors with net sales, commissions, and payable balances.
    Restricted to local administrative loopback interface.
    """
    return revenue_service.get_vendor_settlements(db)
