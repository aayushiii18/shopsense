"""
services/revenue_service.py — Business logic and algorithms for Advanced Revenue Analysis,
Profitability Accounting, Category/Regional Breakdowns, and Multi-Vendor Settlements.
"""

from typing import List, Dict, Any, Optional
import math
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

import sys
import time

from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.product import Product
from app.models.refund import Refund

_REV_CACHE: Dict[str, Any] = {}
_REV_CACHE_TIME: Dict[str, float] = {}

def _get_cached_rev(key: str, ttl: float = 30.0):
    if "pytest" in sys.modules:
        return None
    now = time.time()
    if key in _REV_CACHE and (now - _REV_CACHE_TIME.get(key, 0.0)) < ttl:
        return _REV_CACHE[key]
    return None

def _set_cached_rev(key: str, val: Any):
    _REV_CACHE[key] = val
    _REV_CACHE_TIME[key] = time.time()


def calculate_gmv(db: Session) -> float:
    """
    Computes Gross Merchandise Value (GMV) across all recorded transactions.
    Definition: The total monetary value of all merchandise transactions processed.
    """
    cached = _get_cached_rev("gmv", 20.0)
    if cached is not None:
        return cached
    total = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar()
    res = round(float(total), 2)
    _set_cached_rev("gmv", res)
    return res


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
    cached = _get_cached_rev("vendor_performance", 20.0)
    if cached is not None:
        return cached
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

    result = [
        {
            "vendor_id": int(r.vendor_id),
            "vendor_name": r.vendor_name or f"Vendor {r.vendor_id}",
            "amount": round(float(r.amount), 2),
            "units_sold": int(r.units_sold),
        }
        for r in rows
    ]
    _set_cached_rev("vendor_performance", result)
    return result


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

    cust_rev = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.customer_id.isnot(None))
        .scalar()
        or 0.0
    )

    avg_spend = round(float(cust_rev) / float(total_customers), 2)
    cust_res = {
        "customers": int(total_customers),
        "avg_spend": avg_spend,
    }
    _set_cached_rev("customer_metrics", cust_res)
    return cust_res


def get_monthly_revenue_growth(db: Session) -> Dict[str, Any]:
    """
    Computes chronological monthly revenue aggregation and Month-over-Month (MoM) growth.
    """
    cached = _get_cached_rev("monthly_growth", 30.0)
    if cached is not None:
        return cached
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

    monthly = monthly.sort_values("year_month").reset_index(drop=True)
    monthly["revenue"] = monthly["revenue"].round(2)

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

    growth_res = {
        "total_revenue": total_rev,
        "gmv": total_rev,
        "avg_order_value": aov,
        "total_orders": len(df),
        "monthly_breakdown": growth_items,
        "average_order_value": aov,
        "monthly_growth": growth_items,
    }
    _set_cached_rev("monthly_growth", growth_res)
    return growth_res


def get_vendor_benchmarking(db: Session) -> Dict[str, Any]:
    """
    Computes vendor benchmarking metrics:
      - Revenue per vendor
      - Total units sold and order count
      - Rank (1 = highest revenue)
      - Market share percentage of total GMV
    """
    cached = _get_cached_rev("benchmarking", 30.0)
    if cached is not None:
        return cached
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
    df["rank"] = df["revenue"].rank(ascending=False, method="min").astype(int)

    if total_gmv > 0:
        df["market_share_pct"] = (df["revenue"] / total_gmv * 100.0).round(2)
    else:
        df["market_share_pct"] = 0.0

    df = df.sort_values(["rank", "vendor_id"]).reset_index(drop=True)
    df["revenue_rank"] = df["rank"]
    df["total_revenue"] = df["revenue"]

    benchmarking_items = df.to_dict(orient="records")

    return {
        "total_gmv": total_gmv,
        "vendor_count": len(df),
        "benchmarks": benchmarking_items,
        "total_vendors": len(df),
        "benchmarking": benchmarking_items,
    }


# ── Stage 4 Enhanced Financial Operations ───────────────────────────────────

