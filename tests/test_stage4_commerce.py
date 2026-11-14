"""
tests/test_stage4_commerce.py — Comprehensive test suite for Stage 4: Advanced Commerce & Financial Operations.

Test Coverage:
1. Vendor lifecycle state machine valid transitions (PENDING_APPROVAL -> ACTIVE -> SUSPENDED -> ACTIVE -> TERMINATED).
2. Illegal vendor lifecycle transitions rejected with HTTP 400.
3. Inactive/Suspended vendors forbidden from listing products (HTTP 403).
4. Nullable COGS accounting and zero data fabrication (0.0% coverage when uncosted, accurate profit when costed).
5. Atomic refund processing and transaction payment status update.
6. Refund exceeding net transaction balance rejected with HTTP 400.
7. Strict refund idempotency (duplicate idempotency_key returns existing record without duplicate deductions).
8. Atomic refund with inventory restocking and StockMovement ('RETURN') audit logging.
9. Interim loopback security gate (local loopback authorized; remote hosts rejected with HTTP 403).
10. Auditable multi-vendor settlements and commission tier calculations.
"""

import pytest
import uuid
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.models.refund import Refund


def _create_test_vendor(client, email="vendor_stage4@example.com", name="Stage4 Vendor", tier="TIER_STANDARD"):
    resp = client.post("/vendors/", json={
        "name": name,
        "email": email,
        "phone": "+1-555-0199",
        "address": "100 Commerce Way",
        "commission_tier": tier,
    })
    assert resp.status_code == 201
    return resp.json()


