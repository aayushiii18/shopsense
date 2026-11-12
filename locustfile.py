"""
locustfile.py — Locust Performance Load Testing for StockPilot Analytics Endpoints.

Targets tested:
  - GET /analytics/revenue
  - GET /analytics/vendor-performance
  - GET /analytics/customers
  - GET /analytics/revenue/growth
  - GET /analytics/revenue/benchmarking
  - GET /forecast/{month}
  - GET /recommend/{customer_id}

Execution instructions:
  Headless mode (command-line):
    locust -f locustfile.py --headless -u 15 -r 5 --run-time 20s --host http://127.0.0.1:8000

  Interactive Web UI:
    locust -f locustfile.py --host http://127.0.0.1:8000
    Open browser at: http://localhost:8089
"""

import random
from locust import HttpUser, task, between


class StockPilotAnalyticsUser(HttpUser):
    """
    Simulates retail management users and external API consumers accessing
    high-frequency analytical and ML inference endpoints.
    """
    wait_time = between(0.05, 0.2)

    @task(3)
    def test_total_revenue(self):
        """Measures total revenue (GMV) aggregation response time."""
        with self.client.get("/analytics/revenue", name="/analytics/revenue", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(2)
    def test_vendor_performance(self):
        """Measures vendor-wise revenue aggregation response time."""
        with self.client.get("/analytics/vendor-performance", name="/analytics/vendor-performance", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(2)
    def test_customer_metrics(self):
        """Measures customer count and average lifetime spend response time."""
        with self.client.get("/analytics/customers", name="/analytics/customers", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(2)
    def test_revenue_growth(self):
        """Measures Month-over-Month revenue growth calculation response time."""
        with self.client.get("/analytics/revenue/growth", name="/analytics/revenue/growth", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(2)
    def test_vendor_benchmarking(self):
        """Measures vendor market share benchmarking response time."""
        with self.client.get("/analytics/revenue/benchmarking", name="/analytics/revenue/benchmarking", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(3)
    def test_inventory_forecast(self):
        """Measures monthly inventory forecasting model inference response time."""
        month = random.randint(1, 12)
        with self.client.get(f"/forecast/{month}", name="/forecast/{month}", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")

    @task(3)
    def test_personalized_recommendation(self):
        """Measures personalized product recommendation response time."""
        customer_id = random.randint(1, 60)
        with self.client.get(f"/recommend/{customer_id}", name="/recommend/{customer_id}", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status code {resp.status_code}")
