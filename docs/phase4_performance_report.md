# ShopSense Milestone 4 – Phase 4: Performance Validation & Scalability Report

**Generated:** 2026-11-27 15:52:35 UTC  
**Baseline Captured:** 2026-11-27 15:29:55 UTC  
**Scope:** Integrated FastAPI + SQLAlchemy + PostgreSQL (live localhost, 606 txns) & Isolated Relational 100,000-Transaction + 2,000-Refund Validation (`seed=42`).

---

## 1. Test Environment & Methodology

| Parameter | Measured Environment |
| :--- | :--- |
| **Operating System** | `Windows-10-10.0.26200-SP0` |
| **Python Version** | `3.10.6` |
| **Logical CPU Cores** | 8 |
| **System Memory** | 7.8 GB total (0.76 GB available at run) |
| **Live Localhost Stack** | Single-worker Uvicorn (`127.0.0.1:8000`) -> local PostgreSQL (`606` transactions, intact) |
| **Isolated 100K Stack** | FastAPI `TestClient` (`dependency_overrides[get_db]`) -> `data/benchmarks/integrated_100k.db` (`100,000` txns, `2,000` refunds) |
| **Caching Discipline** | Uncached cold SQL timing enforced (`_REV_CACHE.clear()` before every measured 100K endpoint) |
| **100K DB File Size** | Baseline: 29.96 MB -> Optimized (with indexes): 45.77 MB |

> **Methodological Guardrail:** All localhost and single-machine SQLite 100K measurements reflect local single-worker behavior without network WAN latency, connection-pool contention across multi-instance deployments, or production PostgreSQL shared-buffers tuning. They validate SQL complexity scaling, memory boundedness, and regression freedom rather than production SLA guarantees.

---

## 2. Isolated 100,000-Transaction Integrated DB/API Comparison (Uncached)

Each workload executes end-to-end through FastAPI routing, RBAC dependency resolution, SQLAlchemy queries, and Pydantic serialization against `integrated_100k.db` (`100,000` transactions + `2,000` completed refunds).

| Endpoint | Baseline Mean (ms) | Optimized Mean (ms) | Speedup / Change | Baseline P95 (ms) | Optimized P95 (ms) | SQL Queries (`Before -> After`) | Peak Heap MB (`Before -> After`) |
| :--- | ---: | ---: | :---: | ---: | ---: | :---: | :---: |
| `GET /analytics/executive/summary` | 1985.92 | 1477.47 | 1.34x faster | 2027.69 | 1513.22 | 20 -> 14 | 0.366 -> 0.382 |
| `GET /analytics/executive/summary (6M window)` | 2254.56 | 284.51 | 7.92x faster | 2268.66 | 289.99 | 22 -> 16 | 0.338 -> 0.358 |
| `GET /analytics/executive/trends (monthly)` | 263.61 | 290.36 | 1.10x slower | 267.08 | 295.02 | 5 -> 5 | 0.122 -> 0.124 |
| `GET /analytics/executive/trends (daily)` | 429.36 | 268.21 | 1.60x faster | 434.77 | 269.88 | 7 -> 5 | 1.416 -> 1.422 |
| `GET /analytics/executive/vendors (limit=25)` | 1139.29 | 574.69 | 1.98x faster | 1155.52 | 583.27 | 8 -> 5 | 0.278 -> 0.322 |
| `GET /analytics/executive/vendor-summary (vid=1)` | 292.25 | 169.31 | 1.73x faster | 300.55 | 174.03 | 15 -> 12 | 0.166 -> 0.178 |
| `GET /analytics/revenue/total` | 30.80 | 31.75 | 1.03x slower | 31.64 | 32.20 | 1 -> 1 | 0.064 -> 0.063 |
| `GET /analytics/revenue/growth` | 13765.05 | 173.76 | 79.22x faster | 15521.66 | 180.25 | 1 -> 1 | 62.076 -> 0.096 |
| `GET /analytics/revenue/profit-margins` | HTTP 500 FAIL | 86.07 | Fixed Crash (500 -> 200) | FAIL | 92.67 | None -> 2 | N/A -> 0.103 |
| `GET /analytics/revenue/benchmarking` | 369.93 | 417.69 | 1.13x slower | 374.89 | 449.49 | 2 -> 2 | 0.125 -> 0.118 |
| `GET /analytics/vendors/payouts` | 5268.38 | 379.62 | 13.88x faster | 5358.52 | 389.57 | 52 -> 4 | 42.409 -> 0.152 |
| `GET /analytics/customers/summary` | 2176.43 | 1356.32 | 1.60x faster | 2183.15 | 1374.41 | 2 -> 3 | 53.078 -> 0.101 |
| `GET /analytics/inventory/turnover` | 461.62 | 36.72 | 12.57x faster | 484.05 | 38.37 | 3 -> 3 | 0.354 -> 0.355 |

