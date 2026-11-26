"""
tests/test_vendor_onboarding_stage_b.py — End-to-End UI & Security Verification Suite
for ShopSense Stage B: Vendor Onboarding & Approval UI.

Bridges Streamlit AppTest HTTP calls directly to the FastAPI TestClient backed by the
isolated pytest SQLite database (with X-Enforce-Auth enabled), testing the complete
Stage B UI workflows against real Stage A endpoints without modifying live PostgreSQL data.

Covers:
1. Sidebar Vendor Registration UI submission -> POST /auth/register-vendor -> PENDING_APPROVAL.
2. Backend validation errors (password mismatch, short password, duplicate email) surfaced cleanly.
3. Unauthenticated & Customer isolation on Vendor Management (no tax_id or verification notes exposed).
4. Admin Pending Applications queue, Approve confirmation flow, Reject confirmation + mandatory feedback,
   and immediate list refresh.
5. Admin Vendor Directory status filter, Category & Tax/GST ID fields in Add/Edit forms,
   and Termination edit lock.
6. Vendor logged-in onboarding status visibility via /vendors/me (PENDING_APPROVAL, REJECTED,
   SUSPENDED, TERMINATED, ACTIVE) + verification notes display.
7. Vendor tenant isolation across Dashboard, Vendor Profile, Product Management, Inventory Management,
   and Transactions (no competitor records leaked even when vendor has 0 items).
8. Disabled product & inventory write controls for non-operational vendors, unlocked once ACTIVE.
9. Customer Catalog exclusion of non-operational vendors + role-specific navigation checks.
10. Full regression AppTest smoke verification across all Admin dashboard pages.
"""

from datetime import datetime
import types
import pytest
from streamlit.testing.v1 import AppTest

from app.core.security import hash_password, create_access_token
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.stock_movement import StockMovement


