"""
services/inventory_service.py — Business logic and algorithms for Product & Inventory Analytics.

Features:
  1. Real-time Inventory Status & Valuation.
  2. Stock Movement Auditing & Restocking.
  3. Inventory Turnover Ratio & Days Sales of Inventory (DSI).
  4. Time-Series Demand Forecasting with Seasonality and Chronological Holdout (MAE, RMSE, WAPE).
  5. Low-Stock Alerts & Depletion Projections.
  6. Dynamic Replenishment Recommendations (ROP, Safety Stock, Recommended Order Qty).
"""

import math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.stock_movement import StockMovement
from app.models.vendor import Vendor


def get_inventory_status(db: Session) -> list[dict]:
    """
    Returns current stock levels, inventory valuation, and status badges for all products.
    """
    rows = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.price,
            Product.category,
            Product.parent_category,
            Vendor.name.label("vendor_name"),
            Inventory.inventory_id,
            Inventory.current_stock,
            Inventory.warehouse,
            Inventory.reorder_level,
            Inventory.updated_at,
        )
        .outerjoin(Inventory, Product.id == Inventory.product_id)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .all()
    )

    result = []
    for r in rows:
        stock = r.current_stock if r.current_stock is not None else 0
        reorder = r.reorder_level if r.reorder_level is not None else 10
        price = float(r.price)
        stock_value = round(stock * price, 2)

        if stock == 0:
            status = "CRITICAL"
        elif stock <= reorder:
            status = "LOW_STOCK"
        else:
            status = "HEALTHY"

        result.append({
            "product_id": r.product_id,
            "product_name": r.product_name,
            "category": r.category,
            "parent_category": r.parent_category,
            "vendor_name": r.vendor_name,
            "warehouse": r.warehouse or "Main Warehouse",
            "current_stock": stock,
            "reorder_level": reorder,
            "unit_price": price,
            "stock_value": stock_value,
            "status": status,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return result


def record_stock_movement(
    db: Session,
    product_id: int,
    movement_type: str,
    quantity: int,
    source_warehouse: str | None = None,
    target_warehouse: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
) -> StockMovement:
    """
    Logs an immutable stock movement and updates the current_stock in the inventory table.
    - RESTOCK / RETURN: quantity should be positive (increases stock).
    - SALE: quantity should be positive (decreases stock by quantity) or negative.
    - ADJUSTMENT: adjustments can be positive or negative.
    """
    if quantity == 0:
        raise ValueError("Movement quantity cannot be zero.")

    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise ValueError(f"Product {product_id} not found.")

    inv = db.query(Inventory).filter_by(product_id=product_id).first()
    if not inv:
        # Create inventory if missing
        inv = Inventory(product_id=product_id, current_stock=0)
        db.add(inv)
        db.flush()

    # Determine delta
    m_type = movement_type.upper().strip()
    if m_type in ["RESTOCK", "RETURN"]:
        delta = abs(quantity)
    elif m_type == "SALE":
        delta = -abs(quantity)
    else:  # ADJUSTMENT, TRANSFER
        delta = quantity

    new_stock = inv.current_stock + delta
    if new_stock < 0:
        raise ValueError(f"Insufficient stock for product {product_id}: current {inv.current_stock}, requested {delta}.")

    inv.current_stock = new_stock
    inv.updated_at = datetime.utcnow()

    movement = StockMovement(
        product_id=product_id,
        movement_type=m_type,
        quantity=delta,
        source_warehouse=source_warehouse,
        target_warehouse=target_warehouse,
        reference_id=reference_id,
        notes=notes,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def get_stock_movements(
    db: Session,
    product_id: int | None = None,
    movement_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Retrieves recent stock movement audit records.
    """
    query = (
        db.query(
            StockMovement.movement_id,
            StockMovement.product_id,
            Product.name.label("product_name"),
            StockMovement.movement_type,
            StockMovement.quantity,
            StockMovement.source_warehouse,
            StockMovement.target_warehouse,
            StockMovement.reference_id,
            StockMovement.notes,
            StockMovement.created_at,
        )
        .join(Product, StockMovement.product_id == Product.id)
        .order_by(StockMovement.created_at.desc())
    )

    if product_id is not None:
        query = query.filter(StockMovement.product_id == product_id)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type.upper())

    rows = query.limit(limit).all()
    return [
        {
            "movement_id": r.movement_id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "movement_type": r.movement_type,
            "quantity": r.quantity,
            "source_warehouse": r.source_warehouse,
            "target_warehouse": r.target_warehouse,
            "reference_id": r.reference_id,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _get_reference_anchor_date(db: Session, lookback_days: int) -> tuple[datetime, datetime]:
    """
    Returns (anchor_date, since_date) for lookback window calculations.
    - If no transactions exist, anchors to datetime.utcnow().
    - If the latest recorded transaction is within lookback_days of datetime.utcnow(),
      anchors to datetime.utcnow() (standard live operating behavior).
    - If the latest recorded transaction is older than lookback_days (e.g. historical/benchmark dataset),
      anchors to the latest transaction timestamp in the database, evaluating over its active window.
    """
    max_txn_date = db.query(func.max(Transaction.transaction_date)).scalar()
    if not max_txn_date:
        now = datetime.utcnow()
        return now, now - timedelta(days=lookback_days)

    now = datetime.utcnow()
    # Check if latest transaction is within the lookback window of current system time
    if (now - max_txn_date).days < lookback_days:
        anchor_date = now
    else:
        anchor_date = max_txn_date

    since_date = anchor_date - timedelta(days=lookback_days)
    return anchor_date, since_date


def calculate_inventory_turnover(db: Session, days: int = 365) -> dict:
    """
    Calculates Inventory Turnover Ratio and Days Sales of Inventory (DSI).
    Formula:
        Turnover = Total Units Sold in period / Average Stock Level
        DSI = days / Turnover
    Classifies products into:
      - FAST_MOVING (Turnover >= 4.0)
      - NORMAL (1.0 <= Turnover < 4.0)
      - SLOW_MOVING (0 < Turnover < 1.0)
      - DEAD_STOCK (Turnover == 0)
    """
    anchor_date, since_date = _get_reference_anchor_date(db, lookback_days=days)

    # 1. Total units sold per product in period
    sales_query = (
        db.query(
            Transaction.product_id,
            func.sum(Transaction.quantity).label("units_sold"),
            func.sum(Transaction.amount).label("sales_revenue"),
        )
        .filter(Transaction.transaction_date >= since_date)
        .filter(Transaction.transaction_date <= anchor_date)
        .group_by(Transaction.product_id)
        .all()
    )
    sales_map = {r.product_id: (int(r.units_sold or 0), float(r.sales_revenue or 0.0)) for r in sales_query}

    # 2. Get current stock and product details
    products = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Product.category,
            Inventory.current_stock,
        )
        .outerjoin(Inventory, Product.id == Inventory.product_id)
        .all()
    )

    product_metrics = []
    total_sales_units = 0
    total_sales_val = 0.0
    total_current_stock = 0

    for p in products:
        stock = p.current_stock if p.current_stock is not None else 0
        units_sold, revenue = sales_map.get(p.id, (0, 0.0))

        # Average inventory: if stock > 0 use current stock, otherwise 1.0
        avg_stock = max(1.0, float(stock if stock > 0 else 1.0))

        turnover = round(units_sold / avg_stock, 2)
        dsi = round(days / turnover, 1) if turnover > 0 else 999.0

        if turnover >= 4.0:
            velocity = "FAST_MOVING"
        elif turnover >= 1.0:
            velocity = "NORMAL"
        elif turnover > 0:
            velocity = "SLOW_MOVING"
        else:
            velocity = "DEAD_STOCK"

        product_metrics.append({
            "product_id": p.id,
            "product_name": p.name,
            "category": p.category,
            "current_stock": stock,
            "units_sold": units_sold,
            "sales_revenue": round(revenue, 2),
            "turnover_ratio": turnover,
            "days_sales_inventory": dsi,
            "velocity": velocity,
        })

        total_sales_units += units_sold
        total_sales_val += revenue
        total_current_stock += stock

    # Catalog aggregate metrics
    catalog_avg_stock = max(1.0, float(total_current_stock))
    catalog_turnover = round(total_sales_units / catalog_avg_stock, 2)
    catalog_dsi = round(days / catalog_turnover, 1) if catalog_turnover > 0 else 999.0

    return {
        "period_days": days,
        "catalog_summary": {
            "total_units_sold": total_sales_units,
            "total_sales_revenue": round(total_sales_val, 2),
            "total_current_stock": total_current_stock,
            "catalog_turnover_ratio": catalog_turnover,
            "catalog_dsi": catalog_dsi,
        },
        "products": sorted(product_metrics, key=lambda x: x["turnover_ratio"], reverse=True),
    }


def get_low_stock_alerts(db: Session) -> list[dict]:
    """
    Identifies all products currently at or below reorder level,
    along with estimated daily sales velocity and days to depletion.
    """
    # 90-day velocity window
    anchor_date, since_date = _get_reference_anchor_date(db, lookback_days=90)
    sales_query = (
        db.query(
            Transaction.product_id,
            func.sum(Transaction.quantity).label("qty_90d"),
        )
        .filter(Transaction.transaction_date >= since_date)
        .filter(Transaction.transaction_date <= anchor_date)
        .group_by(Transaction.product_id)
        .all()
    )
    velocity_map = {r.product_id: max(0.01, float(r.qty_90d or 0) / 90.0) for r in sales_query}

    products = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Vendor.name.label("vendor_name"),
            Inventory.current_stock,
            Inventory.reorder_level,
            Inventory.warehouse,
        )
        .join(Inventory, Product.id == Inventory.product_id)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .filter(Inventory.current_stock <= Inventory.reorder_level)
        .order_by(Inventory.current_stock.asc())
        .all()
    )

    alerts = []
    for p in products:
        stock = p.current_stock
        reorder = p.reorder_level
        daily_vel = velocity_map.get(p.id, 0.5)
        days_remaining = round(stock / daily_vel, 1) if daily_vel > 0 else 999.0

        severity = "CRITICAL" if stock == 0 else "WARNING"

        alerts.append({
            "product_id": p.id,
            "product_name": p.name,
            "vendor_name": p.vendor_name,
            "warehouse": p.warehouse,
            "current_stock": stock,
            "reorder_level": reorder,
            "daily_sales_velocity": round(daily_vel, 2),
            "days_until_stockout": days_remaining,
            "severity": severity,
            "recommended_action": "Order immediate restock" if severity == "CRITICAL" else "Initiate purchase order",
        })
    return alerts


def get_replenishment_recommendations(db: Session, lead_time_days: int = 5, service_factor: float = 1.65) -> list[dict]:
    """
    Calculates dynamic replenishment recommendations.
    Formulas:
        Daily Demand (D_avg) = avg daily units sold over past 90 days.
        Demand Standard Deviation (sigma_D) = std of daily sales.
        Safety Stock (SS) = service_factor * sigma_D * sqrt(lead_time_days).
        Reorder Point (ROP) = (D_avg * lead_time_days) + SS.
        Recommended Order Quantity = max(0, ceil(ROP - current_stock + (D_avg * 14))).
    """
    # 90-day transactions to compute daily demand and variance
    anchor_date, since_date = _get_reference_anchor_date(db, lookback_days=90)
    txns = (
        db.query(
            Transaction.product_id,
            Transaction.quantity,
            Transaction.transaction_date,
        )
        .filter(Transaction.transaction_date >= since_date)
        .filter(Transaction.transaction_date <= anchor_date)
        .all()
    )

    df_txns = pd.DataFrame([
        {
            "product_id": t.product_id,
            "quantity": t.quantity,
            "txn_date": t.transaction_date.strftime("%Y-%m-%d") if hasattr(t.transaction_date, "strftime") else str(t.transaction_date)[:10],
        }
        for t in txns
    ])

    products = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Product.vendor_id,
            Vendor.name.label("vendor_name"),
            Inventory.current_stock,
            Inventory.reorder_level,
        )
        .join(Inventory, Product.id == Inventory.product_id)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .all()
    )

    recommendations = []
    for p in products:
        stock = p.current_stock
        unit_price = float(p.price)

        if not df_txns.empty and p.id in df_txns["product_id"].values:
            p_sales = df_txns[df_txns["product_id"] == p.id].groupby("txn_date")["quantity"].sum()
            # Fill inactive days with 0 over 90 days
            daily_demand = float(p_sales.sum() / 90.0)
            daily_std = float(p_sales.std()) if len(p_sales) > 1 else max(1.0, daily_demand * 0.5)
            if math.isnan(daily_std) or daily_std <= 0:
                daily_std = max(1.0, daily_demand * 0.5)
        else:
            daily_demand = 1.0
            daily_std = 0.5

        # Safety Stock & ROP
        calc_ss = math.ceil(service_factor * daily_std * math.sqrt(lead_time_days))
        safety_stock = max(1, calc_ss) if daily_demand > 0 else 0
        lead_time_demand = daily_demand * lead_time_days
        rop = math.ceil(lead_time_demand + safety_stock)

        # 14 days cycle inventory replenishment buffer
        target_inventory = rop + math.ceil(daily_demand * 14)
        recommended_qty = max(0, target_inventory - stock)
        needs_reorder = stock <= rop or stock <= p.reorder_level

        recommendations.append({
            "product_id": p.id,
            "product_name": p.name,
            "vendor_id": p.vendor_id,
            "vendor_name": p.vendor_name,
            "current_stock": stock,
            "reorder_level": p.reorder_level,
            "lead_time_days": lead_time_days,
            "avg_daily_demand": round(daily_demand, 2),
            "safety_stock": safety_stock,
            "reorder_point": rop,
            "recommended_order_quantity": recommended_qty,
            "estimated_order_cost": round(recommended_qty * unit_price, 2),
            "needs_reorder": needs_reorder,
            "priority": "HIGH" if stock <= p.reorder_level else ("MEDIUM" if stock <= rop else "LOW"),
        })

    return sorted(recommendations, key=lambda x: (x["priority"] != "HIGH", x["priority"] != "MEDIUM", -x["recommended_order_quantity"]))


def forecast_product_demand(db: Session, product_id: int, forecast_days: int = 14) -> dict:
    """
    Time-Series Demand Forecasting using Seasonality and Chronological Holdout Evaluation.

    Methodology:
      1. Aggregates daily transaction volume for the product.
      2. Chronological Split: First 80% of days for training, remaining 20% holdout for testing.
      3. Features: Day-of-week indicators (seasonality) + Linear trend component.
      4. Holdout Evaluation Metrics:
         - MAE (Mean Absolute Error)
         - RMSE (Root Mean Squared Error)
         - WAPE (Weighted Absolute Percentage Error = sum(|y - y_hat|) / sum(y))
         * Explicitly rejects R^2 * 100 as invalid for time-series forecasting.
      5. Generates forward predictions for next `forecast_days` days with confidence bands.
    """
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise ValueError(f"Product {product_id} not found.")

    txns = (
        db.query(
            Transaction.quantity,
            Transaction.transaction_date,
        )
        .filter(Transaction.product_id == product_id)
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    if len(txns) < 5:
        # Fallback heuristic for sparse data
        return {
            "product_id": product_id,
            "product_name": product.name,
            "forecast_days": forecast_days,
            "insufficient_data": True,
            "message": "Not enough historical transaction records (< 5) to compute statistical forecast.",
            "metrics": {"mae": 0.0, "rmse": 0.0, "wape": 0.0},
            "historical_daily": [],
            "forecast": [
                {
                    "date": (datetime.utcnow() + timedelta(days=i)).strftime("%Y-%m-%d"),
                    "predicted_demand": 1.0,
                    "lower_bound": 0.0,
                    "upper_bound": 2.0,
                }
                for i in range(1, forecast_days + 1)
            ],
        }

    # Aggregate by calendar date
    records = []
    for t in txns:
        d = t.transaction_date.strftime("%Y-%m-%d")
        records.append({"date": d, "quantity": t.quantity})

    df_raw = pd.DataFrame(records)
    daily = df_raw.groupby("date")["quantity"].sum().reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)

    # Fill date range gaps with 0
    full_idx = pd.date_range(start=daily["date"].min(), end=daily["date"].max(), freq="D")
    daily = daily.set_index("date").reindex(full_idx, fill_value=0).reset_index()
    daily.rename(columns={"index": "date"}, inplace=True)

    # Feature engineering: trend + day of week
    daily["trend"] = np.arange(len(daily))
    daily["day_of_week"] = daily["date"].dt.dayofweek

    # One-hot encode day of week (0=Mon .. 6=Sun)
    for dow in range(7):
        daily[f"dow_{dow}"] = (daily["day_of_week"] == dow).astype(float)

    feature_cols = ["trend"] + [f"dow_{dow}" for dow in range(7)]
    X = daily[feature_cols].values
    y = daily["quantity"].values.astype(float)

    # Chronological 80/20 train/test holdout
    n_total = len(daily)
    n_train = max(4, int(n_total * 0.8))
    X_train, X_test = X[:n_train], X[n_train:]
    y_train, y_test = y[:n_train], y[n_train:]

    # Fit linear regression via least squares: beta = (X^T X)^-1 X^T y (with ridge regularization for stability)
    reg_lambda = 1.0
    XtX = X_train.T @ X_train + reg_lambda * np.eye(X_train.shape[1])
    Xty = X_train.T @ y_train
    beta = np.linalg.solve(XtX, Xty)

    # Evaluate on test holdout
    if len(y_test) > 0:
        y_pred_test = np.clip(X_test @ beta, 0, None)
        mae = float(np.mean(np.abs(y_test - y_pred_test)))
        rmse = float(np.sqrt(np.mean((y_test - y_pred_test) ** 2)))
        sum_y_test = float(np.sum(y_test))
        wape = float(np.sum(np.abs(y_test - y_pred_test)) / sum_y_test) if sum_y_test > 0 else 0.0
    else:
        mae, rmse, wape = 0.0, 0.0, 0.0

    # Refit on all historical data for forward forecasting
    XtX_full = X.T @ X + reg_lambda * np.eye(X.shape[1])
    Xty_full = X.T @ y
    beta_full = np.linalg.solve(XtX_full, Xty_full)

    # Forward forecast
    last_date = daily["date"].max()
    last_trend = daily["trend"].max()
    forecast_results = []
    residual_std = max(0.5, float(np.std(y - (X @ beta_full))))

    for i in range(1, forecast_days + 1):
        f_date = last_date + timedelta(days=i)
        f_trend = last_trend + i
        f_dow = f_date.dayofweek
        x_f = np.array([f_trend] + [1.0 if f_dow == d else 0.0 for d in range(7)])
        pred_val = max(0.0, float(x_f @ beta_full))

        forecast_results.append({
            "date": f_date.strftime("%Y-%m-%d"),
            "predicted_demand": round(pred_val, 2),
            "lower_bound": round(max(0.0, pred_val - 1.65 * residual_std), 2),
            "upper_bound": round(pred_val + 1.65 * residual_std, 2),
        })

    # Sample historical points for chart display (last 30 days)
    recent_history = daily.tail(30)
    historical_points = [
        {"date": row["date"].strftime("%Y-%m-%d"), "actual_demand": int(row["quantity"])}
        for _, row in recent_history.iterrows()
    ]

    return {
        "product_id": product_id,
        "product_name": product.name,
        "forecast_days": forecast_days,
        "insufficient_data": False,
        "metrics": {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "wape": round(wape, 4),
            "train_samples": n_train,
            "test_samples": len(y_test),
            "split_type": "Chronological 80/20 (Zero Data Leakage)",
        },
        "historical_daily": historical_points,
        "forecast": forecast_results,
    }