### Analytical Parity Verification (100,000 Transactions)

| Metric | Vectorized Ground Truth | Integrated Executive API | Parity Match |
| :--- | ---: | ---: | :---: |
| Total Transactions | 100,000 | 100,000 | True |
| Gross Merchandise Value (GMV) | 22,598,219.98 | 22,598,219.98 | True |
| Total Discounts | 621,514.40 | 621,514.40 | True |
| Completed Refunds | 110,255.93 | 110,255.93 | True |
| Net Sales | 21,866,449.65 | 21,866,449.65 | True |
| Gross Profit (100% COGS Coverage) | 7,509,777.66 | 7,509,777.66 | True |
| Average Order Value (AOV) | 225.98 | 225.98 | True |

---

## 3. Live Localhost Integrated API & Concurrent Load (PostgreSQL, 606 Transactions)

### Endpoint Latency & SQL Count Comparison

| Endpoint | Baseline Mean (ms) | Optimized Mean (ms) | Baseline P95 (ms) | Optimized P95 (ms) | Delta (Mean) |
| :--- | ---: | ---: | ---: | ---: | :---: |
| `GET /analytics/executive/summary` | 27.55 | 20.55 | 33.09 | 25.3 | -25.4% |
| `GET /analytics/executive/summary (date-filtered)` | 30.46 | 24.08 | 33.18 | 26.07 | -20.9% |
| `GET /analytics/executive/trends (monthly)` | 12.78 | 12.87 | 16.67 | 14.52 | +0.7% |
| `GET /analytics/executive/trends (daily)` | 17.88 | 15.75 | 24.91 | 17.04 | -11.9% |
| `GET /analytics/executive/vendors` | 14.89 | 9.29 | 16.28 | 10.35 | -37.6% |
| `GET /analytics/executive/vendor-summary` | 19.92 | 22.28 | 22.3 | 32.17 | +11.8% |
| `GET /analytics/revenue/total` | 4.45 | 4.36 | 5.21 | 5.58 | -2.0% |
| `GET /analytics/revenue/growth` | 2.53 | 2.94 | 3.61 | 3.84 | +16.2% |
| `GET /analytics/revenue/profit-margins` | 2.59 | 2.89 | 3.6 | 4.18 | +11.6% |
| `GET /analytics/customers/summary` | 12.18 | 9.2 | 13.66 | 11.35 | -24.5% |
| `GET /analytics/inventory/turnover` | 6.29 | 6.91 | 7.47 | 8.02 | +9.9% |
| `GET /forecast/12` | 7.22 | 9.11 | 8.35 | 9.8 | +26.2% |
| `GET /recommend/1` | 8.34 | 8.43 | 10.27 | 9.63 | +1.1% |
| `GET /admin/overview` | 8.65 | 8.6 | 11.23 | 10.07 | -0.6% |

### 10-User Concurrent Mixed Workload (10s Sustained Localhost Test)

