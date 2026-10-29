"""
tests/test_recommendations.py — Tests for Module 3: Recommendation Engine & Evaluation.

Covers:
  - Popularity fallback (cold-start)
  - Collaborative filtering recommendations with item-item similarity
  - Exclusion of already-interacted items
  - Recommendation rationale explanations
  - Chronological leave-20%-out offline evaluation (Precision@K, Recall@K, Hit Rate)
"""

from datetime import datetime, timedelta
import pytest
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.customer_interaction import CustomerInteraction


def _seed_recommendation_data(db_session):
    v = Vendor(name="Test Vendor", email="v_rec@test.com", phone="+91-9876543210")
    db_session.add(v)
    db_session.flush()

    # Create 5 products
    products = [
        Product(name="Coffee Maker", price=120.0, category="Kitchen", vendor_id=v.id),
        Product(name="Coffee Beans", price=20.0, category="Groceries", vendor_id=v.id),
        Product(name="Coffee Mug", price=15.0, category="Kitchen", vendor_id=v.id),
        Product(name="Desk Lamp", price=45.0, category="Lighting", vendor_id=v.id),
        Product(name="Laptop Stand", price=55.0, category="Office", vendor_id=v.id),
    ]
    db_session.add_all(products)
    db_session.flush()

    # Create 4 customers
    customers = [
        Customer(name=f"Shopper {i}", email=f"shopper{i}@test.com")
        for i in range(1, 5)
    ]
    db_session.add_all(customers)
    db_session.flush()

    # Inter-product co-interaction patterns:
    # Shopper 1 & 2 bought Coffee Maker + Coffee Beans + Coffee Mug
    # Shopper 3 bought Coffee Maker + Coffee Beans
    # Shopper 4 bought Desk Lamp + Laptop Stand
    base_date = datetime(2024, 1, 1)

    interactions = [
        # Customer 1: Maker, Beans, Mug
        CustomerInteraction(customer_id=customers[0].customer_id, product_id=products[0].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=1)),
        CustomerInteraction(customer_id=customers[0].customer_id, product_id=products[1].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=2)),
        CustomerInteraction(customer_id=customers[0].customer_id, product_id=products[2].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=3)),

        # Customer 2: Maker, Beans, Mug
        CustomerInteraction(customer_id=customers[1].customer_id, product_id=products[0].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=4)),
        CustomerInteraction(customer_id=customers[1].customer_id, product_id=products[1].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=5)),
        CustomerInteraction(customer_id=customers[1].customer_id, product_id=products[2].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=6)),

        # Customer 3: Maker, Beans (has NOT interacted with Mug yet!)
        CustomerInteraction(customer_id=customers[2].customer_id, product_id=products[0].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=7)),
        CustomerInteraction(customer_id=customers[2].customer_id, product_id=products[1].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=8)),

        # Customer 4: Lamp, Stand
        CustomerInteraction(customer_id=customers[3].customer_id, product_id=products[3].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=9)),
        CustomerInteraction(customer_id=customers[3].customer_id, product_id=products[4].id, interaction_type="purchase", interaction_weight=4.0, interaction_date=base_date + timedelta(days=10)),
    ]
    db_session.add_all(interactions)
    db_session.commit()
    return products, customers


def test_popular_products_empty(client):
    res = client.get("/recommendations/popular")
    assert res.status_code == 200
    assert res.json() == []


def test_popular_products_ranking(client, db_session):
    products, _ = _seed_recommendation_data(db_session)
    # Add sales transactions
    t1 = Transaction(product_id=products[0].id, vendor_id=products[0].vendor_id, quantity=50, unit_price=120.0, amount=6000.0)
    t2 = Transaction(product_id=products[1].id, vendor_id=products[1].vendor_id, quantity=100, unit_price=20.0, amount=2000.0)
    db_session.add_all([t1, t2])
    db_session.commit()

    res = client.get("/recommendations/popular?top_n=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    # Products[1] has 100 units sold, should be #1
    assert data[0]["product_id"] == products[1].id
    assert data[1]["product_id"] == products[0].id


def test_personalized_recommendations_cold_start(client, db_session):
    _, customers = _seed_recommendation_data(db_session)
    # New customer with 0 interactions
    new_c = Customer(name="Brand New", email="newbie@test.com")
    db_session.add(new_c)
    db_session.commit()

    res = client.get(f"/recommendations/customer/{new_c.customer_id}?top_n=3")
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == new_c.customer_id
    assert data["is_personalized"] is False
    assert len(data["recommendations"]) <= 3


def test_personalized_recommendations_collaborative_filtering(client, db_session):
    products, customers = _seed_recommendation_data(db_session)

    # Customer 3 bought Coffee Maker and Coffee Beans.
    # Co-occurrence with Customer 1 & 2 strongly suggests Coffee Mug (products[2]).
    res = client.get(f"/recommendations/customer/{customers[2].customer_id}?top_n=2")
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == customers[2].customer_id
    assert data["is_personalized"] is True
    assert len(data["recommendations"]) > 0

    top_rec = data["recommendations"][0]
    # Top recommendation should be Coffee Mug
    assert top_rec["product_id"] == products[2].id
    assert top_rec["product_name"] == "Coffee Mug"
    assert "rationale" in top_rec
    assert "Coffee" in top_rec["rationale"]


def test_recommendations_nonexistent_customer_404(client):
    res = client.get("/recommendations/customer/99999")
    assert res.status_code == 404


def test_recommendation_offline_evaluation(client, db_session):
    _seed_recommendation_data(db_session)

    res = client.get("/recommendations/evaluation?k=3")
    assert res.status_code == 200
    data = res.json()
    assert "mean_precision_at_k" in data
    assert "mean_recall_at_k" in data
    assert "hit_rate_at_k" in data
    assert 0.0 <= data["mean_precision_at_k"] <= 1.0
    assert 0.0 <= data["mean_recall_at_k"] <= 1.0
    assert 0.0 <= data["hit_rate_at_k"] <= 1.0
    assert "Chronological" in data["split_method"]
