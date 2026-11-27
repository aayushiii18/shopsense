"""
app/services/executive_service.py — SQL-Aggregated Executive Analytics Engine (Phase 2).

Computes centralized executive KPIs using efficient database-level GROUP BY / SUM / CASE
aggregations without loading full Transaction tables into memory, while reusing ShopSense's
canonical financial, customer, and inventory accounting definitions.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.services import inventory_service

OPERATIONAL_VENDOR_STATUSES = ("ACTIVE", "LEGACY_ACTIVE")


def _normalize_date_bounds(
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[Optional[datetime], Optional[datetime], Dict[str, Any]]:
    """Validate optional inclusive date bounds and convert into `[start_dt, end_dt_exclusive)`."""
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date.")

    start_dt = datetime.combine(start_date, time.min) if start_date else None
    end_dt_excl = datetime.combine(end_date + timedelta(days=1), time.min) if end_date else None
    meta = {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "is_filtered": bool(start_date or end_date),
    }
    return start_dt, end_dt_excl, meta


def _apply_tx_filters(
    query,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    vendor_id: Optional[int],
):
    """Apply optional chronological range and vendor tenant filters to a Transaction query."""
    if start_dt is not None:
        query = query.filter(Transaction.transaction_date >= start_dt)
    if end_dt_excl is not None:
        query = query.filter(Transaction.transaction_date < end_dt_excl)
    if vendor_id is not None:
        query = query.filter(Transaction.vendor_id == vendor_id)
    return query


def _pct_change(current: float, previous: Optional[float]) -> Optional[float]:
    """Compute guarded percentage change avoiding division by zero."""
    if previous is None or previous == 0.0:
        return None
    return round(((current - previous) / previous) * 100.0, 2)


def _build_financials_payload(
    tx_count: int,
    total_units: int,
    raw_gmv: float,
    raw_discounts: float,
    raw_refunds: float,
    covered_count: int,
    covered_gross: float,
    covered_disc: float,
    covered_ref: float,
    raw_covered_cogs: float,
) -> Dict[str, Any]:
    """Format canonical executive financial & cost-coverage KPIs from SQL aggregates."""
    gross_gmv = round(raw_gmv, 2)
    discounts = round(raw_discounts, 2)
    refunds = round(raw_refunds, 2)
    net_sales = max(0.0, round(gross_gmv - discounts - refunds, 2))

    aov = round(gross_gmv / tx_count, 2) if tx_count > 0 else 0.0
    avg_net_aov = round(net_sales / tx_count, 2) if tx_count > 0 else 0.0
    has_cost_data = covered_count > 0

    if has_cost_data:
        covered_net = max(0.0, round(covered_gross - covered_disc - covered_ref, 2))
        covered_cogs = round(raw_covered_cogs, 2)
        gross_profit = round(covered_net - covered_cogs, 2)
        margin_pct = round((gross_profit / covered_net) * 100.0, 2) if covered_net > 0 else None
        coverage_pct = round((covered_net / net_sales) * 100.0, 2) if net_sales > 0 else 0.0
        cost_complete = coverage_pct >= 99.9
        is_partial = not cost_complete and coverage_pct > 0.0
        coverage_status = (
            f"Full cost data coverage ({coverage_pct:.1f}% of net sales)."
            if cost_complete
            else f"Partial cost data coverage ({coverage_pct:.1f}% of net sales); profit calculated strictly on covered items."
        )
    else:
        covered_net = 0.0
        covered_cogs = 0.0
        gross_profit = None
        margin_pct = None
        coverage_pct = 0.0
        cost_complete = False
        is_partial = False
        coverage_status = (
            "No transaction volume in selected scope."
            if tx_count == 0
            else "No product cost data recorded (0.0% coverage); gross profit omitted to prevent misleading calculations."
        )

    return {
        "gross_sales_gmv": gross_gmv,
        "discounts_total": discounts,
        "refunds_total": refunds,
        "net_sales": net_sales,
        "total_transactions": tx_count,
        "total_units_sold": total_units,
        "avg_order_value": aov,
        "avg_net_order_value": avg_net_aov,
        "has_cost_data": has_cost_data,
        "cost_coverage_complete": cost_complete,
        "is_partial_profit": is_partial,
        "cogs_coverage_pct": coverage_pct,
        "covered_net_sales": covered_net,
        "covered_cogs": covered_cogs,
        "gross_profit_reported": gross_profit,
        "gross_margin_pct_reported": margin_pct,
        "coverage_status": coverage_status,
    }


def _compute_financial_kpis(
    db: Session,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    vendor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregate GMV, discounts, refunds, net sales, AOV, and incomplete-cost-safe gross profit
    using two single-row SQL queries (no Transaction row iteration).
    """
    tx_q = (
        db.query(
            func.count(Transaction.transaction_id).label("tx_count"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_units"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("gross_gmv"),
            func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
            func.coalesce(
                func.sum(case((Product.cost_price.isnot(None), Transaction.amount), else_=0.0)),
                0.0,
            ).label("covered_gross"),
            func.coalesce(
                func.sum(case((Product.cost_price.isnot(None), Transaction.discount_amount), else_=0.0)),
                0.0,
            ).label("covered_disc"),
            func.coalesce(
                func.sum(
                    case(
                        (Product.cost_price.isnot(None), Product.cost_price * Transaction.quantity),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("covered_cogs"),
            func.coalesce(
                func.sum(case((Product.cost_price.isnot(None), 1), else_=0)),
                0,
            ).label("covered_count"),
        )
        .join(Product, Transaction.product_id == Product.id)
    )
    tx_row = _apply_tx_filters(tx_q, start_dt, end_dt_excl, vendor_id).first()

    ref_q = (
        db.query(
            func.coalesce(func.sum(Refund.amount), 0.0).label("refunds_total"),
            func.coalesce(
                func.sum(case((Product.cost_price.isnot(None), Refund.amount), else_=0.0)),
                0.0,
            ).label("covered_refunds"),
        )
        .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
        .join(Product, Transaction.product_id == Product.id)
        .filter(Refund.status == "COMPLETED")
    )
    ref_row = _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id).first()

    return _build_financials_payload(
        tx_count=int(tx_row.tx_count or 0) if tx_row else 0,
        total_units=int(tx_row.total_units or 0) if tx_row else 0,
        raw_gmv=float(tx_row.gross_gmv or 0.0) if tx_row else 0.0,
        raw_discounts=float(tx_row.discounts or 0.0) if tx_row else 0.0,
        raw_refunds=float(ref_row.refunds_total or 0.0) if ref_row else 0.0,
        covered_count=int(tx_row.covered_count or 0) if tx_row else 0,
        covered_gross=float(tx_row.covered_gross or 0.0) if tx_row else 0.0,
        covered_disc=float(tx_row.covered_disc or 0.0) if tx_row else 0.0,
        covered_ref=float(ref_row.covered_refunds or 0.0) if ref_row else 0.0,
        raw_covered_cogs=float(tx_row.covered_cogs or 0.0) if tx_row else 0.0,
    )


def _compute_trends(
    db: Session,
    granularity: str,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    vendor_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Aggregate chronological monthly or daily revenue, refunds, orders, AOV, and growth % in SQL."""
    is_daily = granularity == "daily"
    if is_daily:
        tx_q = db.query(
            func.date(Transaction.transaction_date).label("period_key"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("gmv"),
            func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units"),
            func.count(Transaction.transaction_id).label("orders"),
        )
        tx_rows = (
            _apply_tx_filters(tx_q, start_dt, end_dt_excl, vendor_id)
            .group_by(func.date(Transaction.transaction_date))
            .order_by(func.date(Transaction.transaction_date).asc())
            .all()
        )
        ref_q = (
            db.query(
                func.date(Transaction.transaction_date).label("period_key"),
                func.coalesce(func.sum(Refund.amount), 0.0).label("refunds"),
            )
            .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
            .filter(Refund.status == "COMPLETED")
        )
        ref_rows = (
            _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id)
            .group_by(func.date(Transaction.transaction_date))
            .all()
        )
        refund_map = {str(r.period_key)[:10]: float(r.refunds or 0.0) for r in ref_rows}
        buckets = [
            (str(r.period_key)[:10], float(r.gmv or 0.0), float(r.discounts or 0.0), int(r.units or 0), int(r.orders or 0))
            for r in tx_rows
        ]
    else:
        yr_col = func.extract("year", Transaction.transaction_date)
        mo_col = func.extract("month", Transaction.transaction_date)
        tx_q = db.query(
            yr_col.label("yr"),
            mo_col.label("mo"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("gmv"),
            func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units"),
            func.count(Transaction.transaction_id).label("orders"),
        )
        tx_rows = (
            _apply_tx_filters(tx_q, start_dt, end_dt_excl, vendor_id)
            .group_by(yr_col, mo_col)
            .order_by(yr_col.asc(), mo_col.asc())
            .all()
        )
        ref_q = (
            db.query(
                yr_col.label("yr"),
                mo_col.label("mo"),
                func.coalesce(func.sum(Refund.amount), 0.0).label("refunds"),
            )
            .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
            .filter(Refund.status == "COMPLETED")
        )
        ref_rows = (
            _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id)
            .group_by(yr_col, mo_col)
            .all()
        )
        refund_map = {
            f"{int(r.yr):04d}-{int(r.mo):02d}": float(r.refunds or 0.0)
            for r in ref_rows
            if r.yr is not None and r.mo is not None
        }
        buckets = [
            (
                f"{int(r.yr):04d}-{int(r.mo):02d}",
                float(r.gmv or 0.0),
                float(r.discounts or 0.0),
                int(r.units or 0),
                int(r.orders or 0),
            )
            for r in tx_rows
            if r.yr is not None and r.mo is not None
        ]

    series: List[Dict[str, Any]] = []
    prev_gmv: Optional[float] = None
    for label, gmv_raw, disc_raw, units, orders in buckets:
        gmv = round(gmv_raw, 2)
        disc = round(disc_raw, 2)
        ref = round(refund_map.get(label, 0.0), 2)
        net = max(0.0, round(gmv - disc - ref, 2))
        aov = round(gmv / orders, 2) if orders > 0 else 0.0
        growth = _pct_change(gmv, prev_gmv)
        prev_gmv = gmv
        series.append({
            "period": label,
            "gmv": gmv,
            "discounts": disc,
            "refunds": ref,
            "net_sales": net,
            "units_sold": units,
            "orders": orders,
            "avg_order_value": aov,
            "growth_pct": growth,
        })
    return series


def _compute_period_comparison(
    db: Session,
    start_date: Optional[date],
    end_date: Optional[date],
    current_financials: Dict[str, Any],
    monthly_series: List[Dict[str, Any]],
    vendor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute comparative metrics:
      1. If both start_date & end_date are supplied: compare against immediately preceding equal-length window.
      2. Otherwise, if >= 2 monthly buckets exist in scope: compare latest active month vs previous month.
      3. Otherwise return comparison_supported=False without fabricating baseline deltas.
    """
    if start_date is not None and end_date is not None:
        span_days = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span_days - 1)
        prev_start_dt = datetime.combine(prev_start, time.min)
        prev_end_excl = datetime.combine(start_date, time.min)
        prev_fin = _compute_financial_kpis(db, prev_start_dt, prev_end_excl, vendor_id=vendor_id)

        cur_label = f"{start_date.isoformat()} to {end_date.isoformat()}"
        prev_label = f"{prev_start.isoformat()} to {prev_end.isoformat()}"

        if prev_fin["total_transactions"] == 0:
            return {
                "comparison_supported": False,
                "comparison_type": "insufficient_data",
                "current_period_label": cur_label,
                "previous_period_label": prev_label,
                "current_gmv": current_financials["gross_sales_gmv"],
                "previous_gmv": None,
                "gmv_change_pct": None,
                "current_net_sales": current_financials["net_sales"],
                "previous_net_sales": None,
                "net_sales_change_pct": None,
                "current_transactions": current_financials["total_transactions"],
                "previous_transactions": 0,
                "transactions_change_pct": None,
                "current_aov": current_financials["avg_order_value"],
                "previous_aov": None,
                "aov_change_pct": None,
                "note": f"No historical transactions found in the preceding {span_days}-day window ({prev_label}).",
            }

        cur_gmv = current_financials["gross_sales_gmv"]
        cur_net = current_financials["net_sales"]
        cur_tx = current_financials["total_transactions"]
        cur_aov = current_financials["avg_order_value"]
        return {
            "comparison_supported": True,
            "comparison_type": "window_over_previous_window",
            "current_period_label": cur_label,
            "previous_period_label": prev_label,
            "current_gmv": cur_gmv,
            "previous_gmv": prev_fin["gross_sales_gmv"],
            "gmv_change_pct": _pct_change(cur_gmv, prev_fin["gross_sales_gmv"]),
            "current_net_sales": cur_net,
            "previous_net_sales": prev_fin["net_sales"],
            "net_sales_change_pct": _pct_change(cur_net, prev_fin["net_sales"]),
            "current_transactions": cur_tx,
            "previous_transactions": prev_fin["total_transactions"],
            "transactions_change_pct": _pct_change(float(cur_tx), float(prev_fin["total_transactions"])),
            "current_aov": cur_aov,
            "previous_aov": prev_fin["avg_order_value"],
            "aov_change_pct": _pct_change(cur_aov, prev_fin["avg_order_value"]),
            "note": f"Compared against preceding {span_days}-day baseline ({prev_label}).",
        }

    if len(monthly_series) >= 2:
        prev_m = monthly_series[-2]
        cur_m = monthly_series[-1]
        return {
            "comparison_supported": True,
            "comparison_type": "latest_month_vs_previous_month",
            "current_period_label": cur_m["period"],
            "previous_period_label": prev_m["period"],
            "current_gmv": cur_m["gmv"],
            "previous_gmv": prev_m["gmv"],
            "gmv_change_pct": _pct_change(cur_m["gmv"], prev_m["gmv"]),
            "current_net_sales": cur_m["net_sales"],
            "previous_net_sales": prev_m["net_sales"],
            "net_sales_change_pct": _pct_change(cur_m["net_sales"], prev_m["net_sales"]),
            "current_transactions": cur_m["orders"],
            "previous_transactions": prev_m["orders"],
            "transactions_change_pct": _pct_change(float(cur_m["orders"]), float(prev_m["orders"])),
            "current_aov": cur_m["avg_order_value"],
            "previous_aov": prev_m["avg_order_value"],
            "aov_change_pct": _pct_change(cur_m["avg_order_value"], prev_m["avg_order_value"]),
            "note": f"Compared latest active month ({cur_m['period']}) against prior active month ({prev_m['period']}).",
        }

    return {
        "comparison_supported": False,
        "comparison_type": "insufficient_data",
        "current_period_label": monthly_series[-1]["period"] if monthly_series else None,
        "previous_period_label": None,
        "current_gmv": current_financials["gross_sales_gmv"] if monthly_series else None,
        "previous_gmv": None,
        "gmv_change_pct": None,
        "current_net_sales": current_financials["net_sales"] if monthly_series else None,
        "previous_net_sales": None,
        "net_sales_change_pct": None,
        "current_transactions": current_financials["total_transactions"] if monthly_series else None,
        "previous_transactions": None,
        "transactions_change_pct": None,
        "current_aov": current_financials["avg_order_value"] if monthly_series else None,
        "previous_aov": None,
        "aov_change_pct": None,
        "note": "At least two monthly periods or an explicit start_date/end_date range with prior history are needed for period comparison.",
    }


def _compute_customer_kpis(
    db: Session,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    vendor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute customer base, active 90d, repeat buyer rate, and average spend using SQL queries."""
    is_platform_scope = vendor_id is None
    total_registered = int(db.query(func.count(Customer.customer_id)).scalar() or 0) if is_platform_scope else None

    cust_agg_subq = (
        _apply_tx_filters(
            db.query(
                Transaction.customer_id.label("customer_id"),
                func.count(Transaction.transaction_id).label("tx_count"),
                func.coalesce(func.sum(Transaction.amount), 0.0).label("total_spend"),
                func.max(Transaction.transaction_date).label("last_tx_date"),
            ).filter(Transaction.customer_id.isnot(None)),
            start_dt,
            end_dt_excl,
            vendor_id,
        )
        .group_by(Transaction.customer_id)
        .subquery()
    )
    row = db.query(
        func.count(cust_agg_subq.c.customer_id).label("purchasing"),
        func.coalesce(func.sum(cust_agg_subq.c.total_spend), 0.0).label("cust_rev"),
        func.max(cust_agg_subq.c.last_tx_date).label("max_tx_date"),
        func.coalesce(
            func.sum(case((cust_agg_subq.c.tx_count >= 2, 1), else_=0)),
            0,
        ).label("repeat_count"),
    ).first()

    purchasing = int(row.purchasing or 0) if row else 0
    cust_rev = float(row.cust_rev or 0.0) if row else 0.0
    max_tx_date = row.max_tx_date if row else None
    repeat_count = int(row.repeat_count or 0) if row else 0

    if purchasing == 0:
        return {
            "total_registered_customers": total_registered,
            "purchasing_customers": 0,
            "active_customers_90d": 0,
            "repeat_customers": 0,
            "repeat_purchase_rate_pct": 0.0 if total_registered else None,
            "avg_customer_spend": 0.0,
        }

    # 90-day active window anchored consistent with inventory_service._get_reference_anchor_date
    now_dt = datetime.utcnow()
    anchor_dt = now_dt if (max_tx_date and (now_dt - max_tx_date).days < 90 and end_dt_excl is None) else (max_tx_date or now_dt)
    since_90d = anchor_dt - timedelta(days=90)

    active_q = db.query(func.count(func.distinct(Transaction.customer_id))).filter(
        Transaction.customer_id.isnot(None),
        Transaction.transaction_date >= since_90d,
        Transaction.transaction_date <= anchor_dt,
    )
    active_90d = int(_apply_tx_filters(active_q, start_dt, end_dt_excl, vendor_id).scalar() or 0)

    is_unfiltered_platform = is_platform_scope and start_dt is None and end_dt_excl is None
    if is_unfiltered_platform and total_registered:
        avg_spend = round(cust_rev / total_registered, 2)
        repeat_rate = round((repeat_count / total_registered) * 100.0, 2)
    else:
        avg_spend = round(cust_rev / purchasing, 2) if purchasing > 0 else 0.0
        repeat_rate = round((repeat_count / purchasing) * 100.0, 2) if purchasing > 0 else None

    return {
        "total_registered_customers": total_registered,
        "purchasing_customers": purchasing,
        "active_customers_90d": active_90d,
        "repeat_customers": repeat_count,
        "repeat_purchase_rate_pct": repeat_rate,
        "avg_customer_spend": avg_spend,
    }


def _rank_vendors_from_totals(
    vendor_rows: List[Any],
    vendor_totals: Dict[int, Dict[str, Any]],
    total_gmv_override: Optional[float] = None,
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """Assemble vendor status counts, rankings, commissions, and payouts from grouped vendor sums."""
    vendor_map = {int(v.id): v for v in vendor_rows}
    status_counts: Dict[str, int] = {}
    for v in vendor_rows:
        st = str(v.status)
        status_counts[st] = status_counts.get(st, 0) + 1
    total_vendors = sum(status_counts.values())
    active_vendors = sum(status_counts.get(s, 0) for s in OPERATIONAL_VENDOR_STATUSES)
    pending_vendors = status_counts.get("PENDING_APPROVAL", 0)

    raw_total_gmv = 0.0
    raw_total_disc = 0.0
    raw_total_ref = 0.0
    valid_entries = []
    for vid, sums in vendor_totals.items():
        v_meta = vendor_map.get(vid)
        if v_meta is None:
            continue
        gross_raw = sums["gross"]
        disc_raw = sums["disc"]
        ref_raw = sums["ref"]
        raw_total_gmv += gross_raw
        raw_total_disc += disc_raw
        raw_total_ref += ref_raw
        valid_entries.append((vid, v_meta, sums, gross_raw, disc_raw, ref_raw))

    valid_entries.sort(key=lambda item: (-item[3], item[0]))
    computed_gmv = round(raw_total_gmv, 2)
    computed_net = max(0.0, round(raw_total_gmv - raw_total_disc - raw_total_ref, 2))
    share_denom = float(total_gmv_override) if total_gmv_override is not None else computed_gmv

    ranked: List[Dict[str, Any]] = []
    for idx, (vid, v_meta, sums, gross_raw, disc_raw, ref_raw) in enumerate(valid_entries, start=1):
        gross = round(gross_raw, 2)
        disc = round(disc_raw, 2)
        ref = round(ref_raw, 2)
        net = max(0.0, round(gross - disc - ref, 2))
        rate = float(v_meta.commission_rate or 0.12)
        comm = round(net * rate, 2)
        payout = round(net - comm, 2)
        share = round((gross / share_denom) * 100.0, 2) if share_denom > 0 else 0.0
        ranked.append({
            "vendor_id": vid,
            "vendor_name": v_meta.name,
            "status": str(v_meta.status or "UNKNOWN"),
            "commission_tier": str(v_meta.commission_tier or "TIER_STANDARD"),
            "commission_rate": round(rate, 4),
            "gross_revenue": gross,
            "discounts_allocated": disc,
            "refunds_deducted": ref,
            "net_sales": net,
            "platform_commission": comm,
            "vendor_payout": payout,
            "units_sold": int(sums["units"]),
            "order_count": int(sums["orders"]),
            "rank": idx,
            "market_share_pct": share,
        })

    return {
        "total_vendors": total_vendors,
        "active_vendors": active_vendors,
        "pending_approval_vendors": pending_vendors,
        "vendors_with_sales": len(ranked),
        "total_gmv": computed_gmv,
        "total_net_sales": computed_net,
        "vendors": ranked[skip : skip + limit],
    }


def _compute_vendor_aggregates(
    db: Session,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    total_gmv_override: Optional[float] = None,
    vendor_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """Compute ranked vendor metrics, status counts, and GMV/net totals via integer-key GROUP BY."""
    vendor_rows = db.query(
        Vendor.id,
        Vendor.name,
        Vendor.status,
        Vendor.commission_tier,
        Vendor.commission_rate,
    ).all()

    agg_q = db.query(
        Transaction.vendor_id,
        func.coalesce(func.sum(Transaction.amount), 0.0).label("gross_revenue"),
        func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        func.count(Transaction.transaction_id).label("order_count"),
    )
    rows = _apply_tx_filters(agg_q, start_dt, end_dt_excl, vendor_id).group_by(Transaction.vendor_id).all()

    ref_q = (
        db.query(
            Transaction.vendor_id,
            func.coalesce(func.sum(Refund.amount), 0.0).label("refunds"),
        )
        .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
        .filter(Refund.status == "COMPLETED")
    )
    ref_rows = _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id).group_by(Transaction.vendor_id).all()
    refund_map = {int(r.vendor_id): float(r.refunds or 0.0) for r in ref_rows}

    vendor_totals = {
        int(r.vendor_id): {
            "gross": float(r.gross_revenue or 0.0),
            "disc": float(r.discounts or 0.0),
            "ref": refund_map.get(int(r.vendor_id), 0.0),
            "units": int(r.units_sold or 0),
            "orders": int(r.order_count or 0),
        }
        for r in rows
    }
    return _rank_vendors_from_totals(
        vendor_rows=vendor_rows,
        vendor_totals=vendor_totals,
        total_gmv_override=total_gmv_override,
        skip=skip,
        limit=limit,
    )


def _compute_vendor_list(
    db: Session,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    total_gmv: float,
    vendor_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Compute ranked SQL vendor revenue, refunds, net sales, commissions, payouts, and share %."""
    return _compute_vendor_aggregates(
        db,
        start_dt=start_dt,
        end_dt_excl=end_dt_excl,
        total_gmv_override=total_gmv,
        vendor_id=vendor_id,
        skip=skip,
        limit=limit,
    )["vendors"]


def _compute_product_overview(
    db: Session,
    start_dt: Optional[datetime],
    end_dt_excl: Optional[datetime],
    vendor_id: Optional[int] = None,
    limit: int = 10,
    include_financials: bool = False,
    include_vendors: bool = False,
    vendor_skip: int = 0,
    vendor_limit: int = 50,
) -> Dict[str, Any]:
    """Compute SQL-aggregated top products and optionally derive financials and vendor rankings."""
    prod_rows = (
        db.query(
            Product.id,
            Product.name,
            Product.category,
            Product.vendor_id,
            Product.cost_price,
            Vendor.name.label("vendor_name"),
            Inventory.current_stock,
            Inventory.reorder_level,
        )
        .join(Vendor, Product.vendor_id == Vendor.id)
        .outerjoin(Inventory, Product.id == Inventory.product_id)
        .all()
    )
    prod_map = {int(p.id): p for p in prod_rows}
    scoped_prods = [p for p in prod_rows if vendor_id is None or int(p.vendor_id) == vendor_id]
    total_products = len(scoped_prods)
    products_with_cost_data = sum(1 for p in scoped_prods if p.cost_price is not None)

    if include_vendors:
        agg_q = db.query(
            Transaction.product_id,
            Transaction.vendor_id,
            func.coalesce(func.sum(Transaction.amount), 0.0).label("gross_revenue"),
            func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
            func.count(Transaction.transaction_id).label("order_count"),
        )
        rows = _apply_tx_filters(agg_q, start_dt, end_dt_excl, vendor_id).group_by(
            Transaction.product_id, Transaction.vendor_id
        ).all()

        ref_q = (
            db.query(
                Transaction.product_id,
                Transaction.vendor_id,
                func.coalesce(func.sum(Refund.amount), 0.0).label("refunds"),
            )
            .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
            .filter(Refund.status == "COMPLETED")
        )
        ref_rows = _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id).group_by(
            Transaction.product_id, Transaction.vendor_id
        ).all()
    else:
        agg_q = db.query(
            Transaction.product_id,
            func.coalesce(func.sum(Transaction.amount), 0.0).label("gross_revenue"),
            func.coalesce(func.sum(Transaction.discount_amount), 0.0).label("discounts"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
            func.count(Transaction.transaction_id).label("order_count"),
        )
        rows = _apply_tx_filters(agg_q, start_dt, end_dt_excl, vendor_id).group_by(
            Transaction.product_id
        ).all()

        ref_q = (
            db.query(
                Transaction.product_id,
                func.coalesce(func.sum(Refund.amount), 0.0).label("refunds"),
            )
            .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
            .filter(Refund.status == "COMPLETED")
        )
        ref_rows = _apply_tx_filters(ref_q, start_dt, end_dt_excl, vendor_id).group_by(
            Transaction.product_id
        ).all()

    prod_buckets: Dict[int, Dict[str, Any]] = {}
    vendor_totals: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        pid = int(r.product_id)
        gross_raw = float(r.gross_revenue or 0.0)
        disc_raw = float(r.discounts or 0.0)
        units = int(r.units_sold or 0)
        orders = int(r.order_count or 0)

        pb = prod_buckets.setdefault(pid, {"gross": 0.0, "disc": 0.0, "ref": 0.0, "units": 0, "orders": 0})
        pb["gross"] += gross_raw
        pb["disc"] += disc_raw
        pb["units"] += units
        pb["orders"] += orders

        if include_vendors:
            vid = int(r.vendor_id)
            vb = vendor_totals.setdefault(vid, {"gross": 0.0, "disc": 0.0, "ref": 0.0, "units": 0, "orders": 0})
            vb["gross"] += gross_raw
            vb["disc"] += disc_raw
            vb["units"] += units
            vb["orders"] += orders

    for rr in ref_rows:
        pid = int(rr.product_id)
        ref_raw = float(rr.refunds or 0.0)
        if pid in prod_buckets:
            prod_buckets[pid]["ref"] += ref_raw
        if include_vendors:
            vid = int(rr.vendor_id)
            if vid in vendor_totals:
                vendor_totals[vid]["ref"] += ref_raw

    tx_count_total = 0
    units_total = 0
    raw_gmv_total = 0.0
    raw_disc_total = 0.0
    raw_ref_total = 0.0
    covered_count = 0
    covered_gross = 0.0
    covered_disc = 0.0
    covered_ref = 0.0
    raw_covered_cogs = 0.0

    raw_items: List[Tuple[float, int, Dict[str, Any]]] = []
    for pid, b in prod_buckets.items():
        meta = prod_map.get(pid)
        if meta is None:
            continue

        gross_raw = b["gross"]
        disc_raw = b["disc"]
        ref_raw = b["ref"]
        units = int(b["units"])
        orders = int(b["orders"])

        tx_count_total += orders
        units_total += units
        raw_gmv_total += gross_raw
        raw_disc_total += disc_raw
        raw_ref_total += ref_raw

        gross = round(gross_raw, 2)
        disc = round(disc_raw, 2)
        ref = round(ref_raw, 2)
        net = max(0.0, round(gross - disc - ref, 2))

        has_cost = meta.cost_price is not None
        if has_cost:
            unit_cost = float(meta.cost_price)
            covered_count += orders
            covered_gross += gross_raw
            covered_disc += disc_raw
            covered_ref += ref_raw
            raw_covered_cogs += unit_cost * units

            cogs = round(unit_cost * units, 2)
            profit = round(net - cogs, 2)
            margin = round((profit / net) * 100.0, 2) if net > 0 else None
        else:
            profit = None
            margin = None

        stock = int(meta.current_stock) if meta.current_stock is not None else 0
        reorder = int(meta.reorder_level) if meta.reorder_level is not None else 10
        stock_status = "CRITICAL" if stock == 0 else ("LOW_STOCK" if stock <= reorder else "HEALTHY")

        raw_items.append((
            gross_raw,
            pid,
            {
                "product_id": pid,
                "product_name": meta.name,
                "category": meta.category or "General",
                "vendor_id": int(meta.vendor_id),
                "vendor_name": meta.vendor_name,
                "gross_revenue": gross,
                "net_sales": net,
                "units_sold": units,
                "order_count": orders,
                "has_cost_data": has_cost,
                "gross_profit_reported": profit,
                "gross_margin_pct": margin,
                "current_stock": stock,
                "stock_status": stock_status,
            },
        ))

    raw_items.sort(key=lambda t: (-t[0], t[1]))
    items = [entry[2] for entry in raw_items]
    top_by_rev = items[0] if items else None
    top_by_units = max(items, key=lambda x: (x["units_sold"], -x["product_id"])) if items else None

    result: Dict[str, Any] = {
        "total_products": total_products,
        "products_with_sales": len(items),
        "products_with_cost_data": products_with_cost_data,
        "top_product_by_revenue": top_by_rev,
        "top_product_by_units": top_by_units,
        "top_products": items[:limit],
    }

    financials_payload: Optional[Dict[str, Any]] = None
    if include_financials:
        financials_payload = _build_financials_payload(
            tx_count=tx_count_total,
            total_units=units_total,
            raw_gmv=raw_gmv_total,
            raw_discounts=raw_disc_total,
            raw_refunds=raw_ref_total,
            covered_count=covered_count,
            covered_gross=covered_gross,
            covered_disc=covered_disc,
            covered_ref=covered_ref,
            raw_covered_cogs=raw_covered_cogs,
        )
        result["_financials"] = financials_payload

    if include_vendors:
        vendor_rows = db.query(
            Vendor.id,
            Vendor.name,
            Vendor.status,
            Vendor.commission_tier,
            Vendor.commission_rate,
        ).all()
        gmv_override = financials_payload["gross_sales_gmv"] if financials_payload else None
        result["_vendors"] = _rank_vendors_from_totals(
            vendor_rows=vendor_rows,
            vendor_totals=vendor_totals,
            total_gmv_override=gmv_override,
            skip=vendor_skip,
            limit=vendor_limit,
        )

    return result


def _compute_inventory_health(db: Session, vendor_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Compute inventory health KPIs consistent with `inventory_service.get_inventory_status`
    and `inventory_service.calculate_inventory_turnover`.
    """
    inv_items = inventory_service.get_inventory_status(db, vendor_id=vendor_id)
    total_skus = len(inv_items)
    total_stock = sum(int(i["current_stock"]) for i in inv_items)
    total_val = round(sum(float(i["stock_value"]) for i in inv_items), 2)
    healthy = sum(1 for i in inv_items if i["status"] == "HEALTHY")
    low_stock = sum(1 for i in inv_items if i["status"] == "LOW_STOCK")
    critical = sum(1 for i in inv_items if i["status"] == "CRITICAL")

    if vendor_id is None:
        turnover_summary = inventory_service.calculate_inventory_turnover(db, days=365).get("catalog_summary", {})
        turnover_ratio = float(turnover_summary.get("catalog_turnover_ratio", 0.0))
        dsi_days = float(turnover_summary.get("catalog_dsi", 999.0))
    else:
        anchor_date, since_date = inventory_service._get_reference_anchor_date(db, lookback_days=365)
        units_365 = (
            db.query(func.coalesce(func.sum(Transaction.quantity), 0))
            .filter(
                Transaction.vendor_id == vendor_id,
                Transaction.transaction_date >= since_date,
                Transaction.transaction_date <= anchor_date,
            )
            .scalar()
        ) or 0
        avg_stock = max(1.0, float(total_stock))
        turnover_ratio = round(float(units_365) / avg_stock, 2)
        dsi_days = round(365.0 / turnover_ratio, 1) if turnover_ratio > 0 else 999.0

    return {
        "total_skus": total_skus,
        "total_current_stock": total_stock,
        "total_stock_valuation": total_val,
        "healthy_skus": healthy,
        "low_stock_skus": low_stock,
        "critical_out_of_stock_skus": critical,
        "catalog_turnover_ratio": turnover_ratio,
        "catalog_dsi_days": dsi_days,
    }


def _rollup_monthly_from_daily(daily_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate chronological monthly buckets directly from daily series without re-scanning Transactions."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in daily_series:
        month_key = str(row["period"])[:7]
        bucket = grouped.setdefault(
            month_key,
            {"gmv": 0.0, "discounts": 0.0, "refunds": 0.0, "units_sold": 0, "orders": 0},
        )
        bucket["gmv"] += float(row["gmv"])
        bucket["discounts"] += float(row["discounts"])
        bucket["refunds"] += float(row["refunds"])
        bucket["units_sold"] += int(row["units_sold"])
        bucket["orders"] += int(row["orders"])

    monthly: List[Dict[str, Any]] = []
    prev_gmv: Optional[float] = None
    for month_key in sorted(grouped.keys()):
        b = grouped[month_key]
        gmv = round(b["gmv"], 2)
        disc = round(b["discounts"], 2)
        ref = round(b["refunds"], 2)
        net = max(0.0, round(gmv - disc - ref, 2))
        orders = int(b["orders"])
        aov = round(gmv / orders, 2) if orders > 0 else 0.0
        growth = _pct_change(gmv, prev_gmv)
        prev_gmv = gmv
        monthly.append({
            "period": month_key,
            "gmv": gmv,
            "discounts": disc,
            "refunds": ref,
            "net_sales": net,
            "units_sold": int(b["units_sold"]),
            "orders": orders,
            "avg_order_value": aov,
            "growth_pct": growth,
        })
    return monthly


def get_executive_summary(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    vendor_id: Optional[int] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Build the centralized Executive KPI payload using optimized SQL aggregations."""
    start_dt, end_dt_excl, filter_meta = _normalize_date_bounds(start_date, end_date)
    filter_meta["vendor_id"] = vendor_id

    products = _compute_product_overview(
        db,
        start_dt,
        end_dt_excl,
        vendor_id=vendor_id,
        limit=top_n,
        include_financials=True,
        include_vendors=True,
        vendor_skip=0,
        vendor_limit=max(top_n, 1),
    )
    financials = products.pop("_financials")
    vendor_agg = products.pop("_vendors")
    monthly_series = _compute_trends(db, "monthly", start_dt, end_dt_excl, vendor_id=vendor_id)
    comparison = _compute_period_comparison(
        db,
        start_date=start_date,
        end_date=end_date,
        current_financials=financials,
        monthly_series=monthly_series,
        vendor_id=vendor_id,
    )
    customers = _compute_customer_kpis(db, start_dt, end_dt_excl, vendor_id=vendor_id)
    ranked_vendors = vendor_agg["vendors"]
    inventory_health = _compute_inventory_health(db, vendor_id=vendor_id)

    latest_m = monthly_series[-1] if monthly_series else None
    sales_growth = {
        "latest_period": latest_m["period"] if latest_m else None,
        "latest_mom_growth_pct": latest_m["growth_pct"] if latest_m else None,
        "periods_count": len(monthly_series),
        "monthly_trends": monthly_series,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filter_meta,
        "financials": financials,
        "period_comparison": comparison,
        "customers": customers,
        "vendors": {
            "total_vendors": vendor_agg["total_vendors"],
            "active_vendors": vendor_agg["active_vendors"],
            "pending_approval_vendors": vendor_agg["pending_approval_vendors"],
            "vendors_with_sales": vendor_agg["vendors_with_sales"],
            "top_vendor": ranked_vendors[0] if ranked_vendors else None,
            "top_vendors": ranked_vendors,
        },
        "products": products,
        "inventory_health": inventory_health,
        "sales_growth": sales_growth,
    }


def get_executive_trends(
    db: Session,
    granularity: str = "monthly",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    vendor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Return chronological executive trend series (monthly or daily) with period comparison."""
    norm_gran = granularity.strip().lower()
    if norm_gran not in {"monthly", "daily"}:
        raise ValueError("granularity must be either 'monthly' or 'daily'.")

    start_dt, end_dt_excl, filter_meta = _normalize_date_bounds(start_date, end_date)
    filter_meta["vendor_id"] = vendor_id

    financials = _compute_financial_kpis(db, start_dt, end_dt_excl, vendor_id=vendor_id)
    series = _compute_trends(db, norm_gran, start_dt, end_dt_excl, vendor_id=vendor_id)
    monthly_for_cmp = series if norm_gran == "monthly" else _rollup_monthly_from_daily(series)
    comparison = _compute_period_comparison(
        db,
        start_date=start_date,
        end_date=end_date,
        current_financials=financials,
        monthly_series=monthly_for_cmp,
        vendor_id=vendor_id,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "granularity": norm_gran,
        "filters": filter_meta,
        "summary": financials,
        "period_comparison": comparison,
        "series": series,
    }


def get_executive_vendors_and_products(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 25,
) -> Dict[str, Any]:
    """Return ranked vendor and product executive performance drilldown for a date window."""
    start_dt, end_dt_excl, filter_meta = _normalize_date_bounds(start_date, end_date)
    filter_meta["vendor_id"] = None

    products = _compute_product_overview(
        db,
        start_dt,
        end_dt_excl,
        vendor_id=None,
        limit=limit,
        include_financials=False,
        include_vendors=True,
        vendor_skip=skip,
        vendor_limit=limit,
    )
    vendor_agg = products.pop("_vendors")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filter_meta,
        "total_gmv": vendor_agg["total_gmv"],
        "total_net_sales": vendor_agg["total_net_sales"],
        "vendors": vendor_agg["vendors"],
        "products": products["top_products"],
    }


def get_vendor_tenant_executive_summary(
    db: Session,
    vendor_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Return strict tenant-scoped executive KPIs for a single vendor."""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise LookupError(f"Vendor with id={vendor_id} not found.")

    start_dt, end_dt_excl, filter_meta = _normalize_date_bounds(start_date, end_date)
    filter_meta["vendor_id"] = vendor_id

    products = _compute_product_overview(
        db,
        start_dt,
        end_dt_excl,
        vendor_id=vendor_id,
        limit=top_n,
        include_financials=True,
    )
    financials = products.pop("_financials")
    monthly_series = _compute_trends(db, "monthly", start_dt, end_dt_excl, vendor_id=vendor_id)
    comparison = _compute_period_comparison(
        db,
        start_date=start_date,
        end_date=end_date,
        current_financials=financials,
        monthly_series=monthly_series,
        vendor_id=vendor_id,
    )
    customers = _compute_customer_kpis(db, start_dt, end_dt_excl, vendor_id=vendor_id)
    inventory_health = _compute_inventory_health(db, vendor_id=vendor_id)

    latest_m = monthly_series[-1] if monthly_series else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vendor_id": vendor.id,
        "vendor_name": vendor.name,
        "vendor_status": str(vendor.status),
        "filters": filter_meta,
        "financials": financials,
        "period_comparison": comparison,
        "customers": customers,
        "products": products,
        "inventory_health": inventory_health,
        "sales_growth": {
            "latest_period": latest_m["period"] if latest_m else None,
            "latest_mom_growth_pct": latest_m["growth_pct"] if latest_m else None,
            "periods_count": len(monthly_series),
            "monthly_trends": monthly_series,
        },
    }
