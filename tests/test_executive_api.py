"""
tests/test_executive_api.py — Verification Suite for Milestone 4 Phase 2: Executive Analytics API.

Covers:
  1. Role-Based Access Control (ADMIN-only platform routes, VENDOR tenant-isolated route, CUSTOMER/unauth blocks).
  2. Centralized Executive KPI accuracy (GMV, discounts, refunds, net sales, COGS coverage, AOV, customers, vendors, products, inventory, growth).
  3. Incomplete & zero cost coverage handling without misleading profit calculations.
  4. Date-range filtering, invalid date rejection, empty database handling, and honest time-period comparisons.
  5. Trends endpoint (monthly & daily granularities) and Vendor/Product drilldown pagination.
  6. Consistency parity against `app.services.revenue_service` and OpenAPI/Swagger documentation checks.
"""

from datetime import datetime
import math
import pytest

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.services import consistency_validator, revenue_service


def _auth_headers(db_session, email: str, role: str, vendor_id=None, customer_id=None) -> dict:
    """Create or reuse a user and return authenticated headers with X-Enforce-Auth enabled."""
    user = db_session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password("ExecTest!234"),
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
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        vendor_id=user.vendor_id,
        customer_id=user.customer_id,
        token_version=user.token_version or 1,
    )
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


def _seed_executive_ecosystem(db_session, partial_cost: bool = True):
    """
    Seed deterministic marketplace ecosystem across 2 vendors, 3 products, 2 customers,
    inventory levels, multi-month transactions (Jan–Mar 2024), discounts, and a completed refund.
    """
    v1 = Vendor(
        name="Alpha Tech Supply",
        email="alpha@exec.test",
        phone="9000000001",
        status="ACTIVE",
        commission_tier="TIER_PREFERRED",
        commission_rate=0.10,
    )
    v2 = Vendor(
        name="Beta Home Goods",
        email="beta@exec.test",
        phone="9000000002",
        status="ACTIVE",
        commission_tier="TIER_STANDARD",
        commission_rate=0.12,
    )
    v3 = Vendor(
        name="Gamma Pending Store",
        email="gamma@exec.test",
        phone="9000000003",
        status="PENDING_APPROVAL",
        commission_tier="TIER_STANDARD",
        commission_rate=0.12,
    )
    db_session.add_all([v1, v2, v3])
    db_session.flush()

    p1 = Product(
        name="Pro Headset",
        price=100.0,
        cost_price=60.0 if partial_cost else None,
        category="Audio",
        vendor_id=v1.id,
    )
    p2 = Product(
        name="Uncosted Cable",
        price=50.0,
        cost_price=None,
        category="Accessories",
        vendor_id=v1.id,
    )
    p3 = Product(
        name="Ceramic Pitcher",
        price=80.0,
        cost_price=40.0 if partial_cost else None,
        category="Kitchen",
        vendor_id=v2.id,
    )
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    db_session.add_all([
        Inventory(product_id=p1.id, current_stock=25, reorder_level=10),
        Inventory(product_id=p2.id, current_stock=5, reorder_level=10),
        Inventory(product_id=p3.id, current_stock=0, reorder_level=8),
    ])

    c1 = Customer(name="Elena Vance", email="elena@exec.test", city="Mumbai", region="Maharashtra")
    c2 = Customer(name="Marcus Chen", email="marcus@exec.test", city="Bengaluru", region="Karnataka")
    db_session.add_all([c1, c2])
    db_session.flush()

    # Jan 2024: 2 transactions -> GMV = 200 + 100 = 300, disc = 10 -> Net = 290
    t1 = Transaction(
        product_id=p1.id, vendor_id=v1.id, customer_id=c1.customer_id,
        quantity=2, unit_price=100.0, amount=200.0, discount_amount=10.0,
        transaction_date=datetime(2024, 1, 10, 10, 0, 0),
    )
    t2 = Transaction(
        product_id=p2.id, vendor_id=v1.id, customer_id=c2.customer_id,
        quantity=2, unit_price=50.0, amount=100.0, discount_amount=0.0,
        transaction_date=datetime(2024, 1, 20, 14, 0, 0),
    )
    # Feb 2024: 2 transactions -> GMV = 300 + 160 = 460, disc = 20, refund = 40 -> Net = 400
    t3 = Transaction(
        product_id=p1.id, vendor_id=v1.id, customer_id=c1.customer_id,
        quantity=3, unit_price=100.0, amount=300.0, discount_amount=20.0,
        transaction_date=datetime(2024, 2, 5, 11, 0, 0),
    )
    t4 = Transaction(
        product_id=p3.id, vendor_id=v2.id, customer_id=c2.customer_id,
        quantity=2, unit_price=80.0, amount=160.0, discount_amount=0.0,
        transaction_date=datetime(2024, 2, 14, 16, 0, 0),
    )
    # Mar 2024: 1 transaction -> GMV = 240
    t5 = Transaction(
        product_id=p3.id, vendor_id=v2.id, customer_id=c1.customer_id,
        quantity=3, unit_price=80.0, amount=240.0, discount_amount=0.0,
        transaction_date=datetime(2024, 3, 12, 9, 30, 0),
    )
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.flush()

    # Completed refund on t3 (Feb): Rs. 40
    r1 = Refund(
        transaction_id=t3.transaction_id,
        idempotency_key="exec-ref-t3",
        amount=40.0,
        reason="Partial return",
        status="COMPLETED",
    )
    db_session.add(r1)
    db_session.commit()

    return {"vendors": (v1, v2, v3), "products": (p1, p2, p3), "customers": (c1, c2)}


