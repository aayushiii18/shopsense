# ShopSense / StockPilot — Multi-Vendor Retail Management, Analytics & Data Warehouse Platform
> **Smarter Stock. Better Decisions.**  
> *Milestones 1–4 Engineering Complete — `DEF-UAT-01..03` Resolved & `305 / 305` Regression Suite Verified | External Stakeholder UAT Pending | Docker Not Installed on Host | `100` Concurrent Users Reached (`500`-User Target Requires Multi-Worker Scale)*

---

## Documentation Suite (`docs/`)

| Document | Audience | Purpose |
| :--- | :--- | :--- |
| [System Architecture](docs/system_architecture.md) | Engineers & Architects | Component overview, 16-table DB schema, RBAC/JWT, ETL, APScheduler, MLflow/models & fallbacks, full API & env reference |
| [Deployment & Setup Guide](docs/deployment_setup_guide.md) | DevOps & Engineers | Host setup, PostgreSQL config, `.env` secrets, migrations, admin bootstrap, startup & Docker Compose topology *(Docker runtime not verified on Windows host)* |
| [Operations Manual](docs/operations_manual.md) | Operators & Admins | Health triage, degraded fallback modes, ETL quarantine, MLflow retraining, backups, benchmarks & troubleshooting |
| [User Guide](docs/user_guide.md) | Admin, Vendor & Customer | Login gate, vendor onboarding/approval, Executive BI, catalog, inventory, refunds, forecasting & recommendations |
| [UAT Test Plan](docs/uat_test_plan.md) | QA & Stakeholders | 16 role-based UAT scenarios & >= 85% acceptance criteria (**External Stakeholder UAT: `PENDING EXTERNAL VALIDATION`**) |
| [UAT Recording Template](docs/uat_recording_template.md) | QA & Stakeholders | Developer pre-UAT execution record (`DEF-UAT-01..03` closed) + pending stakeholder evaluation & sign-off sheet |
| [Step 12 UAT Execution Report](docs/uat_execution_report.md) | QA & Engineering | Developer functional UAT outcomes (`8 PASS / 7 PARTIAL / 1 BLOCKED / 0 FAIL`) & `DEF-UAT-01..03` closure verification |
| [100K Benchmark Report](docs/benchmark_100k_report.md) | Performance / Eng | Milestone 4 Phase 1 vectorized 100K transaction dataset & analytics benchmark |
| [Phase 4 Performance Report](docs/phase4_performance_report.md) | Performance / Eng | Integrated live PostgreSQL + isolated 100K relational DB baseline vs post-optimization telemetry |
| [Step 11 Load Testing Report](docs/load_testing_report.md) | Performance / Ops | Progressive authenticated Locust load test (`50 -> 100` concurrent users reached cleanly; `500`-user target not achieved on 1-worker host) |
| [Milestone 4 Final Report](docs/milestone4_final_report.md) | Leadership & Reviewers | Final Milestone 4 closure summary: Phases 1–5 results, `DEF-UAT-01..03` fixes, Docker/load disclosures, `305`-test pass, DB preservation & commit history |

---

## 1. Executive Overview

**ShopSense (StockPilot)** is an enterprise multi-vendor retail management, analytics, machine learning, and data warehousing platform. Designed with a modular service-oriented architecture using **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0**, and **Streamlit**, ShopSense provides:

