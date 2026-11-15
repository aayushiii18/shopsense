"""
services/etl/daily_mart_service.py — Dimensional daily sales mart aggregator and refresh engine.

Aggregates at (date, product_id, vendor_id) grain:
  - Units sold, Gross Sales GMV, Discounts Total, Refunds Total, Net Sales.
  - Known COGS, Reported Gross Profit, and COGS Coverage Percentage (preserving Stage 4 financial rules).
  - Idempotent upsert logic ensuring repeated refreshes never inflate totals or duplicate rows.
  - Supports both date-window incremental refreshes and complete catalog-wide rebuilds.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, select

from app.models.etl import DailySalesMart
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.refund import Refund


def refresh_daily_sales_mart(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    full_rebuild: bool = False,
) -> Dict[str, Any]:
    """
    Refreshes the DailySalesMart dimensional table.
    If full_rebuild is True, truncates/clears existing mart and recalculates all historical dates.
    Otherwise, recalculates only the specified date range (or past 30 days by default).
    """
    if full_rebuild:
        db.query(DailySalesMart).delete()
        db.flush()

    # Determine date range
    tx_query = db.query(
        func.min(func.date(Transaction.transaction_date)),
        func.max(func.date(Transaction.transaction_date)),
    )
    min_date_in_db, max_date_in_db = tx_query.first()

    if not min_date_in_db or not max_date_in_db:
        return {
            "status": "SUCCESS",
            "message": "No transactions found in database to aggregate into DailySalesMart.",
            "records_upserted": 0,
            "date_range": None,
        }

    def _to_date(val):
        if val is None:
            return None
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            return datetime.strptime(val[:10], "%Y-%m-%d").date()
        return None

    min_date_in_db = _to_date(min_date_in_db)
    max_date_in_db = _to_date(max_date_in_db)

    # Normalize date filters
    if start_date is None:
        start_date = min_date_in_db if full_rebuild else max(min_date_in_db, max_date_in_db - timedelta(days=30))
    else:
        start_date = _to_date(start_date)

    if end_date is None:
        end_date = max_date_in_db
    else:
        end_date = _to_date(end_date)

    # Fetch product metadata map: pid -> (vendor_id, category, cost_price)
    products = db.query(Product.id, Product.vendor_id, Product.category, Product.cost_price).all()
    product_map = {
        p.id: {
            "vendor_id": p.vendor_id,
            "category": p.category or "Uncategorized",
            "cost_price": p.cost_price,
        }
        for p in products
    }

    # Query transactions aggregated by (date(transaction_date), product_id, vendor_id)
    tx_agg = (
        db.query(
            func.date(Transaction.transaction_date).label("tx_date"),
            Transaction.product_id,
            Transaction.vendor_id,
            func.sum(Transaction.quantity).label("units_sold"),
            func.sum(Transaction.amount).label("gross_gmv"),
            func.sum(Transaction.discount_amount).label("discounts"),
            func.count(Transaction.transaction_id).label("tx_count"),
        )
        .filter(
            func.date(Transaction.transaction_date) >= str(start_date),
            func.date(Transaction.transaction_date) <= str(end_date),
            Transaction.payment_status != "FAILED",
        )
        .group_by(
            func.date(Transaction.transaction_date),
            Transaction.product_id,
            Transaction.vendor_id,
        )
        .all()
    )

    # Query refunds aggregated by matching transaction dates and products
    refund_agg = (
        db.query(
            func.date(Transaction.transaction_date).label("tx_date"),
            Transaction.product_id,
            Transaction.vendor_id,
            func.sum(Refund.amount).label("refunds_sum"),
        )
        .join(Transaction, Refund.transaction_id == Transaction.transaction_id)
        .filter(
            func.date(Transaction.transaction_date) >= str(start_date),
            func.date(Transaction.transaction_date) <= str(end_date),
            Refund.status == "COMPLETED",
        )
        .group_by(
            func.date(Transaction.transaction_date),
            Transaction.product_id,
            Transaction.vendor_id,
        )
        .all()
    )
    refund_map = {
        (str(r.tx_date)[:10], r.product_id, r.vendor_id): (r.refunds_sum or 0.0)
        for r in refund_agg
    }

    upsert_count = 0
    now_dt = datetime.utcnow()

    for row in tx_agg:
        row_date = _to_date(row.tx_date)
        if not row_date:
            continue
        pid = row.product_id
        vid = row.vendor_id
        units = int(row.units_sold or 0)
        gross_gmv = float(row.gross_gmv or 0.0)
        discounts = float(row.discounts or 0.0)
        tx_count = int(row.tx_count or 0)

        refund_amt = refund_map.get((str(row_date), pid, vid), 0.0)
        net_sales = max(0.0, gross_gmv - discounts - refund_amt)

        prod_info = product_map.get(pid, {})
        category = prod_info.get("category", "Uncategorized")
        cost_price = prod_info.get("cost_price")

        # Nullable COGS accounting
        if cost_price is not None and cost_price > 0:
            known_cogs = round(units * cost_price, 2)
            reported_profit = round(net_sales - known_cogs, 2)
            coverage_pct = 100.0
        else:
            known_cogs = None
            reported_profit = None
            coverage_pct = 0.0

        # Check existing mart entry for upsert
        mart_entry = (
            db.query(DailySalesMart)
            .filter(
                DailySalesMart.date == row_date,
                DailySalesMart.product_id == pid,
                DailySalesMart.vendor_id == vid,
            )
            .first()
        )

        if mart_entry:
            # Idempotent update
            mart_entry.category = category
            mart_entry.units_sold = units
            mart_entry.gross_sales_gmv = round(gross_gmv, 2)
            mart_entry.discounts_total = round(discounts, 2)
            mart_entry.refunds_total = round(refund_amt, 2)
            mart_entry.net_sales = round(net_sales, 2)
            mart_entry.known_cogs = known_cogs
            mart_entry.reported_gross_profit = reported_profit
            mart_entry.cogs_coverage_pct = coverage_pct
            mart_entry.transaction_count = tx_count
            mart_entry.last_refreshed_at = now_dt
        else:
            # Insert new record
            mart_entry = DailySalesMart(
                date=row_date,
                product_id=pid,
                vendor_id=vid,
                category=category,
                units_sold=units,
                gross_sales_gmv=round(gross_gmv, 2),
                discounts_total=round(discounts, 2),
                refunds_total=round(refund_amt, 2),
                net_sales=round(net_sales, 2),
                known_cogs=known_cogs,
                reported_gross_profit=reported_profit,
                cogs_coverage_pct=coverage_pct,
                transaction_count=tx_count,
                last_refreshed_at=now_dt,
            )
            db.add(mart_entry)

        upsert_count += 1

    db.commit()

    return {
        "status": "SUCCESS",
        "message": f"Daily sales mart refreshed successfully ({upsert_count} dimensional records updated/created).",
        "records_upserted": upsert_count,
        "date_range": {
            "start_date": str(start_date),
            "end_date": str(end_date),
        },
        "full_rebuild": full_rebuild,
    }


def query_daily_sales_mart(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    vendor_id: Optional[int] = None,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
    """
    Queries aggregated daily sales mart records with pagination and dimension filters.
    Returns (records, total_count, aggregated_summary).
    """
    q = db.query(DailySalesMart)
    if start_date:
        q = q.filter(DailySalesMart.date >= start_date)
    if end_date:
        q = q.filter(DailySalesMart.date <= end_date)
    if vendor_id:
        q = q.filter(DailySalesMart.vendor_id == vendor_id)
    if product_id:
        q = q.filter(DailySalesMart.product_id == product_id)
    if category:
        q = q.filter(DailySalesMart.category == category)

    total_count = q.count()

    # Aggregate summaries
    sum_query = db.query(
        func.sum(DailySalesMart.units_sold),
        func.sum(DailySalesMart.gross_sales_gmv),
        func.sum(DailySalesMart.discounts_total),
        func.sum(DailySalesMart.refunds_total),
        func.sum(DailySalesMart.net_sales),
        func.sum(DailySalesMart.known_cogs),
        func.sum(DailySalesMart.reported_gross_profit),
        func.sum(DailySalesMart.transaction_count),
    )
    if start_date:
        sum_query = sum_query.filter(DailySalesMart.date >= start_date)
    if end_date:
        sum_query = sum_query.filter(DailySalesMart.date <= end_date)
    if vendor_id:
        sum_query = sum_query.filter(DailySalesMart.vendor_id == vendor_id)
    if product_id:
        sum_query = sum_query.filter(DailySalesMart.product_id == product_id)
    if category:
        sum_query = sum_query.filter(DailySalesMart.category == category)

    res = sum_query.first()
    summary = {
        "total_units_sold": int(res[0] or 0),
        "total_gross_gmv": round(float(res[1] or 0.0), 2),
        "total_discounts": round(float(res[2] or 0.0), 2),
        "total_refunds": round(float(res[3] or 0.0), 2),
        "total_net_sales": round(float(res[4] or 0.0), 2),
        "total_known_cogs": round(float(res[5] or 0.0), 2) if res[5] is not None else None,
        "total_reported_gross_profit": round(float(res[6] or 0.0), 2) if res[6] is not None else None,
        "total_transactions": int(res[7] or 0),
    }

    records = q.order_by(DailySalesMart.date.desc(), DailySalesMart.gross_sales_gmv.desc()).offset(offset).limit(limit).all()
    return [r.to_dict() for r in records], total_count, summary
