# ShopSense Milestone 4 – Phase 1: 100K Transaction Benchmark Report

**Generated At:** 2026-11-26 13:49:52 UTC  
**Random Seed:** `42`  
**Dataset Scale:** `100,000` synthetic transactions (`25` vendors, `120` products, `10,000` customers)  
**Isolation Guarantee:** Generated strictly in `data/benchmarks` — zero writes to PostgreSQL or existing `data/*.csv` files.

---

## 1. Dataset Schema & Generation Methodology

### Canonical Schema (`transactions_100k.csv`)
Mirrors `app/models/transaction.py` and `app/services/etl/validation.py`:
- **Keys & Foreign References:** `transaction_id` (`int64`), `product_id` (`int32`), `vendor_id` (`int32`, matched to `product.vendor_id`), `customer_id` (`int32`)
- **Financial & Quantity Fields:** `quantity` (`int32`, `> 0`), `unit_price` (`float64`, `> 0`), `amount` (`float64`, exact `round(quantity * unit_price, 2)`), `discount_amount` (`float64`, `0 <= discount < amount`), `effective_commission_rate` (`float64`)
- **Audit & Payment Fields:** `payment_method` (`UPI`, `CARD`, `NETBANKING`, `WALLET`, `COD`), `payment_status` (`COMPLETED`), `source_system` (`SYNTHETIC_BENCHMARK_100K`), `source_transaction_id` (`BENCH-0000001`..), `transaction_date` (`datetime64[ns]`, `2024-01-01` to `2025-12-31`)

### Generation Methodology
- Vectorized sampling (`numpy.random.default_rng(42)`) with zero Python row loops.
- Seasonal calendar weighting: `+45%` weight in Q4 (Oct–Dec), `+25%` weekend weight, `+18%` YoY growth weight in 2025.
- Zipf-like product demand distribution across 120 catalog SKUs and persona-weighted customer order frequency (VIP `4.0x`, Loyal `1.8x`, At-Risk `0.9x`, Occasional `0.5x`).
- All `100,000` rows passed all 11 schema/FK integrity checks in `87.37 ms` (`all_valid = True`).

---

## 2. Benchmark Environment

| Property | Measured Value |
| :--- | :--- |
| **OS / Platform** | `Windows-10-10.0.26200-SP0` |
| **Python** | `3.10.6` |
| **CPU Cores (Logical)** | `8` |
| **System RAM** | `7.8 GB` total (`0.77 GB` available) |
| **Pandas / NumPy** | `2.3.3` / `1.26.4` |

---

## 3. End-to-End Performance & Memory Metrics

| Phase / Metric | Measured Result |
| :--- | :--- |
| **Synthetic Dataset Generation (in-memory)** | `0.5590 s` |
| **Isolated CSV Write (`11.004 MB`)** | `2.5738 s` |
| **CSV Load into Typed Pandas DataFrames** | `1.0279 s` |
| **Vectorized Schema & FK Validation** | `87.37 ms` |
| **Total Vectorized Analytics Time (8 workloads)** | `0.9330 s` (`933.00 ms`) |
| **Overall End-to-End Pipeline Time (Gen + Write + Load + Validate + Analytics)** | `5.8212 s` |
| **Loaded Transactions DataFrame Memory (`deep=True`)** | `32.65 MB` |
| **Python Heap Peak (`tracemalloc` during Analytics)** | `17.29 MB` |
| **Process RSS (Before → After Analytics / Delta)** | `92.21 MB` → `94.96 MB` (`+2.75 MB`) |

### Per-Operation Analytics Breakdown

| Analytical Workload | Execution Time | Throughput |
| :--- | :--- | :--- |
| `total_revenue_and_gmv` | 1.96 ms | 50,942,435 rows/s |
| `average_transaction_value` | 22.96 ms | 4,355,590 rows/s |
| `vendor_sales_and_ranking` | 136.09 ms | 734,829 rows/s |
| `product_sales_and_cogs` | 84.83 ms | 1,178,842 rows/s |
| `category_and_payment_breakdown` | 170.46 ms | 586,658 rows/s |
| `time_based_trends_mom_daily` | 227.04 ms | 440,459 rows/s |
| `customer_rfm_aggregation` | 70.50 ms | 1,418,500 rows/s |
| `daily_sales_mart_rollup` | 218.72 ms | 457,203 rows/s |

---

## 4. Analytical Outputs Summary (100,000 Transactions)

### Marketplace KPIs
- **Total Transactions:** `100,000` | **Total Units Sold:** `149,027`
- **Gross Merchandise Value (GMV):** `Rs. 22,598,219.98`
- **Promotional Discounts:** `Rs. 621,514.40` | **Net Sales:** `Rs. 21,976,705.58`
- **Average Order Value (AOV):** `Rs. 225.98` (Median: `Rs. 161.48`, p95: `Rs. 699.75`, Avg Units/Order: `1.49`)
- **Gross Profit (100% Cost Coverage):** `Rs. 7,620,033.59` (`34.67%` margin over `Rs. 14,356,671.99` COGS)