def _create_test_product(client, vendor_id, price=100.0, cost_price=None, name="Stage4 Product"):
    payload = {
        "name": name,
        "price": price,
        "category": "Electronics",
        "vendor_id": vendor_id,
    }
    if cost_price is not None:
        payload["cost_price"] = cost_price
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ── Test 1: Vendor Lifecycle Valid Transitions ─────────────────────────────
def test_vendor_lifecycle_valid_transitions(client):
    v = _create_test_vendor(client, email="lifecycle@example.com")
    vendor_id = v["id"]
    assert v["status"] == "PENDING_APPROVAL"

    # PENDING_APPROVAL -> ACTIVE
    resp1 = client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE", "verification_notes": "Documents approved"})
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "ACTIVE"

    # ACTIVE -> SUSPENDED
    resp2 = client.put(f"/vendors/{vendor_id}/status", json={"status": "SUSPENDED", "verification_notes": "Policy violation under review"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "SUSPENDED"

    # SUSPENDED -> ACTIVE (reinstatement)
    resp3 = client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE", "verification_notes": "Reinstated after review"})
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "ACTIVE"

    # ACTIVE -> TERMINATED (permanent termination)
    resp4 = client.put(f"/vendors/{vendor_id}/status", json={"status": "TERMINATED", "verification_notes": "Account closed"})
    assert resp4.status_code == 200
    assert resp4.json()["status"] == "TERMINATED"


# ── Test 2: Vendor Lifecycle Illegal Transitions Rejected ──────────────────
def test_vendor_lifecycle_illegal_transitions_rejected(client):
    v = _create_test_vendor(client, email="illegal_trans@example.com")
    vendor_id = v["id"]

    # PENDING_APPROVAL -> SUSPENDED is illegal (must be ACTIVE or REJECTED)
    bad_resp = client.put(f"/vendors/{vendor_id}/status", json={"status": "SUSPENDED"})
    assert bad_resp.status_code == 400
    assert "Illegal vendor status transition" in bad_resp.json()["detail"]

    # Terminate vendor
    client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"})
    client.put(f"/vendors/{vendor_id}/status", json={"status": "TERMINATED"})

    # TERMINATED -> ACTIVE is illegal (terminal state)
    terminal_resp = client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"})
    assert terminal_resp.status_code == 400
    assert "Illegal vendor status transition" in terminal_resp.json()["detail"]


# ── Test 3: Inactive Vendor Cannot List Products ────────────────────────────
def test_inactive_vendor_cannot_list_products(client):
    v = _create_test_vendor(client, email="suspended_vendor@example.com")
    vendor_id = v["id"]

    # Transition to ACTIVE: can list product
    client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"})
    prod1 = _create_test_product(client, vendor_id, price=50.0, name="Allowed Product")
    assert prod1["id"] is not None

    # Transition to SUSPENDED
    client.put(f"/vendors/{vendor_id}/status", json={"status": "SUSPENDED"})

    # Attempt to create product while SUSPENDED -> rejected with HTTP 403
    resp = client.post("/products/", json={
        "name": "Blocked Product",
        "price": 75.0,
        "vendor_id": vendor_id,
    })
    assert resp.status_code == 403
    assert "Inactive vendors cannot list products" in resp.json()["detail"]


# ── Test 4: Nullable COGS Accounting & Zero Fabrication ────────────────────
def test_nullable_cogs_accounting_and_zero_fabrication(client, db_session):
    v = _create_test_vendor(client, email="cogs_vendor@example.com")
    vendor_id = v["id"]
    client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"})

    # Uncosted product (cost_price=None)
    p_uncosted = _create_test_product(client, vendor_id, price=100.0, cost_price=None, name="Uncosted Gadget")
    # Costed product (cost_price=60.0, price=100.0)
    p_costed = _create_test_product(client, vendor_id, price=100.0, cost_price=60.0, name="Costed Gadget")

    # Transaction on uncosted product: 1 unit @ 100
    t1 = Transaction(product_id=p_uncosted["id"], vendor_id=vendor_id, quantity=1, unit_price=100.0, amount=100.0, discount_amount=0.0)
    # Transaction on costed product: 2 units @ 100 = 200, discount 10 = net 190, cost = 2 * 60 = 120
    t2 = Transaction(product_id=p_costed["id"], vendor_id=vendor_id, quantity=2, unit_price=100.0, amount=200.0, discount_amount=10.0)
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.get("/analytics/revenue/profit-margins")
    assert resp.status_code == 200
    data = resp.json()

    assert data["gross_sales_gmv"] == 300.0
    assert data["discounts_total"] == 10.0
    assert data["net_sales"] == 290.0

    # Covered net sales is strictly t2 (190.0)
    assert data["covered_net_sales"] == 190.0
    assert data["covered_cogs"] == 120.0
    assert data["gross_profit_reported"] == 70.0
    assert data["gross_margin_pct_reported"] == round((70.0 / 190.0) * 100.0, 2)
    # Coverage pct: 190.0 / 290.0 * 100 = 65.52%
    assert data["cogs_coverage_pct"] == round((190.0 / 290.0) * 100.0, 2)


# ── Test 5: Atomic Refund & Payment Status Update ──────────────────────────
def test_atomic_refund_and_payment_status(client, db_session):
    v = _create_test_vendor(client, email="refund_vendor@example.com")
    p = _create_test_product(client, v["id"], price=50.0)

    t = Transaction(product_id=p["id"], vendor_id=v["id"], quantity=2, unit_price=50.0, amount=100.0, discount_amount=0.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # Partial refund of 40.0
    r1 = client.post("/refunds/", json={
        "transaction_id": t.transaction_id,
        "amount": 40.0,
        "idempotency_key": f"ref_part_{uuid.uuid4().hex[:8]}",
        "reason": "Partial customer satisfaction discount",
        "returned_quantity": 0,
        "restock_inventory": False,
    })
    assert r1.status_code == 201
    db_session.refresh(t)
    assert t.payment_status == "PARTIALLY_REFUNDED"

    # Remaining refund of 60.0
    r2 = client.post("/refunds/", json={
        "transaction_id": t.transaction_id,
        "amount": 60.0,
        "idempotency_key": f"ref_full_{uuid.uuid4().hex[:8]}",
        "reason": "Return remaining",
        "returned_quantity": 0,
        "restock_inventory": False,
    })
    assert r2.status_code == 201
    db_session.refresh(t)
    assert t.payment_status == "REFUNDED"


# ── Test 6: Refund Exceeding Net Value Rejected ────────────────────────────
def test_refund_exceeding_net_value_rejected(client, db_session):
    v = _create_test_vendor(client, email="exceed_vendor@example.com")
    p = _create_test_product(client, v["id"], price=100.0)

    # Net value = 100 - 20 discount = 80
    t = Transaction(product_id=p["id"], vendor_id=v["id"], quantity=1, unit_price=100.0, amount=100.0, discount_amount=20.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # Attempting refund of 85.0 when max refundable is 80.0
    resp = client.post("/refunds/", json={
        "transaction_id": t.transaction_id,
        "amount": 85.0,
        "idempotency_key": f"exceed_key_{uuid.uuid4().hex[:8]}",
        "reason": "Exceeding refund attempt",
    })
    assert resp.status_code == 400
    assert "exceeds remaining refundable balance" in resp.json()["detail"]


# ── Test 7: Strict Refund Idempotency ──────────────────────────────────────
def test_refund_idempotency(client, db_session):
    v = _create_test_vendor(client, email="idemp_vendor@example.com")
    p = _create_test_product(client, v["id"], price=100.0)

    t = Transaction(product_id=p["id"], vendor_id=v["id"], quantity=1, unit_price=100.0, amount=100.0, discount_amount=0.0)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    idemp_key = "unique-safe-idempotency-key-001"
    payload = {
        "transaction_id": t.transaction_id,
        "amount": 50.0,
        "idempotency_key": idemp_key,
        "reason": "Idempotency verification test",
    }

    # First call -> 201 created
    resp1 = client.post("/refunds/", json=payload)
    assert resp1.status_code == 201
    refund_id = resp1.json()["refund_id"]

    # Second call with SAME idempotency key -> returns existing record without error or double-deduction
    resp2 = client.post("/refunds/", json=payload)
    assert resp2.status_code == 200 or resp2.status_code == 201
    assert resp2.json()["refund_id"] == refund_id
    assert resp2.json()["idempotency_key"] == idemp_key

    # Total refunds count in DB for this key must be strictly 1
    count = db_session.query(Refund).filter(Refund.idempotency_key == idemp_key).count()
    assert count == 1


# ── Test 8: Refund with Inventory Restocking & Audit Movement ───────────────
def test_refund_with_inventory_restock(client, db_session):
    v = _create_test_vendor(client, email="restock_vendor@example.com")
    p = _create_test_product(client, v["id"], price=50.0)

    inv = Inventory(product_id=p["id"], current_stock=20, warehouse="CENTRAL", reorder_level=5)
    t = Transaction(product_id=p["id"], vendor_id=v["id"], quantity=3, unit_price=50.0, amount=150.0, discount_amount=0.0)
    db_session.add_all([inv, t])
    db_session.commit()
    db_session.refresh(inv)
    db_session.refresh(t)

    # Return 2 units with restocking
    resp = client.post("/refunds/", json={
        "transaction_id": t.transaction_id,
        "amount": 100.0,
        "idempotency_key": f"restock_key_{uuid.uuid4().hex[:8]}",
        "returned_quantity": 2,
        "restock_inventory": True,
        "reason": "Damaged box returned by customer",
    })
    assert resp.status_code == 201

    # Verify inventory was incremented from 20 to 22
    db_session.refresh(inv)
    assert inv.current_stock == 22

    # Verify StockMovement record exists with type 'RETURN'
    movement = (
        db_session.query(StockMovement)
        .filter(StockMovement.product_id == p["id"], StockMovement.movement_type == "RETURN")
        .first()
    )
    assert movement is not None
    assert movement.quantity == 2
    assert movement.source_warehouse == "CUSTOMER_RETURN"
    assert movement.target_warehouse == "CENTRAL"


# ── Test 9: Interim Loopback Security Gate ─────────────────────────────────
def test_interim_loopback_security_gate(client):
    from fastapi.testclient import TestClient
    from app.main import app

    # Default TestClient connects with client.host = "testclient" -> allowed
    resp = client.get("/analytics/vendors/payouts")
    assert resp.status_code == 200

    # Simulate an unauthorized external client (e.g. 198.51.100.25)
    untrusted_client = TestClient(app, client=("198.51.100.25", 54321))
    resp_untrusted = untrusted_client.get("/analytics/vendors/payouts")
    assert resp_untrusted.status_code == 403
    assert "Access restricted to local administrative loopback interface" in resp_untrusted.json()["detail"]

    # Verify loopback 127.0.0.1 is authorized
    loopback_client = TestClient(app, client=("127.0.0.1", 54321))
    resp_loopback = loopback_client.get("/analytics/vendors/payouts")
    assert resp_loopback.status_code == 200


# ── Test 10: Auditable Multi-Vendor Settlements & Commission Tiers ──────────
def test_vendor_settlements_and_commission_tiers(client, db_session):
    # Create vendors across different approved tiers
    v_starter = _create_test_vendor(client, email="starter@example.com", name="Starter Co", tier="TIER_STARTER")
    v_pref = _create_test_vendor(client, email="pref@example.com", name="Preferred Co", tier="TIER_PREFERRED")

    p1 = _create_test_product(client, v_starter["id"], price=100.0)
    p2 = _create_test_product(client, v_pref["id"], price=200.0)

    # Starter: 1 order @ 100, discount 0, rate 15% -> commission 15, payout 85
    t1 = Transaction(product_id=p1["id"], vendor_id=v_starter["id"], quantity=1, unit_price=100.0, amount=100.0, discount_amount=0.0)
    # Preferred: 1 order @ 200, discount 20 = net 180, rate 10% -> commission 18, payout 162
    t2 = Transaction(product_id=p2["id"], vendor_id=v_pref["id"], quantity=1, unit_price=200.0, amount=200.0, discount_amount=20.0)
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.get("/analytics/vendors/payouts")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_net_sales"] == 280.0
    assert data["total_platform_commission"] == 33.0  # 15 + 18
    assert data["total_vendor_payouts"] == 247.0      # 85 + 162

    # Check vendor items
    settlements = {s["vendor_id"]: s for s in data["settlements"]}
    assert settlements[v_starter["id"]]["commission_tier"] == "TIER_STARTER"
    assert settlements[v_starter["id"]]["commission_rate"] == 0.15
    assert settlements[v_starter["id"]]["vendor_payout"] == 85.0

    assert settlements[v_pref["id"]]["commission_tier"] == "TIER_PREFERRED"
    assert settlements[v_pref["id"]]["commission_rate"] == 0.10
    assert settlements[v_pref["id"]]["vendor_payout"] == 162.0