def test_01_rbac_and_tenant_isolation(client, db_session):
    """Verify strict RBAC on platform executive endpoints and tenant isolation on /vendor-summary."""
    seeded = _seed_executive_ecosystem(db_session)
    v1, v2, _ = seeded["vendors"]
    c1, _ = seeded["customers"]

    adm_hdrs = _auth_headers(db_session, "adm@exec.test", UserRole.ADMIN)
    vend1_hdrs = _auth_headers(db_session, "vend1@exec.test", UserRole.VENDOR, vendor_id=v1.id)
    cust_hdrs = _auth_headers(db_session, "cust@exec.test", UserRole.CUSTOMER, customer_id=c1.customer_id)

    for path in (
        "/analytics/executive/summary",
        "/analytics/executive/trends",
        "/analytics/executive/vendors",
        "/analytics/executive/vendor-summary",
    ):
        resp_unauth = client.get(path, headers={"X-Enforce-Auth": "true"})
        assert resp_unauth.status_code == 401
        resp_cust = client.get(path, headers=cust_hdrs)
        assert resp_cust.status_code == 403

    # VENDOR blocked from platform-wide executive endpoints
    for platform_path in (
        "/analytics/executive/summary",
        "/analytics/executive/trends",
        "/analytics/executive/vendors",
    ):
        assert client.get(platform_path, headers=vend1_hdrs).status_code == 403

    # VENDOR can view own /vendor-summary but receives 403 for competitor vendor_id
    resp_own = client.get("/analytics/executive/vendor-summary", headers=vend1_hdrs)
    assert resp_own.status_code == 200
    assert resp_own.json()["vendor_id"] == v1.id
    assert resp_own.json()["financials"]["gross_sales_gmv"] == 600.0  # t1(200) + t2(100) + t3(300)
    assert resp_own.json()["customers"]["total_registered_customers"] is None

    resp_cross = client.get(f"/analytics/executive/vendor-summary?vendor_id={v2.id}", headers=vend1_hdrs)
    assert resp_cross.status_code == 403

    # ADMIN accesses global summary + any vendor_summary; missing vendor_id -> 422; unknown vendor -> 404
    assert client.get("/analytics/executive/summary", headers=adm_hdrs).status_code == 200
    assert client.get(f"/analytics/executive/vendor-summary?vendor_id={v2.id}", headers=adm_hdrs).status_code == 200
    assert client.get("/analytics/executive/vendor-summary", headers=adm_hdrs).status_code == 422
    assert client.get("/analytics/executive/vendor-summary?vendor_id=99999", headers=adm_hdrs).status_code == 404