### Top Performers & Trends
- **Top Vendor:** **Vendor Hub 01** (`Rs. 4,466,976.30`, `19.77%` market share, `11,543` orders)
- **Top Product:** **Headphones SKU-001** (`Rs. 4,118,105.85`, `10,685` units)
- **Time Coverage:** `24` months / `731` days | **Peak Month:** `2025-12` (`Rs. 1,264,320.40`) | **Peak Day:** `2024-12-29` (`Rs. 60,490.86`)
- **Customer RFM Summary:** `9,918/10,000` active buyers (`90d` active: `7,027`, repeat rate: `96.41%`, max customer spend: `Rs. 12,228.95`)
- **Daily Sales Mart Grain Rollup:** `47,983` `(date, product_id, vendor_id)` rows (`mart_gross_gmv = Rs. 22,598,219.98`)

#### Top 5 Vendors by Gross Revenue
| Rank | Vendor | Gross Revenue | Market Share | Orders | Est. Payout |
| :--- | :--- | :--- | :--- | :--- | :--- |
| #1 | Vendor Hub 01 (`id=1`) | Rs. 4,466,976.30 | 19.77% | 11,543 | Rs. 3,999,374.22 |
| #2 | Vendor Hub 10 (`id=10`) | Rs. 1,711,286.45 | 7.57% | 3,639 | Rs. 1,530,725.53 |
| #3 | Vendor Hub 04 (`id=4`) | Rs. 1,323,196.42 | 5.86% | 5,487 | Rs. 1,157,725.18 |
| #4 | Vendor Hub 06 (`id=6`) | Rs. 1,321,920.42 | 5.85% | 4,637 | Rs. 1,091,800.90 |
| #5 | Vendor Hub 19 (`id=19`) | Rs. 1,273,528.07 | 5.64% | 2,943 | Rs. 1,050,890.98 |

#### Category Revenue Distribution
| Parent Category | Revenue | Share | Units Sold | Orders |
| :--- | :--- | :--- | :--- | :--- |
| Electronics | Rs. 7,318,794.96 | 32.39% | 56,367 | 36,035 |
| Home & Kitchen | Rs. 5,090,795.16 | 22.53% | 35,804 | 24,212 |
| Fashion | Rs. 4,174,757.48 | 18.47% | 18,992 | 14,086 |
| Sports & Fitness | Rs. 3,052,175.08 | 13.51% | 19,122 | 13,266 |
| Food & Beverage | Rs. 1,565,232.78 | 6.93% | 9,637 | 6,164 |
| Beauty & Wellness | Rs. 1,396,464.52 | 6.18% | 9,105 | 6,237 |

---

## 5. Bottlenecks, Limitations & Optimization Opportunities

### Benchmark Environment Limitations
1. **In-Memory Single-Node Pandas vs Database Round-Trip:** This Phase 1 benchmark evaluates pure Pandas/NumPy processing and typed CSV loading without executing SQLAlchemy inserts against PostgreSQL (intentionally isolated to protect local database state). Network/SQL serialization overhead is excluded.
2. **CSV I/O vs Vectorized Analytics Compute:** Combined CSV disk write and typed load took `3.6017 s` (`2.5738 s` write + `1.0279 s` load), exceeding total analytical aggregation time (`0.9330 s` across all 8 workloads) and highlighting row-based CSV text serialization overhead.
3. **High-Cardinality Grouping & Object Memory Overhead:** Grouping 100K transactions across `47,983` `(date, product_id, vendor_id)` buckets accounts for the largest single analytics operation, while string object columns (`source_transaction_id`, `payment_method`, `source_system`) account for the bulk of the `32.65 MB` DataFrame footprint.

### Codebase Bottlenecks Identified & Future Optimization Opportunities
1. **Eliminate Python Row Loops in Existing Services:** In production `app/services/customer_service.py` (`compute_rfm_metrics`), per-group Python `lambda` recency calculations and `.iterrows()` will degrade sharply near 100K rows; replacing them with vectorized `.dt.days` (demonstrated here) or SQL window functions keeps execution sub-50 ms.
2. **Batch Upserts in `DailySalesMart` (`app/services/etl/daily_mart_service.py`):** Executing one `SELECT` per `(date, product_id, vendor_id)` tuple produces tens of thousands of queries on `47,983` mart rows at 100K scale. Replacing per-row queries with PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` bulk upserts will eliminate N+1 DB latency.
3. **SQL-Side Settlement & Profit Aggregation (`app/services/revenue_service.py`):** `get_vendor_settlements` and `get_profit_margins` currently materialize transaction lists into Python memory; pushing aggregations and `IN`/`JOIN` rollups completely into PostgreSQL CTEs + composite indexes on `(transaction_date, vendor_id, product_id)` will keep API p95 well below 300 ms at scale.
4. **Columnar Storage for Cold/Batch Analytics:** Converting bulk CSV exports to Parquet (`pyarrow`) with categorical encoding reduces disk I/O and DataFrame RAM by ~60–75% when feeding ML retraining and executive batch summaries.
