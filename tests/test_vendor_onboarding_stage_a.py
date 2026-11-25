"""
tests/test_vendor_onboarding_stage_a.py — Verification Suite for Vendor Onboarding Stage A:
Backend & Security Hardening.

Covers:
1. Unified atomic vendor registration (POST /auth/register-vendor).
2. Input validation, password confirmation matching, and email normalization.
3. Cross-table duplicate email detection across users and vendors.
4. Atomic rollback guarantee if User creation or commit fails mid-registration.
5. Server-side role=VENDOR & status=PENDING_APPROVAL enforcement against tampering.
6. Operational vendor status gating (PENDING_APPROVAL, REJECTED, SUSPENDED, TERMINATED blocked
   on POST /products/, PUT /products/{id} without vendor_id change, POST /inventory/movements).
7. Admin-only vendor approval/rejection & User.is_verified synchronization + GET /vendors/me.
8. LEGACY_ACTIVE backward compatibility across catalog, inventory, and recommendations.
9. Protected vendor endpoints & tenant isolation (/vendors/, /vendors/me, /vendors/{id}).
10. Vendor analytics & inventory read tenant isolation + revenue cache key isolation.
11. Public & customer catalog filtering via get_optional_user (hides non-operational vendors).
12. Recommendation engine filtering (popular, CF, hybrid exclude non-operational vendors).
13. Loopback bypass hardening against reverse-proxy headers (X-Forwarded-For, X-Real-IP, Forwarded),
    ENVIRONMENT=production, and non-pytest runtime execution.
"""

from datetime import datetime
from unittest.mock import patch
import sys
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import _is_legacy_test_client
from app.core.security import hash_password, create_access_token
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.customer_interaction import CustomerInteraction


def _valid_vendor_reg_payload(email="newvendor@shop.com", **overrides):
    data = {
        "owner_name": "Asha Mehta",
        "business_name": "Mehta Artisans",
        "email": email,
        "phone": "+91-9876543210",
        "category": "Home Decor",
        "tax_id": "27AAACM1234F1Z5",
        "address": "42 MG Road, Pune",
        "password": "VendorStrongPass!99",
        "password_confirmation": "VendorStrongPass!99",
    }
    data.update(overrides)
    return data


