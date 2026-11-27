"""
tests/test_phase4_performance.py — Automated Regression Suite for Milestone 4 Phase 4.

Verifies:
  1. ORM secondary & composite indexes on `transactions` and `refunds`.
  2. SQLite bind-parameter overflow elimination (>1,200 transactions on `/analytics/revenue/profit-margins`).
  3. Rewritten SQL aggregations (`growth`, `vendors/payouts`, `customers/summary`, `executive/*`)
     preserve exact mathematical parity, bounded SQL query counts (zero N+1), and cost-coverage rules.
  4. Daily-to-monthly trend rollup parity and date-range window accuracy.
  5. RBAC & Vendor tenant isolation remain enforced on optimized endpoints.
  6. Phase 4 benchmark utilities & Markdown report generator work cleanly in isolated paths.
"""

from datetime import datetime, timedelta
import json
from sqlalchemy import inspect, event

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.services import executive_service, revenue_service
from benchmarks import phase4_performance_validation as p4


def _auth_headers(db_session, email: str, role: str, vendor_id=None, customer_id=None) -> dict:
    user = db_session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password("Phase4Test!23"),
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


def _count_queries(engine, fn):
    """Execute `fn()` while counting SQL statements emitted on `engine`."""
    queries = []

    def _listener(_conn, _cursor, statement, _parameters, _context, _executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return len(queries), result


def _seed_scale_dataset(db_session, n_tx: int = 1250, partial_cost: bool = True):
    """
    Seed multi-vendor marketplace dataset exceeding SQLite's 999 SQL-variable limit
    to validate O(1)-query SQL aggregations and accounting parity.
    """
    vendors = []
    for idx, rate in enumerate((0.10, 0.12, 0.15, 0.08, 0.12), start=1):
        vendors.append(
            Vendor(
                name=f"Scale Vendor {idx}",
                email=f"scale_v{idx}@shopsense.test",
                phone=f"910000000{idx}",
                status="PENDING_APPROVAL" if idx == 5 else "ACTIVE",
                commission_tier="TIER_PREFERRED" if idx == 1 else "TIER_STANDARD",
                commission_rate=rate,
            )
        )
    db_session.add_all(vendors)
    db_session.flush()

    products = []
    for p_idx in range(10):
        v = vendors[p_idx % 4]  # vendors 1..4 sell products; vendor 5 pending
        has_cost = (not partial_cost) or (p_idx % 2 == 0)
        products.append(
            Product(
                name=f"Scale Product {p_idx + 1}",
                price=100.0 + (p_idx * 25.0),
                cost_price=(55.0 + p_idx * 10.0) if has_cost else None,
                category="Electronics" if p_idx < 5 else "Home",
                vendor_id=v.id,
            )
        )
    db_session.add_all(products)
    db_session.flush()

    db_session.add_all(
        [
            Inventory(
                product_id=prod.id,
                current_stock=50 if idx % 3 == 0 else (5 if idx % 3 == 1 else 0),
                reorder_level=10,
            )
            for idx, prod in enumerate(products)
        ]
    )

    customers = [
        Customer(name=f"Buyer {c}", email=f"buyer{c}@shopsense.test", city="Mumbai")
        for c in range(1, 26)
    ]
    db_session.add_all(customers)
    db_session.flush()

    base_dt = datetime(2025, 1, 5, 10, 0, 0)
    txs = []
    for i in range(n_tx):
        prod = products[i % len(products)]
        cust = customers[i % 20]  # 20 purchasing customers, 5 zero-order registered customers
        qty = (i % 3) + 1
        disc = 5.0 if i % 4 == 0 else 0.0
        gross = round(prod.price * qty, 2)
        tx_dt = base_dt + timedelta(days=(i % 120), hours=(i % 12))
        txs.append(
            Transaction(
                product_id=prod.id,
                vendor_id=prod.vendor_id,
                customer_id=cust.customer_id,
                quantity=qty,
                unit_price=prod.price,
                discount_amount=disc,
                amount=gross,
                transaction_date=tx_dt,
            )
        )
    db_session.add_all(txs)
    db_session.flush()

    refunds = []
    for r_i in range(0, min(n_tx, 100), 2):
        tx = txs[r_i]
        refunds.append(
            Refund(
                transaction_id=tx.transaction_id,
                idempotency_key=f"p4_ref_{r_i}",
                amount=round(min(tx.amount, 30.0), 2),
                reason="Test refund",
                status="COMPLETED" if r_i < 80 else "REJECTED",
            )
        )
    db_session.add_all(refunds)
    db_session.commit()
    return vendors, products, customers, txs


def test_orm_indexes_declared_and_created(db_session):
    """Critical filter and refund join columns expose SQLAlchemy indexes in schema metadata."""
    tx_indexes = {idx.name: [c.name for c in idx.columns] for idx in Transaction.__table__.indexes}
    assert tx_indexes.get("ix_transactions_transaction_date") == ["transaction_date"]
    assert tx_indexes.get("ix_transactions_vendor_date") == ["vendor_id", "transaction_date"]
    assert tx_indexes.get("ix_transactions_product_date") == ["product_id", "transaction_date"]
    assert tx_indexes.get("ix_transactions_customer_date") == ["customer_id", "transaction_date"]

    ref_indexes = {idx.name: [c.name for c in idx.columns] for idx in Refund.__table__.indexes}
    assert ref_indexes.get("ix_refunds_status_tx") == ["status", "transaction_id"]

    insp = inspect(db_session.get_bind())
    db_tx_idx_names = {i["name"] for i in insp.get_indexes("transactions")}
    db_ref_idx_names = {i["name"] for i in insp.get_indexes("refunds")}
    assert {
        "ix_transactions_transaction_date",
        "ix_transactions_vendor_date",
        "ix_transactions_product_date",
        "ix_transactions_customer_date",
    }.issubset(db_tx_idx_names)
    assert "ix_refunds_status_tx" in db_ref_idx_names


def test_profit_margins_handles_over_1200_transactions_without_sql_var_overflow(client, db_session):
    """Rewritten SQL CASE profit-margins must succeed above SQLite's 999 variable limit."""
    revenue_service._REV_CACHE.clear()
    vendors, _products, _customers, txs = _seed_scale_dataset(db_session, n_tx=1250, partial_cost=False)
    admin_hdr = _auth_headers(db_session, "admin_p4@shopsense.test", "ADMIN")

    engine = db_session.get_bind()
    sql_count, resp = _count_queries(
        engine,
        lambda: client.get("/analytics/revenue/profit-margins", headers=admin_hdr),
    )
    assert resp.status_code == 200
    assert sql_count <= 5  # auth + 2 SQL aggregations (no N+1, no large IN clause)

    data = resp.json()
    expected_gmv = round(sum(t.amount for t in txs), 2)
    expected_disc = round(sum(t.discount_amount for t in txs), 2)
    assert data["gross_sales_gmv"] == expected_gmv
    assert data["discounts_total"] == expected_disc
    assert data["refunds_total"] == 1200.0  # 40 completed refunds * 30.0 (idx < 80 step 2)
    assert data["net_sales"] == round(expected_gmv - expected_disc - data["refunds_total"], 2)
    assert data["cogs_coverage_pct"] == 100.0

    # Also verify vendor payouts uses constant SQL query count (eliminated N+1 per vendor)
    revenue_service._REV_CACHE.clear()
    payout_sql_count, payout_resp = _count_queries(
        engine,
        lambda: client.get("/analytics/vendors/payouts", headers=admin_hdr),
    )
    assert payout_resp.status_code == 200
    assert payout_sql_count <= 6
    payout_vendors = payout_resp.json()["settlements"]
    assert len(payout_vendors) == len(vendors)


def test_optimized_services_parity_and_bounded_sql_counts(client, db_session):
    """Optimized executive, growth, and customer SQL paths match exact accounting definitions."""
    revenue_service._REV_CACHE.clear()
    vendors, _products, _customers, _txs = _seed_scale_dataset(db_session, n_tx=400, partial_cost=True)
    admin_hdr = _auth_headers(db_session, "admin_parity@shopsense.test", "ADMIN")
    engine = db_session.get_bind()

    # 1. Executive Summary query count reduced & matches standalone _compute_financial_kpis
    summary_sql, summary_resp = _count_queries(
        engine,
        lambda: client.get("/analytics/executive/summary", headers=admin_hdr),
    )
    assert summary_resp.status_code == 200
    assert summary_sql <= 14
    summary = summary_resp.json()

    direct_fin = executive_service._compute_financial_kpis(db_session, None, None, vendor_id=None)
    assert summary["financials"] == direct_fin
    assert summary["financials"]["is_partial_profit"] is True
    assert summary["vendors"]["total_vendors"] == 5
    assert summary["vendors"]["active_vendors"] == 4
    assert summary["vendors"]["pending_approval_vendors"] == 1
    assert summary["vendors"]["vendors_with_sales"] == 4
    assert summary["customers"]["total_registered_customers"] == 25
    assert summary["customers"]["purchasing_customers"] == 20
    assert summary["customers"]["repeat_customers"] == 20

    # 2. Monthly growth endpoint matches executive trends monthly series
    revenue_service._REV_CACHE.clear()
    growth_resp = client.get("/analytics/revenue/growth", headers=admin_hdr)
    assert growth_resp.status_code == 200
    growth_months = growth_resp.json()["monthly_growth"]
    exec_months = summary["sales_growth"]["monthly_trends"]
    assert len(growth_months) == len(exec_months)
    for gm, em in zip(growth_months, exec_months):
        assert gm["year_month"] == em["period"]
        assert abs(gm["revenue"] - em["gmv"]) <= 0.01

    # 3. Daily trends rollup period_comparison matches monthly trends period_comparison
    daily_sql, daily_resp = _count_queries(
        engine,
        lambda: client.get("/analytics/executive/trends?granularity=daily", headers=admin_hdr),
    )
    assert daily_resp.status_code == 200
    assert daily_sql <= 8
    assert daily_resp.json()["period_comparison"] == summary["period_comparison"]

    # 4. Executive vendors drilldown reuses vendor aggregates cleanly without redundant GMV scan
    vp_sql, vp_resp = _count_queries(
        engine,
        lambda: client.get("/analytics/executive/vendors?limit=10", headers=admin_hdr),
    )
    assert vp_resp.status_code == 200
    assert vp_sql <= 7
    assert vp_resp.json()["total_gmv"] == summary["financials"]["gross_sales_gmv"]
    assert vp_resp.json()["total_net_sales"] == summary["financials"]["net_sales"]

    # 5. Customer summary uses grouped SQL subquery with bounded query count
    cust_sql, cust_resp = _count_queries(
        engine,
        lambda: client.get("/analytics/customers/summary", headers=admin_hdr),
    )
    assert cust_resp.status_code == 200
    assert cust_sql <= 6
    cdata = cust_resp.json()
    assert cdata["total_customers"] == 25
    assert cdata["repeat_customers"] == 20
    assert cdata["active_customers_90d"] <= 20


def test_optimized_executive_rbac_and_vendor_tenant_isolation(client, db_session):
    """Optimizations preserve strict ADMIN checks and single-vendor tenant boundaries."""
    vendors, _products, customers, _txs = _seed_scale_dataset(db_session, n_tx=120, partial_cost=False)
    v1_hdr = _auth_headers(db_session, "v1_p4@shopsense.test", "VENDOR", vendor_id=vendors[0].id)
    cust_hdr = _auth_headers(db_session, "c1_p4@shopsense.test", "CUSTOMER", customer_id=customers[0].customer_id)

    for forbidden_url in (
        "/analytics/executive/summary",
        "/analytics/executive/trends",
        "/analytics/executive/vendors",
    ):
        assert client.get(forbidden_url, headers=v1_hdr).status_code == 403
        assert client.get(forbidden_url, headers=cust_hdr).status_code == 403

    v_resp = client.get("/analytics/executive/vendor-summary", headers=v1_hdr)
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["vendor_id"] == vendors[0].id
    assert all(p["vendor_id"] == vendors[0].id for p in v_data["products"]["top_products"])
    assert v_data["financials"] == executive_service._compute_financial_kpis(
        db_session, None, None, vendor_id=vendors[0].id
    )


def test_phase4_report_generator_produces_markdown_without_touching_live_data(tmp_path):
    """Report generator builds structured Markdown cleanly from baseline/optimized telemetry files."""
    base_json = tmp_path / "base.json"
    opt_json = tmp_path / "opt.json"
    report_md = tmp_path / "phase4_report.md"

    common_acc = {
        "total_transactions_match": True,
        "gmv_match": True,
        "discounts_match": True,
        "refunds_match": True,
        "net_sales_match": True,
        "gross_profit_match": True,
        "aov_match": True,
        "api_financials": {
            "total_transactions": 100000,
            "gross_sales_gmv": 500000.0,
            "discounts_total": 10000.0,
            "refunds_total": 5000.0,
            "net_sales": 485000.0,
            "gross_profit_reported": 120000.0,
            "avg_order_value": 5.0,
        },
        "ground_truth": {
            "total_transactions": 100000,
            "expected_gmv": 500000.0,
            "expected_discounts": 10000.0,
            "expected_refunds": 5000.0,
            "expected_net_sales": 485000.0,
            "expected_gross_profit": 120000.0,
            "expected_aov": 5.0,
        },
    }

    base_payload = {
        "timestamp_utc": "2026-11-27 10:00:00 UTC",
        "environment": {"os": "TestOS", "python": "3.10", "cpu_cores": 8, "ram_total_gb": 16, "ram_available_gb": 8},
        "live_localhost_postgresql": {
            "endpoints": [{"endpoint": "GET /analytics/executive/summary", "mean_ms": 25.0, "p95_ms": 30.0}],
            "concurrent_load": {"total_requests": 500, "failures": 0, "failure_rate_pct": 0.0, "throughput_rps": 50.0, "mean_ms": 100.0, "p50_ms": 95.0, "p95_ms": 180.0, "p99_ms": 250.0},
        },
        "isolated_100k_integrated": {
            "db_file_size_mb": 10.0,
            "workloads": [
                {"endpoint": "GET /analytics/revenue/profit-margins", "status_code": 500, "sql_queries": 1, "tracemalloc_peak_mb": 5.0},
                {"endpoint": "GET /analytics/revenue/growth", "status_code": 200, "mean_ms": 10000.0, "p95_ms": 12000.0, "sql_queries": 1, "tracemalloc_peak_mb": 60.0},
            ],
            "accuracy_checks": common_acc,
        },
    }
    opt_payload = {
        "timestamp_utc": "2026-11-27 11:00:00 UTC",
        "environment": base_payload["environment"],
        "live_localhost_postgresql": {
            "endpoints": [{"endpoint": "GET /analytics/executive/summary", "mean_ms": 18.0, "p95_ms": 22.0}],
            "concurrent_load": {"total_requests": 650, "failures": 0, "failure_rate_pct": 0.0, "throughput_rps": 65.0, "mean_ms": 75.0, "p50_ms": 70.0, "p95_ms": 130.0, "p99_ms": 190.0},
        },
        "isolated_100k_integrated": {
            "db_file_size_mb": 18.0,
            "workloads": [
                {"endpoint": "GET /analytics/revenue/profit-margins", "status_code": 200, "mean_ms": 120.0, "p95_ms": 135.0, "sql_queries": 2, "tracemalloc_peak_mb": 0.1},
                {"endpoint": "GET /analytics/revenue/growth", "status_code": 200, "mean_ms": 95.0, "p95_ms": 110.0, "sql_queries": 1, "tracemalloc_peak_mb": 0.1},
            ],
            "accuracy_checks": common_acc,
        },
    }

    base_json.write_text(json.dumps(base_payload), encoding="utf-8")
    opt_json.write_text(json.dumps(opt_payload), encoding="utf-8")

    out = p4.generate_phase4_report(str(base_json), str(opt_json), str(report_md))
    text = report_md.read_text(encoding="utf-8")
    assert out == str(report_md)
    assert "Fixed Crash (500 -> 200)" in text
    assert "105.26x faster" in text
    assert "Methodological Guardrail" in text
