# ShopSense / StockPilot — Multi-Vendor Retail Management, Analytics & Data Warehouse Platform
> **Smarter Stock. Better Decisions.**  
> *Infosys Springboard Internship Project — Stages 1 through 6 Complete*

---

## 1. Executive Overview

**ShopSense (StockPilot)** is an enterprise multi-vendor retail management, analytics, machine learning, and data warehousing platform. Designed with a modular service-oriented architecture using **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0**, and **Streamlit**, ShopSense provides:

- **End-to-End Retail Operations:** Vendor onboarding, category hierarchies, product catalogs, physical inventory tracking, and transaction ledgers.
- **Advanced Commerce & Financial Operations (Stage 4):** Commission tiers with transaction-time rate snapshotting, nullable Cost of Goods Sold (COGS) reporting with explicit coverage disclosure, atomic refunds with idempotency, and vendor settlement ledgers.
- **Customer Retention & Intelligence Engine (Stage 5):** Temporal churn prediction, cohort retention matrices, customer lifetime value (CLV), item-based collaborative filtering, catalog taxonomy normalization, and promotion safety stock validation.
- **Structured ETL, Bulk Ingestion & Data Warehouse (Stage 6):** Chunked CSV data ingestion, staging buffer, row-level validation, database-enforced deduplication, quarantine triage and reprocessing, automated reconciliation, and dimensional data marts with scheduled refresh.

---

## 2. Core Architecture & Modules

```
                                    ┌────────────────────────────────────────────────────────┐
                                    │               Streamlit Interactive UI                 │
                                    │    (10 Modular Analytics & Operational Views)          │
                                    └───────────────────────────┬────────────────────────────┘
                                                                │
                                                                ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           FastAPI REST API Services                                                │
│  /vendors  •  /products  •  /inventory  •  /analytics  •  /recommendations  •  /refunds  •  /offers  •  /etl       │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┘
                                                    │
                   ┌────────────────────────────────┴────────────────────────────────┐
                   │                                                                 │
                   ▼                                                                 ▼
┌──────────────────────────────────────┐                         ┌──────────────────────────────────────────────┐
│           Operational Core           │                         │             ETL & Data Warehouse             │
│  • Transaction Ledger & Payouts      │                         │  • Chunked CSV Extractor & Header Normalizer │
│  • Multi-Tier Commission Snapshot    │                         │  • Staging Buffer (etl_staging_records)      │
│  • Nullable COGS Accounting          │                         │  • Validation Engine (4 Error Categories)    │
│  • Idempotent Refund Operations      │                         │  • (source_system, source_tx_id) Deduplication│
│  • Physical Stock & Movement Logs    │                         │  • Quarantine Triage & Reprocessing          │
│  • APScheduler Analytical Pipeline   │                         │  • Reconciliation Audit (Count & Monetary)   │
│  • MLflow Model Tracking & Registry  │                         │  • DailySalesMart (Date x Product x Vendor)  │
└──────────────────┬───────────────────┘                         └──────────────────────┬───────────────────────┘
                   │                                                                    │
                   └────────────────────────────────┬───────────────────────────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │    PostgreSQL 16 Database     │
                                    │     (14 Relational Tables)    │
                                    └───────────────────────────────┘
```

---

## 3. Stage 6: Structured ETL & Data Warehouse Specification

### A. Modular ETL Architecture (`app/services/etl/`)
The ingestion pipeline strictly enforces clean stage separation:
**Extract → Stage → Validate → Deduplicate → Quarantine / Load → Reconcile → Audit**

1. **Extract (`extract.py`):**
   - Streaming generator with chunked processing (`chunk_size=1000`) for bounded memory usage.
   - Robust character encoding detection (`utf-8`, `utf-8-sig`, `latin-1`, `cp1252`) and delimiter sniffing (`,`, `;`, `\t`, `|`).
   - Header aliasing supporting varying CSV source naming conventions.
   - SHA-256 batch file checksumming.

2. **Validation (`validation.py`):**
   - Row-level schema validation with pre-cached catalog lookups to eliminate $N+1$ query overhead.
   - Strict range constraints: `quantity > 0`, `unit_price > 0`, `discount_amount >= 0`, `amount > 0`.
   - Referential integrity checks against `products`, `vendors`, and `customers`.
   - Structured error classification: `VALIDATION_ERROR`, `INVALID_DATA_TYPE`, `MISSING_FOREIGN_KEY`, `MALFORMED_ROW`.

