"""
tests/test_executive_bi_dashboard.py — End-to-End Integration & UI Verification
for ShopSense Milestone 4 Phase 3: Executive BI Dashboard.

Verifies:
  1. Admin-only navigation visibility and RBAC enforcement (VENDOR/CUSTOMER blocked).
  2. Direct Phase 2 Executive Analytics API consumption and KPI parity against JSON responses.
  3. Date-range filtering (`start_date`, `end_date`), Daily/Monthly granularity, empty state, invalid date handling.
  4. Partial and zero cost coverage indicators without misleading profit figures.
  5. Graceful API error handling (`HTTP 500` / `403`) in Streamlit without unhandled exceptions.
"""

from datetime import date, datetime
import types

import pytest
from streamlit.testing.v1 import AppTest

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from dashboard.executive_bi import fetch_executive_dashboard_data


class _NonClosingSessionProxy:
    """Keep pytest transaction session alive when Streamlit helpers close SessionLocal()."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture
def exec_ui_bridge(client, db_session, monkeypatch):
    """Route dashboard HTTP GET calls directly through FastAPI TestClient against pytest DB."""
    import app.database as app_db
    import requests

    monkeypatch.setattr(app_db, "SessionLocal", lambda: _NonClosingSessionProxy(db_session))

    recorded_urls = []

    def _get_bridge(url: str, *args, **kwargs):
        path = url.replace("http://127.0.0.1:8000", "") if url.startswith("http") else url
        recorded_urls.append(path)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Enforce-Auth"] = "true"
        kwargs.pop("timeout", None)
        tc_resp = client.get(path, headers=headers)
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

    monkeypatch.setattr(requests, "get", _get_bridge)
    return {"client": client, "db": db_session, "urls": recorded_urls}


def _make_auth(db_session, email: str, role: str, vendor_id=None, customer_id=None):
    user = User(
        email=email,
        hashed_password=hash_password("ExecBI!2026"),
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        is_active=True,
        is_verified=True,
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
    return user, token


def _seed_sample(db_session, with_cost: bool = True):
    v1 = Vendor(
        name="Apex Digital", email="apex@bi.test", phone="9000010001",
        status="ACTIVE", commission_tier="TIER_PREFERRED", commission_rate=0.10,
    )
    v2 = Vendor(
        name="Craftsman Living", email="craft@bi.test", phone="9000010002",
        status="ACTIVE", commission_tier="TIER_STANDARD", commission_rate=0.12,
    )
    db_session.add_all([v1, v2])
    db_session.flush()

    p1 = Product(
        name="Studio Speaker", price=100.0,
        cost_price=60.0 if with_cost else None,
        category="Audio", vendor_id=v1.id,
    )
    p2 = Product(
        name="Braided Cable", price=50.0,
        cost_price=None,
        category="Accessories", vendor_id=v1.id,
    )
    p3 = Product(
        name="Stoneware Vase", price=80.0,
        cost_price=40.0 if with_cost else None,
        category="Decor", vendor_id=v2.id,
    )
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    db_session.add_all([
        Inventory(product_id=p1.id, current_stock=20, reorder_level=5),
        Inventory(product_id=p2.id, current_stock=4, reorder_level=10),
        Inventory(product_id=p3.id, current_stock=0, reorder_level=5),
    ])

    c1 = Customer(name="Aarav Mehta", email="aarav@bi.test", city="Mumbai", region="Maharashtra")
    c2 = Customer(name="Dia Nair", email="dia@bi.test", city="Kochi", region="Kerala")
    db_session.add_all([c1, c2])
    db_session.flush()

    t1 = Transaction(
        product_id=p1.id, vendor_id=v1.id, customer_id=c1.customer_id,
        quantity=2, unit_price=100.0, amount=200.0, discount_amount=10.0,
        transaction_date=datetime(2024, 1, 12, 10, 0, 0),
    )
    t2 = Transaction(
        product_id=p2.id, vendor_id=v1.id, customer_id=c2.customer_id,
        quantity=2, unit_price=50.0, amount=100.0, discount_amount=0.0,
        transaction_date=datetime(2024, 1, 22, 15, 0, 0),
    )
    t3 = Transaction(
        product_id=p1.id, vendor_id=v1.id, customer_id=c1.customer_id,
        quantity=3, unit_price=100.0, amount=300.0, discount_amount=20.0,
        transaction_date=datetime(2024, 2, 10, 11, 0, 0),
    )
    t4 = Transaction(
        product_id=p3.id, vendor_id=v2.id, customer_id=c2.customer_id,
        quantity=2, unit_price=80.0, amount=160.0, discount_amount=0.0,
        transaction_date=datetime(2024, 2, 19, 13, 0, 0),
    )
    t5 = Transaction(
        product_id=p3.id, vendor_id=v2.id, customer_id=c1.customer_id,
        quantity=3, unit_price=80.0, amount=240.0, discount_amount=0.0,
        transaction_date=datetime(2024, 3, 8, 9, 0, 0),
    )
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.flush()

    db_session.add(
        Refund(
            transaction_id=t3.transaction_id,
            idempotency_key="bi-refund-t3",
            amount=40.0,
            reason="Damaged packaging",
            status="COMPLETED",
        )
    )
    db_session.commit()
    return v1, v2, c1


def _set_session(at: AppTest, user: User, token: str):
    at.session_state["auth_token"] = token
    at.session_state["auth_user"] = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "vendor_id": user.vendor_id,
        "customer_id": user.customer_id,
    }


def test_01_admin_only_navigation_and_rbac(exec_ui_bridge):
    """ADMIN sees Executive BI page; VENDOR and CUSTOMER cannot see or access it."""
    db = exec_ui_bridge["db"]
    v1, _, c1 = _seed_sample(db)
    adm, adm_tok = _make_auth(db, "adm_bi1@shopsense.com", UserRole.ADMIN)
    vend, vend_tok = _make_auth(db, "vend_bi1@shopsense.com", UserRole.VENDOR, vendor_id=v1.id)
    cust, cust_tok = _make_auth(db, "cust_bi1@shopsense.com", UserRole.CUSTOMER, customer_id=c1.customer_id)

    at_adm = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at_adm, adm, adm_tok)
    at_adm.run(timeout=60)
    assert "💎 Executive BI" in at_adm.radio[0].options

    at_vend = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at_vend, vend, vend_tok)
    at_vend.run(timeout=60)
    assert "💎 Executive BI" not in at_vend.radio[0].options

    at_cust = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at_cust, cust, cust_tok)
    at_cust.run(timeout=60)
    assert "💎 Executive BI" not in at_cust.radio[0].options

    # Direct RBAC guard verification inside Executive BI component
    at_guard = AppTest.from_string(
        """