| Metric | Baseline | Post-Optimization | Change |
| :--- | ---: | ---: | :---: |
| Total Requests Completed | 882 | 955 | +8.3% |
| Error Rate | 0.0% (0) | 0.0% (0) | Zero failures |
| Throughput (RPS) | 87.5 | 94.26 | +7.7% |
| Mean Latency (ms) | 113.91 | 105.76 | -7.2% |
| P50 Latency (ms) | 104.69 | 97.98 | -6.4% |
| P95 Latency (ms) | 199.13 | 182.19 | -8.5% |
| P99 Latency (ms) | 286.0 | 266.61 | -6.8% |

---

## 4. Empirical Bottlenecks Found & Evidence-Backed Optimizations

1. **Critical Crash (`HTTP 500`) in `GET /analytics/revenue/profit-margins` (`app/services/revenue_service.py`):**
   - **Root Cause:** `get_profit_margins()` loaded every filtered `Transaction` row into Python and executed `Refund.transaction_id.in_(tx_ids)`, overflowing SQLite's bind parameter limit (`OperationalError: too many SQL variables`) and allocating tens of MBs at 100K rows.
   - **Optimization:** Rewrote `get_profit_margins()` into two single-row SQL `SUM(CASE ...)` aggregations joined at DB level, removing both the parameter overflow and full-table row loading.
2. **13.77s Latency & 62 MB Heap in `GET /analytics/revenue/growth` (`app/services/revenue_service.py`):**
   - **Root Cause:** `get_monthly_revenue_growth()` fetched all 100K `(transaction_date, amount)` tuples into a Pandas DataFrame and iterated with `.iterrows()`.
   - **Optimization:** Replaced with SQL `GROUP BY extract(year, transaction_date), extract(month, transaction_date)` keeping memory sub-megabyte.
3. **5.27s Latency, 52 N+1 Queries & 42 MB Heap in `GET /analytics/vendors/payouts` (`app/services/revenue_service.py`):**
   - **Root Cause:** `get_vendor_settlements()` triggered one `Transaction` + `Refund` query loop per vendor (`N+1`) and loaded full transaction ORM objects per vendor.
   - **Optimization:** Consolidated into two `GROUP BY vendor_id` SQL aggregations merged cleanly in O(vendors) memory.
4. **2.18s Latency & 53 MB Heap in `GET /analytics/customers/summary` (`app/services/customer_service.py`):**
   - **Root Cause:** `get_customer_summary()` loaded all 100K `(customer_id, amount, transaction_date)` rows into Pandas to compute repeat buyers and 90-day active counts.
   - **Optimization:** Replaced with a grouped SQL customer subquery + indexed 90-day `COUNT(DISTINCT)` query.
5. **Redundant Scans, Multi-Table 100K Joins & Missing Indexes in Executive Analytics (`app/services/executive_service.py`, `app/models/transaction.py`, `app/models/refund.py`):**
   - **Root Cause:** `Transaction.transaction_date` and composite filter/refund join keys lacked secondary indexes; `get_executive_summary` ran 20 queries including duplicate customer distinct scans, multi-table string-grouped product/vendor scans, and redundant GMV/COGS scans.
   - **Optimization:** Added SQLAlchemy indexes on `transactions` (`ix_transactions_transaction_date`, `ix_transactions_vendor_date`, `ix_transactions_product_date`, `ix_transactions_customer_date`) and `refunds` (`ix_refunds_status_tx`); unified product, financial, and vendor aggregations into a single integer-key `GROUP BY (product_id, vendor_id)` scan before joining small catalog tables; rolled up daily trends into monthly comparisons; consolidated customer repeat & revenue metrics into one grouped subquery.

---

## 5. Reproducibility

```bash
# 1. Capture uncached baseline (writes gitignored data/benchmarks/phase4_baseline.json)
python benchmarks/phase4_performance_validation.py --mode baseline --rebuild-db

# 2. Rebuild isolated 100K DB with indexes, run optimized suite & regenerate this report
python benchmarks/phase4_performance_validation.py --mode optimized --rebuild-db

# 3. Execute automated Phase 4 scalability & parity tests
pytest tests/test_phase4_performance.py -v
```