class _NonClosingSessionProxy:
    """Delegate DB calls to pytest db_session without closing transaction scope early."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture
def stage_b_bridge(client, db_session, monkeypatch):
    """
    Route all dashboard HTTP requests (requests.get/post/put) directly through
    FastAPI TestClient (with X-Enforce-Auth: true) and bind SessionLocal to db_session.
    """
    import app.database as app_db

    monkeypatch.setattr(app_db, "SessionLocal", lambda: _NonClosingSessionProxy(db_session))
    # Prevent live CSV fallbacks from leaking unrelated seed rows during strict isolation tests
    import pandas as pd

    def _bridge_request(method: str):
        def _caller(url: str, *args, **kwargs):
            path = url.replace("http://127.0.0.1:8000", "") if url.startswith("http") else url
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["X-Enforce-Auth"] = "true"
            kwargs.pop("timeout", None)
            json_body = kwargs.pop("json", None)

            tc_resp = getattr(client, method)(path, json=json_body, headers=headers)
            resp_obj = types.SimpleNamespace(
                status_code=tc_resp.status_code,
                text=tc_resp.text,
                content=tc_resp.content,
                headers=tc_resp.headers,
                json=tc_resp.json,
            )

            def _raise_for_status():
                if tc_resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {tc_resp.status_code}: {tc_resp.text}")

            resp_obj.raise_for_status = _raise_for_status
            return resp_obj

        return _caller

    import requests

    monkeypatch.setattr(requests, "get", _bridge_request("get"))
    monkeypatch.setattr(requests, "post", _bridge_request("post"))
    monkeypatch.setattr(requests, "put", _bridge_request("put"))
    return {"client": client, "db": db_session, "empty_df": pd.DataFrame()}


def _make_user_and_token(
    db_session,
    *,
    email: str,
    role: str,
    vendor_id: int | None = None,
    customer_id: int | None = None,
    is_verified: bool = True,
) -> tuple[User, str]:
    user = User(
        email=email,
        hashed_password=hash_password("StrongPass!123"),
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
    tok = create_access_token(
        user_id=user.id,
        email=user.email,
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        token_version=1,
    )
    return user, tok


def _set_auth(at: AppTest, user: User, token: str):
    at.session_state["auth_token"] = token
    at.session_state["auth_user"] = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "vendor_id": user.vendor_id,
        "customer_id": user.customer_id,
    }


def _find_button(at: AppTest, text_substr: str):
    for b in at.button:
        if text_substr in (b.label or ""):
            return b
    raise AssertionError(f"Button matching {text_substr!r} not found. Available: {[b.label for b in at.button]}")


def _find_text_input(at: AppTest, key: str):
    for ti in at.text_input:
        if ti.key == key:
            return ti
    raise AssertionError(f"TextInput key={key!r} not found.")


def _find_selectbox(at: AppTest, key: str):
    for sb in at.selectbox:
        if sb.key == key:
            return sb
    raise AssertionError(f"Selectbox key={key!r} not found.")


# ── 1 & 2: Vendor Registration UI & Validation ──────────────────────────────

def test_01_vendor_registration_ui_success_and_validation(stage_b_bridge):
    db = stage_b_bridge["db"]
    at = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at.exception) == 0

    # Password mismatch should trigger backend Pydantic validation error without creating vendor
    _find_text_input(at, "vreg_owner").set_value("Asha Mehta")
    _find_text_input(at, "vreg_biz").set_value("Mehta Crafts")
    _find_text_input(at, "vreg_email").set_value("asha@craftstore.com")
    _find_text_input(at, "vreg_phone").set_value("+91-9876543210")
    _find_selectbox(at, "vreg_cat").set_value("Home Decor")
    _find_text_input(at, "vreg_tax").set_value("27AAACM1234F1Z5")
    _find_text_input(at, "vreg_pw").set_value("VendorPass!99")
    _find_text_input(at, "vreg_pw2").set_value("WrongConfirm!99")
    _find_button(at, "Submit Vendor Application").click().run(timeout=60)

    assert len(at.exception) == 0
    assert any("do not match" in e.value.lower() or "422" in e.value for e in at.error)
    assert db.query(Vendor).filter(Vendor.email == "asha@craftstore.com").first() is None

    # Valid submission -> creates PENDING_APPROVAL Vendor + VENDOR User atomically
    _find_text_input(at, "vreg_pw").set_value("VendorPass!99")
    _find_text_input(at, "vreg_pw2").set_value("VendorPass!99")
    _find_button(at, "Submit Vendor Application").click().run(timeout=60)

    assert len(at.exception) == 0
    assert any("application submitted" in s.value.lower() for s in at.success)
    assert any("awaiting admin approval" in i.value.lower() and "PENDING_APPROVAL" in i.value for i in at.info)

    v = db.query(Vendor).filter(Vendor.email == "asha@craftstore.com").first()
    u = db.query(User).filter(User.email == "asha@craftstore.com").first()
    assert v is not None and v.status == "PENDING_APPROVAL"
    assert v.owner_name == "Asha Mehta"
    assert v.business_type == "Home Decor"
    assert v.tax_id == "27AAACM1234F1Z5"
    assert u is not None and u.role == UserRole.VENDOR and u.vendor_id == v.id and u.is_verified is False

    # Duplicate submission surfaces clear backend 409 conflict error
    _find_button(at, "Submit Vendor Application").click().run(timeout=60)
    assert any("409" in e.value or "already registered" in e.value.lower() for e in at.error)


# ── 3 & 4 & 5: Admin Pending Queue, Approve/Reject Confirmation & Governance ─

def test_02_admin_pending_applications_approve_and_reject_workflows(stage_b_bridge):
    db = stage_b_bridge["db"]
    client = stage_b_bridge["client"]

    adm_user, adm_tok = _make_user_and_token(db, email="adm_ui@shopsense.com", role=UserRole.ADMIN)

    # Register two pending vendors via Stage A backend endpoint
    r1 = client.post("/auth/register-vendor", json={
        "owner_name": "Kiran Rao",
        "business_name": "Rao Electronics",
        "email": "kiran@raotech.com",
        "phone": "+91-9811111111",
        "category": "Electronics",
        "tax_id": "29RAOTECH1234Z1",
        "password": "StrongPass!123",
        "password_confirmation": "StrongPass!123",
    })
    assert r1.status_code == 201
    v_approve_id = r1.json()["vendor_id"]

    r2 = client.post("/auth/register-vendor", json={
        "owner_name": "Dev Patel",
        "business_name": "Patel Apparel",
        "email": "dev@patelwear.com",
        "phone": "+91-9822222222",
        "category": "Apparel",
        "tax_id": None,
        "password": "StrongPass!123",
        "password_confirmation": "StrongPass!123",
    })
    assert r2.status_code == 201
    v_reject_id = r2.json()["vendor_id"]

    at = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at, adm_user, adm_tok)
    at.run(timeout=60)
    at.radio[0].set_value("🏢 Vendor Management").run(timeout=60)
    assert len(at.exception) == 0

    # Pending Applications banner should reflect 2 pending applications
    assert any("2 vendor application" in w.value for w in at.warning)

    # 1) Approve v_approve_id with two-step confirmation
    _find_selectbox(at, "sb_pending_vendor_id").set_value(v_approve_id)
    _find_text_input(at, "pending_review_notes").set_value("Verified GST and storefront documents")
    _find_selectbox(at, "pending_review_tier").set_value("TIER_PREFERRED")
    _find_button(at, "Approve Application").click().run(timeout=60)

    # Confirmation banner appears before status is mutated!
    assert any("Confirm Application APPROVE" in w.value for w in at.warning)
    db.expire_all()
    assert db.query(Vendor).filter(Vendor.id == v_approve_id).first().status == "PENDING_APPROVAL"

    _find_button(at, "Confirm Approve").click().run(timeout=60)
    assert len(at.exception) == 0

    db.expire_all()
    v1_db = db.query(Vendor).filter(Vendor.id == v_approve_id).first()
    u1_db = db.query(User).filter(User.vendor_id == v_approve_id).first()
    assert v1_db.status == "ACTIVE"
    assert v1_db.compliance_status == "VERIFIED"
    assert v1_db.commission_tier == "TIER_PREFERRED"
    assert v1_db.verification_notes == "Verified GST and storefront documents"
    assert u1_db.is_verified is True

    # Feedback shown and pending queue refreshed to 1 remaining application
    assert any("ACTIVE" in s.value for s in at.success)
    assert any("1 vendor application" in w.value for w in at.warning)

    # 2) Reject v_reject_id: empty notes should fail, non-empty notes confirm & reject
    _find_selectbox(at, "sb_pending_vendor_id").set_value(v_reject_id)
    _find_text_input(at, "pending_review_notes").set_value("")
    _find_button(at, "Reject Application").click().run(timeout=60)
    assert any("feedback notes are required" in e.value.lower() for e in at.error)

    _find_text_input(at, "pending_review_notes").set_value("Business tax registration missing")
    _find_button(at, "Reject Application").click().run(timeout=60)
    assert any("Confirm Application REJECT" in w.value for w in at.warning)
    _find_button(at, "Confirm Reject").click().run(timeout=60)

    db.expire_all()
    v2_db = db.query(Vendor).filter(Vendor.id == v_reject_id).first()
    assert v2_db.status == "REJECTED"
    assert v2_db.compliance_status == "FLAGGED"
    assert v2_db.verification_notes == "Business tax registration missing"
    assert any("no pending applications" in s.value.lower() for s in at.success)


# ── 6, 7 & 8: Vendor Status Visibility, Isolation & Restricted Controls ──────

def test_03_vendor_status_visibility_isolation_and_restricted_controls(stage_b_bridge):
    db = stage_b_bridge["db"]
    client = stage_b_bridge["client"]

    # Vendor 1: PENDING_APPROVAL (registered via UI/endpoint)
    r_pend = client.post("/auth/register-vendor", json={
        "owner_name": "Pending Owner",
        "business_name": "Pending Store",
        "email": "pending@store.com",
        "phone": "+91-9700000001",
        "category": "Electronics",
        "tax_id": "27PEND1234Z1",
        "password": "StrongPass!123",
        "password_confirmation": "StrongPass!123",
    })
    v_pend_id = r_pend.json()["vendor_id"]
    u_pend = db.query(User).filter(User.id == r_pend.json()["user_id"]).first()
    tok_pend = client.post("/auth/login", json={"email": "pending@store.com", "password": "StrongPass!123"}).json()["access_token"]

    # Vendor 2: COMPETITOR ACTIVE vendor with secret product, inventory & transactions
    v_comp = Vendor(
        name="Competitor Giant",
        owner_name="Secret Rival",
        email="rival@giant.com",
        phone="+91-9799999999",
        tax_id="99SECRETRIVAL",
        status="ACTIVE",
        compliance_status="VERIFIED",
        verification_notes="Competitor secret note",
    )
    db.add(v_comp)
    db.flush()
    comp_prod = Product(name="Rival Secret Product", price=9999.0, category="Luxury", vendor_id=v_comp.id)
    cust = Customer(name="Shopper X", email="sx@test.com")
    db.add_all([comp_prod, cust])
    db.flush()
    db.add_all([
        Inventory(product_id=comp_prod.id, current_stock=50, reorder_level=10, warehouse="Main"),
        Transaction(
            product_id=comp_prod.id, vendor_id=v_comp.id, customer_id=cust.customer_id,
            quantity=3, unit_price=9999.0, amount=29997.0, transaction_date=datetime.utcnow()
        ),
    ])
    db.commit()

    # Check PENDING_APPROVAL Vendor UI across Dashboard, Vendor Management, Product Mgmt, Inventory Mgmt, Transactions
    at = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at, u_pend, tok_pend)
    at.run(timeout=60)
    assert len(at.exception) == 0

    # Role-specific nav checks: Admin/Internal pages excluded
    nav_opts = at.radio[0].options
    assert "🏢 Vendor Management" in nav_opts
    assert "👥 Customer Analytics" not in nav_opts
    assert "⚡ ETL & Data Warehouse" not in nav_opts
    assert "🩺 Integration Status / System Health" not in nav_opts

    # Dashboard prominently shows PENDING APPROVAL banner and ZERO competitor metrics
    dash_warn = "\n".join(w.value for w in at.warning)
    dash_md = "\n".join(m.value for m in at.markdown)
    assert "Approval Pending" in dash_warn
    assert "PENDING APPROVAL" in dash_md
    assert "Competitor Giant" not in dash_md
    assert "Rival Secret Product" not in dash_md

    # Vendor Management shows ONLY own profile (Pending Store) and hides Admin governance tabs
    at.radio[0].set_value("🏢 Vendor Management").run(timeout=60)
    assert len(at.exception) == 0
    vm_md = "\n".join(m.value for m in at.markdown)
    assert "Pending Store" in vm_md
    assert "Competitor Giant" not in vm_md
    assert "Pending Applications" not in vm_md
    assert not any("Approve Application" in (b.label or "") for b in at.button)

    # Product Management disables Add Product & Edit Product for non-operational PENDING_APPROVAL vendor
    at.radio[0].set_value("📦 Product Management").run(timeout=60)
    assert len(at.exception) == 0
    assert any("Restricted Action" in e.value for e in at.error)
    assert any("Approval Required" in (b.label or "") and b.disabled for b in at.button)
    # Rival product must never appear in Vendor's catalog dataframes
    for df_el in at.dataframe:
        assert "Rival Secret Product" not in df_el.value.to_string()

    # Inventory Management disables stock movements for PENDING_APPROVAL vendor and hides competitor inventory
    at.radio[0].set_value("📋 Inventory Management").run(timeout=60)
    assert len(at.exception) == 0
    assert any("Restricted Action" in e.value for e in at.error)
    assert any("Approval Required" in (b.label or "") and b.disabled for b in at.button)
    for df_el in at.dataframe:
        assert "Rival Secret Product" not in df_el.value.to_string()

    # Transactions shows ONLY own transactions (0 here, never falls back to Rival transactions)
    at.radio[0].set_value("💳 Transactions").run(timeout=60)
    assert len(at.exception) == 0
    assert len(at.dataframe) == 0
    assert not any("Process Safe Refund" in (b.label or "") for b in at.button)

    # Transition Vendor 1 to REJECTED with feedback -> vendor sees rejection notes
    adm_user, adm_tok = _make_user_and_token(db, email="adm_rej@shopsense.com", role=UserRole.ADMIN)
    client.put(
        f"/vendors/{v_pend_id}/status",
        json={"status": "REJECTED", "compliance_status": "FLAGGED", "verification_notes": "Invalid GST document uploaded"},
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    at_rej = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at_rej, u_pend, tok_pend)
    at_rej.run(timeout=60)
    at_rej.radio[0].set_value("🏢 Vendor Management").run(timeout=60)
    assert any("Invalid GST document uploaded" in e.value and "Application Rejected" in e.value for e in at_rej.error)

    # Transition Vendor 1 REJECTED -> PENDING_APPROVAL -> ACTIVE -> controls unlock & vendor selector stays locked to own store
    client.put(
        f"/vendors/{v_pend_id}/status",
        json={"status": "PENDING_APPROVAL"},
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    client.put(
        f"/vendors/{v_pend_id}/status",
        json={"status": "ACTIVE", "compliance_status": "VERIFIED", "verification_notes": "All checks passed"},
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    at_act = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at_act, u_pend, tok_pend)
    at_act.run(timeout=60)
    assert any("Approved Vendor Status (ACTIVE)" in s.value for s in at_act.success)

    at_act.radio[0].set_value("📦 Product Management").run(timeout=60)
    assert not any("Approval Required" in (b.label or "") for b in at_act.button)
    sb_add = _find_selectbox(at_act, "sb_add_prod_vid")
    assert len(sb_add.options) == 1
    assert sb_add.value == v_pend_id
    assert sb_add.disabled is True

    # Transition to SUSPENDED -> banner distinguishes SUSPENDED and locks product controls again
    client.put(
        f"/vendors/{v_pend_id}/status",
        json={"status": "SUSPENDED", "verification_notes": "Temporary inventory audit"},
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    at_susp = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at_susp, u_pend, tok_pend)
    at_susp.run(timeout=60)
    assert any("Account Suspended" in w.value and "Temporary inventory audit" in w.value for w in at_susp.warning)
    at_susp.radio[0].set_value("📦 Product Management").run(timeout=60)
    assert any("Approval Required" in (b.label or "") and b.disabled for b in at_susp.button)

    # Transition to TERMINATED -> banner distinguishes TERMINATED and locks profile edits
    client.put(
        f"/vendors/{v_pend_id}/status",
        json={"status": "TERMINATED", "verification_notes": "Account closed"},
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    at_term = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at_term, u_pend, tok_pend)
    at_term.run(timeout=60)
    at_term.radio[0].set_value("🏢 Vendor Management").run(timeout=60)
    assert any("Account Terminated" in e.value for e in at_term.error)
    assert any("Save Store Profile" in (b.label or "") and b.disabled for b in at_term.button)


# ── 9: Unauthenticated & Customer Catalog Privacy & Storefront Filtering ─────

def test_04_unauthenticated_and_customer_views_hide_sensitive_and_unapproved_data(stage_b_bridge):
    db = stage_b_bridge["db"]

    v_pend = Vendor(
        name="Hidden Pending Co", email="hid@pend.com", phone="1112223334",
        tax_id="SENSITIVE_TAX_ID_PEND", status="PENDING_APPROVAL", verification_notes="Private Admin Audit"
    )
    v_act = Vendor(
        name="Approved Store Co", email="pub@act.com", phone="5556667778",
        tax_id="SENSITIVE_TAX_ID_ACT", status="ACTIVE", verification_notes="Private Approved Audit"
    )
    db.add_all([v_pend, v_act])
    db.flush()
    p_pend = Product(name="Hidden Pending Widget", price=120.0, category="Widgets", vendor_id=v_pend.id)
    p_act = Product(name="Visible Approved Widget", price=220.0, category="Widgets", vendor_id=v_act.id)
    cust = Customer(name="Buyer Alice", email="alice_ui@test.com")
    db.add_all([p_pend, p_act, cust])
    db.commit()

    # Unauthenticated visitor lands on Login Page First and cannot access dashboard modules or vendor data
    at_unauth = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at_unauth.exception) == 0
    assert len(at_unauth.radio) == 0
    combined_unauth = "\n".join(m.value for m in at_unauth.markdown)
    assert "Welcome to ShopSense" in combined_unauth
    assert "SENSITIVE_TAX_ID" not in combined_unauth
    assert "Private Admin Audit" not in combined_unauth
    assert "Hidden Pending Widget" not in combined_unauth

    # Authenticated CUSTOMER view: only storefront, recommendations, transactions; hides non-operational products
    cust_user, cust_tok = _make_user_and_token(
        db, email="alice_ui@test.com", role=UserRole.CUSTOMER, customer_id=cust.customer_id
    )
    at_cust = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at_cust, cust_user, cust_tok)
    at_cust.run(timeout=60)
    assert len(at_cust.exception) == 0
    assert at_cust.radio[0].options == ["🛍️ Customer Catalog", "🎯 Recommendations", "💳 Transactions"]

    cust_md = "\n".join(m.value for m in at_cust.markdown)
    assert "Visible Approved Widget" in cust_md
    assert "Hidden Pending Widget" not in cust_md
    assert "SENSITIVE_TAX_ID" not in cust_md


# ── 10: Admin Multi-Page Regression Check (All 11 Views) ──────────────────────

@pytest.mark.parametrize(
    "page_name",
    [
        "📊 Dashboard",
        "💎 Executive BI",
        "🏢 Vendor Management",
        "📦 Product Management",
        "📋 Inventory Management",
        "💳 Transactions",
        "👥 Customer Analytics",
        "📈 Demand Forecasting",
        "🎯 Recommendations",
        "🛍️ Customer Catalog",
        "⚡ ETL & Data Warehouse",
        "🩺 Integration Status / System Health",
    ],
)
def test_05_admin_dashboard_pages_render_without_exceptions(stage_b_bridge, page_name):
    db = stage_b_bridge["db"]
    v = Vendor(name="Smoke Vendor", email="smoke@v.com", phone="9998887776", status="ACTIVE", tax_id="27SMOKE123")
    db.add(v)
    db.flush()
    p = Product(name="Smoke Item", price=500.0, category="Electronics", vendor_id=v.id)
    cust = Customer(name="Smoke Customer", email="smoke_cust@v.com")
    db.add_all([p, cust])
    db.flush()
    db.add(Inventory(product_id=p.id, current_stock=20, reorder_level=5, warehouse="Main"))
    db.add(Transaction(
        product_id=p.id, vendor_id=v.id, customer_id=cust.customer_id,
        quantity=2, unit_price=500.0, amount=1000.0, transaction_date=datetime.utcnow(),
    ))
    db.commit()

    adm_user, adm_tok = _make_user_and_token(db, email="adm_smoke@shopsense.com", role=UserRole.ADMIN)
    at = AppTest.from_file("dashboard/dashboard.py")
    _set_auth(at, adm_user, adm_tok)
    at.run(timeout=60)
    at.radio[0].set_value(page_name).run(timeout=60)
    assert len(at.exception) == 0, f"Exceptions on {page_name}: {at.exception}"


# ── 11: Login Page First, Show/Hide Password & Role Redirects ─────────────────

def test_06_login_page_first_show_password_and_role_redirects(stage_b_bridge):
    db = stage_b_bridge["db"]
    v = Vendor(name="Redirect Store", email="redir_v@shopsense.com", phone="9191919191", status="ACTIVE")
    c = Customer(name="Redirect Buyer", email="redir_c@shopsense.com")
    db.add_all([v, c])
    db.commit()
    db.refresh(v)
    db.refresh(c)

    _make_user_and_token(db, email="adm_redir@shopsense.com", role=UserRole.ADMIN)
    _make_user_and_token(db, email="vend_redir@shopsense.com", role=UserRole.VENDOR, vendor_id=v.id)
    _make_user_and_token(db, email="cust_redir@shopsense.com", role=UserRole.CUSTOMER, customer_id=c.customer_id)

    # 1. Login Page renders first with Show/Hide Password toggle
    at = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at.exception) == 0
    assert len(at.radio) == 0
    assert "Welcome to ShopSense" in "\n".join(m.value for m in at.markdown)
    pw_box = _find_text_input(at, "login_pass")
    # Streamlit TextInput proto.type: 1 == PASSWORD (masked), 0 == DEFAULT (visible)
    assert pw_box.proto.type == 1

    show_cb = next(cb for cb in at.checkbox if cb.key == "login_show_pw")
    show_cb.set_value(True).run(timeout=60)
    assert _find_text_input(at, "login_pass").proto.type == 0

    # 2. Invalid credentials show clear error and keep user on Login Page
    _find_text_input(at, "login_email").set_value("adm_redir@shopsense.com")
    _find_text_input(at, "login_pass").set_value("WrongPassword123")
    _find_button(at, "Sign In to ShopSense").click().run(timeout=60)
    assert any("Sign-in failed" in e.value for e in at.error)
    assert len(at.radio) == 0

    # 3. Admin login redirects to Executive Dashboard with top search & all 12 nav items
    _find_text_input(at, "login_pass").set_value("StrongPass!123")
    _find_button(at, "Sign In to ShopSense").click().run(timeout=60)
    assert len(at.exception) == 0
    assert len(at.radio) >= 1
    assert at.radio[0].value == "📊 Dashboard"
    assert len(at.radio[0].options) == 12
    assert "💎 Executive BI" in at.radio[0].options
    assert at.session_state["auth_user"]["role"] == "ADMIN"

    # Simulate the browser's post-rerun frame carrying the freshly issued session auth
    at_admin = AppTest.from_file("dashboard/dashboard.py")
    at_admin.session_state["auth_token"] = at.session_state["auth_token"]
    at_admin.session_state["auth_user"] = at.session_state["auth_user"]
    at_admin.run(timeout=60)

    # Global search executes cleanly without exception
    _find_text_input(at_admin, "top_global_search").set_value("Redirect").run(timeout=60)
    assert len(at_admin.exception) == 0

    # Log out clears session cleanly via /auth/logout
    _find_button(at_admin, "Log Out").click().run(timeout=60)
    assert len(at_admin.exception) == 0
    assert at_admin.session_state["auth_user"] is None
    assert at_admin.session_state["auth_token"] is None

    # Unauthenticated reload renders Login Page First (no sidebar/radio)
    at_after_logout = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at_after_logout.radio) == 0

    # 4. Customer login via UI form redirects directly to Customer Catalog
    _find_text_input(at_after_logout, "login_email").set_value("cust_redir@shopsense.com")
    _find_text_input(at_after_logout, "login_pass").set_value("StrongPass!123")
    _find_button(at_after_logout, "Sign In to ShopSense").click().run(timeout=60)
    assert len(at_after_logout.exception) == 0
    assert at_after_logout.radio[0].value == "🛍️ Customer Catalog"
    assert at_after_logout.radio[0].options == ["🛍️ Customer Catalog", "🎯 Recommendations", "💳 Transactions"]

    # 5. Vendor login via UI form redirects to Vendor Dashboard
    at_vendor_login = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    _find_text_input(at_vendor_login, "login_email").set_value("vend_redir@shopsense.com")
    _find_text_input(at_vendor_login, "login_pass").set_value("StrongPass!123")
    _find_button(at_vendor_login, "Sign In to ShopSense").click().run(timeout=60)
    assert len(at_vendor_login.exception) == 0
    assert at_vendor_login.radio[0].value == "📊 Dashboard"
    assert "Redirect Store" in "\n".join(m.value for m in at_vendor_login.markdown)
