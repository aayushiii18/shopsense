"""
tests/measure_api_performance.py — API Latency Benchmarking Script for Milestone 4 Step 2.

Measures actual, honest response times across representative endpoints from:
1. Sales API
2. Forecasting API
3. Recommendation API
4. Admin API

Target: <= 300 ms per endpoint.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import statistics
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.models.user import User, UserRole
from app.core.security import create_access_token


def get_or_create_admin_token(db) -> str:
    user = db.query(User).filter(User.email == "admin_perf@shopsense.internal").first()
    if not user:
        user = User(
            email="admin_perf@shopsense.internal",
            hashed_password="test_perf_admin_hash",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            token_version=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    return create_access_token(user_id=user.id, email=user.email, role=role_val, token_version=user.token_version or 1)


def benchmark():
    db = next(get_db())
    admin_token = get_or_create_admin_token(db)
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Enforce-Auth": "true"}

    client = TestClient(app)

    endpoints = [
        # Sales API
        ("Sales API", "GET /analytics/revenue", "/analytics/revenue", {}),
        ("Sales API", "GET /analytics/vendor-performance", "/analytics/vendor-performance", {}),
        ("Sales API", "GET /analytics/revenue/total", "/analytics/revenue/total", {}),
        ("Sales API", "GET /analytics/revenue/by-vendor", "/analytics/revenue/by-vendor", {}),
        ("Sales API", "GET /analytics/revenue/by-product", "/analytics/revenue/by-product", {}),
        ("Sales API", "GET /analytics/top-selling-product", "/analytics/top-selling-product", {}),
        ("Sales API", "GET /analytics/summary", "/analytics/summary", {}),
        ("Sales API", "GET /analytics/transactions (paginated)", "/analytics/transactions?skip=0&limit=50", {}),
        # Forecasting API
        ("Forecasting API", "GET /forecast/{month} (RF Model)", "/forecast/12", {}),
        ("Forecasting API", "GET /analytics/inventory/forecast/{id}", "/analytics/inventory/forecast/1?forecast_days=14", {}),
        # Recommendation API
        ("Recommendation API", "GET /recommendations/popular", "/recommendations/popular?top_n=5", {}),
        ("Recommendation API", "GET /recommend/{customer_id}", "/recommend/1", {}),
        ("Recommendation API", "GET /recommendations/evaluation", "/recommendations/evaluation?k=5", {}),
        # Admin API
        ("Admin API", "GET /admin/overview (Secured)", "/admin/overview", admin_headers),
        ("Admin API", "GET /admin/stats (Secured)", "/admin/stats", admin_headers),
        ("Admin API", "GET /admin/health (Secured)", "/admin/health", admin_headers),
        ("Admin API", "GET /auth/admin/users (Secured)", "/auth/admin/users?limit=10", admin_headers),
        ("Admin API", "GET /etl/batches (Secured)", "/etl/batches?limit=10", admin_headers),
    ]

    print("=" * 80)
    print("ShopSense Analytics Platform — API Latency Benchmark (Milestone 4 Step 2)")
    print("=" * 80)
    print(f"{'Category':<20} {'Endpoint':<38} {'Runs':<5} {'Mean (ms)':<10} {'Min (ms)':<9} {'Max (ms)':<9} {'Target'}")
    print("-" * 95)

    all_passed = True
    results = []

    for category, name, path, headers in endpoints:
        # Warmup call
        warmup_resp = client.get(path, headers=headers)
        if warmup_resp.status_code != 200:
            print(f"FAILED warmup for {name}: {warmup_resp.status_code} {warmup_resp.text}")
            all_passed = False
            continue

        latencies = []
        for _ in range(5):
            t0 = time.perf_counter()
            resp = client.get(path, headers=headers)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)

        mean_lat = statistics.mean(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        status_str = "PASS (<=300ms)" if mean_lat <= 300.0 else "FAIL (>300ms)"
        if mean_lat > 300.0:
            all_passed = False

        results.append({
            "category": category,
            "endpoint": name,
            "mean_ms": round(mean_lat, 2),
            "min_ms": round(min_lat, 2),
            "max_ms": round(max_lat, 2),
            "status": status_str,
        })

        print(f"{category:<20} {name:<38} {'5':<5} {mean_lat:8.2f} ms {min_lat:7.2f} ms {max_lat:7.2f} ms  {status_str}")

    print("=" * 95)
    print(f"Overall Result: {'ALL ENDPOINTS PASSED (<=300ms)' if all_passed else 'SOME ENDPOINTS EXCEEDED 300ms'}")
    return all_passed, results


if __name__ == "__main__":
    benchmark()
