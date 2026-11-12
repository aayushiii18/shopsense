"""
services/revenue_service.py — Business logic and algorithms for Advanced Revenue Analysis.
Milestone 3 Module 2.

Features:
  1. GMV (Gross Merchandise Value) Calculation.
  2. Average Order Value (AOV) based on transaction ledger records.
  3. Chronological Monthly Revenue Aggregation.
  4. Month-over-Month (MoM) Revenue Growth Percentage with baseline handling.
  5. Marketplace Vendor Benchmarking, Revenue Ranking, and Market Share Percentages.
  6. Customer Spending Metrics.
"""

from typing import List, Dict, Any, Optional
import math
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.customer import Customer


def calculate_gmv(db: Session) -> float:
    """
    Computes Gross Merchandise Value (GMV) across all recorded transactions.
    Definition: The total monetary value of all merchandise transactions processed.
    """
    total = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar()
    return round(float(total), 2)


def avg_order_value(db: Session) -> float:
    """
    Computes Average Order Value (AOV) across all recorded transactions.
    Definition: GMV / Total transaction count. Returns 0.0 if no transactions exist.
    """
    row = (
        db.query(
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total_amount"),
            func.count(Transaction.transaction_id).label("total_orders"),
        )
        .first()
    )
    if not row or row.total_orders == 0:
        return 0.0
    return round(float(row.total_amount) / float(row.total_orders), 2)


def get_total_revenue(db: Session) -> Dict[str, float]:
    """
    Returns total revenue formatted for GET /analytics/revenue.
    """
    return {"total_revenue": calculate_gmv(db)}


def get_vendor_performance(db: Session) -> List[Dict[str, Any]]:
    """
    Aggregates vendor sales performance across all transactions.
    Returns list of vendor-wise revenue and unit counts.
    """
    rows = (
        db.query(
            Transaction.vendor_id,
            Vendor.name.label("vendor_name"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("amount"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        )
        .outerjoin(Vendor, Transaction.vendor_id == Vendor.id)
        .group_by(Transaction.vendor_id, Vendor.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    if not rows:
        return []

    return [
        {
            "vendor_id": int(r.vendor_id),
            "vendor_name": r.vendor_name or f"Vendor {r.vendor_id}",
            "amount": round(float(r.amount), 2),
            "units_sold": int(r.units_sold),
        }
        for r in rows
    ]


def get_customer_metrics(db: Session) -> Dict[str, Any]:
    """
    Computes customer volume and average customer lifetime spend.
    Definition:
      customers: Total registered customer count in the customer registry.
      avg_spend: Total transaction amount attributed to customers / total customers.
    """
    total_customers = db.query(func.count(Customer.customer_id)).scalar() or 0
    if total_customers == 0:
        return {"customers": 0, "avg_spend": 0.0}

    # Sum of customer spend (transactions with customer_id)
    cust_rev = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.customer_id.isnot(None))
        .scalar()
        or 0.0
    )

    avg_spend = round(float(cust_rev) / float(total_customers), 2)
    return {
        "customers": int(total_customers),
        "avg_spend": avg_spend,
    }


def get_monthly_revenue_growth(db: Session) -> Dict[str, Any]:
    """
    Computes chronological monthly revenue aggregation and Month-over-Month (MoM) growth.
    Formula:
      MoM Growth (%) = ((Revenue_t - Revenue_{t-1}) / Revenue_{t-1}) * 100
    Edge cases:
      - Empty transaction history: returns 0.0 GMV, 0.0 AOV, empty monthly list.
      - First month: mom_growth_pct is None (baseline, no previous month exists).
      - Zero previous month revenue with current positive revenue: growth is 100.0%.
    """
    txns = (
        db.query(
            Transaction.amount,
            Transaction.quantity,
            Transaction.transaction_date,
        )
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    if not txns:
        return {
            "total_revenue": 0.0,
            "average_order_value": 0.0,
            "monthly_growth": [],
        }

    df = pd.DataFrame([
        {
            "amount": float(t.amount),
            "quantity": int(t.quantity),
            "date": pd.to_datetime(t.transaction_date),
        }
        for t in txns
    ])

    total_rev = round(float(df["amount"].sum()), 2)
    aov = round(total_rev / len(df), 2) if len(df) > 0 else 0.0

    df["year_month"] = df["date"].dt.to_period("M").astype(str)
    df["month"] = df["date"].dt.month

    monthly = (
        df.groupby(["year_month", "month"])
        .agg(
            revenue=("amount", "sum"),
            units=("quantity", "sum"),
            orders=("amount", "count"),
        )
        .reset_index()
    )

    # Sort strictly chronologically by year_month
    monthly = monthly.sort_values("year_month").reset_index(drop=True)
    monthly["revenue"] = monthly["revenue"].round(2)

    # Calculate MoM growth percentage
    growth_items: List[Dict[str, Any]] = []
    prev_rev: Optional[float] = None

    for idx, row in monthly.iterrows():
        rev = float(row["revenue"])
        if idx == 0 or prev_rev is None:
            growth_pct = None
            note = "Baseline month - no previous comparison"
        elif prev_rev == 0.0:
            growth_pct = 100.0 if rev > 0 else 0.0
            note = "Previous month had zero revenue"
        else:
            growth_pct = round(((rev - prev_rev) / prev_rev) * 100.0, 2)
            note = None

        prev_rev = rev
        growth_items.append({
            "year_month": str(row["year_month"]),
            "month": int(row["month"]),
            "revenue": rev,
            "units": int(row["units"]),
            "orders": int(row["orders"]),
            "mom_growth_pct": growth_pct,
            "note": note,
        })

    return {
        "total_revenue": total_rev,
        "average_order_value": aov,
        "monthly_growth": growth_items,
    }


def get_vendor_benchmarking(db: Session) -> Dict[str, Any]:
    """
    Computes vendor benchmarking metrics:
      - Revenue per vendor
      - Total units sold and order count
      - Rank (1 = highest revenue, minimum dense rank for ties)
      - Market share percentage of total GMV (sum of market share = 100.0%)
    """
    rows = (
        db.query(
            Transaction.vendor_id,
            Vendor.name.label("vendor_name"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("revenue"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
            func.count(Transaction.transaction_id).label("order_count"),
        )
        .outerjoin(Vendor, Transaction.vendor_id == Vendor.id)
        .group_by(Transaction.vendor_id, Vendor.name)
        .all()
    )

    if not rows:
        return {
            "total_gmv": 0.0,
            "total_vendors": 0,
            "benchmarking": [],
        }

    df = pd.DataFrame([
        {
            "vendor_id": int(r.vendor_id),
            "vendor_name": r.vendor_name or f"Vendor {r.vendor_id}",
            "revenue": round(float(r.revenue), 2),
            "units_sold": int(r.units_sold),
            "order_count": int(r.order_count),
        }
        for r in rows
    ])

    total_gmv = round(float(df["revenue"].sum()), 2)

    # Rank descending (rank 1 is highest)
    df["rank"] = df["revenue"].rank(ascending=False, method="min").astype(int)

    # Market share percentage
    if total_gmv > 0:
        df["market_share_pct"] = (df["revenue"] / total_gmv * 100.0).round(2)
    else:
        df["market_share_pct"] = 0.0

    # Sort by rank ascending (top vendors first)
    df = df.sort_values(["rank", "vendor_id"]).reset_index(drop=True)

    benchmarking_items = df.to_dict(orient="records")

    return {
        "total_gmv": total_gmv,
        "total_vendors": len(df),
        "benchmarking": benchmarking_items,
    }