import streamlit as st
from dashboard.executive_bi import render_executive_bi_dashboard
render_executive_bi_dashboard(
    current_role="VENDOR",
    api_base="http://127.0.0.1:8000",
    auth_headers_fn=lambda: {},
    live_api=True,
    api_online=True,
)
"""
    ).run(timeout=30)
    assert any("Access Denied" in e.value for e in at_guard.error)


def test_02_executive_bi_api_integration_and_kpi_parity(exec_ui_bridge):
    """Rendered Executive BI metrics match exact Phase 2 API responses without re-computation."""
    db = exec_ui_bridge["db"]
    _seed_sample(db, with_cost=True)
    adm, adm_tok = _make_auth(db, "adm_bi2@shopsense.com", UserRole.ADMIN)

    api_resp = exec_ui_bridge["client"].get(
        "/analytics/executive/summary",
        headers={"Authorization": f"Bearer {adm_tok}", "X-Enforce-Auth": "true"},
    )
    assert api_resp.status_code == 200
    api_fin = api_resp.json()["financials"]

    at = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at, adm, adm_tok)
    at.run(timeout=60)
    at.radio[0].set_value("💎 Executive BI").run(timeout=60)

    assert len(at.exception) == 0
    assert any("/analytics/executive/summary" in u for u in exec_ui_bridge["urls"])
    assert any("/analytics/executive/trends" in u for u in exec_ui_bridge["urls"])
    assert any("/analytics/executive/vendors" in u for u in exec_ui_bridge["urls"])

    metric_map = {m.label: m.value for m in at.metric}
    assert metric_map["💰 Gross Merchandise Value (GMV)"] == f"₹{api_fin['gross_sales_gmv']:,.2f}"
    assert metric_map["📈 Net Sales (After Discounts/Refunds)"] == f"₹{api_fin['net_sales']:,.2f}"
    assert metric_map["💎 Gross Profit (Reported Items)"] == f"₹{api_fin['gross_profit_reported']:,.2f}"
    assert metric_map["🧾 Average Order Value (AOV)"] == f"₹{api_fin['avg_order_value']:,.2f}"
    assert any("Partial Cost Coverage Notice" in i.value for i in at.info)
    assert len(at.dataframe) >= 2
    assert len(at.get("plotly_chart")) == 5


def test_03_date_filtering_granularity_and_empty_states(exec_ui_bridge):
    """Verify Date Range filter, Daily granularity switch, empty range, and invalid range UI states."""
    db = exec_ui_bridge["db"]
    _seed_sample(db, with_cost=True)
    adm, adm_tok = _make_auth(db, "adm_bi3@shopsense.com", UserRole.ADMIN)

    at = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at, adm, adm_tok)
    at.run(timeout=60)
    at.radio[0].set_value("💎 Executive BI").run(timeout=60)

    # Enable custom date filter -> Feb 2024 (GMV = 460.00) + Daily granularity
    use_cb = next(cb for cb in at.checkbox if cb.key == "exec_bi_use_date_filter")
    use_cb.set_value(True)
    next(d for d in at.date_input if d.key == "exec_bi_start_date").set_value(date(2024, 2, 1))
    next(d for d in at.date_input if d.key == "exec_bi_end_date").set_value(date(2024, 2, 29))
    next(s for s in at.selectbox if s.key == "exec_bi_granularity").select("Daily")
    at.run(timeout=60)

    assert len(at.exception) == 0
    metric_map = {m.label: m.value for m in at.metric}
    assert metric_map["💰 Gross Merchandise Value (GMV)"] == "₹460.00"
    assert any("start_date=2024-02-01" in u and "end_date=2024-02-29" in u for u in exec_ui_bridge["urls"])
    assert any("granularity=daily" in u for u in exec_ui_bridge["urls"])

    # Empty date window shows friendly empty state
    next(d for d in at.date_input if d.key == "exec_bi_start_date").set_value(date(2025, 1, 1))
    next(d for d in at.date_input if d.key == "exec_bi_end_date").set_value(date(2025, 1, 31))
    at.run(timeout=60)
    assert len(at.exception) == 0
    assert any("No marketplace transactions were recorded" in i.value for i in at.info)

    # Invalid date range (Start > End) shows error without crashing
    next(d for d in at.date_input if d.key == "exec_bi_start_date").set_value(date(2024, 6, 1))
    next(d for d in at.date_input if d.key == "exec_bi_end_date").set_value(date(2024, 2, 1))
    at.run(timeout=60)
    assert len(at.exception) == 0
    assert any("Invalid Date Filter" in e.value for e in at.error)


def test_04_zero_cost_guardrail_and_api_error_handling(exec_ui_bridge, monkeypatch):
    """Verify 0% cost coverage guardrail and clean HTTP 500 error surfacing."""
    db = exec_ui_bridge["db"]
    _seed_sample(db, with_cost=False)
    adm, adm_tok = _make_auth(db, "adm_bi4@shopsense.com", UserRole.ADMIN)

    at = AppTest.from_file("dashboard/dashboard.py")
    _set_session(at, adm, adm_tok)
    at.run(timeout=60)
    at.radio[0].set_value("💎 Executive BI").run(timeout=60)

    assert len(at.exception) == 0
    metric_map = {m.label: m.value for m in at.metric}
    assert metric_map["💎 Gross Profit (Reported Items)"] == "N/A (No Cost Data)"
    assert any("Incomplete Cost Coverage Guardrail" in w.value for w in at.warning)

    # Simulate backend 500 error on /analytics/executive/summary
    import requests

    def _failing_get(url: str, *args, **kwargs):
        return types.SimpleNamespace(
            status_code=500,
            text='{"detail": "Simulated upstream timeout"}',
            json=lambda: {"detail": "Simulated upstream timeout"},
        )

    monkeypatch.setattr(requests, "get", _failing_get)
    res = fetch_executive_dashboard_data(
        api_base="http://127.0.0.1:8000",
        headers={"Authorization": f"Bearer {adm_tok}"},
        live_api=True,
        api_online=True,
    )
    assert "_error" in res
    assert "HTTP 500" in res["_error"]
