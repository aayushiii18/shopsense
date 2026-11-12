"""
tests/test_revenue_analytics.py — Test suite for Milestone 3 Modules 1 & 2.

Covers:
  1. GET /analytics/revenue (GMV)
  2. GET /analytics/vendor-performance (Vendor revenue & units aggregation)
  3. GET /analytics/customers (Total customers & average spend)
  4. GET /forecast/{month} (RandomForest inventory demand prediction & input validation)
  5. GET /recommend/{customer_id} (Collaborative filtering recommendation & 404 handling)
  6. GET /analytics/revenue/growth (Monthly revenue & Month-over-Month growth rates)
  7. GET /analytics/revenue/benchmarking (Vendor revenue ranking & market share percentages)
  8. Empty dataset and edge case handling (division by zero, missing records)
"""

from datetime import datetime, timedelta
import pytest
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.customer_interaction import CustomerInteraction


def _seed_sample_ecosystem(db_session):
    """Seed 2 vendors, 3 products, 2 customers, and multiple transactions across months."""
    v1 = Vendor(name="Tech Vendor Alpha", email="alpha@test.com", phone="+91-9876543210")
    v2 = Vendor(name="Apparel Vendor Beta", email="beta@test.com", phone="+91-9876543211")
    db_session.add_all([v1, v2])
    db_session.flush()

    p1 = Product(name="Smart Watch", price=2000.0, category="Electronics", vendor_id=v1.id)
    p2 = Product(name="Wireless Earbuds", price=1500.0, category="Electronics", vendor_id=v1.id)
    p3 = Product(name="Cotton T-Shirt", price=500.0, category="Apparel", vendor_id=v2.id)
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    c1 = Customer(name="Alice Wonder", email="alice@test.com", city="Bengaluru")
    c2 = Customer(name="Bob Builder", email="bob@test.com", city="Mumbai")
    db_session.add_all([c1, c2])
    db_session.flush()

    # Transactions spanning Jan, Feb, Mar 2024
    t1 = Transaction(
        product_id=p1.id,
        vendor_id=v1.id,
        customer_id=c1.customer_id,
        quantity=2,
        unit_price=2000.0,
        amount=4000.0,
        transaction_date=datetime(2024, 1, 15, 10, 0, 0),
    )
    t2 = Transaction(
        product_id=p3.id,
        vendor_id=v2.id,
        customer_id=c2.customer_id,
        quantity=4,
        unit_price=500.0,
        amount=2000.0,
        transaction_date=datetime(2024, 1, 20, 11, 0, 0),
    )
    # Feb transactions (growth expected)
    t3 = Transaction(
        product_id=p2.id,
        vendor_id=v1.id,
        customer_id=c1.customer_id,
        quantity=4,
        unit_price=1500.0,
        amount=6000.0,
        transaction_date=datetime(2024, 2, 10, 12, 0, 0),
    )
    t4 = Transaction(
        product_id=p3.id,
        vendor_id=v2.id,
        customer_id=c2.customer_id,
        quantity=6,
        unit_price=500.0,
        amount=3000.0,
        transaction_date=datetime(2024, 2, 18, 14, 0, 0),
    )
    # Mar transactions
    t5 = Transaction(
        product_id=p1.id,
        vendor_id=v1.id,
        customer_id=c1.customer_id,
        quantity=1,
        unit_price=2000.0,
        amount=2000.0,
        transaction_date=datetime(2024, 3, 5, 9, 0, 0),
    )

    db_session.add_all([t1, t2, t3, t4, t5])

    # Add interaction for recommendations
    ci1 = CustomerInteraction(
        customer_id=c1.customer_id,
        product_id=p1.id,
        interaction_type="PURCHASE",
        interaction_weight=4.0,
    )
    ci2 = CustomerInteraction(
        customer_id=c1.customer_id,
        product_id=p2.id,
        interaction_type="VIEW",
        interaction_weight=1.0,
    )
    db_session.add_all([ci1, ci2])
    db_session.commit()

    return {
        "v1": v1, "v2": v2,
        "p1": p1, "p2": p2, "p3": p3,
        "c1": c1, "c2": c2,
        "total_revenue": 17000.0,  # 4000 + 2000 + 6000 + 3000 + 2000
        "v1_revenue": 12000.0,     # 4000 + 6000 + 2000
        "v2_revenue": 5000.0,      # 2000 + 3000
        "jan_revenue": 6000.0,     # 4000 + 2000
        "feb_revenue": 9000.0,     # 6000 + 3000
        "mar_revenue": 2000.0,     # 2000
    }


