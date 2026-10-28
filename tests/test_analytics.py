"""
tests/test_analytics.py — Tests for analytics endpoints and calculations.

Covers:
  - Total revenue on empty DB returns 0
  - Revenue by vendor on empty DB returns []
  - Revenue by product on empty DB returns []
  - Top-selling product on empty DB returns 404
  - Summary on empty DB returns zero counts
  - Total revenue is calculated correctly
  - Vendor-wise revenue aggregation
  - Product-wise revenue aggregation
  - Top-selling product identification
  - Summary report completeness
"""

import pytest
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.transaction import Transaction


# ── Helper: seed test data ────────────────────────────────────────────────────

def _seed_data(db_session):
    """
    Insert 2 vendors, 3 products, and 5 transactions into the test DB.
    Returns a dict with expected computed values for assertions.
    """
    v1 = Vendor(name="Vendor Alpha", email="alpha@test.com", phone="1234567890")
    v2 = Vendor(name="Vendor Beta", email="beta@test.com", phone="0987654321")
    db_session.add_all([v1, v2])
    db_session.flush()  # get IDs without committing

    p1 = Product(name="Widget A", price=100.0, vendor_id=v1.id)
    p2 = Product(name="Widget B", price=200.0, vendor_id=v1.id)
    p3 = Product(name="Gadget C", price=50.0, vendor_id=v2.id)
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    # Transactions:
    # p1: 2 × 100 = 200  (vendor 1)
    # p1: 3 × 100 = 300  (vendor 1)  → p1 total: 500, qty: 5
    # p2: 1 × 200 = 200  (vendor 1)  → p2 total: 200, qty: 1
    # p3: 4 × 50  = 200  (vendor 2)  → p3 total: 200, qty: 4
    # p3: 2 × 50  = 100  (vendor 2)  → p3 qty cumulative: 6
    txns = [
        Transaction(product_id=p1.id, vendor_id=v1.id, quantity=2, unit_price=100.0, amount=200.0),
        Transaction(product_id=p1.id, vendor_id=v1.id, quantity=3, unit_price=100.0, amount=300.0),
        Transaction(product_id=p2.id, vendor_id=v1.id, quantity=1, unit_price=200.0, amount=200.0),
        Transaction(product_id=p3.id, vendor_id=v2.id, quantity=4, unit_price=50.0,  amount=200.0),
        Transaction(product_id=p3.id, vendor_id=v2.id, quantity=2, unit_price=50.0,  amount=100.0),
    ]
    db_session.add_all(txns)
    db_session.commit()

    return {
        "v1_id": v1.id, "v2_id": v2.id,
        "p1_id": p1.id, "p2_id": p2.id, "p3_id": p3.id,
        "total_revenue": 1000.0,          # 200+300+200+200+100
        "v1_revenue": 700.0,              # 200+300+200
        "v2_revenue": 300.0,              # 200+100
        "p1_units": 5,                    # top seller by units (p3 = 6, p1 = 5, p2 = 1)
        "top_seller_id": p3.id,           # p3: 6 units
        "top_seller_units": 6,
    }


# ── Empty DB behaviour ────────────────────────────────────────────────────────

def test_total_revenue_empty(client):
    resp = client.get("/analytics/revenue/total")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_revenue"] == 0.0
    assert data["transaction_count"] == 0


def test_revenue_by_vendor_empty(client):
    resp = client.get("/analytics/revenue/by-vendor")
    assert resp.status_code == 200
    assert resp.json() == []


def test_revenue_by_product_empty(client):
    resp = client.get("/analytics/revenue/by-product")
    assert resp.status_code == 200
    assert resp.json() == []


def test_top_selling_empty(client):
    resp = client.get("/analytics/top-selling-product")
    assert resp.status_code == 404


def test_summary_empty(client):
    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_revenue"] == 0.0
    assert data["transaction_count"] == 0
    assert data["top_selling_product"] is None


# ── Calculations with real data ───────────────────────────────────────────────

def test_total_revenue_correct(client, db_session):
    expected = _seed_data(db_session)
    resp = client.get("/analytics/revenue/total")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_revenue"] == pytest.approx(expected["total_revenue"], rel=1e-4)
    assert data["transaction_count"] == 5


def test_revenue_by_vendor_correct(client, db_session):
    expected = _seed_data(db_session)
    resp = client.get("/analytics/revenue/by-vendor")
    assert resp.status_code == 200
    by_vendor = {row["vendor_id"]: row["total_revenue"] for row in resp.json()}
    assert by_vendor[expected["v1_id"]] == pytest.approx(expected["v1_revenue"], rel=1e-4)
    assert by_vendor[expected["v2_id"]] == pytest.approx(expected["v2_revenue"], rel=1e-4)


def test_revenue_by_product_correct(client, db_session):
    expected = _seed_data(db_session)
    resp = client.get("/analytics/revenue/by-product")
    assert resp.status_code == 200
    by_product = {row["product_id"]: row["total_units_sold"] for row in resp.json()}
    assert by_product[expected["p1_id"]] == expected["p1_units"]


def test_top_selling_product_correct(client, db_session):
    expected = _seed_data(db_session)
    resp = client.get("/analytics/top-selling-product")
    assert resp.status_code == 200
    data = resp.json()
    assert data["product_id"] == expected["top_seller_id"]
    assert data["total_units_sold"] == expected["top_seller_units"]


def test_summary_report_correct(client, db_session):
    expected = _seed_data(db_session)
    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_revenue"] == pytest.approx(expected["total_revenue"], rel=1e-4)
    assert data["transaction_count"] == 5
    assert data["vendor_count"] == 2
    assert data["product_count"] == 3
    assert data["top_selling_product"] is not None
    assert data["top_selling_product"]["product_id"] == expected["top_seller_id"]
    assert data["top_vendor_by_revenue"]["vendor_id"] == expected["v1_id"]