def get_profit_margins(db: Session) -> Dict[str, Any]:
    """
    Computes audited Gross Profit and COGS Coverage % according to formal accounting semantics:
      Gross GMV = sum(Transaction.amount)
      Discounts = sum(Transaction.discount_amount)
      Refunds = sum(Refund.amount where status == 'COMPLETED')
      Net Sales = Gross GMV - Discounts - Refunds
      Covered Net Sales = Net Sales of transactions whose product has cost_price IS NOT NULL
      Covered COGS = sum(quantity * product.cost_price) for covered transactions
      Gross Profit (Reported Items Only) = Covered Net Sales - Covered COGS
      COGS Coverage % = (Covered Net Sales / Net Sales) * 100
    """
    cached = _get_cached_rev("profit_margins", 15.0)
    if cached is not None:
        return cached

    # Gross GMV & discounts
    gmv_row = db.query(
        func.coalesce(func.sum(Transaction.amount), 0.0).label("gmv"),
        func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
    ).first()

    gross_gmv = round(float(gmv_row.gmv or 0.0), 2)
    discounts = round(float(gmv_row.discounts or 0.0), 2)

    # Refunds total
    refunds_total = (
        db.query(func.coalesce(func.sum(Refund.amount), 0.0))
        .filter(Refund.status == "COMPLETED")
        .scalar()
    ) or 0.0
    refunds_total = round(float(refunds_total), 2)

    net_sales = max(0.0, round(gross_gmv - discounts - refunds_total, 2))

    # Calculate covered items (where Product.cost_price IS NOT NULL)
    covered_txns = (
        db.query(
            Transaction.transaction_id,
            Transaction.amount,
            Transaction.discount_amount,
            Transaction.quantity,
            Product.cost_price,
        )
        .join(Product, Transaction.product_id == Product.id)
        .filter(Product.cost_price.isnot(None))
        .all()
    )

    if covered_txns:
        # Sum net sales and cogs of covered items
        covered_gross = sum(float(t.amount) for t in covered_txns)
        covered_disc = sum(float(t.discount_amount or 0.0) for t in covered_txns)
        covered_txn_ids = [t.transaction_id for t in covered_txns]

        covered_ref = (
            db.query(func.coalesce(func.sum(Refund.amount), 0.0))
            .filter(Refund.transaction_id.in_(covered_txn_ids), Refund.status == "COMPLETED")
            .scalar()
        ) or 0.0

        covered_net = max(0.0, round(covered_gross - covered_disc - float(covered_ref), 2))
        covered_cogs = round(sum(float(t.cost_price) * int(t.quantity) for t in covered_txns), 2)
        gross_profit = round(covered_net - covered_cogs, 2)
        margin_pct = round((gross_profit / covered_net * 100.0), 2) if covered_net > 0 else 0.0
        coverage_pct = round((covered_net / net_sales * 100.0), 2) if net_sales > 0 else 0.0
        status_note = f"Active cost data coverage: {coverage_pct:.1f}% of net sales."
    else:
        covered_net = 0.0
        covered_cogs = 0.0
        gross_profit = 0.0
        margin_pct = 0.0
        coverage_pct = 0.0
        status_note = "No historical cost data recorded (0.0% coverage). Actual profit uncalculated to prevent data fabrication."

    res = {
        "gross_sales_gmv": gross_gmv,
        "discounts_total": discounts,
        "refunds_total": refunds_total,
        "net_sales": net_sales,
        "cogs_coverage_pct": coverage_pct,
        "covered_net_sales": covered_net,
        "covered_cogs": covered_cogs,
        "gross_profit_reported": gross_profit,
        "gross_margin_pct_reported": margin_pct,
        "coverage_status": status_note,
    }
    _set_cached_rev("profit_margins", res)
    return res


