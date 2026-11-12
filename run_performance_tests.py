"""
run_performance_tests.py — Automated Performance Test Runner for StockPilot Analytics.

Measures:
  - Average response time (ms)
  - Median (p50) response time (ms)
  - 95th percentile (p95) response time (ms) [Target: < 300 ms]
  - 99th percentile (p99) response time (ms)
  - Throughput (Requests per Second / RPS)
  - Failure rate (%)
"""

import os
import sys
import time
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

import numpy as np
import requests

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def execute_load_test(
    base_url: str = "http://127.0.0.1:8000",
    concurrent_users: int = 15,
    duration_seconds: int = 15,
    target_p95_ms: float = 300.0,
) -> Dict[str, Any]:
    """
    Executes controlled multi-user load testing across the 7 required endpoints.
    Measures latency percentiles, throughput, and error rates.
    """
    endpoints = [
        {"name": "/analytics/revenue", "path": lambda: "/analytics/revenue"},
        {"name": "/analytics/vendor-performance", "path": lambda: "/analytics/vendor-performance"},
        {"name": "/analytics/customers", "path": lambda: "/analytics/customers"},
        {"name": "/analytics/revenue/growth", "path": lambda: "/analytics/revenue/growth"},
        {"name": "/analytics/revenue/benchmarking", "path": lambda: "/analytics/revenue/benchmarking"},
        {"name": "/forecast/{month}", "path": lambda: f"/forecast/{random.randint(1, 12)}"},
        {"name": "/recommend/{customer_id}", "path": lambda: f"/recommend/{random.randint(1, 60)}"},
    ]

    stop_event = threading.Event()
    results: List[Dict[str, Any]] = []
    results_lock = threading.Lock()

    def user_worker():
        session = requests.Session()
        while not stop_event.is_set():
            ep = random.choice(endpoints)
            url = f"{base_url.rstrip('/')}{ep['path']()}"
            t0 = time.perf_counter()
            success = False
            status_code = 0
            error = None
            try:
                resp = session.get(url, timeout=5.0)
                status_code = resp.status_code
                success = (status_code == 200)
            except Exception as e:
                error = str(e)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            with results_lock:
                results.append({
                    "endpoint": ep["name"],
                    "elapsed_ms": elapsed_ms,
                    "success": success,
                    "status_code": status_code,
                    "error": error,
                })
            time.sleep(random.uniform(0.05, 0.15))

    print(f"[*] Starting load test: {concurrent_users} users, {duration_seconds}s duration against {base_url}...")
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
        futures = [executor.submit(user_worker) for _ in range(concurrent_users)]
        time.sleep(duration_seconds)
        stop_event.set()
        for f in futures:
            f.result()

    total_time = time.time() - t_start
    total_requests = len(results)
    if total_requests == 0:
        raise RuntimeError("No requests were recorded during the load test.")

    all_latencies = [r["elapsed_ms"] for r in results]
    failures = sum(1 for r in results if not r["success"])
    failure_rate = (failures / total_requests) * 100.0
    rps = round(total_requests / total_time, 2)

    avg_ms = float(np.mean(all_latencies))
    median_ms = float(np.median(all_latencies))
    p95_ms = float(np.percentile(all_latencies, 95))
    p99_ms = float(np.percentile(all_latencies, 99))
    min_ms = float(np.min(all_latencies))
    max_ms = float(np.max(all_latencies))

    # Per-endpoint breakdown
    breakdown = {}
    for ep in endpoints:
        name = ep["name"]
        ep_res = [r for r in results if r["endpoint"] == name]
        if ep_res:
            lats = [r["elapsed_ms"] for r in ep_res]
            fails = sum(1 for r in ep_res if not r["success"])
            breakdown[name] = {
                "requests": len(ep_res),
                "failures": fails,
                "failure_rate_pct": round((fails / len(ep_res)) * 100.0, 2),
                "avg_ms": round(float(np.mean(lats)), 2),
                "median_ms": round(float(np.median(lats)), 2),
                "p95_ms": round(float(np.percentile(lats, 95)), 2),
                "p99_ms": round(float(np.percentile(lats, 99)), 2),
            }

    p95_target_met = (p95_ms <= target_p95_ms)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "target_url": base_url,
        "concurrent_users": concurrent_users,
        "duration_seconds": round(total_time, 2),
        "total_requests": total_requests,
        "total_failures": failures,
        "failure_rate_pct": round(failure_rate, 2),
        "throughput_rps": rps,
        "metrics_ms": {
            "min": round(min_ms, 2),
            "avg": round(avg_ms, 2),
            "median": round(median_ms, 2),
            "p95": round(p95_ms, 2),
            "p99": round(p99_ms, 2),
            "max": round(max_ms, 2),
        },
        "target_p95_ms": target_p95_ms,
        "target_met": p95_target_met,
        "endpoint_breakdown": breakdown,
    }

    # Save report
    out_dir = os.path.join(ROOT_DIR, "data")
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "performance_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    report = execute_load_test()
    print("=" * 70)
    print("StockPilot - API Performance Load Test Results")
    print("=" * 70)
    print(f"Total Requests:     {report['total_requests']:,}")
    print(f"Duration:           {report['duration_seconds']}s")
    print(f"Throughput:         {report['throughput_rps']} req/s")
    print(f"Failures:           {report['total_failures']} ({report['failure_rate_pct']}%)")
    print(f"Average Latency:    {report['metrics_ms']['avg']} ms")
    print(f"Median (p50):       {report['metrics_ms']['median']} ms")
    print(f"95th Percentile:    {report['metrics_ms']['p95']} ms (Target: < {report['target_p95_ms']} ms) -> {'PASSED' if report['target_met'] else 'FAILED'}")
    print(f"99th Percentile:    {report['metrics_ms']['p99']} ms")
    print("-" * 70)
    print(f"{'Endpoint':<34} {'Reqs':<8} {'Avg(ms)':<10} {'p95(ms)':<10} {'Fails'}")
    print("-" * 70)
    for name, stats in report["endpoint_breakdown"].items():
        print(f"{name:<34} {stats['requests']:<8} {stats['avg_ms']:<10} {stats['p95_ms']:<10} {stats['failures']}")
    print("=" * 70)
