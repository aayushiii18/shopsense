"""
tests/test_inventory_analytics.py — Tests for Module 1: Product & Inventory Analytics Engine.

Covers:
  - Inventory status and valuation endpoints
  - Stock movement auditing, restocks, sales deductions, and stock constraint enforcement
  - Inventory turnover, DSI, and velocity classification
  - Low-stock alerts and depletion projections
  - Dynamic replenishment recommendations (ROP, Safety Stock, Recommended Qty)
  - Time-series demand forecasting with chronological holdout evaluation (MAE, RMSE, WAPE)
"""

from datetime import datetime, timedelta
import pytest
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.stock_movement import StockMovement


def _seed_basic_catalog(db_session):
    v = Vendor(name="Test Vendor", email="v1@test.com", phone="+91-9999999991")
    db_session.add(v)
    db_session.flush()

    p1 = Product(name="Item A", price=100.0, category="Electronics", parent_category="Tech", vendor_id=v.id)
    p2 = Product(name="Item B", price=50.0, category="Accessories", parent_category="Tech", vendor_id=v.id)
    db_session.add_all([p1, p2])
    db_session.flush()

    inv1 = Inventory(product_id=p1.id, current_stock=25, reorder_level=10, warehouse="Main")
    inv2 = Inventory(product_id=p2.id, current_stock=5, reorder_level=15, warehouse="Main")
    db_session.add_all([inv1, inv2])
    db_session.commit()
    return v, p1, p2, inv1, inv2


def test_inventory_status_empty(client):
    res = client.get("/analytics/inventory/status")
    assert res.status_code == 200
    assert res.json() == []


def test_inventory_status_with_products(client, db_session):
    _, p1, p2, inv1, inv2 = _seed_basic_catalog(db_session)

    res = client.get("/analytics/inventory/status")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2

    item_a = next(d for d in data if d["product_id"] == p1.id)
    assert item_a["current_stock"] == 25
    assert item_a["stock_value"] == 2500.0
    assert item_a["status"] == "HEALTHY"

    item_b = next(d for d in data if d["product_id"] == p2.id)
    assert item_b["current_stock"] == 5
    assert item_b["stock_value"] == 250.0
    assert item_b["status"] == "LOW_STOCK"


