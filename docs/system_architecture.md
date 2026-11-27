# ShopSense Technical Architecture & System Overview

**Platform:** ShopSense (StockPilot) — Multi-Vendor Retail Management, Analytics & Data Warehouse Platform  
**Version:** `1.0.0` (`backend/config.py`)  
**Milestone Coverage:** Milestones 1–4 (Stages 1–8 Core Platform + Vendor Onboarding + UI Redesign + 100K Benchmark, Executive Analytics APIs, Executive BI Dashboard, Performance Validation & Hardening)

---

## 1. System Component Overview

ShopSense follows a modular service-oriented architecture separating interactive analytics presentation, REST API orchestration, business/ML services, background job automation, and relational/dimensional persistence:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        Streamlit Web Application                           │
│   dashboard/dashboard.py + dashboard/executive_bi.py + dashboard/ui_theme  │
│   • Login-First Auth Gate (Sign In / Customer Register / Vendor Apply)     │
│   • Midnight Navy & Electric Violet Role-Scoped Navigation:                │
│     ADMIN (12 views) | VENDOR (6 views) | CUSTOMER (3 views)               │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │ HTTPS / HTTP REST + JWT Bearer
                                        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Backend (ASGI)                           │
│              app/main.py (Uvicorn) + app/core/dependencies.py              │
│   16 Router Modules: Auth, Admin, Vendors, Products, Inventory, Executive, │
│   Revenue, Analytics, Customers, Recommendations, Forecast, Refunds,       │
│   Offers, Catalog, Reports (PDF/XLSX), ETL & Warehouse                     │
└──────┬─────────────────────────────┬──────────────────────────┬────────────┘
       │                             │                          │
       ▼                             ▼                          ▼