def test_02_centralized_kpis_partial_cost_and_service_parity(client, db_session):
    """Verify exact financials, partial COGS coverage accounting, and consistency with existing services."""
    _seed_executive_ecosystem(db_session, partial_cost=True)
    adm_hdrs = _auth_headers(db_session, "adm2@exec.test", UserRole.ADMIN)

    resp = client.get("/analytics/executive/summary", headers=adm_hdrs)
    assert resp.status_code == 200
    data = resp.json()

    # Expected totals:
    # GMV = 200 + 100 + 300 + 160 + 240 = 1000.0
    # Discounts = 10 + 20 = 30.0
    # Refunds = 40.0 (on t3)
    # Net Sales = 1000 - 30 - 40 = 930.0
    # Covered items (p1, p3): t1(200-10), t3(300-20-40), t4(160), t5(240) -> covered_net = 830.0
    # Covered COGS: p1(60 * (2+3)) + p3(40 * (2+3)) = 300 + 200 = 500.0
    # Gross Profit Reported = 830 - 500 = 330.0 (excludes uncosted t2 without assuming 0 COGS)
    fin = data["financials"]
    assert fin["gross_sales_gmv"] == 1000.0
    assert fin["discounts_total"] == 30.0
    assert fin["refunds_total"] == 40.0
    assert fin["net_sales"] == 930.0
    assert fin["total_transactions"] == 5
    assert fin["total_units_sold"] == 12
    assert fin["avg_order_value"] == 200.0
    assert fin["has_cost_data"] is True
    assert fin["is_partial_profit"] is True
    assert fin["cost_coverage_complete"] is False
    assert fin["covered_net_sales"] == 830.0
    assert fin["covered_cogs"] == 500.0
    assert fin["gross_profit_reported"] == 330.0
    assert math.isclose(fin["cogs_coverage_pct"], round(830.0 / 930.0 * 100.0, 2), abs_tol=0.01)

    # Parity check against existing revenue_service & consistency_validator
    svc_margin = revenue_service.get_profit_margins(db_session)
    assert fin["gross_sales_gmv"] == svc_margin["gross_sales_gmv"]
    assert fin["net_sales"] == svc_margin["net_sales"]
    assert fin["gross_profit_reported"] == svc_margin["gross_profit_reported"]

    cons = consistency_validator.run_consistency_validation(db_session)
    assert cons["failed_checks"] == 0

    # Vendors & inventory KPIs
    vends = data["vendors"]
    assert vends["total_vendors"] == 3
    assert vends["active_vendors"] == 2
    assert vends["pending_approval_vendors"] == 1
    assert vends["top_vendor"]["vendor_name"] == "Alpha Tech Supply"
    assert vends["top_vendor"]["gross_revenue"] == 600.0

    inv = data["inventory_health"]
    assert inv["total_skus"] == 3
    assert inv["total_current_stock"] == 30
    assert inv["healthy_skus"] == 1
    assert inv["low_stock_skus"] == 1
    assert inv["critical_out_of_stock_skus"] == 1


def test_03_zero_cost_data_and_empty_db_handling(client, db_session):
    """Ensure 0% cost coverage and empty databases never emit misleading profits."""
    adm_hdrs = _auth_headers(db_session, "adm3@exec.test", UserRole.ADMIN)

    # 1. Empty database
    empty_resp = client.get("/analytics/executive/summary", headers=adm_hdrs)
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["financials"]["gross_sales_gmv"] == 0.0
    assert empty_data["financials"]["gross_profit_reported"] is None
    assert empty_data["financials"]["gross_margin_pct_reported"] is None
    assert empty_data["financials"]["has_cost_data"] is False
    assert empty_data["period_comparison"]["comparison_supported"] is False

    # 2. Populated transactions where NO product has cost_price
    _seed_executive_ecosystem(db_session, partial_cost=False)
    nocost_resp = client.get("/analytics/executive/summary", headers=adm_hdrs)
    assert nocost_resp.status_code == 200
    fin = nocost_resp.json()["financials"]
    assert fin["gross_sales_gmv"] == 1000.0
    assert fin["has_cost_data"] is False
    assert fin["cogs_coverage_pct"] == 0.0
    assert fin["gross_profit_reported"] is None
    assert fin["gross_margin_pct_reported"] is None
    assert "0.0% coverage" in fin["coverage_status"]


