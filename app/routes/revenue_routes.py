"""
routes/revenue_routes.py — FastAPI endpoints for Advanced Revenue Analysis.
Milestone 3 Modules 1 & 2.

Endpoints:
  GET  /analytics/revenue               Total gross merchandise value (GMV)
  GET  /analytics/vendor-performance    Vendor-wise revenue aggregation
  GET  /analytics/revenue/growth        Chronological MoM revenue growth rates
  GET  /analytics/revenue/benchmarking  Vendor benchmarking, ranking & market share
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
)

router = APIRouter(tags=["Revenue & Vendor Analytics"])


@router.get(
    "/analytics/revenue",
    response_model=TotalRevenueResponse,
    summary="Total Gross Merchandise Value (GMV)",
)
def revenue_analysis(db: Session = Depends(get_db)):
    """
    Returns total revenue / GMV across all recorded marketplace transactions.
    """
    return revenue_service.get_total_revenue(db)


@router.get(
    "/analytics/vendor-performance",
    response_model=List[VendorPerformanceItem],
    summary="Vendor Sales Performance Aggregation",
)
def vendor_performance(db: Session = Depends(get_db)):
    """
    Returns total revenue and units sold grouped by vendor.
    """
    return revenue_service.get_vendor_performance(db)


@router.get(
    "/analytics/revenue/growth",
    response_model=RevenueGrowthResponse,
    summary="Month-over-Month (MoM) Revenue Growth Analytics",
)
def revenue_growth(db: Session = Depends(get_db)):
    """
    Returns chronological monthly revenue breakdown with Month-over-Month (MoM) growth percentages.
    The first month is treated as the baseline (null MoM growth).
    """
    return revenue_service.get_monthly_revenue_growth(db)


@router.get(
    "/analytics/revenue/benchmarking",
    response_model=VendorBenchmarkResponse,
    summary="Marketplace Vendor Revenue Benchmarking & Market Share",
)
def vendor_benchmarking(db: Session = Depends(get_db)):
    """
    Returns ranked vendor benchmarking with total revenue, units sold, order count,
    revenue ranking (1 = highest revenue), and percentage market share.
    """
    return revenue_service.get_vendor_benchmarking(db)