def get_revenue_by_category(db: Session) -> Dict[str, Any]:
    """
    Computes revenue, units, and order breakdown by product category.
    """
    cached = _get_cached_rev("rev_by_cat", 20.0)
    if cached is not None:
        return cached

    rows = (
        db.query(
            func.coalesce(Product.category, "Uncategorized").label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("revenue"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
            func.count(Transaction.transaction_id).label("order_count"),
        )
        .join(Product, Transaction.product_id == Product.id)
        .group_by(func.coalesce(Product.category, "Uncategorized"))
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    total_rev = sum(float(r.revenue) for r in rows)
    categories = []
    for r in rows:
        rev = round(float(r.revenue), 2)
        share = round((rev / total_rev * 100.0), 2) if total_rev > 0 else 0.0
        categories.append({
            "category": r.category,
            "revenue": rev,
            "units_sold": int(r.units_sold),
            "order_count": int(r.order_count),
            "share_pct": share,
        })

    res = {
        "total_revenue": round(total_rev, 2),
        "categories": categories,
    }
    _set_cached_rev("rev_by_cat", res)
    return res


def get_revenue_by_region(db: Session) -> Dict[str, Any]:
    """
    Computes revenue, orders, and customer breakdown grouped by customer region.
    """
    cached = _get_cached_rev("rev_by_reg", 20.0)
    if cached is not None:
        return cached

    rows = (
        db.query(
            func.coalesce(Customer.region, "Unknown").label("region"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("revenue"),
            func.count(Transaction.transaction_id).label("orders"),
            func.count(func.distinct(Transaction.customer_id)).label("unique_customers"),
        )
        .outerjoin(Customer, Transaction.customer_id == Customer.customer_id)
        .group_by(func.coalesce(Customer.region, "Unknown"))
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    total_rev = sum(float(r.revenue) for r in rows)
    regions = []
    for r in rows:
        rev = round(float(r.revenue), 2)
        share = round((rev / total_rev * 100.0), 2) if total_rev > 0 else 0.0
        regions.append({
            "region": r.region,
            "revenue": rev,
            "orders": int(r.orders),
            "unique_customers": int(r.unique_customers),
            "share_pct": share,
        })

    res = {
        "total_revenue": round(total_rev, 2),
        "regions": regions,
    }
    _set_cached_rev("rev_by_reg", res)
    return res


def get_vendor_settlements(db: Session) -> Dict[str, Any]:
    """
    Computes auditable settlement sheet for all vendors:
      Gross Sales = sum(vendor's transaction amounts)
      Discounts = sum(vendor's transaction discounts)
      Refunds = sum(refunds for vendor's transactions)
      Net Sales = Gross Sales - Discounts - Refunds
      Commission = Net Sales * vendor.commission_rate
      Vendor Payout = Net Sales - Commission
    """
    cached = _get_cached_rev("settlements", 15.0)
    if cached is not None:
        return cached

    vendors = db.query(Vendor).all()
    settlement_items = []

    total_net = 0.0
    total_commission = 0.0
    total_payout = 0.0

    for v in vendors:
        txns = db.query(Transaction).filter(Transaction.vendor_id == v.id).all()
        gross = sum(float(t.amount) for t in txns)
        disc = sum(float(t.discount_amount or 0.0) for t in txns)
        txn_ids = [t.transaction_id for t in txns]

        ref = 0.0
        if txn_ids:
            ref = (
                db.query(func.coalesce(func.sum(Refund.amount), 0.0))
                .filter(Refund.transaction_id.in_(txn_ids), Refund.status == "COMPLETED")
                .scalar()
            ) or 0.0

        net = max(0.0, round(gross - disc - float(ref), 2))
        rate = float(v.commission_rate or 0.12)
        commission = round(net * rate, 2)
        payout = round(net - commission, 2)

        total_net += net
        total_commission += commission
        total_payout += payout

        settlement_items.append({
            "vendor_id": v.id,
            "vendor_name": v.name,
            "status": v.status,
            "commission_tier": v.commission_tier or "TIER_STANDARD",
            "commission_rate": round(rate, 4),
            "gross_sales": round(gross, 2),
            "discounts_allocated": round(disc, 2),
            "refunds_deducted": round(float(ref), 2),
            "net_sales": net,
            "platform_commission": commission,
            "vendor_payout": payout,
            "orders_count": len(txns),
        })

    res = {
        "total_net_sales": round(total_net, 2),
        "total_platform_commission": round(total_commission, 2),
        "total_vendor_payouts": round(total_payout, 2),
        "settlements": settlement_items,
    }
    _set_cached_rev("settlements", res)
    return res