- **End-to-End Retail Operations:** Vendor onboarding, category hierarchies, product catalogs, physical inventory tracking, and transaction ledgers.
- **Advanced Commerce & Financial Operations (Stage 4):** Commission tiers with transaction-time rate snapshotting, nullable Cost of Goods Sold (COGS) reporting with explicit coverage disclosure, atomic refunds with idempotency, and vendor settlement ledgers.
- **Customer Retention & Intelligence Engine (Stage 5):** Temporal churn prediction, cohort retention matrices, customer lifetime value (CLV), item-based collaborative filtering, catalog taxonomy normalization, and promotion safety stock validation.
- **Structured ETL, Bulk Ingestion & Data Warehouse (Stage 6):** Chunked CSV data ingestion, staging buffer, row-level validation, database-enforced deduplication, quarantine triage and reprocessing, automated reconciliation, and dimensional data marts with scheduled refresh.
- **Authentication, JWT Security & Multi-Tenant RBAC (Stage 7 / 7.1):** Bcrypt credential hashing, JWT access and refresh token lifecycle, refresh token family rotation with reuse detection, token versioning with immediate revocation on logout/password change/deactivation, backend-enforced multi-tenant vendor isolation, customer data privacy, administrative bootstrap CLI, and authentication-aware Streamlit navigation.
- **Docker, Containerization, CI/CD & Final Integration (Stage 8):** Production-grade multi-service Docker Compose topology (PostgreSQL, FastAPI backend, Streamlit dashboard, MLflow tracking server), non-root user execution, automated idempotent schema initialization entrypoint, service dependency healthchecks, named persistent volumes, and GitHub Actions automated CI verification pipeline.

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
# Run production configuration test suite
pytest tests/test_config.py -v

# Run dedicated Stage 7 authentication & security test suite
pytest tests/test_stage7_auth_security.py -v

# Run Executive Analytics API, BI Dashboard & Phase 4 performance tests
pytest tests/test_executive_api.py tests/test_executive_bi_dashboard.py tests/test_phase4_performance.py -v

# Run full repository regression suite
pytest tests/ -q

# Run platform consistency validation (12 assertions)
python validate_consistency.py
```

### Verification Summary (Milestone 4 Closure)
- **Full Repository Regression Suite:** **305 / 305 passed (`pytest tests/ -q`, `0` 1st-party deprecation warnings, post-`DEF-UAT-01..03` fixes)**
- **Consistency Verification:** **12 / 12 passed (`100.0%` Consistency Score, `validate_consistency.py`)**
- **100K Scale Validation:** Verified via isolated vectorized & relational benchmarks ([docs/benchmark_100k_report.md](docs/benchmark_100k_report.md), [docs/phase4_performance_report.md](docs/phase4_performance_report.md))
- **Dashboard Latency & UI Closure:** Admin `📊 Dashboard` cold load improved `18,947.47 ms -> 6,369.57 ms` (`2.97x` parallel) / `6,881.45 ms` (`2.75x` sequential spy), version caption aligned to `v1.0.0`, and `78` `use_container_width` + `@app.on_event` deprecations resolved ([docs/uat_execution_report.md](docs/uat_execution_report.md))
- **Progressive Load & Functional UAT:** Reached `100` concurrent users (`50` stable, `0` failures, `P95 7,000 ms` ceiling; `500`-user target `NOT ACHIEVED` on 1-worker host; [docs/load_testing_report.md](docs/load_testing_report.md)) and completed Developer-Assisted UAT (`8 PASS / 7 PARTIAL / 1 BLOCKED / 0 FAIL`; External Stakeholder UAT `PENDING EXTERNAL VALIDATION`; Docker runtime `NOT VERIFIED`) — full closure report in [docs/milestone4_final_report.md](docs/milestone4_final_report.md).

---

## 10. Historical Data Integrity & Invariants

Stage 7 migration & Milestone 4 verification enforce zero data loss and preserve historical records across migrations (`vendors`, `products` retaining nullable legacy `cost_price`, `customers`, `transactions`, `inventory`, `users`, and `daily_sales_mart` matching operational DB GMV).

---

## 11. Stage 8: Docker, Containerization & CI/CD Pipeline

ShopSense is fully containerized using Docker and orchestrated with Docker Compose. The architecture comprises four core interconnected services running on an isolated bridge network with healthcheck dependencies and persistent storage.

### A. Container Topology & Service Architecture

```
                                  ┌───────────────────────────┐
                                  │   Host Browser / Client   │
                                  └─────────────┬─────────────┘
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 │ :8501                        │ :8000                        │ :5000
                 ▼                              ▼                              ▼
  ┌──────────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
  │      shopsense-dashboard     │ │     shopsense-backend     │ │      shopsense-mlflow     │
  │     (Streamlit 10 Views)     │ │    (FastAPI REST APIs)    │ │ (Tracking Server & Registry)│
  │  Internal: :8501             │ │ Internal: :8000           │ │ Internal: :5000           │
  │  User: appuser (non-root)    │ │ User: appuser (non-root)  │ │ User: appuser (non-root)  │
  └──────────────┬───────────────┘ └─────────────┬─────────────┘ └─────────────┬─────────────┘
                 │                               │                             │
                 │ http://backend:8000           │ http://mlflow:5000          │
                 │                               │                             │
                 └───────────────────────────────┼─────────────────────────────┘
                                                 │
                                                 │ postgresql://db:5432/shopsense
                                                 ▼
                                  ┌───────────────────────────┐
                                  │        shopsense-db       │
                                  │   (PostgreSQL 15 Alpine)  │
                                  │ Internal: :5432           │
                                  │ Persistent: postgres_data │
                                  └───────────────────────────┘