def test_04_date_filtering_and_period_comparisons(client, db_session):
    """Verify date filtering, validation, and window-over-window vs MoM period comparisons."""
    _seed_executive_ecosystem(db_session, partial_cost=True)
    adm_hdrs = _auth_headers(db_session, "adm4@exec.test", UserRole.ADMIN)

    # Custom range covering Feb 2024 (29 days: Feb 1..Feb 29 -> compares Jan 3..Jan 31 which has t1+t2)
    feb_resp = client.get(
        "/analytics/executive/summary?start_date=2024-02-01&end_date=2024-02-29",
        headers=adm_hdrs,
    )
    assert feb_resp.status_code == 200
    feb_data = feb_resp.json()
    assert feb_data["filters"]["is_filtered"] is True
    assert feb_data["financials"]["gross_sales_gmv"] == 460.0
    assert feb_data["financials"]["total_transactions"] == 2
    cmp = feb_data["period_comparison"]
    assert cmp["comparison_supported"] is True
    assert cmp["comparison_type"] == "window_over_previous_window"
    assert cmp["previous_gmv"] == 300.0
    assert math.isclose(cmp["gmv_change_pct"], round((460.0 - 300.0) / 300.0 * 100.0, 2), abs_tol=0.01)

    # First window (Jan) has no prior baseline -> comparison_supported False
    jan_resp = client.get(
        "/analytics/executive/summary?start_date=2024-01-01&end_date=2024-01-31",
        headers=adm_hdrs,
    )
    assert jan_resp.status_code == 200
    assert jan_resp.json()["period_comparison"]["comparison_supported"] is False

    # Unfiltered -> latest month (2024-03: GMV 240) vs prior month (2024-02: GMV 460)
    unfiltered = client.get("/analytics/executive/summary", headers=adm_hdrs).json()
    assert unfiltered["period_comparison"]["comparison_type"] == "latest_month_vs_previous_month"
    assert unfiltered["period_comparison"]["current_period_label"] == "2024-03"
    assert unfiltered["period_comparison"]["previous_period_label"] == "2024-02"

    # Invalid date range rejected cleanly
    bad_resp = client.get(
        "/analytics/executive/summary?start_date=2024-05-01&end_date=2024-01-01",
        headers=adm_hdrs,
    )
    assert bad_resp.status_code == 422


def test_05_trends_and_vendor_product_drilldown(client, db_session):
    """Verify /trends (monthly + daily) and /vendors pagination & share totals."""
    _seed_executive_ecosystem(db_session, partial_cost=True)
    adm_hdrs = _auth_headers(db_session, "adm5@exec.test", UserRole.ADMIN)

    m_resp = client.get("/analytics/executive/trends?granularity=monthly", headers=adm_hdrs)
    assert m_resp.status_code == 200
    m_series = m_resp.json()["series"]
    assert [p["period"] for p in m_series] == ["2024-01", "2024-02", "2024-03"]
    assert m_series[0]["growth_pct"] is None
    assert math.isclose(m_series[1]["growth_pct"], 53.33, abs_tol=0.02)

    d_resp = client.get("/analytics/executive/trends?granularity=daily", headers=adm_hdrs)
    assert d_resp.status_code == 200
    assert len(d_resp.json()["series"]) == 5

    assert client.get("/analytics/executive/trends?granularity=hourly", headers=adm_hdrs).status_code == 422

    v_resp = client.get("/analytics/executive/vendors?skip=0&limit=10", headers=adm_hdrs)
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["total_gmv"] == 1000.0
    assert len(v_data["vendors"]) == 2
    assert math.isclose(sum(v["market_share_pct"] for v in v_data["vendors"]), 100.0, abs_tol=0.1)


def test_06_openapi_documentation_and_security_contract(client):
    """Verify Executive Analytics API tag, endpoints, and security requirements appear in /openapi.json."""
    schema = client.get("/openapi.json").json()
    tags = {t["name"] for t in schema.get("tags", [])}
    assert "Executive Analytics API" in tags

    paths = schema.get("paths", {})
    for ep in (
        "/analytics/executive/summary",
        "/analytics/executive/trends",
        "/analytics/executive/vendors",
        "/analytics/executive/vendor-summary",
    ):
        assert ep in paths
        get_op = paths[ep]["get"]
        assert "Executive Analytics API" in get_op.get("tags", [])
        assert get_op.get("description")
        assert "security" in get_op