def test_get_analytics_revenue_empty(client):
    """GET /analytics/revenue returns 0.0 when no transactions exist."""
    res = client.get("/analytics/revenue")
    assert res.status_code == 200
    assert res.json() == {"total_revenue": 0.0}


def test_get_analytics_revenue_with_data(client, db_session):
    """GET /analytics/revenue returns accurate GMV matching seeded transactions."""
    data = _seed_sample_ecosystem(db_session)
    res = client.get("/analytics/revenue")
    assert res.status_code == 200
    assert res.json()["total_revenue"] == pytest.approx(data["total_revenue"], rel=1e-3)


def test_get_analytics_vendor_performance_empty(client):
    """GET /analytics/vendor-performance returns empty list on empty DB."""
    res = client.get("/analytics/vendor-performance")
    assert res.status_code == 200
    assert res.json() == []


def test_get_analytics_vendor_performance_with_data(client, db_session):
    """GET /analytics/vendor-performance aggregates revenue and units per vendor."""
    data = _seed_sample_ecosystem(db_session)
    res = client.get("/analytics/vendor-performance")
    assert res.status_code == 200
    perf = res.json()
    assert len(perf) == 2

    v1_row = next(r for r in perf if r["vendor_id"] == data["v1"].id)
    assert v1_row["amount"] == pytest.approx(data["v1_revenue"], rel=1e-3)
    assert v1_row["units_sold"] == 7  # 2 + 4 + 1

    v2_row = next(r for r in perf if r["vendor_id"] == data["v2"].id)
    assert v2_row["amount"] == pytest.approx(data["v2_revenue"], rel=1e-3)
    assert v2_row["units_sold"] == 10  # 4 + 6


def test_get_analytics_customers_empty(client):
    """GET /analytics/customers handles empty customer table without division by zero."""
    res = client.get("/analytics/customers")
    assert res.status_code == 200
    assert res.json() == {"customers": 0, "avg_spend": 0.0}


def test_get_analytics_customers_with_data(client, db_session):
    """GET /analytics/customers returns customer count and average spend."""
    data = _seed_sample_ecosystem(db_session)
    res = client.get("/analytics/customers")
    assert res.status_code == 200
    body = res.json()
    assert body["customers"] == 2
    # Total revenue 17000 / 2 customers = 8500.0
    assert body["avg_spend"] == pytest.approx(8500.0, rel=1e-3)


def test_get_forecast_valid_months(client, db_session):
    """GET /forecast/{month} returns predicted demand for valid month indices."""
    _seed_sample_ecosystem(db_session)
    for m in [1, 6, 12, 18]:
        res = client.get(f"/forecast/{m}")
        assert res.status_code == 200
        data = res.json()
        assert data["month"] == m
        assert data["forecast"] > 0
        assert "RandomForest" in data["model_name"]


def test_get_forecast_invalid_month_rejected(client):
    """GET /forecast/{month} rejects out-of-range months with HTTP 400."""
    res_zero = client.get("/forecast/0")
    assert res_zero.status_code == 400
    assert "Invalid month" in res_zero.json()["detail"]

    res_neg = client.get("/forecast/-3")
    assert res_neg.status_code == 400

    res_large = client.get("/forecast/25")
    assert res_large.status_code == 400


def test_get_recommend_existing_customer(client, db_session):
    """GET /recommend/{customer_id} returns top recommended product dynamically."""
    data = _seed_sample_ecosystem(db_session)
    cid = data["c1"].customer_id
    res = client.get(f"/recommend/{cid}")
    assert res.status_code == 200
    body = res.json()
    assert body["customer"] == cid
    assert body["recommended_product"] is not None
    assert isinstance(body["recommended_product"], str)
    assert len(body["recommended_product"]) > 0


