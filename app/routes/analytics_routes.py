"""
routes/analytics_routes.py — FastAPI endpoints for sales analytics.

GET /analytics/revenue/total          Total revenue across all transactions
GET /analytics/revenue/by-vendor      Revenue grouped by vendor
GET /analytics/revenue/by-product     Revenue grouped by product
GET /analytics/top-selling-product    Product with highest total units sold
GET /analytics/summary                Combined marketplace summary report
GET /analytics/transactions           Paginated list of transactions
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd

from app.database import get_db
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.user import User, UserRole
from app.core.dependencies import get_current_user
from app.schemas.revenue_schema import (
    TotalRevenueSummaryResponse,
    VendorRevenueItem,
    ProductRevenueItem,
    TopSellingProductResponse,
    AnalyticsSummaryResponse,
    TransactionListItem,
)

router = APIRouter(prefix="/analytics", tags=["Sales API", "Analytics"])


def _load_transactions_df(db: Session) -> pd.DataFrame:
    """
    Load all transaction rows into a Pandas DataFrame.
    Retained for backward compatibility and analytical consumers.
    """
    rows = (
        db.query(
            Transaction.transaction_id,
            Transaction.product_id,
            Transaction.vendor_id,
            Transaction.quantity,
            Transaction.unit_price,
            Transaction.amount,
            Transaction.transaction_date,
            Product.name.label("product_name"),
            Vendor.name.label("vendor_name"),
        )
        .join(Product, Transaction.product_id == Product.id)
        .join(Vendor, Transaction.vendor_id == Vendor.id)
        .all()
    )

    if not rows:
        return pd.DataFrame(
            columns=[
                "transaction_id", "product_id", "vendor_id", "quantity",
                "unit_price", "amount", "transaction_date",
                "product_name", "vendor_name",
            ]
        )

    return pd.DataFrame(rows, columns=[
        "transaction_id", "product_id", "vendor_id", "quantity",
        "unit_price", "amount", "transaction_date",
        "product_name", "vendor_name",
    ])


@router.get(
    "/revenue/total",
    response_model=TotalRevenueSummaryResponse,
    summary="Total revenue across all transactions",
)
def total_revenue(db: Session = Depends(get_db)):
    """Returns the sum of amount and transaction count across all transactions via optimized SQL."""
    row = (
        db.query(
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total_rev"),
            func.count(Transaction.transaction_id).label("tx_count"),
        )
        .first()
    )
    rev = round(float(row.total_rev if row and row.total_rev is not None else 0.0), 2)
    cnt = int(row.tx_count if row and row.tx_count is not None else 0)
    return {
        "total_revenue": rev,
        "transaction_count": cnt,
    }


@router.get(
    "/revenue/by-vendor",
    response_model=List[VendorRevenueItem],
    summary="Revenue grouped by vendor",
)
def revenue_by_vendor(db: Session = Depends(get_db)):
    """Returns total revenue, units sold, and transaction count for each vendor via optimized SQL."""
    rows = (
        db.query(
            Transaction.vendor_id,
            Vendor.name.label("vendor_name"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total_revenue"),
            func.count(Transaction.transaction_id).label("transaction_count"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_units_sold"),
        )
        .join(Vendor, Transaction.vendor_id == Vendor.id)
        .group_by(Transaction.vendor_id, Vendor.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    return [
        {
            "vendor_id": int(r.vendor_id),
            "vendor_name": r.vendor_name,
            "total_revenue": round(float(r.total_revenue), 2),
            "transaction_count": int(r.transaction_count),
            "total_units_sold": int(r.total_units_sold),
        }
        for r in rows
    ]


@router.get(
    "/revenue/by-product",
    response_model=List[ProductRevenueItem],
    summary="Revenue grouped by product",
)
def revenue_by_product(db: Session = Depends(get_db)):
    """Returns total revenue, units sold, and transaction count for each product via optimized SQL."""
    rows = (
        db.query(
            Transaction.product_id,
            Product.name.label("product_name"),
            Transaction.vendor_id,
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total_revenue"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_units_sold"),
            func.count(Transaction.transaction_id).label("transaction_count"),
        )
        .join(Product, Transaction.product_id == Product.id)
        .group_by(Transaction.product_id, Product.name, Transaction.vendor_id)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    return [
        {
            "product_id": int(r.product_id),
            "product_name": r.product_name,
            "vendor_id": int(r.vendor_id),
            "total_revenue": round(float(r.total_revenue), 2),
            "total_units_sold": int(r.total_units_sold),
            "transaction_count": int(r.transaction_count),
        }
        for r in rows
    ]


@router.get(
    "/top-selling-product",
    response_model=TopSellingProductResponse,
    summary="Product with highest total units sold",
)
def top_selling_product(db: Session = Depends(get_db)):
    """Returns the product with the most total units sold across all transactions via optimized SQL."""
    top = (
        db.query(
            Transaction.product_id,
            Product.name.label("product_name"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_units_sold"),
        )
        .join(Product, Transaction.product_id == Product.id)
        .group_by(Transaction.product_id, Product.name)
        .order_by(func.sum(Transaction.quantity).desc(), Transaction.product_id.asc())
        .first()
    )
    if not top:
        raise HTTPException(status_code=404, detail="No transactions found.")
    return {
        "product_id": int(top.product_id),
        "product_name": top.product_name,
        "total_units_sold": int(top.total_units_sold),
    }


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Marketplace summary report",
)
def analytics_summary(db: Session = Depends(get_db)):
    """
    Combined baseline marketplace report via direct database aggregations:
    - Total revenue & transaction count
    - Number of active vendors & products
    - Top-selling product (by units)
    - Top vendor (by revenue)
    """
    vendor_count = db.query(func.count(Vendor.id)).scalar() or 0
    product_count = db.query(func.count(Product.id)).scalar() or 0

    totals = (
        db.query(
            func.coalesce(func.sum(Transaction.amount), 0.0),
            func.count(Transaction.transaction_id),
        )
        .first()
    )
    total_rev = round(float(totals[0] if totals and totals[0] is not None else 0.0), 2)
    tx_count = int(totals[1] if totals and totals[1] is not None else 0)

    if tx_count == 0:
        return {
            "total_revenue": 0.0,
            "transaction_count": 0,
            "vendor_count": vendor_count,
            "product_count": product_count,
            "top_selling_product": None,
            "top_vendor_by_revenue": None,
        }

    top_prod = (
        db.query(
            Transaction.product_id,
            Product.name.label("product_name"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_units_sold"),
        )
        .join(Product, Transaction.product_id == Product.id)
        .group_by(Transaction.product_id, Product.name)
        .order_by(func.sum(Transaction.quantity).desc(), Transaction.product_id.asc())
        .first()
    )

    top_vend = (
        db.query(
            Transaction.vendor_id,
            Vendor.name.label("vendor_name"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("amount"),
        )
        .join(Vendor, Transaction.vendor_id == Vendor.id)
        .group_by(Transaction.vendor_id, Vendor.name)
        .order_by(func.sum(Transaction.amount).desc(), Transaction.vendor_id.asc())
        .first()
    )

    return {
        "total_revenue": total_rev,
        "transaction_count": tx_count,
        "vendor_count": vendor_count,
        "product_count": product_count,
        "top_selling_product": {
            "product_id": int(top_prod.product_id),
            "product_name": top_prod.product_name,
            "total_units_sold": int(top_prod.total_units_sold),
        } if top_prod else None,
        "top_vendor_by_revenue": {
            "vendor_id": int(top_vend.vendor_id),
            "vendor_name": top_vend.vendor_name,
            "total_revenue": round(float(top_vend.amount), 2),
        } if top_vend else None,
    }


@router.get(
    "/transactions",
    response_model=List[TransactionListItem],
    summary="List transactions with joined product and vendor details",
)
def list_transactions(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of transactions to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent transaction records with join details, paginated and tenant-filtered by caller role."""
    query = (
        db.query(
            Transaction.transaction_id,
            Transaction.product_id,
            Product.name.label("product_name"),
            Product.category.label("category"),
            Transaction.vendor_id,
            Vendor.name.label("vendor_name"),
            Transaction.customer_id,
            Transaction.quantity,
            Transaction.unit_price,
            Transaction.amount,
            Transaction.payment_method,
            Transaction.payment_status,
            Transaction.transaction_date,
        )
        .join(Product, Transaction.product_id == Product.id)
        .join(Vendor, Transaction.vendor_id == Vendor.id)
    )

    if current_user.role == UserRole.VENDOR:
        query = query.filter(Transaction.vendor_id == current_user.vendor_id)
    elif current_user.role == UserRole.CUSTOMER:
        query = query.filter(Transaction.customer_id == current_user.customer_id)

    rows = (
        query.order_by(Transaction.transaction_date.desc(), Transaction.transaction_id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "transaction_id": r.transaction_id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "category": r.category or "General",
            "vendor_id": r.vendor_id,
            "vendor_name": r.vendor_name,
            "customer_id": r.customer_id,
            "quantity": r.quantity,
            "unit_price": float(r.unit_price) if r.unit_price is not None else round(float(r.amount) / r.quantity, 2),
            "amount": float(r.amount),
            "payment_method": getattr(r, "payment_method", "UNKNOWN") or "UNKNOWN",
            "payment_status": getattr(r, "payment_status", "COMPLETED") or "COMPLETED",
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
        }
        for r in rows
    ]


@router.get("/pipeline/audit", summary="Get automated analytical pipeline audit records")
def get_pipeline_audit_logs(limit: int = 10, db: Session = Depends(get_db)):
    """Returns recent audit execution records for the background analytical pipeline."""
    from app.scheduler import get_workflow_audit_logs
    return get_workflow_audit_logs(db=db, limit=limit)


@router.post("/pipeline/run", summary="Trigger manual run of the analytical pipeline")
def trigger_pipeline_run(db: Session = Depends(get_db)):
    """Manually triggers the full analytical pipeline and records execution in the audit log."""
    from app.scheduler import run_analytical_pipeline
    report = run_analytical_pipeline(db=db)
    return report
