# ShopSense / StockPilot — Multi-Vendor Retail Management, Analytics & Data Warehouse Platform
> **Smarter Stock. Better Decisions.**  
> *Infosys Springboard Internship Project — Stages 1 through 7 Complete*

---

## 1. Executive Overview

**ShopSense (StockPilot)** is an enterprise multi-vendor retail management, analytics, machine learning, and data warehousing platform. Designed with a modular service-oriented architecture using **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0**, and **Streamlit**, ShopSense provides:

- **End-to-End Retail Operations:** Vendor onboarding, category hierarchies, product catalogs, physical inventory tracking, and transaction ledgers.
- **Advanced Commerce & Financial Operations (Stage 4):** Commission tiers with transaction-time rate snapshotting, nullable Cost of Goods Sold (COGS) reporting with explicit coverage disclosure, atomic refunds with idempotency, and vendor settlement ledgers.
- **Customer Retention & Intelligence Engine (Stage 5):** Temporal churn prediction, cohort retention matrices, customer lifetime value (CLV), item-based collaborative filtering, catalog taxonomy normalization, and promotion safety stock validation.
- **Structured ETL, Bulk Ingestion & Data Warehouse (Stage 6):** Chunked CSV data ingestion, staging buffer, row-level validation, database-enforced deduplication, quarantine triage and reprocessing, automated reconciliation, and dimensional data marts with scheduled refresh.
- **Authentication, JWT Security & Multi-Tenant RBAC (Stage 7):** Bcrypt credential hashing, JWT access and refresh token lifecycle, refresh token family rotation with reuse detection, public customer registration with role escalation protection, backend-enforced multi-tenant vendor isolation, customer data privacy, administrative bootstrap CLI, and authentication-aware Streamlit navigation.

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

## 4. Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control

### A. Security Architecture & Specifications
1. **Cryptographic Protection (`app/core/security.py`):**
   - **Password Hashing:** Bcrypt work factor 12 with automatic per-user salt generation.
   - **Token Signing:** HMAC-SHA256 (`HS256`) cryptographically signed JWTs using high-entropy secret key.
   - **Token Hashing:** SHA-256 digests stored in the database for refresh tokens (zero plaintext token storage).

2. **JWT Lifecycle & Token Family Rotation:**
   - **Access Tokens:** Short-lived (30 minutes), carrying claims: `sub` (user_id), `email`, `role`, `vendor_id`, `customer_id`, `type="access"`, `iat`, `exp`, `jti`.
   - **Refresh Tokens:** Long-lived (7 days), carrying claims: `sub`, `email`, `role`, `family` (UUID), `type="refresh"`, `jti`.
   - **Rotation & Reuse Detection:** Presenting a valid refresh token rotates it and issues a successor within the same `family`. If an already-rotated (revoked) token is presented (replay attack), the system immediately detects reuse and revokes **all** active tokens in that `family`.

3. **Role-Based Access Control (RBAC):**
   - `ADMIN`: Global oversight, user provisioning, role assignments, financial approvals (`/refunds/`, `/vendors/{id}/status`), ETL operations.
   - `VENDOR`: Strictly scoped to vendor's own catalog (`/products/`), inventory stock movements (`/inventory/movements`), and settlement payouts (`/analytics/vendors/payouts`). Cross-vendor operations return `HTTP 403 Forbidden`.
   - `CUSTOMER`: Personal profile management, customer-specific recommendations (`/recommendations/customer/{id}`), and order history. Cross-customer inquiries return `HTTP 403 Forbidden`.

4. **Public Self-Service Registration:**
   - Public registration (`POST /auth/register`) strictly assigns the `CUSTOMER` role. Role escalation attempts in the request payload are rejected. Automatically links existing shopper profile by email or verified customer ID.

5. **Administrative Bootstrap CLI (`bootstrap_admin.py`):**
   - Idempotent tool to initialize the root platform administrator (`python bootstrap_admin.py --email admin@shopsense.com --password <password>`).
   - Supports interactive hidden password prompts, CLI flags, or environment variables. Never logs plaintext credentials.

---

## 5. Database Schema Additions (Stages 6 & 7)