def _create_auth_user(
    db_session,
    *,
    email: str,
    role: str,
    vendor_id: int | None = None,
    customer_id: int | None = None,
    is_verified: bool = True,
) -> tuple[User, dict[str, str]]:
    user = User(
        email=email,
        hashed_password=hash_password("TestPass123!"),
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        is_active=True,
        is_verified=is_verified,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        token_version=1,
    )
    return user, {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


def _login_headers(client, email: str, password: str) -> dict[str, str]:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


# ── 1 & 2: Unified Registration, Validation & Normalization ──────────────────

def test_01_register_vendor_unified_success(client, db_session):
    payload = _valid_vendor_reg_payload(email="  Owner.Shop@Example.COM ", tax_id=" gstin-29abc123 ")
    resp = client.post("/auth/register-vendor", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["email"] == "owner.shop@example.com"
    assert data["role"] == UserRole.VENDOR
    assert data["owner_name"] == "Asha Mehta"
    assert data["business_name"] == "Mehta Artisans"
    assert data["category"] == "Home Decor"
    assert data["tax_id"] == "GSTIN-29ABC123"
    assert data["vendor_status"] == "PENDING_APPROVAL"
    assert data["compliance_status"] == "PENDING_REVIEW"
    assert data["is_active"] is True
    assert data["is_verified"] is False

    vendor = db_session.query(Vendor).filter(Vendor.id == data["vendor_id"]).first()
    user = db_session.query(User).filter(User.id == data["user_id"]).first()
    assert vendor is not None
    assert user is not None
    assert user.vendor_id == vendor.id
    assert vendor.owner_name == "Asha Mehta"
    assert vendor.vendor_category == "Home Decor"
    assert vendor.status == "PENDING_APPROVAL"

    # Verify optional Tax/GST ID may be omitted or blank string -> normalized to None
    opt_resp = client.post("/auth/register-vendor", json=_valid_vendor_reg_payload(
        email="notax@example.com", tax_id="   "
    ))
    assert opt_resp.status_code == 201
    assert opt_resp.json()["tax_id"] is None

    # Pending vendor can authenticate via /auth/login
    login_resp = client.post("/auth/login", json={
        "email": "owner.shop@example.com",
        "password": payload["password"],
    })
    assert login_resp.status_code == 200
    tok = login_resp.json()
    assert tok["role"] == "VENDOR"
    assert tok["vendor_id"] == vendor.id


def test_02_register_vendor_validation_and_password_mismatch(client):
    mismatch = _valid_vendor_reg_payload(password_confirmation="DifferentPass!1")
    resp = client.post("/auth/register-vendor", json=mismatch)
    assert resp.status_code == 422

    short_pw = _valid_vendor_reg_payload(password="abc", password_confirmation="abc")
    resp2 = client.post("/auth/register-vendor", json=short_pw)
    assert resp2.status_code == 422

    bad_phone = _valid_vendor_reg_payload(phone="12")
    resp3 = client.post("/auth/register-vendor", json=bad_phone)
    assert resp3.status_code == 422


def test_03_register_vendor_cross_table_duplicate_email(client, db_session):
    # Conflict against existing User (customer) email
    client.post("/auth/register", json={"email": "shared@example.com", "password": "CustomerPass!99"})
    resp1 = client.post("/auth/register-vendor", json=_valid_vendor_reg_payload(email="SHARED@example.com"))
    assert resp1.status_code == 409

    # Conflict against existing standalone legacy Vendor email (without User row)
    legacy_vendor = Vendor(
        name="Legacy Store",
        email="legacyonly@example.com",
        phone="+91-9000000111",
        status="LEGACY_ACTIVE",
    )
    db_session.add(legacy_vendor)
    db_session.commit()

    resp2 = client.post("/auth/register-vendor", json=_valid_vendor_reg_payload(email="LegacyOnly@example.com"))
    assert resp2.status_code == 409


def test_04_register_vendor_atomic_rollback_no_orphan_vendor(client, db_session):
    payload = _valid_vendor_reg_payload(email="atomicfail@example.com")

    with patch("app.services.auth.auth_service.hash_password", side_effect=RuntimeError("Simulated failure")):
        with pytest.raises(RuntimeError):
            client.post("/auth/register-vendor", json=payload)

    # Now simulate failure AFTER Vendor flush / add (during User commit)
    orig_commit = db_session.commit
    call_count = {"n": 0}

    def failing_commit():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Simulated DB commit failure after vendor flush")
        return orig_commit()

    with patch.object(db_session, "commit", side_effect=failing_commit):
        with pytest.raises(RuntimeError, match="Simulated DB commit failure"):
            client.post("/auth/register-vendor", json=payload)

    assert db_session.query(Vendor).filter(Vendor.email == "atomicfail@example.com").first() is None
    assert db_session.query(User).filter(User.email == "atomicfail@example.com").first() is None


def test_05_register_vendor_ignores_privilege_escalation_fields(client):
    payload = _valid_vendor_reg_payload(
        email="tamper@example.com",
        role="ADMIN",
        status="ACTIVE",
        vendor_id=99999,
        is_verified=True,
    )
    resp = client.post("/auth/register-vendor", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "VENDOR"
    assert data["vendor_status"] == "PENDING_APPROVAL"
    assert data["is_verified"] is False
    assert data["vendor_id"] != 99999


# ── 6 & 7: Operational Status Gating & Approval Lifecycle ────────────────────

def test_06_non_operational_vendors_blocked_from_products_and_inventory(client, db_session):
    reg = client.post("/auth/register-vendor", json=_valid_vendor_reg_payload(email="pending_ops@example.com")).json()
    vendor_id = reg["vendor_id"]
    vendor_headers = _login_headers(client, "pending_ops@example.com", "VendorStrongPass!99")
    _, admin_headers = _create_auth_user(db_session, email="adm_ops@example.com", role=UserRole.ADMIN)

    # 1. PENDING_APPROVAL vendor cannot create products
    p_fail = client.post("/products/", json={
        "name": "Pending Watch",
        "price": 199.0,
        "category": "Electronics",
        "vendor_id": vendor_id,
    }, headers=vendor_headers)
    assert p_fail.status_code == 403
    assert "Inactive vendors cannot list products" in p_fail.json()["detail"]

    # Seed an existing product directly for this vendor to test PUT /products/{id} and POST /inventory/movements
    seeded_prod = Product(name="Pre-existing Item", price=99.0, category="Electronics", vendor_id=vendor_id)
    db_session.add(seeded_prod)
    db_session.flush()
    db_session.add(Inventory(product_id=seeded_prod.id, current_stock=10, reorder_level=5))
    db_session.commit()
    db_session.refresh(seeded_prod)

    # 2. PENDING_APPROVAL vendor cannot update product even WITHOUT changing vendor_id
    upd_fail = client.put(f"/products/{seeded_prod.id}", json={"price": 120.0}, headers=vendor_headers)
    assert upd_fail.status_code == 403

    # 3. PENDING_APPROVAL vendor cannot record inventory movements
    mov_fail = client.post("/inventory/movements", json={
        "product_id": seeded_prod.id,
        "movement_type": "RESTOCK",
        "quantity": 5,
    }, headers=vendor_headers)
    assert mov_fail.status_code == 403

    # 4. Non-admin (vendor & customer) cannot approve or transition vendor status
    _, cust_headers = _create_auth_user(db_session, email="cust_no_approve@example.com", role=UserRole.CUSTOMER)
    assert client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"}, headers=vendor_headers).status_code == 403
    assert client.put(f"/vendors/{vendor_id}/status", json={"status": "ACTIVE"}, headers=cust_headers).status_code == 403

    # 5. Reject vendor -> check /vendors/me feedback + still blocked
    rej = client.put(
        f"/vendors/{vendor_id}/status",
        json={"status": "REJECTED", "verification_notes": "Missing tax certificate"},
        headers=admin_headers,
    )
    assert rej.status_code == 200
    me_rej = client.get("/vendors/me", headers=vendor_headers)
    assert me_rej.status_code == 200
    assert me_rej.json()["status"] == "REJECTED"
    assert me_rej.json()["verification_notes"] == "Missing tax certificate"

    assert client.put(f"/products/{seeded_prod.id}", json={"price": 110.0}, headers=vendor_headers).status_code == 403
    assert client.post("/inventory/movements", json={
        "product_id": seeded_prod.id, "movement_type": "RESTOCK", "quantity": 5
    }, headers=vendor_headers).status_code == 403

    # 6. Admin moves REJECTED -> PENDING_APPROVAL -> ACTIVE (syncs is_verified=True)
    assert client.put(f"/vendors/{vendor_id}/status", json={"status": "PENDING_APPROVAL"}, headers=admin_headers).status_code == 200
    act = client.put(
        f"/vendors/{vendor_id}/status",
        json={"status": "ACTIVE", "compliance_status": "VERIFIED"},
        headers=admin_headers,
    )
    assert act.status_code == 200

    linked_user = db_session.query(User).filter(User.vendor_id == vendor_id).first()
    assert linked_user.is_verified is True

    # Approved ACTIVE vendor can create products, update products, and record stock movements
    p_ok = client.post("/products/", json={
        "name": "Approved Watch", "price": 249.0, "category": "Electronics", "vendor_id": vendor_id
    }, headers=vendor_headers)
    assert p_ok.status_code == 201
    assert client.put(f"/products/{seeded_prod.id}", json={"price": 135.0}, headers=vendor_headers).status_code == 200
    assert client.post("/inventory/movements", json={
        "product_id": seeded_prod.id, "movement_type": "RESTOCK", "quantity": 5
    }, headers=vendor_headers).status_code == 201

    # 7. Suspended & Terminated vendors are immediately blocked again and is_verified reverts to False
    assert client.put(f"/vendors/{vendor_id}/status", json={"status": "SUSPENDED"}, headers=admin_headers).status_code == 200
    db_session.refresh(linked_user)
    assert linked_user.is_verified is False
    assert client.put(f"/products/{seeded_prod.id}", json={"price": 140.0}, headers=vendor_headers).status_code == 403
    assert client.post("/inventory/movements", json={
        "product_id": seeded_prod.id, "movement_type": "RESTOCK", "quantity": 5
    }, headers=vendor_headers).status_code == 403

    assert client.put(f"/vendors/{vendor_id}/status", json={"status": "TERMINATED"}, headers=admin_headers).status_code == 200
    assert client.put(f"/vendors/{vendor_id}", json={"phone": "+91-9999999999"}, headers=vendor_headers).status_code == 403


# ── 8: LEGACY_ACTIVE Backward Compatibility ──────────────────────────────────

def test_07_legacy_active_vendor_remains_fully_operational(client, db_session):
    legacy_v = Vendor(
        name="Legacy Heritage",
        email="heritage@example.com",
        phone="+91-9111111111",
        status="LEGACY_ACTIVE",
        compliance_status="LEGACY_EXEMPT",
    )
    db_session.add(legacy_v)
    db_session.commit()
    db_session.refresh(legacy_v)

    _, v_headers = _create_auth_user(
        db_session, email="heritage@example.com", role=UserRole.VENDOR, vendor_id=legacy_v.id
    )
    prod_resp = client.post("/products/", json={
        "name": "Legacy Ceramic Vase", "price": 450.0, "category": "Home", "vendor_id": legacy_v.id
    }, headers=v_headers)
    assert prod_resp.status_code == 201
    pid = prod_resp.json()["id"]

    assert client.put(f"/products/{pid}", json={"price": 475.0}, headers=v_headers).status_code == 200
    assert client.post("/inventory/movements", json={
        "product_id": pid, "movement_type": "RESTOCK", "quantity": 20
    }, headers=v_headers).status_code == 201

    # Visible on public catalog without auth
    pub = client.get("/products/")
    assert pub.status_code == 200
    assert any(p["id"] == pid for p in pub.json())


# ── 9 & 10: Vendor Routes Protection & Analytics Tenant/Cache Isolation ──────

def test_08_vendor_endpoints_and_analytics_tenant_isolation(client, db_session):
    v1 = Vendor(name="Vendor Alpha", email="alpha_iso@example.com", phone="1111111111", status="ACTIVE")
    v2 = Vendor(name="Vendor Beta", email="beta_iso@example.com", phone="2222222222", status="ACTIVE")
    db_session.add_all([v1, v2])
    db_session.flush()

    p1 = Product(name="Alpha Item", price=100.0, category="CatA", vendor_id=v1.id)
    p2 = Product(name="Beta Item", price=200.0, category="CatB", vendor_id=v2.id)
    c1 = Customer(name="Cust Iso", email="cust_iso@example.com")
    db_session.add_all([p1, p2, c1])
    db_session.flush()

    db_session.add_all([
        Inventory(product_id=p1.id, current_stock=15, reorder_level=5),
        Inventory(product_id=p2.id, current_stock=25, reorder_level=5),
        Transaction(product_id=p1.id, vendor_id=v1.id, customer_id=c1.customer_id, quantity=1, unit_price=100.0, amount=100.0),
        Transaction(product_id=p2.id, vendor_id=v2.id, customer_id=c1.customer_id, quantity=2, unit_price=200.0, amount=400.0),
    ])
    db_session.commit()

    _, adm_h = _create_auth_user(db_session, email="adm_iso@example.com", role=UserRole.ADMIN)
    _, v1_h = _create_auth_user(db_session, email="v1_iso@example.com", role=UserRole.VENDOR, vendor_id=v1.id)
    _, v2_h = _create_auth_user(db_session, email="v2_iso@example.com", role=UserRole.VENDOR, vendor_id=v2.id)
    _, cust_h = _create_auth_user(db_session, email="c_iso@example.com", role=UserRole.CUSTOMER, customer_id=c1.customer_id)

    # /vendors/ listing & /vendors/ POST restricted to ADMIN
    assert client.get("/vendors/", headers=v1_h).status_code == 403
    assert client.get("/vendors/", headers=cust_h).status_code == 403
    assert client.get("/vendors/", headers=adm_h).status_code == 200
    assert client.post("/vendors/", json={
        "name": "Unauthorized Direct", "email": "ud@example.com", "phone": "3333333333"
    }, headers=cust_h).status_code == 403

    # /vendors/me & /vendors/{id}
    assert client.get("/vendors/me", headers=v1_h).json()["id"] == v1.id
    assert client.get("/vendors/me", headers=cust_h).status_code == 403
    assert client.get(f"/vendors/{v1.id}", headers=v1_h).status_code == 200
    assert client.get(f"/vendors/{v2.id}", headers=v1_h).status_code == 403
    assert client.get(f"/vendors/{v2.id}", headers=cust_h).status_code == 403
    assert client.get(f"/vendors/{v2.id}", headers=adm_h).status_code == 200

    # Inventory status & analytics tenant scoping + benchmarking admin-only
    assert client.get("/analytics/inventory/status", headers=cust_h).status_code == 403
    inv_v1 = client.get("/analytics/inventory/status", headers=v1_h).json()
    assert all(row["vendor_name"] == "Vendor Alpha" for row in inv_v1)

    assert client.get("/analytics/revenue/by-vendor", headers=cust_h).status_code == 403
    rev_v1 = client.get("/analytics/revenue/by-vendor", headers=v1_h).json()
    assert [r["vendor_id"] for r in rev_v1] == [v1.id]

    # Cache isolation check on /analytics/vendor-performance
    perf_v1 = client.get("/analytics/vendor-performance", headers=v1_h).json()
    perf_v2 = client.get("/analytics/vendor-performance", headers=v2_h).json()
    perf_adm = client.get("/analytics/vendor-performance", headers=adm_h).json()
    assert [r["vendor_id"] for r in perf_v1] == [v1.id]
    assert [r["vendor_id"] for r in perf_v2] == [v2.id]
    assert {r["vendor_id"] for r in perf_adm} == {v1.id, v2.id}

    assert client.get("/analytics/revenue/benchmarking", headers=v1_h).status_code == 403
    assert client.get("/analytics/revenue/benchmarking", headers=cust_h).status_code == 403
    assert client.get("/analytics/revenue/benchmarking", headers=adm_h).status_code == 200


# ── 11 & 12: Public Catalog & Recommendation Engine Filtering ────────────────

def test_09_public_catalog_and_recommendations_exclude_non_operational_vendors(client, db_session):
    v_active = Vendor(name="Active Co", email="act_cat@example.com", phone="1010101010", status="ACTIVE")
    v_legacy = Vendor(name="Legacy Co", email="leg_cat@example.com", phone="2020202020", status="LEGACY_ACTIVE")
    v_pend = Vendor(name="Pending Co", email="pen_cat@example.com", phone="3030303030", status="PENDING_APPROVAL")
    v_rej = Vendor(name="Rejected Co", email="rej_cat@example.com", phone="4040404040", status="REJECTED")
    v_susp = Vendor(name="Suspended Co", email="sus_cat@example.com", phone="5050505050", status="SUSPENDED")
    db_session.add_all([v_active, v_legacy, v_pend, v_rej, v_susp])
    db_session.flush()

    p_act = Product(name="Active Blender", price=50.0, category="Kitchen", vendor_id=v_active.id)
    p_leg = Product(name="Legacy Kettle", price=40.0, category="Kitchen", vendor_id=v_legacy.id)
    p_pen = Product(name="Pending Mixer", price=60.0, category="Kitchen", vendor_id=v_pend.id)
    p_rej = Product(name="Rejected Toaster", price=30.0, category="Kitchen", vendor_id=v_rej.id)
    p_sus = Product(name="Suspended Oven", price=90.0, category="Kitchen", vendor_id=v_susp.id)
    c1 = Customer(name="Shopper One", email="shopper1@example.com")
    c2 = Customer(name="Shopper Two", email="shopper2@example.com")
    db_session.add_all([p_act, p_leg, p_pen, p_rej, p_sus, c1, c2])
    db_session.flush()

    for p in (p_act, p_leg, p_pen, p_rej, p_sus):
        db_session.add(Inventory(product_id=p.id, current_stock=50, reorder_level=5))

    # Give non-operational products higher sales volume to prove recommendations strictly filter them out
    db_session.add_all([
        Transaction(product_id=p_act.id, vendor_id=v_active.id, customer_id=c1.customer_id, quantity=1, unit_price=50.0, amount=50.0),
        Transaction(product_id=p_pen.id, vendor_id=v_pend.id, customer_id=c1.customer_id, quantity=20, unit_price=60.0, amount=1200.0),
        Transaction(product_id=p_sus.id, vendor_id=v_susp.id, customer_id=c1.customer_id, quantity=30, unit_price=90.0, amount=2700.0),
        CustomerInteraction(customer_id=c1.customer_id, product_id=p_act.id, interaction_type="view", interaction_weight=1.0),
        CustomerInteraction(customer_id=c1.customer_id, product_id=p_pen.id, interaction_type="purchase", interaction_weight=4.0),
        CustomerInteraction(customer_id=c1.customer_id, product_id=p_leg.id, interaction_type="cart", interaction_weight=2.5),
    ])
    db_session.commit()

    # Public catalog (unauthenticated loopback — get_optional_user must NOT promote to admin)
    pub_list = client.get("/products/").json()
    pub_ids = {p["id"] for p in pub_list}
    assert {p_act.id, p_leg.id}.issubset(pub_ids)
    assert pub_ids.isdisjoint({p_pen.id, p_rej.id, p_sus.id})

    # Public detail returns 404 for non-operational vendors
    assert client.get(f"/products/{p_act.id}").status_code == 200
    assert client.get(f"/products/{p_leg.id}").status_code == 200
    assert client.get(f"/products/{p_pen.id}").status_code == 404
    assert client.get(f"/products/{p_sus.id}").status_code == 404

    # Customer sees same restricted view, whereas Admin sees all
    _, cust_h = _create_auth_user(db_session, email="c_cat@example.com", role=UserRole.CUSTOMER, customer_id=c2.customer_id)
    _, adm_h = _create_auth_user(db_session, email="a_cat@example.com", role=UserRole.ADMIN)
    cust_ids = {p["id"] for p in client.get("/products/", headers=cust_h).json()}
    adm_ids = {p["id"] for p in client.get("/products/", headers=adm_h).json()}
    assert cust_ids == {p_act.id, p_leg.id}
    assert {p_act.id, p_leg.id, p_pen.id, p_rej.id, p_sus.id}.issubset(adm_ids)

    # Recommendation endpoints must never recommend PENDING_APPROVAL/REJECTED/SUSPENDED vendor items
    pop = client.get("/recommendations/popular?top_n=10").json()
    assert isinstance(pop, list)
    assert {r["product_id"] for r in pop}.issubset({p_act.id, p_leg.id})

    cf = client.get(f"/recommendations/customer/{c2.customer_id}?top_n=10", headers=cust_h).json()["recommendations"]
    assert {r["product_id"] for r in cf}.issubset({p_act.id, p_leg.id})

    hyb = client.get(f"/recommendations/hybrid/{c2.customer_id}?top_n=10", headers=cust_h).json()["recommendations"]
    assert {r["product_id"] for r in hyb}.issubset({p_act.id, p_leg.id})

    single_rec = client.get(f"/recommend/{c2.customer_id}", headers=cust_h).json()
    assert single_rec["recommended_product"] in {"Active Blender", "Legacy Kettle"}


# ── 13: Loopback Bypass Hardening ────────────────────────────────────────────

def test_10_loopback_bypass_blocked_for_proxy_production_and_non_test(client, monkeypatch):
    loopback = TestClient(app, client=("127.0.0.1", 54321))

    # Reverse-proxy forwarding headers must prevent loopback bypass -> 401
    for header in ("X-Forwarded-For", "X-Real-IP", "Forwarded"):
        resp = loopback.get("/vendors/", headers={header: "203.0.113.50"})
        assert resp.status_code == 401, f"Expected 401 with {header}, got {resp.status_code}"

    # ENVIRONMENT=production must prevent loopback bypass -> 401
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert loopback.get("/vendors/").status_code == 401
    assert loopback.get("/vendors/me").status_code == 401
    assert loopback.get("/analytics/vendors/payouts").status_code == 401
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Explicit opt-out disables legacy bypass even inside pytest
    monkeypatch.setenv("ALLOW_LEGACY_TEST_BYPASS", "false")
    assert loopback.get("/vendors/").status_code == 401
    monkeypatch.delenv("ALLOW_LEGACY_TEST_BYPASS", raising=False)

    # Simulating a live non-pytest HTTP process: remove 'pytest' from sys.modules momentarily
    saved_pytest = sys.modules.pop("pytest", None)
    try:
        assert loopback.get("/vendors/").status_code == 401
        assert loopback.get("/analytics/vendors/payouts").status_code == 401
    finally:
        if saved_pytest is not None:
            sys.modules["pytest"] = saved_pytest
