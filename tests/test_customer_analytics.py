"""
tests/test_customer_analytics.py — Tests for Module 2: Customer Analytics & K-Means Segmentation.

Covers:
  - Customer summary and KPI aggregation (active customers, repeat rates, AOV)
  - RFM metric calculation (Recency, Frequency, Monetary, AOV)
  - Edge cases (no customers, no transactions)
  - K-Means behavioral clustering with StandardScaler
  - Silhouette score quantitative evaluation and cluster profiling
"""

from datetime import datetime, timedelta
import pytest
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction


def _seed_customer_data(db_session):
    v = Vendor(name="Vendor A", email="v_cust@test.com", phone="+91-9988776655")
    db_session.add(v)
    db_session.flush()

    p = Product(name="Widget X", price=50.0, vendor_id=v.id)
    db_session.add(p)
    db_session.flush()

    # Create 8 customers with distinct behavioral profiles
    customers = []
    for i in range(1, 9):
        c = Customer(
            name=f"Customer {i}",
            email=f"user{i}@test.com",
            city="Bengaluru" if i % 2 == 0 else "Mumbai",
        )
        customers.append(c)
    db_session.add_all(customers)
    db_session.flush()

    # Customer 1 & 2: High spend, frequent, recent (VIP)
    # Customer 3 & 4: Moderate spend, recent (Loyal)
    # Customer 5 & 6: Lapsed (purchased 180 days ago)
    # Customer 7 & 8: Single small purchase recently
    now = datetime.utcnow()

    txns = []
    # VIPs
    for c in [customers[0], customers[1]]:
        for d in [5, 15, 25]:
            txns.append(Transaction(product_id=p.id, vendor_id=v.id, customer_id=c.customer_id, quantity=4, unit_price=50.0, amount=200.0, transaction_date=now - timedelta(days=d)))

    # Loyals
    for c in [customers[2], customers[3]]:
        for d in [10, 30]:
            txns.append(Transaction(product_id=p.id, vendor_id=v.id, customer_id=c.customer_id, quantity=2, unit_price=50.0, amount=100.0, transaction_date=now - timedelta(days=d)))

    # Lapsed
    for c in [customers[4], customers[5]]:
        txns.append(Transaction(product_id=p.id, vendor_id=v.id, customer_id=c.customer_id, quantity=3, unit_price=50.0, amount=150.0, transaction_date=now - timedelta(days=180)))

    # Occasional
    for c in [customers[6], customers[7]]:
        txns.append(Transaction(product_id=p.id, vendor_id=v.id, customer_id=c.customer_id, quantity=1, unit_price=50.0, amount=50.0, transaction_date=now - timedelta(days=2)))

    db_session.add_all(txns)
    db_session.commit()
    return customers


def test_customer_summary_empty(client):
    res = client.get("/analytics/customers/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_customers"] == 0
    assert data["active_customers_90d"] == 0
    assert data["repeat_purchase_rate_pct"] == 0.0


def test_customer_summary_with_transactions(client, db_session):
    customers = _seed_customer_data(db_session)

    res = client.get("/analytics/customers/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_customers"] == 8
    # 6 customers active in last 90 days (all except lapsed 5 and 6)
    assert data["active_customers_90d"] == 6
    # 4 customers have >= 2 orders (customers 1, 2, 3, 4)
    assert data["repeat_customers"] == 4
    assert data["repeat_purchase_rate_pct"] == 50.0
    assert data["total_customer_revenue"] > 0
    assert data["avg_customer_spend"] > 0
    assert data["avg_order_value"] > 0


def test_customer_rfm_metrics(client, db_session):
    customers = _seed_customer_data(db_session)

    res = client.get("/analytics/customers/rfm")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 8

    c1 = next(c for c in data if c["customer_id"] == customers[0].customer_id)
    assert c1["frequency"] == 3
    assert c1["monetary"] == 600.0
    assert c1["avg_order_value"] == 200.0
    assert c1["recency_days"] >= 0


def test_customer_segmentation_insufficient_data(client, db_session):
    v = Vendor(name="Vendor A", email="v_short@test.com", phone="+91-9988776655")
    db_session.add(v)
    db_session.commit()

    # Only 2 customers
    c1 = Customer(name="User 1", email="u1@test.com")
    c2 = Customer(name="User 2", email="u2@test.com")
    db_session.add_all([c1, c2])
    db_session.commit()

    res = client.get("/analytics/customers/segments")
    assert res.status_code == 200
    data = res.json()
    assert data["n_clusters"] == 0
    assert "Insufficient active customers" in data["message"]


def test_customer_segmentation_kmeans_and_silhouette(client, db_session):
    _seed_customer_data(db_session)

    res = client.get("/analytics/customers/segments")
    assert res.status_code == 200
    data = res.json()

    assert data["n_clusters"] >= 2
    # Silhouette score must be valid number between -1.0 and 1.0
    assert -1.0 <= data["silhouette_score"] <= 1.0
    assert len(data["cluster_profiles"]) == data["n_clusters"]

    # Verify cluster profiles contain expected business attributes
    for prof in data["cluster_profiles"]:
        assert "cluster_id" in prof
        assert "segment_name" in prof
        assert prof["customer_count"] > 0
        assert "avg_recency_days" in prof
        assert "avg_monetary" in prof
        assert "cluster_silhouette" in prof

    # Verify each customer is assigned a cluster
    assert len(data["customers"]) == 8
    for cust in data["customers"]:
        assert "cluster" in cust
        assert "segment_name" in cust
        assert "silhouette" in cust


def test_customer_segmentation_custom_clusters(client, db_session):
    _seed_customer_data(db_session)

    res = client.get("/analytics/customers/segments?n_clusters=3")
    assert res.status_code == 200
    data = res.json()
    assert data["n_clusters"] == 3
    assert len(data["cluster_profiles"]) == 3