def test_get_recommend_nonexistent_customer_404(client):
    """GET /recommend/{customer_id} returns 404 if customer does not exist."""
    res = client.get("/recommend/99999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_get_revenue_growth_empty(client):
    """GET /analytics/revenue/growth handles empty database cleanly."""
    res = client.get("/analytics/revenue/growth")
    assert res.status_code == 200
    body = res.json()
    assert body["total_revenue"] == 0.0
    assert body["average_order_value"] == 0.0
    assert body["monthly_growth"] == []


def test_get_revenue_growth_mom_calculation(client, db_session):
    """GET /analytics/revenue/growth computes chronological MoM growth correctly."""
    data = _seed_sample_ecosystem(db_session)
    res = client.get("/analytics/revenue/growth")
    assert res.status_code == 200
    body = res.json()
    assert body["total_revenue"] == pytest.approx(17000.0, rel=1e-3)
    # 17000 / 5 orders = 3400.0
    assert body["average_order_value"] == pytest.approx(3400.0, rel=1e-3)

    mg = body["monthly_growth"]
    assert len(mg) == 3

    # Month 1 (Jan): Baseline, mom_growth_pct is None
    assert mg[0]["month"] == 1
    assert mg[0]["revenue"] == pytest.approx(data["jan_revenue"], rel=1e-3)
    assert mg[0]["mom_growth_pct"] is None
    assert "Baseline" in mg[0]["note"]

    # Month 2 (Feb): Revenue 9000, previous 6000 -> Growth = ((9000-6000)/6000)*100 = 50.0%
    assert mg[1]["month"] == 2
    assert mg[1]["revenue"] == pytest.approx(data["feb_revenue"], rel=1e-3)
    assert mg[1]["mom_growth_pct"] == pytest.approx(50.0, rel=1e-2)

    # Month 3 (Mar): Revenue 2000, previous 9000 -> Growth = ((2000-9000)/9000)*100 = -77.78%
    assert mg[2]["month"] == 3
    assert mg[2]["revenue"] == pytest.approx(data["mar_revenue"], rel=1e-3)
    assert mg[2]["mom_growth_pct"] == pytest.approx(-77.78, rel=1e-2)


def test_get_revenue_benchmarking_empty(client):
    """GET /analytics/revenue/benchmarking handles empty database cleanly."""
    res = client.get("/analytics/revenue/benchmarking")
    assert res.status_code == 200
    body = res.json()
    assert body["total_gmv"] == 0.0
    assert body["total_vendors"] == 0
    assert body["benchmarking"] == []


def test_get_revenue_benchmarking_ranking_and_share(client, db_session):
    """GET /analytics/revenue/benchmarking computes rank 1 to N and 100% market share."""
    data = _seed_sample_ecosystem(db_session)
    res = client.get("/analytics/revenue/benchmarking")
    assert res.status_code == 200
    body = res.json()
    assert body["total_gmv"] == pytest.approx(17000.0, rel=1e-3)
    assert body["total_vendors"] == 2

    bm = body["benchmarking"]
    # Vendor Alpha has 12,000 -> Rank 1
    assert bm[0]["vendor_id"] == data["v1"].id
    assert bm[0]["rank"] == 1
    assert bm[0]["revenue"] == pytest.approx(12000.0, rel=1e-3)
    # Market share = (12000 / 17000) * 100 = 70.59%
    assert bm[0]["market_share_pct"] == pytest.approx(70.59, rel=1e-2)

    # Vendor Beta has 5,000 -> Rank 2
    assert bm[1]["vendor_id"] == data["v2"].id
    assert bm[1]["rank"] == 2
    assert bm[1]["revenue"] == pytest.approx(5000.0, rel=1e-3)
    # Market share = (5000 / 17000) * 100 = 29.41%
    assert bm[1]["market_share_pct"] == pytest.approx(29.41, rel=1e-2)

    # Sum of market share percentages must equal 100.0%
    total_share = sum(item["market_share_pct"] for item in bm)
    assert total_share == pytest.approx(100.0, rel=1e-2)
