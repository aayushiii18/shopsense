# ShopSense Milestone 4 – Step 11: Load Testing & Concurrency Validation Report

**Executed:** 2026-11-27 18:15:11 UTC  
**Target Stack:** `http://127.0.0.1:8000` (Single-worker Uvicorn ASGI -> local PostgreSQL)  
**Peak Concurrent Users Reached:** `100` (`50` stable within latency/error gates; `1,074` total requests, `0` failures, `56.63s` cumulative active load)  
**Load Profile:** Multi-role authenticated Locust workload (`StockPilotAnalyticsUser` ADMIN w=5, `VendorOperationsUser` w=2, `CustomerShopperUser` w=3), spawn rate `25 users/s`, think time `0.35s–1.15s`, strictly read-only GET queries (`<4%` `/health/ready` weight).

---

## 1. Environment & Safety Guardrails

| Parameter | Measured Configuration |
| :--- | :--- |
| **OS Platform** | `Windows-10-10.0.26200-SP0` |
| **Python / Locust** | Python `3.10.6` / Locust `2.46.0` |
| **CPU / RAM** | 8 logical cores / 7.8 GB total (1.14 GB free before test) |
| **Database Pool** | SQLAlchemy `pool_size=30`, `max_overflow=20` (50 max connections/worker); PostgreSQL `max_connections=100` |
| **Authentication** | Pre-minted JWT Bearer tokens from existing active `ADMIN`, `VENDOR` (tenant 7), and `CUSTOMER` (tenant 61) accounts (`X-Enforce-Auth: true`, zero DB inserts) |
| **Stop Conditions** | Auto-halt scaling if host free RAM < 180 MB, stage error rate >= 5.0%, P95 > 5,000 ms, or API/Streamlit/MLflow health fails |

> **Scope Limitation:** Load tests ran against a single-machine, single-worker local Uvicorn deployment co-located with PostgreSQL, Streamlit, MLflow, and the Locust load generator. Tail latency and saturation points therefore reflect host CPU sharing and 1-worker thread/DB-pool bounds rather than multi-node production capacity.

---

## 2. Progressive Concurrency Ramp Results (`25 users/s` spawn rate)

| Stage | Users | Duration | Requests | Failures (%) | Throughput (RPS) | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Peak CPU% | Peak Uvicorn RSS (MB) | Peak PG Conns | Min Free RAM (MB) |
| :--- | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stage 1 (50 users) | 50 | 23.83s | 441 | 0 (0.0%) | 22.03 | 1449.06 | 1300.0 | 2900.0 | 7000.0 | 58.5% | 291.76 | 35 | 716.3 |
| Stage 2 (100 users) | 100 | 32.8s | 633 | 0 (0.0%) | 22.49 | 3165.71 | 2900.0 | 7000.0 | 8400.0 | 51.7% | 298.66 | 51 | 544.0 |

**Cumulative Executed Totals:** `1,074` requests across `2` progressive stages (`56.63s` active load), **`0` HTTP/connection failures (`0.0%` error rate)**.

**Scaling Outcome:** P95 latency reached 7000.0 ms (> 5,000 ms latency saturation ceiling) at 100 users.

---

## 3. Endpoint Breakdown at Peak Evaluated Load (100 Concurrent Users)