```

### B. Docker Compose Services & Port Mappings

| Service | Container Name | Image / Build | Port Mapping | Healthcheck Endpoint / Command |
|---|---|---|---|---|
| **Database** | `shopsense-db` | `postgres:15-alpine` | `5432:5432` | `pg_isready -U postgres -d shopsense` |
| **Backend API** | `shopsense-backend` | `./Dockerfile.backend` | `8000:8000` | `curl -f http://localhost:8000/docs` |
| **Dashboard** | `shopsense-dashboard` | `./Dockerfile.dashboard` | `8501:8501` | `curl -f http://localhost:8501/_stcore/health` |
| **MLflow Server**| `shopsense-mlflow` | `./Dockerfile.backend` (mlflow cmd) | `5000:5000` | `curl -f http://localhost:5000/` |

### C. Prerequisites
- **Docker Desktop** (Windows / macOS) or **Docker Engine 20.10+ & Docker Compose V2** (Linux).
- Minimum 4 GB RAM recommended for multi-container orchestration.

### D. Environment Configuration
Copy `.env.example` to create `.env`:
```powershell
copy .env.example .env     # Windows PowerShell
# or
cp .env.example .env       # Linux / macOS
```
Key configuration parameters:
```dotenv
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/shopsense
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgrespassword
POSTGRES_DB=shopsense
POSTGRES_PORT=5432
API_BASE_URL=http://backend:8000
MLFLOW_TRACKING_URI=http://mlflow:5000
ADMIN_EMAIL=admin@shopsense.internal
ADMIN_PASSWORD=AdminSecure123!
SECRET_KEY=replace-with-a-secure-32-byte-hex-secret-in-production
```

### E. Quickstart with Docker Compose

1. **Build and start all services in background:**
   ```bash
   docker compose up --build -d
   ```

2. **Monitor startup and healthchecks:**
   ```bash
   docker compose ps
   docker compose logs -f backend
   ```