3. **Deduplication & Idempotency (`deduplication.py`):**
   - Database-enforced composite idempotency key on `(source_system, source_transaction_id)`.
   - Catches in-batch duplicates (repeated rows in same upload) and cross-batch duplicates (re-uploaded transactions).
   - Invariant guarantee: Legacy historical records retain `NULL` source keys and remain 100% valid.

4. **Staging & Quarantine Management (`quarantine.py`):**
   - Isolates invalid rows into `etl_quarantine_records` while buffering all raw inputs in `etl_staging_records`.
   - Preserves original JSON payloads for full auditability.
   - Interactive triage: manual corrections can be submitted to re-validate and commit quarantined records.

5. **Loading & Transformation (`loading.py`, `transformation.py`):**
   - Transformed records snapshot the vendor's active commission rate at ingestion time.
   - Optional inventory synchronization decrements stock and logs `SALE` movements atomically.
   - Links staging records to generated `transaction_id`.

6. **Reconciliation & Data Quality (`reconciliation.py`):**
   - Computes source vs. staged vs. committed vs. quarantined vs. duplicate counts.
   - Monetary reconciliation: verifies batch gross sum equals actual database transaction amounts ($\Delta = 0.00$).
   - Platform-wide data quality benchmark reporting catalog health and referential integrity.

7. **Dimensional Data Warehouse (`daily_mart_service.py`):**
   - Aggregates operational sales into `daily_sales_mart` at `(date, product_id, vendor_id)` grain.
   - Preserves Stage 4 Nullable COGS rules: uncosted legacy items report `NULL` cost and profit with explicit coverage disclosures.
   - Idempotent upsert logic prevents aggregate duplication or GMV inflation on repeated refreshes.

8. **Scheduled Automation (`app/scheduler.py`):**
   - Nightly 01:30 AM background refresh job via APScheduler.
   - Process-level overlap protection (`max_instances=1` and in-process execution lock).

---

## 4. Database Schema Additions (Stage 6)

| Table Name | Primary Key | Key Foreign Keys & Constraints | Description |
| :--- | :--- | :--- | :--- |
| `etl_batches` | `batch_id` (VARCHAR 50) | Status: `RECEIVED`, `PROCESSING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` | Ingestion batch lifecycle and audit summary. |
| `etl_staging_records` | `staging_id` (SERIAL) | `FK -> etl_batches(batch_id)`, `FK -> transactions(transaction_id)` | Staging buffer preserving raw CSV payloads. |
| `etl_quarantine_records` | `quarantine_id` (SERIAL) | `FK -> etl_batches(batch_id)`, `FK -> etl_staging_records(staging_id)` | Quarantined invalid rows with resolution status. |
| `daily_sales_mart` | `id` (SERIAL) | `UNIQUE(date, product_id, vendor_id)`, `FK -> products`, `FK -> vendors` | Dimensional data warehouse sales aggregates. |
| `transactions` *(extended)* | `transaction_id` (SERIAL) | `UNIQUE(source_system, source_transaction_id)` | Added external source tracking and idempotency. |

---

## 5. Technology Stack

- **Language:** Python 3.10+
- **Backend API:** FastAPI 0.111+ / Uvicorn (ASGI) / Pydantic 2.x
- **Database & Warehouse:** PostgreSQL 16 / SQLAlchemy 2.0 / `psycopg2-binary`
- **Data Analytics & ML:** Scikit-Learn 1.7+, Pandas 2.2+, NumPy
- **Experiment Tracking:** MLflow 2.x
- **Background Scheduling:** APScheduler 3.10+ (Cross-process file lock & overlap protection)
- **Interactive UI:** Streamlit / Plotly
- **Automated Testing:** Pytest 8.2+ / FastAPI TestClient / Streamlit AppTest / Locust

---

## 6. Directory Structure