┌─────────────────────┐  ┌─────────────────────────┐  ┌──────────────────────┐
│   Service & ML      │  │   ETL & Warehouse       │  │  Background Jobs &   │
│   app/services/     │  │   app/services/etl/     │  │  Experiment Tracking │
│ • executive_service │  │ • extract / validation  │  │ • app/scheduler.py   │
│ • revenue_service   │  │ • deduplication / load  │  │   (APScheduler + OS  │
│ • inventory_service │  │ • quarantine / reconcile│  │    process file lock)│
│ • customer / churn  │  │ • daily_mart_service    │  │ • track_inventory.py │
│ • clv / cohort      │  │   (DailySalesMart)      │  │   (MLflow Server /   │
│ • hybrid_recommender│  └───────────┬─────────────┘  │    sqlite:///mlflow) │
└──────┬──────────────┘              │                └──────────┬───────────┘
       │                             │                           │
       └─────────────────────────────┼───────────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │   PostgreSQL Relational DB      │
                    │     (SQLAlchemy 2.0 ORM,        │
                    │      16 Core & Mart Tables)     │
                    └─────────────────────────────────┘
```

### Runtime Entry Points
| Layer | Entry Point | Purpose | Default Port |
| :--- | :--- | :--- | :---: |
| **Backend API** | `app/main.py` (`backend/api/main.py` alias) | FastAPI application, 16 routers, `/health/live`, `/health/ready`, APScheduler lifecycle | `8000` |
| **Dashboard UI** | `dashboard/dashboard.py` | Streamlit UI consuming FastAPI APIs (with bounded local DB/service fallbacks in offline/test harness mode) | `8501` |
| **MLflow Tracking** | `mlflow server` (`sqlite:///mlflow.db`) | Experiment runs, parameters, validation metrics (`MAE`, `RMSE`, `WAPE`, `R2`), and model registry (`InventoryForecast`) | `5000` |
| **Container Init** | `docker_entrypoint.py` / `docker-entrypoint.sh` | DB wait, non-destructive `create_all`, migrations, fresh-only seeding, admin bootstrap | Container init |

---

## 2. Database Schema & Relationships (16 ORM Tables)

Defined across `app/models/` and registered via `app/models/__init__.py`. Engine pooled in `app/database.py` (`pool_size=30`, `max_overflow=20`, `pool_pre_ping=True` on PostgreSQL; `check_same_thread=False` on SQLite tests).

| Table | Primary Key | Key Foreign Keys & Uniqueness | Role in Platform |
| :--- | :--- | :--- | :--- |
| `vendors` | `id` | `UNIQUE(email)` | Marketplace sellers (`PENDING_APPROVAL`, `ACTIVE`, `LEGACY_ACTIVE`, `SUSPENDED`, `REJECTED`, `TERMINATED`), commission tiers (`TIER_STARTER`, `TIER_STANDARD`, `TIER_PREFERRED`, `TIER_ENTERPRISE`), `commission_rate`, compliance, `owner_name`, `tax_id`. |
| `products` | `id` | `FK vendor_id -> vendors.id` | Product catalog (`price`, nullable `cost_price`, `category`, `parent_category`). Nullable `cost_price` enables honest COGS-coverage accounting. |
| `inventory` | `inventory_id` | `UNIQUE / FK product_id -> products.id` | Live physical stock (`current_stock`), `warehouse`, `reorder_level`. |
| `customers` | `customer_id` | `UNIQUE(email)` | Customer profiles (`name`, `email`, `city`, `region`, `signup_date`). |
| `transactions` | `transaction_id` | `FK product_id`, `FK vendor_id`, `FK customer_id` (nullable); `UNIQUE(source_system, source_transaction_id)` | Purchase ledger storing `quantity`, `unit_price`, `amount`, `discount_amount`, `effective_commission_rate`, `payment_method`, `payment_status`, `transaction_date`. Phase 4 indexes: `ix_transactions_transaction_date`, `ix_transactions_vendor_date`, `ix_transactions_product_date`, `ix_transactions_customer_date`. |
| `stock_movements` | `movement_id` | `FK product_id -> products.id` | Immutable audit trail for `SALE`, `RESTOCK`, `RETURN`, `ADJUSTMENT`. |
| `customer_interactions` | `interaction_id` | `FK customer_id -> customers.customer_id`, `FK product_id -> products.id` | Behavioral weights (`view=1.0`, `cart=2.5`, `purchase=4.0`, rating `1.0–5.0`) used for CF recommendations and churn signals. |
| `refunds` | `refund_id` | `FK transaction_id -> transactions.transaction_id`, `UNIQUE(idempotency_key)` | Idempotent full/partial refund records (`COMPLETED`, `REJECTED`, etc.) with optional restocking. Phase 4 composite index: `ix_refunds_status_tx(status, transaction_id)`. |
| `vendor_settlements` | `settlement_id` | `FK vendor_id -> vendors.id` | Periodic vendor settlement accounting (`gross_sales`, `discounts`, `refunds`, `net_sales`, `platform_commission`, `vendor_payout`). |
| `users` | `id` | `UNIQUE(email)`, `FK vendor_id`, `FK customer_id` | Auth credentials (`bcrypt` hash), `role` (`ADMIN`, `VENDOR`, `CUSTOMER`), `is_active`, `is_verified`, `token_version`. |
| `refresh_tokens` | `id` | `FK user_id -> users.id`, `UNIQUE(token_hash)`, `UNIQUE(jti)` | SHA-256 hashed refresh tokens with `token_family` replay detection and `is_revoked` flags. |
| `etl_batches` | `batch_id` | PK `VARCHAR(50)` | CSV ingestion batch header (`file_hash`, counts, `total_gross_value`, `status`). |
| `etl_staging_records` | `staging_id` | `FK batch_id`, `FK target_transaction_id -> transactions.transaction_id` | Raw staged CSV JSON rows with validation state. |
| `etl_quarantine_records` | `quarantine_id` | `FK batch_id`, `FK staging_id` | Invalid CSV rows queued for manual correction/reprocessing. |
| `daily_sales_mart` | `id` | `UNIQUE(date, product_id, vendor_id)`, `FK product_id`, `FK vendor_id` | Dimensional warehouse rollup with `cogs_coverage_pct` and nullable `reported_gross_profit`. |
| `workflow_audit_logs` | `id` | `UNIQUE(run_id)` | APScheduler & manual pipeline execution history (`SUCCESS`, `PARTIAL`, `FAILED`, JSON per-task timings). |

---

## 3. Authentication, RBAC & Tenant Isolation

- **Password & Token Security (`app/core/security.py`, `app/core/config.py`):**
  - Passwords hashed using **bcrypt** (configurable `BCRYPT_ROUNDS=12`).
  - Access JWT (`HS256`, default 30-min expiry `ACCESS_TOKEN_EXPIRE_MINUTES`) carries `sub`, `email`, `role`, `vendor_id`, `customer_id`, `token_version`, `jti`, `type="access"`.
  - Refresh JWT (`HS256`, default 7-day expiry `REFRESH_TOKEN_EXPIRE_DAYS`) stores only a SHA-256 digest in `refresh_tokens`. Presenting an already-revoked refresh token invalidates its entire `token_family`.
  - Logout (`/auth/logout`, `/auth/logout-all`) and password changes increment `token_version` and/or blacklist active `jti` values (`_REVOKED_ACCESS_JTIS`).
- **RBAC Dependencies (`app/core/dependencies.py`):**
  - `require_admin`: restricts platform governance, user management, vendor approval, ETL/warehouse, refund issuance, and global Executive Analytics to `ADMIN`.
  - `require_vendor_or_admin`: permits `ADMIN` (global or specified `vendor_id`) and `VENDOR` (strictly own `vendor_id`).
  - `verify_vendor_tenant` & `verify_customer_tenant`: return `HTTP 403 Forbidden` if a `VENDOR` or `CUSTOMER` requests another tenant's resource ID.
  - Note: `_is_legacy_test_client` allows unauthenticated loopback access only inside active automated test runs (`pytest` in `sys.modules` or `ENVIRONMENT in {"test","testing"}` with `ALLOW_LEGACY_TEST_BYPASS=true`) when `X-Enforce-Auth` and proxy headers are absent. It is **strictly disabled** in production and normal runtime.
- **Vendor Onboarding Flow (Stages A & B):**
  1. Prospective seller submits `POST /auth/register-vendor` via UI (`Register as Vendor`) or API -> atomically creates `Vendor(status="PENDING_APPROVAL")` and linked `User(role="VENDOR")`.
  2. Pending vendor may sign in to view onboarding status and verification notes (`/vendors/me`), while store catalog write/management actions remain gated by `ACTIVE`/`LEGACY_ACTIVE` approval state.
  3. Admin reviews pending applications in **Vendor Management -> Pending Applications** and confirms Approve (`ACTIVE`, `VERIFIED`, commission tier) or Reject (`REJECTED`, `FLAGGED`, mandatory notes) via `PUT /vendors/{id}/status`.

---

## 4. Analytics, ETL, Scheduler & MLflow Architecture

### Executive Analytics Engine & BI Dashboard (Milestone 4 Phases 2–3)
- **Backend (`app/services/executive_service.py`, `app/routes/executive_routes.py`):**
  - `GET /analytics/executive/summary` (`ADMIN`): Aggregates GMV, discounts, refunds, net sales, COGS-guarded gross profit (`is_partial_profit`, `cogs_coverage_pct`), period-over-period comparisons, customer engagement (registered, purchasing, 90d active, repeat rate), ranked top vendors/products, inventory health/turnover, and monthly growth.
  - `GET /analytics/executive/trends` (`ADMIN`): Chronological `monthly` or `daily` revenue/order/AOV/growth series with daily-to-monthly rollup optimization.
  - `GET /analytics/executive/vendors` (`ADMIN`): Paginated vendor settlement rankings (`platform_commission`, `vendor_payout`, market share) and top products.
  - `GET /analytics/executive/vendor-summary` (`VENDOR` / `ADMIN`): Single-vendor tenant-isolated executive KPI snapshot.
- **Dashboard (`dashboard/executive_bi.py`):** Renders the Admin-only `💎 Executive BI` page with Midnight Navy/Electric Violet Plotly charts, inclusive date-range filtering, granularity toggle, explicit partial/0%-cost disclaimers, empty-window states, and strict API error surfacing.

### ETL & Data Warehouse (`app/services/etl/`)
- **Pipeline Stages:** `extract.py` (streaming chunked CSV reader with encoding & delimiter sniffing) -> `validation.py` (4 error categories) -> `deduplication.py` (`(source_system, source_transaction_id)`) -> `quarantine.py` -> `transformation.py` & `loading.py` (commission tier snapshotting, optional inventory decrement) -> `reconciliation.py` -> `daily_mart_service.py` (idempotent `DailySalesMart` upsert).

### Scheduler (`app/scheduler.py`)
- Uses `APScheduler` `BackgroundScheduler` guarded by an OS-level advisory lock (`stockpilot_scheduler.lock` via `msvcrt` on Windows / `fcntl` on Unix):
  - **`01:30 AM` (`daily_sales_mart_refresh`):** Refreshes `daily_sales_mart` (`DAILY_MART_CRON_HOUR`, `DAILY_MART_CRON_MINUTE`).
  - **`02:00 AM` (`daily_analytical_pipeline`):** Runs 5 analytical tasks (Forecast retraining + MLflow logging, Customer RFM & K-Means clustering, Recommendation similarity matrix refresh, Revenue metrics refresh, Low-stock alerts) and persists audit status (`SUCCESS`, `PARTIAL`, or `FAILED`) to `workflow_audit_logs`.
- Startup disabled cleanly via `DISABLE_BACKGROUND_SCHEDULER=true` or `ENABLE_SCHEDULER=false` (automatically skipped during `pytest`).

---

## 5. ML Models, Locations, Inputs/Outputs & Fallback Behavior

| Model / Engine | Location & Config Reference | Purpose | Inputs | Outputs | Verified Runtime / Fallback Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Monthly Demand Forecast (`RandomForestRegressor`)** | Config default `FORECAST_MODEL_PATH = models/forecast.pkl` (`backend/config.py`); saved artifact on disk: `models/inventory_model.pkl`; MLflow registered name: `InventoryForecast` | Monthly platform demand prediction (`GET /forecast/{month}`, `month` 1–24) | Month integer `[[month]]` | `forecast`, `units_predicted`, `model_name="RandomForest"` | `inventory_service.predict_monthly_demand` tries `settings.forecast_model_path` -> `models/inventory_model.pkl` -> MLflow Registry -> on-demand retrain (DB or canonical baseline). Because `models/forecast.pkl` does not exist by default while `models/inventory_model.pkl` is present, `/admin/health` reports `DEGRADED` fallback active cleanly. |
| **Product Daily Demand Forecast (Ridge Linear Regression)** | `app/services/inventory_service.py` (`forecast_product_demand`) | Per-SKU forward projection (`GET /analytics/inventory/forecast/{product_id}`) | Historical daily qty aggregated per SKU (`trend` index + 7 day-of-week one-hot features) | Daily `predicted_demand`, 95% confidence bounds, chronological 80/20 `MAE`, `RMSE`, `WAPE` | Computed dynamically in memory (`numpy.linalg.solve` with `reg_lambda=1.0`). Dashboard (`dashboard.py`) falls back to local CSV day-of-week heuristic only if live API is unreachable. |
| **Collaborative Filtering & Hybrid Recommender** | Config default `RECOMMENDATION_MODEL_PATH = models/recommender.pkl`; live services: `app/services/recommendation_service.py`, `app/services/hybrid_recommender.py` | Personalized & cold-start top-N recommendations (`/recommendations/*`, `/recommend/{id}`) | `customer_interactions` weights + `transactions` implicit purchases (`4.0`); TF-IDF over normalized catalog text | Top-N items filtered for stock > 0 & active vendors, rationale, holdout `Precision@K`, `Recall@K`, `Hit Rate`, `NDCG@K` | No static `models/recommender.pkl` is saved on disk; engine executes dynamically in memory with cold-start popularity fallback (`get_popular_products`). `/admin/health` reports `DEGRADED ("dynamic CF/TF-IDF engine")`. |
| **Customer Churn Prediction (`LogisticRegression`)** | `app/services/churn_service.py` | Predict customer churn probability & retention risk drivers (`/analytics/customers/churn*`) | Pre-cutoff features (`<= 2024-09-30`); target outcome window `2024-10-01`..`2024-12-31` | Churn probability, feature importances, 5-fold stratified CV ROC-AUC / F1 | Trained in memory (`C=0.1`, `StandardScaler`), cached in `_CHURN_CACHE`. |
| **Customer Segmentation (`KMeans`)** | `app/services/customer_service.py` | Behavioral RFM customer clustering (`/analytics/customers/segments`) | Recency, Frequency, Monetary per customer (`StandardScaler`) | Cluster IDs, persona labels, `silhouette_score` | Computed dynamically in memory; returns insufficient-data guard cleanly on empty/small tables. |
| **Predictive CLV (Bayesian Shrinkage)** | `app/services/clv_service.py` | 12-month forward CLV estimation (`/analytics/customers/clv*`) | Customer order tenure, AOV shrinkage (`n_0=3`), inactivity decay, churn `p_active` | Historical spend vs 12M predicted future value & loyalty tiers | Computed dynamically in memory from DB + `churn_service`. |

---

## 6. Performance Benchmarks & Phase 4 Optimization Summary

ShopSense separates isolated analytical stress validation from live system validation:
1. **Milestone 4 Phase 1 (Vectorized 100K Benchmark):** See [docs/benchmark_100k_report.md](benchmark_100k_report.md) (`benchmarks/run_100k_benchmark.py`, `seed=42`, `100,000` synthetic transactions in `0.933 s` across 8 Pandas/NumPy analytics workloads, `17.29 MB` heap peak).
2. **Milestone 4 Phase 4 (Integrated API + 100K Relational DB + SQL/Index Optimizations):** See [docs/phase4_performance_report.md](phase4_performance_report.md) (`benchmarks/phase4_performance_validation.py`).
   - Fixed a critical `HTTP 500` crash on `/analytics/revenue/profit-margins` at 100K rows (`OperationalError: too many SQL variables` -> rewritten via SQL `SUM(CASE)` in `86.07 ms`).
   - Accelerated `/analytics/revenue/growth` `79.22x` (`13,765.05 ms -> 173.76 ms`; heap `62.08 MB -> 0.096 MB`) and `/analytics/vendors/payouts` `13.88x` (`5,268.38 ms -> 379.62 ms`; SQL queries `52 -> 4`).
   - Reduced unfiltered `/analytics/executive/summary` SQL count (`20 -> 14`, `1,985.92 ms -> 1,477.47 ms`) and 6-month windowed executive summary `7.92x` (`2,254.56 ms -> 284.51 ms`).
   - Live single-worker localhost PostgreSQL (`606` txns) achieved `94.26 RPS` across 10 concurrent users (`955` requests, `0.0%` failure rate, `P95 = 182.19 ms`).

---

## 7. Complete API Endpoint Reference

| Domain | Endpoints & Methods | Guard / Scope |
| :--- | :--- | :--- |
| **Health & Admin** | `GET /`, `GET /health/live`, `GET /health/ready`; `GET /admin/overview`, `GET /admin/stats`, `GET /admin/health` | Probes public; `/admin/*` `ADMIN` only |
| **Auth & Users** | `POST /auth/register`, `POST /auth/register-vendor`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/logout-all`, `POST /auth/change-password`; `POST/GET /auth/admin/users`, `GET /auth/admin/users/{user_id}`, `PATCH /auth/admin/users/{user_id}/status`, `PATCH /auth/admin/users/{user_id}/role` | Public reg/login; Bearer session ops; `/auth/admin/*` `ADMIN` only |
| **Executive Analytics** | `GET /analytics/executive/summary`, `GET /analytics/executive/trends`, `GET /analytics/executive/vendors`, `GET /analytics/executive/vendor-summary` | First 3 `ADMIN` only; `vendor-summary` `VENDOR` (own) / `ADMIN` |
| **Vendors & Onboarding** | `POST /vendors/`, `GET /vendors/`, `GET /vendors/me`, `GET/PUT /vendors/{vendor_id}`, `PUT /vendors/{vendor_id}/status` | Create/list/status `ADMIN` only; `/me` own `VENDOR`; get/update `VENDOR` (own) or `ADMIN` |
| **Products & Catalog** | `POST/GET /products/`, `GET/PUT /products/{product_id}`; `GET /catalog/normalize`, `GET /catalog/normalize/{product_id}` | `GET /products/*` public; catalog write `VENDOR` (own approved) / `ADMIN` |
| **Inventory & Forecasting** | `GET /analytics/inventory/status`, `movements`, `turnover`, `low-stock`, `replenishment`, `forecast/{product_id}`, `GET /forecast/{month}`; `POST /inventory/movements` | Analytics read / `POST /inventory/movements` `VENDOR` (own) / `ADMIN` |
| **Revenue & Sales** | `GET /analytics/revenue`, `revenue/total`, `revenue/by-vendor`, `revenue/by-product`, `top-selling-product`, `summary`, `transactions`, `vendor-performance`, `revenue/growth`, `revenue/benchmarking`, `revenue/profit-margins`, `revenue/by-category`, `revenue/by-region`, `vendors/payouts` | Tenant-filtered where applicable (`vendor-performance`, `vendors/payouts`, `transactions`) and `ADMIN`-guarded on benchmarking |
| **Customers & Recs** | `GET /analytics/customers`, `summary`, `rfm`, `segments`, `churn`, `churn/{customer_id}`, `cohorts`, `clv`, `clv/{customer_id}`, `conversion-funnel`; `GET /recommend/{customer_id}`, `/recommendations/customer/{customer_id}`, `popular`, `evaluation`, `hybrid/evaluation`, `hybrid/{customer_id}` | Customer-scoped endpoints enforce `verify_customer_tenant` (`CUSTOMER` own ID or `ADMIN`) |
| **Commerce, Reports & ETL** | `POST /refunds/`, `GET /refunds/{refund_id}`, `/refunds/transaction/{transaction_id}`; `GET /offers/strategy`, `stock-impact/{product_id}`, `elasticity/{product_id}`, `POST /offers/stock-impact`; `GET /reports/pdf`, `/reports/excel`; `POST /etl/batches/upload`, `GET/POST /etl/*`, `GET /analytics/pipeline/audit`, `POST /analytics/pipeline/run` | Refunds/ETL/Pipeline `ADMIN` only |

---

## 8. Environment Variables & Configuration (`backend/config.py`, `app/core/config.py`)

| Variable | Default / Fallback | Required in Prod? | Purpose |
| :--- | :--- | :---: | :--- |
| `ENVIRONMENT` / `ENV` | `development` | Recommended (`production`) | Disables SQLite fallback and legacy test bypasses when `production`/`prod`. |
| `DATABASE_URL` | Dev fallback `sqlite:///./test_shopsense.db` (normalized `postgres://` -> `postgresql://`) | **Yes (PostgreSQL)** | Primary SQLAlchemy database connection string. |
| `JWT_SECRET_KEY` | Insecure Stage 7 dev default string (`app/core/config.py`) | **Yes (>= 32 chars)** | Cryptographic signing key actually read by `app/core/security.py` for access/refresh JWTs. |
| `SECRET_KEY` | Insecure dev string (`backend/config.py`, `.env.example`, `docker-compose.yml`) | Recommended | Config/compose template key (keep identical to `JWT_SECRET_KEY` across `.env` / Compose). |
| `API_BASE_URL` | `http://127.0.0.1:8000` (`http://backend:8000` in Compose) | For Dashboard | FastAPI URL called by Streamlit UI (`dashboard/dashboard.py`). |
| `MLFLOW_TRACKING_URI` | `sqlite:///./mlflow.db` (`http://mlflow:5000` in Compose) | Optional | MLflow backend store or HTTP server URI. |
| `FORECAST_MODEL_PATH` | `models/forecast.pkl` | Optional | Primary forecast `.pkl` path (`models/inventory_model.pkl` is fallback if absent). |
| `RECOMMENDATION_MODEL_PATH` / `RECOMMENDER_MODEL_PATH` | `models/recommender.pkl` | Optional | Recommender `.pkl` path (dynamic in-memory CF/TF-IDF used if absent). |
| `MAX_RECORDS` | `100000` | Optional | Config sanity cap (> 0 integer validated at startup). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` / `BCRYPT_ROUNDS` | `30` / `7` / `12` | Optional | JWT lifetime & bcrypt cost (`app/core/config.py`). |
| `DISABLE_BACKGROUND_SCHEDULER` / `ENABLE_SCHEDULER` | `false` / `true` | Optional | Disable scheduler in multi-instance/test setups if needed. |
| `DAILY_MART_CRON_HOUR` / `MINUTE` | `1` / `30` | Optional | Nightly Daily Sales Mart refresh cron schedule (default 01:30 AM). |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Set in `.env.example` / Compose | For Bootstrap | Used by `bootstrap_admin.py` and `docker_entrypoint.py`. |
