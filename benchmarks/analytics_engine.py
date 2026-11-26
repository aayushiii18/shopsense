"""
benchmarks/analytics_engine.py — Vectorized Analytics Suite for 100K+ Transaction Benchmarking.

Implements ShopSense's production analytical formulas (`revenue_service.py`, `customer_service.py`,
`daily_mart_service.py`) using vectorized Pandas/NumPy operations cleanly isolated from PostgreSQL:
  1. Total Revenue / Gross GMV, Discounts & Net Sales
  2. Average Transaction Value (AOV) & Order Basket Metrics
  3. Vendor-Level Sales Aggregation, Rank, Market Share & Commission Payouts
  4. Product-Level Sales Aggregation & COGS Margin Evaluation
  5. Category & Payment Method Revenue Distribution
  6. Chronological Monthly MoM Growth & Daily Sales Trends
  7. Customer RFM Segmentation Features (Recency, Frequency, Monetary, Active 90d, Repeat Rate)
  8. Dimensional Daily Sales Mart Aggregation (`(date, product_id, vendor_id)` grain)
"""

from __future__ import annotations

import time
from typing import Dict, Any, Tuple, Callable

import numpy as np
import pandas as pd


def _timed_op(name: str, fn: Callable[[], Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Execute one benchmark operation and capture exact wall-clock latency."""
    t0 = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    timing = {"operation": name, "elapsed_ms": round(elapsed_ms, 3)}
    return result, timing


def compute_total_revenue_and_gmv(df: pd.DataFrame) -> Dict[str, Any]:
    """Vectorized calculation matching `revenue_service.calculate_gmv` & net sales accounting."""
    total_gmv = round(float(df["amount"].sum()), 2)
    total_discounts = round(float(df["discount_amount"].sum()), 2)
    net_sales = round(total_gmv - total_discounts, 2)
    total_units = int(df["quantity"].sum())
    return {
        "total_transactions": int(len(df)),
        "total_units_sold": total_units,
        "gross_merchandise_value": total_gmv,
        "discounts_total": total_discounts,
        "net_sales": net_sales,
    }


def compute_average_transaction_value(df: pd.DataFrame) -> Dict[str, Any]:
    """Vectorized AOV & order basket statistics matching `revenue_service.avg_order_value`."""
    amounts = df["amount"]
    net_amounts = amounts - df["discount_amount"]
    return {
        "avg_order_value": round(float(amounts.mean()), 2) if len(df) else 0.0,
        "avg_net_order_value": round(float(net_amounts.mean()), 2) if len(df) else 0.0,
        "median_order_value": round(float(amounts.median()), 2) if len(df) else 0.0,
        "p95_order_value": round(float(amounts.quantile(0.95)), 2) if len(df) else 0.0,
        "avg_units_per_order": round(float(df["quantity"].mean()), 3) if len(df) else 0.0,
    }


def compute_vendor_analytics(df: pd.DataFrame, vendors_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Vectorized vendor revenue ranking, market share %, commission & payout summary
    mirroring `revenue_service.get_vendor_benchmarking` & `get_vendor_settlements`.
    """
    agg = (
        df.groupby("vendor_id", sort=False)
        .agg(
            gross_revenue=("amount", "sum"),
            discounts=("discount_amount", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("transaction_id", "count"),
        )
        .reset_index()
    )
    agg = agg.merge(
        vendors_df[["vendor_id", "vendor_name", "commission_tier", "commission_rate"]],
        on="vendor_id",
        how="left",
    )
    total_gmv = float(agg["gross_revenue"].sum())
    agg["net_sales"] = (agg["gross_revenue"] - agg["discounts"]).round(2)
    agg["gross_revenue"] = agg["gross_revenue"].round(2)
    agg["market_share_pct"] = (
        (agg["gross_revenue"] / total_gmv * 100.0).round(2) if total_gmv > 0 else 0.0
    )
    agg["platform_commission"] = (agg["net_sales"] * agg["commission_rate"]).round(2)
    agg["vendor_payout"] = (agg["net_sales"] - agg["platform_commission"]).round(2)
    agg["rank"] = agg["gross_revenue"].rank(ascending=False, method="min").astype(int)
    agg = agg.sort_values(["rank", "vendor_id"]).reset_index(drop=True)

    top_row = agg.iloc[0].to_dict() if not agg.empty else None
    return {
        "active_vendors_with_sales": int(len(agg)),
        "market_share_sum_pct": round(float(agg["market_share_pct"].sum()), 2),
        "total_platform_commission": round(float(agg["platform_commission"].sum()), 2),
        "total_vendor_payouts": round(float(agg["vendor_payout"].sum()), 2),
        "top_vendor": top_row,
        "top_5_vendors": agg.head(5).to_dict(orient="records"),
    }


def compute_product_analytics(df: pd.DataFrame, products_df: pd.DataFrame) -> Dict[str, Any]:
    """Vectorized product-level sales aggregation, COGS accounting & top SKU ranking."""
    agg = (
        df.groupby("product_id", sort=False)
        .agg(
            gross_revenue=("amount", "sum"),
            discounts=("discount_amount", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("transaction_id", "count"),
        )
        .reset_index()
    )
    agg = agg.merge(
        products_df[["product_id", "product_name", "category", "parent_category", "price", "cost_price"]],
        on="product_id",
        how="left",
    )
    agg["net_sales"] = (agg["gross_revenue"] - agg["discounts"]).round(2)
    agg["gross_revenue"] = agg["gross_revenue"].round(2)
    agg["cogs"] = (agg["units_sold"] * agg["cost_price"]).round(2)
    agg["gross_profit"] = (agg["net_sales"] - agg["cogs"]).round(2)
    agg = agg.sort_values("gross_revenue", ascending=False).reset_index(drop=True)

    total_net = float(agg["net_sales"].sum())
    total_cogs = float(agg["cogs"].sum())
    total_profit = round(total_net - total_cogs, 2)
    margin_pct = round((total_profit / total_net * 100.0), 2) if total_net > 0 else 0.0

    return {
        "products_sold_count": int(len(agg)),
        "total_cogs": round(total_cogs, 2),
        "gross_profit": total_profit,
        "gross_margin_pct": margin_pct,
        "top_product": agg.iloc[0].to_dict() if not agg.empty else None,
        "top_5_products": agg.head(5).to_dict(orient="records"),
    }


def compute_category_and_payment_analytics(df: pd.DataFrame, products_df: pd.DataFrame) -> Dict[str, Any]:
    """Vectorized category & payment-channel revenue share mirroring `get_revenue_by_category`."""
    prod_cat_map = products_df.set_index("product_id")["parent_category"]
    parent_cats = df["product_id"].map(prod_cat_map)

    cat_agg = (
        df.assign(parent_category=parent_cats)
        .groupby("parent_category", sort=False)
        .agg(
            revenue=("amount", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("transaction_id", "count"),
        )
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    total_rev = float(cat_agg["revenue"].sum())
    cat_agg["revenue"] = cat_agg["revenue"].round(2)
    cat_agg["share_pct"] = (cat_agg["revenue"] / total_rev * 100.0).round(2) if total_rev > 0 else 0.0

    pay_agg = (
        df.groupby("payment_method", sort=False)
        .agg(revenue=("amount", "sum"), order_count=("transaction_id", "count"))
        .reset_index()
        .sort_values("order_count", ascending=False)
    )
    pay_agg["revenue"] = pay_agg["revenue"].round(2)
    pay_agg["order_share_pct"] = (pay_agg["order_count"] / len(df) * 100.0).round(2)

    return {
        "categories": cat_agg.to_dict(orient="records"),
        "payment_methods": pay_agg.to_dict(orient="records"),
    }


def compute_time_trends(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Vectorized monthly & daily sales aggregation with MoM growth % (no Python loops)
    matching `revenue_service.get_monthly_revenue_growth`.
    Uses integer `(year, month)` grouping to avoid 100K per-row Period string allocations.
    """
    monthly = (
        df.assign(
            year=df["transaction_date"].dt.year,
            month=df["transaction_date"].dt.month,
        )
        .groupby(["year", "month"], sort=True)
        .agg(
            revenue=("amount", "sum"),
            net_sales=("discount_amount", "sum"),
            units=("quantity", "sum"),
            orders=("transaction_id", "count"),
        )
        .reset_index()
    )
    monthly["year_month"] = monthly["year"].astype(str) + "-" + monthly["month"].astype(str).str.zfill(2)
    monthly["net_sales"] = (monthly["revenue"] - monthly["net_sales"]).round(2)
    monthly["revenue"] = monthly["revenue"].round(2)
    monthly["mom_growth_pct"] = (monthly["revenue"].pct_change() * 100.0).round(2)

    daily = (
        df.assign(tx_date=df["transaction_date"].dt.normalize())
        .groupby("tx_date", sort=True)
        .agg(revenue=("amount", "sum"), orders=("transaction_id", "count"))
        .reset_index()
    )
    daily["revenue"] = daily["revenue"].round(2)
    peak_day_row = daily.loc[daily["revenue"].idxmax()] if not daily.empty else None
    peak_month_row = monthly.loc[monthly["revenue"].idxmax()] if not monthly.empty else None

    return {
        "months_covered": int(len(monthly)),
        "days_covered": int(len(daily)),
        "peak_month": {
            "year_month": str(peak_month_row["year_month"]),
            "revenue": float(peak_month_row["revenue"]),
            "orders": int(peak_month_row["orders"]),
        }
        if peak_month_row is not None
        else None,
        "peak_day": {
            "date": str(peak_day_row["tx_date"])[:10],
            "revenue": float(peak_day_row["revenue"]),
            "orders": int(peak_day_row["orders"]),
        }
        if peak_day_row is not None
        else None,
        "monthly_sample": monthly.head(6).assign(
            mom_growth_pct=monthly.head(6)["mom_growth_pct"].where(monthly.head(6)["mom_growth_pct"].notna(), None)
        ).to_dict(orient="records"),
    }


def compute_customer_rfm_analytics(df: pd.DataFrame, customers_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Fully vectorized RFM feature engineering & summary KPIs mirroring `customer_service.py`
    without per-group lambdas or row iteration.
    """
    ref_date = df["transaction_date"].max()
    ninety_days_ago = ref_date - pd.Timedelta(days=90)

    grouped = (
        df.groupby("customer_id", sort=False)
        .agg(
            last_purchase=("transaction_date", "max"),
            frequency=("amount", "count"),
            monetary=("amount", "sum"),
            avg_order_value=("amount", "mean"),
        )
        .reset_index()
    )
    grouped["recency_days"] = (ref_date - grouped["last_purchase"]).dt.days.astype(np.int32)

    total_customers = int(len(customers_df))
    active_90d = int((grouped["last_purchase"] >= ninety_days_ago).sum())
    repeat_customers = int((grouped["frequency"] >= 2).sum())
    repeat_rate = round((repeat_customers / total_customers) * 100.0, 2) if total_customers else 0.0
    total_rev = float(df["amount"].sum())

    return {
        "total_registered_customers": total_customers,
        "purchasing_customers": int(len(grouped)),
        "active_customers_90d": active_90d,
        "repeat_customers": repeat_customers,
        "repeat_purchase_rate_pct": repeat_rate,
        "avg_customer_lifetime_spend": round(total_rev / total_customers, 2) if total_customers else 0.0,
        "mean_frequency_among_buyers": round(float(grouped["frequency"].mean()), 2),
        "max_customer_spend": round(float(grouped["monetary"].max()), 2),
    }


def compute_daily_sales_mart_aggregation(df: pd.DataFrame, products_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Vectorized dimensional rollup at `(date, product_id, vendor_id)` grain
    matching `app/services/etl/daily_mart_service.py`.
    """
    mart = (
        df.assign(tx_date=df["transaction_date"].dt.normalize())
        .groupby(["tx_date", "product_id", "vendor_id"], sort=False)
        .agg(
            units_sold=("quantity", "sum"),
            gross_sales_gmv=("amount", "sum"),
            discounts_total=("discount_amount", "sum"),
            transaction_count=("transaction_id", "count"),
        )
        .reset_index()
    )
    cost_map = products_df.set_index("product_id")["cost_price"]
    mart["unit_cost"] = mart["product_id"].map(cost_map)
    mart["net_sales"] = (mart["gross_sales_gmv"] - mart["discounts_total"]).round(2)
    mart["known_cogs"] = (mart["units_sold"] * mart["unit_cost"]).round(2)
    mart["reported_gross_profit"] = (mart["net_sales"] - mart["known_cogs"]).round(2)

    return {
        "mart_grain_rows": int(len(mart)),
        "mart_gross_gmv": round(float(mart["gross_sales_gmv"].sum()), 2),
        "mart_net_sales": round(float(mart["net_sales"].sum()), 2),
        "mart_total_units": int(mart["units_sold"].sum()),
    }


def run_all_benchmark_analytics(
    tx_df: pd.DataFrame,
    vendors_df: pd.DataFrame,
    products_df: pd.DataFrame,
    customers_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all 8 analytical workloads and return results + detailed per-operation timings."""
    t_all0 = time.perf_counter()

    ops = [
        ("total_revenue_and_gmv", lambda: compute_total_revenue_and_gmv(tx_df)),
        ("average_transaction_value", lambda: compute_average_transaction_value(tx_df)),
        ("vendor_sales_and_ranking", lambda: compute_vendor_analytics(tx_df, vendors_df)),
        ("product_sales_and_cogs", lambda: compute_product_analytics(tx_df, products_df)),
        ("category_and_payment_breakdown", lambda: compute_category_and_payment_analytics(tx_df, products_df)),
        ("time_based_trends_mom_daily", lambda: compute_time_trends(tx_df)),
        ("customer_rfm_aggregation", lambda: compute_customer_rfm_analytics(tx_df, customers_df)),
        ("daily_sales_mart_rollup", lambda: compute_daily_sales_mart_aggregation(tx_df, products_df)),
    ]

    results: Dict[str, Any] = {}
    timings = []
    for name, fn in ops:
        res, tm = _timed_op(name, fn)
        tm["rows_per_sec"] = round(len(tx_df) / (tm["elapsed_ms"] / 1000.0), 0) if tm["elapsed_ms"] > 0 else 0
        results[name] = res
        timings.append(tm)

    total_analytics_s = round(time.perf_counter() - t_all0, 4)
    return {
        "results": results,
        "timings": timings,
        "total_analytics_time_s": total_analytics_s,
    }