def test_record_stock_movement_restock(client, db_session):
    _, p1, _, inv1, _ = _seed_basic_catalog(db_session)
    initial_stock = inv1.current_stock

    payload = {
        "product_id": p1.id,
        "movement_type": "RESTOCK",
        "quantity": 50,
        "source_warehouse": "Supplier",
        "target_warehouse": "Main",
        "notes": "Incoming replenishment shipment",
    }
    res = client.post("/inventory/movements", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["movement_id"] is not None
    assert data["quantity"] == 50

    db_session.refresh(inv1)
    assert inv1.current_stock == initial_stock + 50


def test_record_stock_movement_sale(client, db_session):
    _, p1, _, inv1, _ = _seed_basic_catalog(db_session)
    initial_stock = inv1.current_stock

    payload = {
        "product_id": p1.id,
        "movement_type": "SALE",
        "quantity": 10,
        "reference_id": 999,
        "notes": "Order fulfillment",
    }
    res = client.post("/inventory/movements", json=payload)
    assert res.status_code == 201

    db_session.refresh(inv1)
    assert inv1.current_stock == initial_stock - 10


def test_record_stock_movement_insufficient_stock_fails(client, db_session):
    _, p1, _, inv1, _ = _seed_basic_catalog(db_session)

    payload = {
        "product_id": p1.id,
        "movement_type": "SALE",
        "quantity": 100,  # current stock is only 25
    }
    res = client.post("/inventory/movements", json=payload)
    assert res.status_code == 400
    assert "Insufficient stock" in res.json()["detail"]


def test_record_stock_movement_zero_qty_fails(client, db_session):
    _, p1, _, _, _ = _seed_basic_catalog(db_session)
    payload = {
        "product_id": p1.id,
        "movement_type": "RESTOCK",
        "quantity": 0,
    }
    res = client.post("/inventory/movements", json=payload)
    assert res.status_code == 422 or res.status_code == 400


def test_list_stock_movements_filtered(client, db_session):
    _, p1, p2, _, _ = _seed_basic_catalog(db_session)

    client.post("/inventory/movements", json={"product_id": p1.id, "movement_type": "RESTOCK", "quantity": 10})
    client.post("/inventory/movements", json={"product_id": p2.id, "movement_type": "RESTOCK", "quantity": 20})

    res = client.get(f"/analytics/inventory/movements?product_id={p1.id}")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["product_id"] == p1.id


def test_inventory_turnover_and_dsi(client, db_session):
    v, p1, p2, _, _ = _seed_basic_catalog(db_session)

    # Add transactions
    now = datetime.utcnow()
    t1 = Transaction(product_id=p1.id, vendor_id=v.id, quantity=100, unit_price=100.0, amount=10000.0, transaction_date=now)
    t2 = Transaction(product_id=p2.id, vendor_id=v.id, quantity=5, unit_price=50.0, amount=250.0, transaction_date=now)
    db_session.add_all([t1, t2])
    db_session.commit()

    res = client.get("/analytics/inventory/turnover?days=365")
    assert res.status_code == 200
    data = res.json()
    assert "catalog_summary" in data
    assert len(data["products"]) == 2

    item_a = next(p for p in data["products"] if p["product_id"] == p1.id)
    assert item_a["units_sold"] == 100
    assert item_a["velocity"] in ["FAST_MOVING", "NORMAL"]
    assert item_a["days_sales_inventory"] > 0


def test_low_stock_alerts(client, db_session):
    _, p1, p2, _, _ = _seed_basic_catalog(db_session)
    # p2 has current_stock=5 <= reorder_level=15
    res = client.get("/analytics/inventory/low-stock")
    assert res.status_code == 200
    alerts = res.json()
    assert len(alerts) >= 1
    p2_alert = next(a for a in alerts if a["product_id"] == p2.id)
    assert p2_alert["severity"] == "WARNING"
    assert p2_alert["current_stock"] == 5


def test_replenishment_recommendations(client, db_session):
    v, p1, p2, _, _ = _seed_basic_catalog(db_session)
    # Seed transactions to establish demand
    now = datetime.utcnow()
    for i in range(10):
        t = Transaction(
            product_id=p2.id,
            vendor_id=v.id,
            quantity=5,
            unit_price=50.0,
            amount=250.0,
            transaction_date=now - timedelta(days=i * 2),
        )
        db_session.add(t)
    db_session.commit()

    res = client.get("/analytics/inventory/replenishment?lead_time_days=5&service_level=0.95")
    assert res.status_code == 200
    recs = res.json()
    assert len(recs) == 2
    p2_rec = next(r for r in recs if r["product_id"] == p2.id)
    assert p2_rec["safety_stock"] > 0
    assert p2_rec["reorder_point"] > 0
    assert p2_rec["needs_reorder"] is True
    assert p2_rec["recommended_order_quantity"] > 0


def test_demand_forecasting_with_chronological_holdout(client, db_session):
    v, p1, _, _, _ = _seed_basic_catalog(db_session)
    # Generate 30 days of transactions for p1
    start_time = datetime.utcnow() - timedelta(days=35)
    for i in range(30):
        t_date = start_time + timedelta(days=i)
        qty = 5 + (i % 7)  # weekly seasonality pattern
        t = Transaction(
            product_id=p1.id,
            vendor_id=v.id,
            quantity=qty,
            unit_price=100.0,
            amount=qty * 100.0,
            transaction_date=t_date,
        )
        db_session.add(t)
    db_session.commit()

    res = client.get(f"/analytics/inventory/forecast/{p1.id}?forecast_days=7")
    assert res.status_code == 200
    data = res.json()
    assert data["product_id"] == p1.id
    assert data["forecast_days"] == 7
    assert not data["insufficient_data"]

    # Verify error metrics exist and use chronological holdout
    metrics = data["metrics"]
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "wape" in metrics
    assert metrics["mae"] >= 0
    assert metrics["rmse"] >= 0
    assert metrics["wape"] >= 0
    assert "Chronological" in metrics["split_type"]

    # Verify forward forecast points
    assert len(data["forecast"]) == 7
    for f in data["forecast"]:
        assert "predicted_demand" in f
        assert "lower_bound" in f
        assert "upper_bound" in f
        assert f["lower_bound"] <= f["predicted_demand"] <= f["upper_bound"]


def test_demand_forecast_nonexistent_product_404(client):
    res = client.get("/analytics/inventory/forecast/99999")
    assert res.status_code == 404


def test_inventory_turnover_historical_dataset(client, db_session):
    """
    Regression test: Transactions from an older historical dataset (e.g., 2 years ago)
    must not silently return 0.0 turnover when queried with a 365-day lookback.
    The service must anchor to the dataset's reference date and evaluate over its active window.
    """
    v, p1, _, _, _ = _seed_basic_catalog(db_session)
    historical_base = datetime(2024, 1, 1, 10, 0, 0)
    for i in range(10):
        t = Transaction(
            product_id=p1.id,
            vendor_id=v.id,
            quantity=10,
            unit_price=100.0,
            amount=1000.0,
            transaction_date=historical_base + timedelta(days=i * 20),
        )
        db_session.add(t)
    db_session.commit()

    res = client.get("/analytics/inventory/turnover?days=365")
    assert res.status_code == 200
    data = res.json()
    item_a = next(p for p in data["products"] if p["product_id"] == p1.id)
    # 10 * 10 = 100 units sold historically
    assert item_a["units_sold"] == 100
    assert item_a["turnover_ratio"] > 0
    assert data["catalog_summary"]["total_units_sold"] == 100
    assert data["catalog_summary"]["catalog_turnover_ratio"] > 0


def test_inventory_turnover_empty_history(client, db_session):
    """
    Verify empty transaction history returns clean zeros without exceptions.
    """
    _, p1, _, _, _ = _seed_basic_catalog(db_session)
    res = client.get("/analytics/inventory/turnover?days=365")
    assert res.status_code == 200
    data = res.json()
    assert data["catalog_summary"]["total_units_sold"] == 0
    assert data["catalog_summary"]["catalog_turnover_ratio"] == 0.0
    assert data["catalog_summary"]["catalog_dsi"] == 999.0
    item_a = next(p for p in data["products"] if p["product_id"] == p1.id)
    assert item_a["units_sold"] == 0
    assert item_a["turnover_ratio"] == 0.0
    assert item_a["velocity"] == "DEAD_STOCK"


def test_inventory_turnover_current_date_data(client, db_session):
    """
    Verify lookback window anchors correctly to datetime.utcnow() when live current data exists.
    """
    v, p1, _, _, _ = _seed_basic_catalog(db_session)
    now = datetime.utcnow()
    t = Transaction(
        product_id=p1.id,
        vendor_id=v.id,
        quantity=25,
        unit_price=100.0,
        amount=2500.0,
        transaction_date=now - timedelta(days=2),
    )
    db_session.add(t)
    db_session.commit()

    res = client.get("/analytics/inventory/turnover?days=365")
    assert res.status_code == 200
    data = res.json()
    item_a = next(p for p in data["products"] if p["product_id"] == p1.id)
    assert item_a["units_sold"] == 25
    assert item_a["turnover_ratio"] == 1.0


def test_replenishment_recommendations_historical_dataset(client, db_session):
    """
    Regression test: Replenishment velocity and safety stock calculation
    must evaluate correctly over active 90-day window on historical benchmark datasets.
    """
    v, _, p2, _, _ = _seed_basic_catalog(db_session)
    historical_base = datetime(2024, 6, 1, 12, 0, 0)
    for i in range(12):
        t = Transaction(
            product_id=p2.id,
            vendor_id=v.id,
            quantity=4,
            unit_price=50.0,
            amount=200.0,
            transaction_date=historical_base - timedelta(days=i * 5),
        )
        db_session.add(t)
    db_session.commit()

    res = client.get("/analytics/inventory/replenishment?lead_time_days=5&service_level=0.95")
    assert res.status_code == 200
    recs = res.json()
    p2_rec = next(r for r in recs if r["product_id"] == p2.id)
    assert p2_rec["avg_daily_demand"] > 0
    assert p2_rec["safety_stock"] > 0
    assert p2_rec["reorder_point"] > 0


def test_inventory_turnover_mixed_dates(client, db_session):
    """
    Regression test: Mixed historical and current transactions.
    When recent transactions exist alongside historical transactions:
    - Lookback window must anchor to current time (live operations).
    - Recent transactions within the window are included.
    - Historical transactions older than the lookback window are excluded.
    """
    v, p1, _, _, _ = _seed_basic_catalog(db_session)
    now = datetime.utcnow()

    # Historical transaction (500 days ago) — should be excluded from a 365-day lookback
    t_old = Transaction(
        product_id=p1.id,
        vendor_id=v.id,
        quantity=100,
        unit_price=100.0,
        amount=10000.0,
        transaction_date=now - timedelta(days=500),
    )
    # Recent transaction (5 days ago) — should be included in a 365-day lookback
    t_new = Transaction(
        product_id=p1.id,
        vendor_id=v.id,
        quantity=20,
        unit_price=100.0,
        amount=2000.0,
        transaction_date=now - timedelta(days=5),
    )
    db_session.add_all([t_old, t_new])
    db_session.commit()

    res = client.get("/analytics/inventory/turnover?days=365")
    assert res.status_code == 200
    data = res.json()
    item_a = next(p for p in data["products"] if p["product_id"] == p1.id)
    # Must only include the 20 units from the recent transaction
    assert item_a["units_sold"] == 20
    assert data["catalog_summary"]["total_units_sold"] == 20


