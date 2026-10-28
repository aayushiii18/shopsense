"""
routes/analytics_routes.py — FastAPI endpoints for sales analytics.

GET /analytics/revenue/total          Total revenue across all transactions
GET /analytics/revenue/by-vendor      Revenue grouped by vendor
GET /analytics/revenue/by-product     Revenue grouped by product
GET /analytics/top-selling-product    Product with highest total units sold
GET /analytics/summary                Combined marketplace summary report
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd

from app.database import get_db
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.product import Product

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _load_transactions_df(db: Session) -> pd.DataFrame:
    """
    Load all transaction rows into a Pandas DataFrame.
    Returns an empty DataFrame (with correct columns) if no data exists.
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


@router.get("/revenue/total", summary="Total revenue across all transactions")
def total_revenue(db: Session = Depends(get_db)):
    """Returns the sum of amount for every transaction."""
    df = _load_transactions_df(db)
    if df.empty:
        return {"total_revenue": 0.0, "transaction_count": 0}
    return {
        "total_revenue": round(float(df["amount"].sum()), 2),
        "transaction_count": int(len(df)),
    }


@router.get("/revenue/by-vendor", summary="Revenue grouped by vendor")
def revenue_by_vendor(db: Session = Depends(get_db)):
    """Returns total revenue and transaction count for each vendor."""
    df = _load_transactions_df(db)
    if df.empty:
        return []

    grouped = (
        df.groupby(["vendor_id", "vendor_name"])
        .agg(
            total_revenue=("amount", "sum"),
            transaction_count=("transaction_id", "count"),
            total_units_sold=("quantity", "sum"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )

    return [
        {
            "vendor_id": int(row["vendor_id"]),
            "vendor_name": row["vendor_name"],
            "total_revenue": round(float(row["total_revenue"]), 2),
            "transaction_count": int(row["transaction_count"]),
            "total_units_sold": int(row["total_units_sold"]),
        }
        for _, row in grouped.iterrows()
    ]


@router.get("/revenue/by-product", summary="Revenue grouped by product")
def revenue_by_product(db: Session = Depends(get_db)):
    """Returns total revenue and units sold for each product."""
    df = _load_transactions_df(db)
    if df.empty:
        return []

    grouped = (
        df.groupby(["product_id", "product_name", "vendor_id"])
        .agg(
            total_revenue=("amount", "sum"),
            total_units_sold=("quantity", "sum"),
            transaction_count=("transaction_id", "count"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )

    return [
        {
            "product_id": int(row["product_id"]),
            "product_name": row["product_name"],
            "vendor_id": int(row["vendor_id"]),
            "total_revenue": round(float(row["total_revenue"]), 2),
            "total_units_sold": int(row["total_units_sold"]),
            "transaction_count": int(row["transaction_count"]),
        }
        for _, row in grouped.iterrows()
    ]


@router.get("/top-selling-product", summary="Product with highest total units sold")
def top_selling_product(db: Session = Depends(get_db)):
    """Returns the product with the most total units sold across all transactions."""
    df = _load_transactions_df(db)
    if df.empty:
        raise HTTPException(status_code=404, detail="No transactions found.")

    by_product = (
        df.groupby(["product_id", "product_name"])["quantity"]
        .sum()
        .reset_index()
    )
    top = by_product.loc[by_product["quantity"].idxmax()]
    return {
        "product_id": int(top["product_id"]),
        "product_name": top["product_name"],
        "total_units_sold": int(top["quantity"]),
    }


@router.get("/summary", summary="Marketplace summary report")
def analytics_summary(db: Session = Depends(get_db)):
    """
    Combined baseline marketplace report:
    - Total revenue & transaction count
    - Number of active vendors & products
    - Top-selling product (by units)
    - Top vendor (by revenue)
    """
    df = _load_transactions_df(db)

    vendor_count = db.query(func.count(Vendor.id)).scalar()
    product_count = db.query(func.count(Product.id)).scalar()

    if df.empty:
        return {
            "total_revenue": 0.0,
            "transaction_count": 0,
            "vendor_count": vendor_count,
            "product_count": product_count,
            "top_selling_product": None,
            "top_vendor_by_revenue": None,
        }

    total_rev = round(float(df["amount"].sum()), 2)

    by_product = df.groupby(["product_id", "product_name"])["quantity"].sum().reset_index()
    top_product = by_product.loc[by_product["quantity"].idxmax()]

    by_vendor = df.groupby(["vendor_id", "vendor_name"])["amount"].sum().reset_index()
    top_vendor = by_vendor.loc[by_vendor["amount"].idxmax()]

    return {
        "total_revenue": total_rev,
        "transaction_count": int(len(df)),
        "vendor_count": vendor_count,
        "product_count": product_count,
        "top_selling_product": {
            "product_id": int(top_product["product_id"]),
            "product_name": top_product["product_name"],
            "total_units_sold": int(top_product["quantity"]),
        },
        "top_vendor_by_revenue": {
            "vendor_id": int(top_vendor["vendor_id"]),
            "vendor_name": top_vendor["vendor_name"],
            "total_revenue": round(float(top_vendor["amount"]), 2),
        },
    }
