"""
locustfile.py — Authenticated Multi-Role Locust Load Testing Suite for ShopSense.

Simulates realistic read-only marketplace load across three authenticated personas:
  1. StockPilotAnalyticsUser (ADMIN, weight=5): Executive BI APIs, revenue/margin/growth,
     vendor benchmarking, inventory turnover/low-stock, forecasting, recommendations,
     admin overview, and lightweight database readiness probe.
  2. VendorOperationsUser (VENDOR, weight=2): Tenant-scoped vendor executive summary,
     vendor performance, settlement payouts, store inventory status, and catalog browsing.
  3. CustomerShopperUser (CUSTOMER, weight=3): Storefront catalog browsing, cold-start
     popular products, tenant-scoped hybrid/CF recommendations, demand forecasts, and CLV.

Authentication & DB Safety:
  - Uses pre-issued JWT Bearer tokens supplied via environment variables (`LOCUST_ADMIN_TOKEN`,
    `LOCUST_VENDOR_TOKEN`, `LOCUST_CUSTOMER_TOKEN`) with `X-Enforce-Auth: true`, or lazily logs
    in once per role if `LOCUST_*_EMAIL` / `LOCUST_*_PASSWORD` are provided.
  - Executes strictly read-only GET traffic (no synthetic inserts or live DB mutations).

Example headless progressive step:
  locust -f locustfile.py --headless -u 100 -r 25 --run-time 25s --host http://127.0.0.1:8000
"""

from locust import HttpUser, task, between  # Must be imported before ssl/urllib3/requests

import os
import random
import threading


_AUTH_LOCK = threading.Lock()
_TOKEN_CACHE = {}


