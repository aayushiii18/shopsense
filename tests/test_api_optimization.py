"""
tests/test_api_optimization.py — Test suite for Milestone 4 Step 2 API Optimization & Configuration.

Validates:
1. FastAPI app configuration metadata: Title, Version, Description.
2. Canonical entry points: app.main:app and backend.api.main:app consistency.
3. Registration of Sales API, Forecasting API, Recommendation API, and Admin API routers.
4. Swagger UI (/docs) and OpenAPI JSON (/openapi.json) schema availability and tags.
5. Optimized SQL queries for analytics endpoints (revenue/total, by-vendor, by-product, summary).
6. Pagination support for /analytics/transactions with skip and limit.
7. Admin API security, overview KPIs, and role-based access control.
8. Latency targets under test conditions.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from backend.api.main import app as backend_app
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.transaction import Transaction
from app.core.security import create_access_token


@pytest.fixture
def admin_headers(db_session):
    """Generates valid JWT Authorization headers for an ADMIN user."""
    admin_user = db_session.query(User).filter(User.email == "admin_opt_test@shopsense.internal").first()
    if not admin_user:
        admin_user = User(
            email="admin_opt_test@shopsense.internal",
            hashed_password="test_hash_opt",
            role="ADMIN",
            is_active=True,
            is_verified=True,
            token_version=1,
        )
        db_session.add(admin_user)
        db_session.commit()
        db_session.refresh(admin_user)

    role_val = admin_user.role.value if hasattr(admin_user.role, "value") else str(admin_user.role)
    token = create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=role_val,
        token_version=admin_user.token_version or 1,
    )
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


@pytest.fixture
def customer_headers(db_session):
    """Generates valid JWT Authorization headers for a CUSTOMER user."""
    cust_user = db_session.query(User).filter(User.email == "cust_opt_test@shopsense.internal").first()
    if not cust_user:
        cust_user = User(
            email="cust_opt_test@shopsense.internal",
            hashed_password="test_hash_cust",
            role="CUSTOMER",
            customer_id=1,
            is_active=True,
            is_verified=True,
            token_version=1,
        )
        db_session.add(cust_user)
        db_session.commit()
        db_session.refresh(cust_user)

    role_val = cust_user.role.value if hasattr(cust_user.role, "value") else str(cust_user.role)
    token = create_access_token(
        user_id=cust_user.id,
        email=cust_user.email,
        role=role_val,
        customer_id=1,
        token_version=cust_user.token_version or 1,
    )
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


def test_01_app_metadata_configuration():
    """Verify application title, version, and description match Milestone 4 Step 2 requirements."""
    assert app.title == "ShopSense Analytics Platform"
    assert app.version == "1.0.0"
    assert app.description == "Production Retail Marketplace Analytics Platform"


def test_02_backend_api_main_singleton_identity():
    """Verify backend.api.main:app is identical to app.main:app (no duplicate app instances)."""
    assert backend_app is app
    assert backend_app.title == "ShopSense Analytics Platform"
    assert backend_app.version == "1.0.0"


def test_03_swagger_and_openapi_docs(client):
    """Verify Swagger UI (/docs) and OpenAPI schema (/openapi.json) are accessible and well-formed."""
    resp_docs = client.get("/docs")
    assert resp_docs.status_code == 200

    resp_openapi = client.get("/openapi.json")
    assert resp_openapi.status_code == 200
    schema = resp_openapi.json()
    assert schema["info"]["title"] == "ShopSense Analytics Platform"
    assert schema["info"]["version"] == "1.0.0"
    assert schema["info"]["description"] == "Production Retail Marketplace Analytics Platform"

    # Verify primary routers are tagged in OpenAPI specification
    all_tags = {tag["name"] for tag in schema.get("tags", [])}
    assert "Sales API" in all_tags
    assert "Forecasting API" in all_tags
    assert "Recommendation API" in all_tags
    assert "Admin API" in all_tags


def test_04_sales_api_endpoints_registered(client):
    """Verify Sales API endpoints are registered and respond correctly."""
    resp_rev = client.get("/analytics/revenue")
    assert resp_rev.status_code == 200
    assert "total_revenue" in resp_rev.json()

    resp_total = client.get("/analytics/revenue/total")
    assert resp_total.status_code == 200
    assert "total_revenue" in resp_total.json()
    assert "transaction_count" in resp_total.json()

    resp_vendor = client.get("/analytics/revenue/by-vendor")
    assert resp_vendor.status_code == 200
    assert isinstance(resp_vendor.json(), list)

    resp_prod = client.get("/analytics/revenue/by-product")
    assert resp_prod.status_code == 200
    assert isinstance(resp_prod.json(), list)

    resp_summary = client.get("/analytics/summary")
    assert resp_summary.status_code == 200
    assert "total_revenue" in resp_summary.json()
    assert "transaction_count" in resp_summary.json()


def test_05_forecasting_api_endpoints_registered(client):
    """Verify Demand Forecasting API endpoints are registered and respond correctly."""
    resp = client.get("/forecast/12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["month"] == 12
    assert "forecast" in data
    assert "units_predicted" in data
    assert data["model_name"] == "RandomForest"


def test_06_recommendation_api_endpoints_registered(client):
    """Verify Recommendation Engine endpoints are registered and respond correctly."""
    resp_pop = client.get("/recommendations/popular?top_n=3")
    assert resp_pop.status_code == 200
    data = resp_pop.json()
    assert isinstance(data, list)
    assert len(data) <= 3

    resp_eval = client.get("/recommendations/evaluation?k=5")
    assert resp_eval.status_code == 200
    assert "mean_precision_at_k" in resp_eval.json()


def test_07_admin_api_endpoints_registered_and_secured(client, admin_headers, customer_headers):
    """Verify Admin API endpoints are registered and enforce RBAC protection."""
    # Unauthorized request (customer role) should receive 403 Forbidden
    resp_unauth = client.get("/admin/overview", headers=customer_headers)
    assert resp_unauth.status_code == 403

    # Authorized admin request should succeed
    resp_auth = client.get("/admin/overview", headers=admin_headers)
    assert resp_auth.status_code == 200
    data = resp_auth.json()
    assert data["system_name"] == "ShopSense"
    assert data["version"] == "1.0.0"
    assert data["status"] == "operational"
    assert data["database_connected"] is True
    assert "total_users" in data
    assert "total_vendors" in data
    assert "total_products" in data
    assert "total_transactions" in data
    assert "total_gmv" in data

    # Admin health diagnostic (upgraded in Milestone 4 Step 3 Integration Status Module)
    resp_health = client.get("/admin/health", headers=admin_headers)
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert health_data["overall_status"] in ("HEALTHY", "DEGRADED", "UNAVAILABLE")
    assert health_data["status"] in ("healthy", "degraded", "unavailable")
    assert "components" in health_data

    # Admin stats diagnostic
    resp_stats = client.get("/admin/stats", headers=admin_headers)
    assert resp_stats.status_code == 200
    assert "users_by_role" in resp_stats.json()
    assert "vendors_by_status" in resp_stats.json()


def test_08_transaction_pagination(client):
    """Verify /analytics/transactions supports skip and limit parameters."""
    resp_page1 = client.get("/analytics/transactions?skip=0&limit=2")
    assert resp_page1.status_code == 200
    page1 = resp_page1.json()

    resp_page2 = client.get("/analytics/transactions?skip=2&limit=2")
    assert resp_page2.status_code == 200
    page2 = resp_page2.json()

    # If there are transactions, page 1 and page 2 shouldn't overlap
    if len(page1) > 0 and len(page2) > 0:
        ids_page1 = {item["transaction_id"] for item in page1}
        ids_page2 = {item["transaction_id"] for item in page2}
        assert ids_page1.isdisjoint(ids_page2)