3. **Access application endpoints:**
   - **Streamlit Interactive UI:** [http://localhost:8501](http://localhost:8501)
   - **FastAPI Interactive Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **FastAPI OpenAPI Schema:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
   - **MLflow Tracking Server:** [http://localhost:5000](http://localhost:5000)
   - **PostgreSQL Database:** `localhost:5432` (user: `postgres`, db: `shopsense`)

4. **Stop services:**
   ```bash
   docker compose down
   ```

5. **Stop services and purge persistent storage:**
   ```bash
   docker compose down -v
   ```

### F. Automated Database Initialization & Idempotency
Container startup is managed by `docker_entrypoint.py`:
- **Readiness Polling:** Waits for PostgreSQL to accept socket connections with retry backoff.
- **Safe Schema Creation:** Invokes `Base.metadata.create_all(bind=engine)` ensuring tables exist without dropping existing tables.
- **Stage 7 Migration Check:** Executes `migrate_stage7.run_migration()` idempotently to verify `users`, `refresh_tokens`, and `token_version`.
- **Fresh vs. Existing Database Handling:**
  - **Fresh Database (0 vendors):** Automatically executes baseline ingestion from `data/` (`seed_data.py`), creating initial vendors, products, inventory, customers, transactions, stock movements, and customer interactions, followed by daily sales mart aggregation.
  - **Existing Database (vendors > 0):** Detects existing rows and preserves 100% of historical transactions, inventory, and customer records without modification or duplication.
- **Idempotent Admin Bootstrap:** Idempotently ensures the administrator account exists with credentials from `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

### G. Manual Database Management in Docker
If manual migration or administration is needed within containers:
```bash
# Execute Stage 7 migration check inside running backend container
docker compose exec backend python migrate_stage7.py

# Bootstrap or update administrator account
docker compose exec backend python bootstrap_admin.py --email admin@shopsense.internal --password NewPassword123! --force

# Run platform consistency validation inside container
docker compose exec backend python validate_consistency.py
```

### H. Local Development Startup (Without Docker)
For local development outside containers:
```powershell
# 1. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 2. Run database setup and migrations
python create_tables.py
python migrate_stage7.py
python seed_data.py
python bootstrap_admin.py --email admin@shopsense.internal --password AdminSecure123!

# 3. Start FastAPI backend (Terminal 1)
uvicorn app.main:app --reload --port 8000

# 4. Start Streamlit dashboard (Terminal 2)
streamlit run dashboard/dashboard.py

# 5. Start MLflow tracking server (Terminal 3)
mlflow server --backend-store-uri sqlite:///mlflow.db --port 5000
```

### I. GitHub Actions CI/CD Pipeline (`.github/workflows/ci.yml`)
The automated CI pipeline runs on every `push` and `pull_request` targeting `main`:
1. **Runner Environment:** `ubuntu-latest` with Python 3.10 and PostgreSQL 15 service container.
2. **Dependency Management:** Pip dependency caching for accelerated builds.
3. **Syntax & AST Validation:** Strict AST parsing across all Python modules to catch syntax and import errors.
4. **Database Migrations:** Automated table generation, Stage 7 migration execution, and seed data verification.
5. **Data Consistency Validation:** Runs `validate_consistency.py` ensuring 100.0% consistency score across 12 platform invariants.
6. **Dedicated Security Testing:** Runs all 46 Stage 7/7.1 authentication, JWT security, and RBAC tests (`test_stage7_auth_security.py`).
7. **Complete Regression Suite:** Runs all 221 unit, integration, ML, and financial tests across Stages 1–7.1.
8. **Streamlit AppTest Verification:** Headless rendering test confirming 0 exceptions across all 10 dashboard views.

### J. Persistent Volume Storage
- `shopsense-postgres-data`: Mounted to `/var/lib/postgresql/data`. Preserves transaction ledgers, customer accounts, and schema tables across container rebuilds.
- `shopsense-mlflow-data`: Mounted to `/mlflow`. Preserves MLflow experiment tracking SQLite database and model artifacts.

### K. Troubleshooting Common Startup Errors
1. **Port Conflict (`bind: address already in use`):**
   - If local PostgreSQL is running on host port `5432`, set `POSTGRES_PORT=5433` in `.env`.
   - If port `8000` or `8501` is occupied, change the host port mapping in `docker-compose.yml` (e.g. `"8080:8000"`, `"8502:8501"`).
2. **Backend Fails Health Check:**
   - Check container logs: `docker compose logs backend`.
   - Verify that the `db` service is healthy: `docker compose ps`.
3. **Streamlit Cannot Connect to API:**
   - Verify `API_BASE_URL` in `.env` is set to `http://backend:8000` (container-to-container), not `http://localhost:8000` (browser-to-host).
4. **Resetting Database to Clean State:**
   - Run `docker compose down -v` to delete persistent volumes.
   - Run `docker compose up --build -d` to spin up a fresh database with automatic initial catalog seeding.