```text
Retail Management Platform for Inventory Control and Sales Analytics/
├── app/
│   ├── core/
│   │   └── security.py                # Loopback protection for administrative endpoints
│   ├── models/
│   │   ├── vendor.py                  # Vendor ORM (commission tiers & compliance)
│   │   ├── product.py                 # Product catalog (nullable cost_price)
│   │   ├── inventory.py               # Inventory model (current_stock, reorder_level)
│   │   ├── transaction.py             # Transaction ledger (source idempotency keys)
│   │   ├── customer.py                # Customer ORM model
│   │   ├── stock_movement.py          # StockMovement audit logs
│   │   ├── customer_interaction.py    # Customer interaction events
│   │   ├── workflow_audit.py          # Pipeline execution audit logs
│   │   ├── refund.py                  # Atomic refund ledger
│   │   ├── vendor_settlement.py       # Vendor settlement ledger
│   │   └── etl.py                     # ETLBatch, Staging, Quarantine, DailySalesMart
│   ├── routes/
│   │   ├── vendor_routes.py           # Vendor operations & status updates
│   │   ├── product_routes.py          # Product catalog operations
│   │   ├── analytics_routes.py        # Baseline revenue analytics
│   │   ├── inventory_routes.py        # Inventory tracking & movements
│   │   ├── customer_routes.py         # Customer RFM, churn, and retention
│   │   ├── recommendation_routes.py   # Hybrid recommendations
│   │   ├── revenue_routes.py          # Advanced revenue benchmarks
│   │   ├── forecast_routes.py         # Demand forecasting endpoints
│   │   ├── report_routes.py           # PDF and Excel report exports
│   │   ├── refund_routes.py           # Atomic refund endpoints
│   │   ├── offer_routes.py            # Offer strategy & safety stock engine
│   │   ├── catalog_routes.py          # Catalog normalizer endpoints
│   │   └── etl_routes.py              # 12 ETL & Data Warehouse REST endpoints
│   ├── services/
│   │   ├── etl/                       # Modular ETL & Data Warehouse Engine
│   │   │   ├── extract.py             # Chunked CSV extractor & encoding detector
│   │   │   ├── validation.py          # Row-level validator & range verifier
│   │   │   ├── deduplication.py       # In-batch & cross-batch deduplicator
│   │   │   ├── transformation.py      # Data normalizer & commission snapshotter
│   │   │   ├── loading.py             # Atomic transactional loader & inventory sync
│   │   │   ├── quarantine.py          # Quarantine triage & reprocessing workflow
│   │   │   ├── reconciliation.py      # Count & monetary reconciliation auditor
│   │   │   ├── batch_manager.py       # End-to-end pipeline orchestrator
│   │   │   └── daily_mart_service.py  # Dimensional daily mart aggregator
│   │   ├── customer_service.py        # RFM metrics & K-Means segmentation
│   │   ├── inventory_service.py       # Turnover, safety stock, DSI calculations
│   │   ├── recommendation_service.py  # Collaborative filtering engine
│   │   ├── hybrid_recommender.py      # Hybrid recommendation engine
│   │   ├── refund_service.py          # Atomic refund processor
│   │   ├── settlement_service.py      # Vendor payout ledger service
│   │   ├── catalog_normalizer.py      # Catalog taxonomy normalizer
│   │   └── offer_intelligence.py      # Offer elasticity & safety stock engine
│   ├── database.py                    # SQLAlchemy database engine
│   ├── scheduler.py                   # APScheduler background automation
│   └── main.py                        # FastAPI application entry point
├── dashboard/
│   └── dashboard.py                   # 10-View Streamlit Platform (including ETL view)
├── tests/
│   ├── conftest.py                    # Isolated SQLite database fixtures
│   ├── test_stage6_etl.py             # Dedicated Stage 6 test suite (20 scenarios)
│   ├── test_stage5_intelligence.py    # Stage 5 Customer Retention & ML tests
│   ├── test_stage4_commerce.py        # Stage 4 Commerce & Financial tests
│   ├── test_vendors.py                # Vendor validation tests
│   ├── test_products.py               # Product catalog tests
│   ├── test_inventory.py              # Inventory constraints tests
│   ├── test_analytics.py              # Baseline revenue tests
│   ├── test_inventory_analytics.py    # Inventory & forecasting tests
│   ├── test_customer_analytics.py     # RFM & segmentation tests
│   ├── test_recommendations.py        # Recommendation tests
│   ├── test_revenue_analytics.py      # Revenue benchmark tests
│   ├── test_reporting_and_validation.py # PDF/Excel and Locust tests
│   └── test_scheduler_pipeline.py     # Scheduler and pipeline audit tests
├── migrate_stage6.py                  # Idempotent Stage 6 PostgreSQL DDL migration
├── validate_consistency.py            # Platform-wide data consistency validation
└── README.md
```