| Endpoint | Requests | Failures | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | RPS |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/analytics/customers/clv/{customer_id}` | 31 | 0 (0.0%) | 7490.35 | 7400.0 | 9000.0 | 9100.0 | 1.1 |
| `/analytics/executive/vendor-summary` | 45 | 0 (0.0%) | 3962.29 | 3800.0 | 8200.0 | 8400.0 | 1.6 |
| `/analytics/executive/trends` | 31 | 0 (0.0%) | 3522.46 | 3200.0 | 8100.0 | 8100.0 | 1.1 |
| `/analytics/executive/summary` | 56 | 0 (0.0%) | 3637.7 | 3500.0 | 6700.0 | 7600.0 | 1.99 |
| `/analytics/revenue/growth` | 31 | 0 (0.0%) | 2401.14 | 2300.0 | 6700.0 | 6900.0 | 1.1 |
| `/analytics/customers` | 16 | 0 (0.0%) | 2372.25 | 1900.0 | 6500.0 | 6500.0 | 0.57 |
| `/analytics/inventory/status` | 24 | 0 (0.0%) | 2819.41 | 2300.0 | 6500.0 | 8000.0 | 0.85 |
| `/analytics/inventory/turnover` | 15 | 0 (0.0%) | 1872.99 | 1500.0 | 6400.0 | 6400.0 | 0.53 |
| `/analytics/vendor-performance` | 22 | 0 (0.0%) | 3115.54 | 3500.0 | 5700.0 | 8200.0 | 0.78 |
| `/analytics/revenue` | 17 | 0 (0.0%) | 2622.79 | 2200.0 | 5600.0 | 5600.0 | 0.6 |
| `/analytics/revenue/benchmarking` | 26 | 0 (0.0%) | 3548.06 | 3500.0 | 5600.0 | 6700.0 | 0.92 |
| `/analytics/executive/vendors` | 27 | 0 (0.0%) | 3728.67 | 3700.0 | 5300.0 | 7100.0 | 0.96 |
| `/recommendations/popular` | 48 | 0 (0.0%) | 1844.23 | 1300.0 | 5300.0 | 5800.0 | 1.71 |
| `/analytics/vendors/payouts` | 24 | 0 (0.0%) | 3520.62 | 3800.0 | 5000.0 | 6700.0 | 0.85 |
| `/analytics/revenue/profit-margins` | 31 | 0 (0.0%) | 2197.46 | 1900.0 | 4600.0 | 6700.0 | 1.1 |
| `/products/` | 81 | 0 (0.0%) | 2810.11 | 2800.0 | 4500.0 | 7900.0 | 2.88 |
| `/admin/overview` | 10 | 0 (0.0%) | 3212.91 | 2900.0 | 4200.0 | 4200.0 | 0.36 |
| `/recommendations/hybrid/{customer_id}` | 47 | 0 (0.0%) | 3037.12 | 3000.0 | 4200.0 | 4400.0 | 1.67 |
| `/recommend/{customer_id}` | 15 | 0 (0.0%) | 2942.51 | 2900.0 | 4100.0 | 4100.0 | 0.53 |
| `/forecast/{month}` | 24 | 0 (0.0%) | 2507.6 | 2500.0 | 3500.0 | 5200.0 | 0.85 |
| `/health/ready` | 12 | 0 (0.0%) | 1527.33 | 1600.0 | 2500.0 | 2500.0 | 0.43 |

---

## 4. Database Preservation & Service Stability Audit

- **PostgreSQL Integrity (`Before == After`):** `True` (`users=8`, `vendors=7`, `products=14`, `customers=61`, `inventory=14`, `transactions=606`, `refunds=0`).
- **Post-Test Service Health:** FastAPI Ready=`True`, Streamlit=`True`, MLflow=`True`.

---

## 5. Observed Bottlenecks & Scaling Recommendations

1. **Single-Worker Saturation at ~22.5 RPS:** Throughput plateaued between `50` users (`22.03 RPS`) and `100` users (`22.49 RPS`) while mean latency doubled (`1,449 ms -> 3,166 ms`) and `P95` climbed from `2,900 ms` to `7,000 ms`, triggering the `> 5,000 ms` safety stop before forcing `200–500` concurrent users.
2. **AnyIO Sync Threadpool & Python GIL Contention:** ShopSense FastAPI routes use synchronous `def` handlers dispatched across AnyIO's default 40-thread pool inside a single Python process. Per-request Pandas/Scikit-Learn work—especially `/analytics/customers/clv/{customer_id}` (`7,490 ms` mean, `9,000 ms` P95 due to full-table Pandas/churn evaluation without response caching) and `/recommendations/hybrid/{customer_id}`—contends on the GIL and delays even lightweight probes (`/health/ready` `P95 = 2,500 ms` at 100 queued users).
3. **Database Connection Pool Saturation (`51` PG Connections):** At `100` concurrent users, active PostgreSQL connections hit `51`, exhausting the single worker's configured SQLAlchemy limit (`pool_size=30 + max_overflow=20 = 50`, plus the monitor session).
4. **Production Path to 500 Concurrent Users:** Reaching `500` sustained interactive users cleanly requires multi-process horizontal scaling (e.g., `4+` Uvicorn/Gunicorn workers behind a reverse proxy with `DISABLE_BACKGROUND_SCHEDULER=true`, sized so `workers * max_pool <= pg_max_connections`), caching `clv_service` / similarity matrices alongside `_CHURN_CACHE` & `_REV_CACHE`, and offloading heavy ML inference from hot synchronous request threads.

---

## 6. Reproducibility Instructions

```powershell
# Automated progressive runner (handles read-only multi-role JWT minting, resource safety guardrails & report generation):
python benchmarks/run_step11_load_test.py

# Regenerate report from saved telemetry JSON without hitting live API:
python benchmarks/run_step11_load_test.py --report-only

# Or invoke Locust manually with tokens exported:
locust -f locustfile.py --headless -u 100 -r 25 --run-time 25s --host http://127.0.0.1:8000
```