| Table Name | Primary Key | Key Foreign Keys & Constraints | Description |
| :--- | :--- | :--- | :--- |
| `users` | `id` (SERIAL) | `UNIQUE(email)`, `role IN ('ADMIN', 'VENDOR', 'CUSTOMER')`, `FK -> vendors`, `FK -> customers` | Platform identity, hashed passwords, roles, and entity links. |
| `refresh_tokens` | `id` (SERIAL) | `UNIQUE(token_hash)`, `UNIQUE(jti)`, `FK -> users(id) ON DELETE CASCADE` | Refresh token hash storage, token families, and revocation audit. |
| `etl_batches` | `batch_id` (VARCHAR 50) | Status: `RECEIVED`, `PROCESSING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` | Ingestion batch lifecycle and audit summary. |
| `etl_staging_records` | `staging_id` (SERIAL) | `FK -> etl_batches(batch_id)`, `FK -> transactions(transaction_id)` | Staging buffer preserving raw CSV payloads. |
| `etl_quarantine_records` | `quarantine_id` (SERIAL) | `FK -> etl_batches(batch_id)`, `FK -> etl_staging_records(staging_id)` | Quarantined invalid rows with resolution status. |
| `daily_sales_mart` | `id` (SERIAL) | `UNIQUE(date, product_id, vendor_id)`, `FK -> products`, `FK -> vendors` | Dimensional data warehouse sales aggregates. |
| `transactions` *(extended)* | `transaction_id` (SERIAL) | `UNIQUE(source_system, source_transaction_id)` | Added external source tracking and idempotency. |

---

## 6. Technology Stack

- **Language:** Python 3.10+
- **Backend API:** FastAPI 0.111+ / Uvicorn (ASGI) / Pydantic 2.x
- **Authentication & Security:** `bcrypt` 5.0+ / `pyjwt` 2.15+ / `cryptography`
- **Database & Warehouse:** PostgreSQL 16 / SQLAlchemy 2.0 / `psycopg2-binary`
- **Data Analytics & ML:** Scikit-Learn 1.7+, Pandas 2.2+, NumPy
- **Experiment Tracking:** MLflow 2.x
- **Background Scheduling:** APScheduler 3.10+ (Cross-process file lock & overlap protection)
- **Interactive UI:** Streamlit / Plotly
- **Automated Testing:** Pytest 8.2+ / FastAPI TestClient / Streamlit AppTest / Locust

---

## 7. Directory Structure

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

## 8. API Reference (Stage 7 Additions)

| Method | Endpoint | Description | Guard / Security |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/register` | Public self-service customer registration | Public (CUSTOMER role enforced) |
| `POST` | `/auth/login` | Authenticate user credentials & issue JWT token pair | Public (Generic 401 on error) |
| `POST` | `/auth/refresh` | Rotate refresh token with reuse attack detection | Bearer Refresh Token |
| `GET` | `/auth/me` | Retrieve profile of authenticated user | Authenticated (Any Role) |
| `POST` | `/auth/logout` | Revoke current refresh token session | Authenticated (Any Role) |
| `POST` | `/auth/logout-all` | Revoke all active sessions across all devices | Authenticated (Any Role) |
| `POST` | `/auth/change-password` | Update user password and terminate old sessions | Authenticated (Any Role) |
| `POST` | `/auth/admin/users` | Admin provision new user (ADMIN, VENDOR, CUSTOMER) | ADMIN Only |
| `GET` | `/auth/admin/users` | Admin list system users with role filters | ADMIN Only |
| `GET` | `/auth/admin/users/{id}` | Admin fetch single user details | ADMIN Only |
| `PATCH` | `/auth/admin/users/{id}/status` | Admin activate/deactivate user | ADMIN Only |
| `PATCH` | `/auth/admin/users/{id}/role` | Admin change role and entity linkage | ADMIN Only |

---

## 9. Comprehensive Test Suite & Verification

### Running Tests
```powershell
# Run dedicated Stage 7 security test suite (46 scenarios)
pytest tests/test_stage7_auth_security.py -v

# Run full repository regression suite (221 tests)
pytest tests/ -q

# Run platform consistency validation (12 assertions)
python validate_consistency.py
```

### Test Suite Summary
- **Stage 7 Dedicated Suite:** **46 / 46 passed (100%)** (including Stage 7.1 session revocation & backend authorization hardening)
- **Stage 6 Dedicated Suite:** **20 / 20 passed (100%)**
- **Full Repository Suite:** **221 / 221 passed (100%)**
- **Consistency Verification:** **12 / 12 passed (100.0% Consistency Score)**
- **Streamlit AppTest:** **10 / 10 views passed (0 exceptions)**

---

## 10. Historical Data Integrity & Invariants

PostgreSQL database verification confirms zero data loss and zero synthetic data fabrication:
- **Users:** 1 root administrator bootstrap account; zero fabricated passwords for legacy entities.
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