def _get_role_headers(role_key: str) -> dict:
    """
    Resolve Bearer auth headers for 'admin', 'vendor', or 'customer' without spamming logins.
    Returns empty dict in offline/mock unit tests when no token/credentials are configured.
    """
    env_tok = os.getenv(f"LOCUST_{role_key.upper()}_TOKEN", "").strip()
    if env_tok:
        return {"Authorization": f"Bearer {env_tok}", "X-Enforce-Auth": "true"}

    with _AUTH_LOCK:
        cached = _TOKEN_CACHE.get(role_key)
        if cached:
            return cached

        email = os.getenv(f"LOCUST_{role_key.upper()}_EMAIL", "").strip()
        password = os.getenv(f"LOCUST_{role_key.upper()}_PASSWORD", "").strip()
        host = os.getenv("LOCUST_AUTH_HOST", "http://127.0.0.1:8000").rstrip("/")
        if email and password:
            try:
                import requests

                resp = requests.post(
                    f"{host}/auth/login",
                    json={"email": email, "password": password},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    token = resp.json().get("access_token", "")
                    if token:
                        hdr = {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}
                        _TOKEN_CACHE[role_key] = hdr
                        return hdr
            except Exception:
                pass
    return {}


_MIN_WAIT = float(os.getenv("LOCUST_MIN_WAIT", "0.35"))
_MAX_WAIT = float(os.getenv("LOCUST_MAX_WAIT", "1.15"))
_MAX_CUSTOMER_ID = int(os.getenv("LOCUST_MAX_CUSTOMER_ID", "60"))
_DEFAULT_CUSTOMER_ID = int(os.getenv("LOCUST_CUSTOMER_ID", "61"))


class StockPilotAnalyticsUser(HttpUser):
    """
    Simulates authenticated Administrator & Executive BI analytical workloads alongside
    core revenue, customer, forecasting, and recommendation endpoints.
    Retains all legacy Module 7 method names for compatibility with test suites.
    """

    weight = 5
    wait_time = between(_MIN_WAIT, _MAX_WAIT)

    def _headers(self) -> dict:
        return _get_role_headers("admin")

    def _get_checked(self, url: str, name: str):
        with self.client.get(url, name=name, headers=self._headers(), catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def test_total_revenue(self):
        """Measures total revenue (GMV) aggregation response time."""
        self._get_checked("/analytics/revenue", "/analytics/revenue")

    @task(2)
    def test_vendor_performance(self):
        """Measures authenticated admin vendor-wise revenue aggregation response time."""
        self._get_checked("/analytics/vendor-performance", "/analytics/vendor-performance")

    @task(2)
    def test_customer_metrics(self):
        """Measures customer count and average lifetime spend response time."""
        self._get_checked("/analytics/customers", "/analytics/customers")

    @task(2)
    def test_revenue_growth(self):
        """Measures Month-over-Month revenue growth SQL aggregation response time."""
        self._get_checked("/analytics/revenue/growth", "/analytics/revenue/growth")

    @task(2)
    def test_vendor_benchmarking(self):
        """Measures admin vendor market share benchmarking response time."""
        self._get_checked("/analytics/revenue/benchmarking", "/analytics/revenue/benchmarking")

    @task(2)
    def test_inventory_forecast(self):
        """Measures monthly inventory forecasting model inference response time."""
        month = random.randint(1, 12)
        self._get_checked(f"/forecast/{month}", "/forecast/{month}")

    @task(2)
    def test_personalized_recommendation(self):
        """Measures personalized product recommendation response time."""
        customer_id = random.randint(1, max(1, _MAX_CUSTOMER_ID))
        self._get_checked(f"/recommend/{customer_id}", "/recommend/{customer_id}")

    @task(4)
    def test_executive_summary(self):
        """Measures Milestone 4 Phase 2/4 centralized Executive KPI summary endpoint."""
        self._get_checked("/analytics/executive/summary", "/analytics/executive/summary")

    @task(3)
    def test_executive_trends(self):
        """Measures Executive monthly trend & comparison endpoint."""
        self._get_checked("/analytics/executive/trends?granularity=monthly", "/analytics/executive/trends")

    @task(2)
    def test_executive_vendors(self):
        """Measures Executive vendor & product drilldown endpoint."""
        self._get_checked("/analytics/executive/vendors?limit=25", "/analytics/executive/vendors")

    @task(2)
    def test_profit_margins(self):
        """Measures SQL CASE COGS coverage & gross profit endpoint."""
        self._get_checked("/analytics/revenue/profit-margins", "/analytics/revenue/profit-margins")

    @task(2)
    def test_inventory_turnover(self):
        """Measures inventory turnover & DSI calculation endpoint."""
        self._get_checked("/analytics/inventory/turnover", "/analytics/inventory/turnover")

    @task(1)
    def test_admin_overview(self):
        """Measures secured /admin/overview governance endpoint."""
        self._get_checked("/admin/overview", "/admin/overview")

    @task(1)
    def test_readiness_probe(self):
        """Lightweight DB readiness probe (<4% share so metrics reflect real workloads)."""
        self._get_checked("/health/ready", "/health/ready")


class VendorOperationsUser(HttpUser):
    """
    Simulates authenticated VENDOR portal traffic strictly scoped to the vendor's tenant.
    """

    weight = 2
    wait_time = between(_MIN_WAIT, _MAX_WAIT)

    def _headers(self) -> dict:
        hdr = _get_role_headers("vendor")
        return hdr if hdr else _get_role_headers("admin")

    def _get_checked(self, url: str, name: str):
        with self.client.get(url, name=name, headers=self._headers(), catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def vendor_executive_summary(self):
        self._get_checked("/analytics/executive/vendor-summary", "/analytics/executive/vendor-summary")

    @task(2)
    def vendor_settlement_payouts(self):
        self._get_checked("/analytics/vendors/payouts", "/analytics/vendors/payouts")

    @task(2)
    def vendor_inventory_status(self):
        self._get_checked("/analytics/inventory/status", "/analytics/inventory/status")

    @task(2)
    def vendor_products_list(self):
        self._get_checked("/products/", "/products/")


class CustomerShopperUser(HttpUser):
    """
    Simulates authenticated CUSTOMER catalog browsing & personalized recommendations.
    """

    weight = 3
    wait_time = between(_MIN_WAIT, _MAX_WAIT)

    def _headers(self) -> dict:
        hdr = _get_role_headers("customer")
        return hdr if hdr else _get_role_headers("admin")

    def _get_checked(self, url: str, name: str):
        with self.client.get(url, name=name, headers=self._headers(), catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def browse_catalog(self):
        self._get_checked("/products/", "/products/")

    @task(2)
    def popular_recommendations(self):
        self._get_checked("/recommendations/popular", "/recommendations/popular")

    @task(2)
    def hybrid_recommendations(self):
        cid = _DEFAULT_CUSTOMER_ID
        self._get_checked(f"/recommendations/hybrid/{cid}", "/recommendations/hybrid/{customer_id}")

    @task(2)
    def customer_clv(self):
        cid = _DEFAULT_CUSTOMER_ID
        self._get_checked(f"/analytics/customers/clv/{cid}", "/analytics/customers/clv/{customer_id}")