---

## 7. Quickstart & Installation

### Step 1: Environment Setup
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy `.env.example` to `.env` and verify database settings:
```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/shopsense
TEST_DATABASE_URL=sqlite:///./test_shopsense.db
ENABLE_AUTO_SCHEDULER=true
```

### Step 3: Run Database Migrations
```powershell
# Applies Stage 6 tables and transaction idempotency keys safely
python migrate_stage6.py
```

### Step 4: Populate Dimensional Data Mart
```powershell
python -c "
from app.database import SessionLocal
from app.services.etl import refresh_daily_sales_mart
db = SessionLocal()
res = refresh_daily_sales_mart(db=db, full_rebuild=True)
print(res)
db.close()
"
```

### Step 5: Start Backend API
```powershell
uvicorn app.main:app --reload
```
Interactive Swagger API docs available at: `http://127.0.0.1:8000/docs`

### Step 6: Launch Streamlit Dashboard
```powershell
streamlit run dashboard/dashboard.py
```
Open `http://localhost:8501` to access all 10 dashboard views.

---

## 8. API Reference (Stage 6 Additions)

| Method | Endpoint | Description | Guard / Security |
| :--- | :--- | :--- | :--- |
| `POST` | `/etl/batches/upload` | Upload CSV for streaming chunked ingestion | Loopback-Guarded |
| `GET` | `/etl/batches` | List paginated ingestion batches with status filters | Public |
| `GET` | `/etl/batches/{batch_id}` | Retrieve batch status, counters, and error summaries | Public |
| `GET` | `/etl/batches/{batch_id}/records` | List raw/staged records for a specific batch | Public |
| `GET` | `/etl/batches/{batch_id}/reconciliation` | Retrieve structured count & monetary reconciliation | Public |
| `GET` | `/etl/quarantine` | List quarantined records with status/category filters | Public |
| `GET` | `/etl/quarantine/{record_id}` | Retrieve single quarantined record detail | Public |
| `POST` | `/etl/quarantine/{record_id}/reprocess` | Submit manual corrections and reprocess record | Loopback-Guarded |
| `POST` | `/etl/batches/{batch_id}/reprocess` | Reprocess all pending quarantine records for batch | Loopback-Guarded |
| `POST` | `/etl/marts/daily-sales/refresh` | Trigger incremental or full Daily Sales Mart refresh | Loopback-Guarded |
| `GET` | `/etl/marts/daily-sales` | Query aggregated daily sales mart by dimensions | Public |
| `GET` | `/etl/quality-report` | Platform-wide data quality & reconciliation score | Public |

---

## 9. Comprehensive Test Suite & Verification

### Running Tests
```powershell
# Run dedicated Stage 6 test suite (20 scenarios)
pytest tests/test_stage6_etl.py -v

# Run full repository regression suite (175 tests)
pytest tests/ -q

# Run platform consistency validation (12 assertions)
python validate_consistency.py
```

### Test Suite Summary
- **Stage 6 Dedicated Suite:** **20 / 20 passed (100%)**
- **Full Repository Suite:** **175 / 175 passed (100%)**
- **Consistency Verification:** **12 / 12 passed (100.0% Consistency Score)**
- **Streamlit AppTest:** **10 / 10 views passed (0 exceptions)**

---

## 10. Historical Data Integrity & Invariants

PostgreSQL database verification confirms zero data loss and zero synthetic data fabrication:
- **Vendors:** 5 (unchanged)
- **Products:** 10 (unchanged; legacy products strictly retain `NULL` cost_price)
- **Customers:** 60 (unchanged)
- **Transactions:** 600 completed orders across 2024 (unchanged)
- **Physical Stock On Hand:** 990 units (unchanged)
- **Stock Movements:** 440 records (unchanged)
- **Customer Interactions:** 1,342 records (unchanged)
- **Refunds:** 0 records (unchanged)
- **Settlements:** 0 records (unchanged)
- **Gross Merchandise Value (GMV):** ₹87,725.58 (exact match across operational DB and dimensional mart)
- **Daily Sales Mart:** 541 dimensional records aggregating 100% of historical transactions.
