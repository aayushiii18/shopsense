# ShopSense Operations & Administration Manual

This manual provides day-to-day operational runbooks for platform operators and administrators managing **ShopSense (`1.0.0`)**.

---

## 1. Service Startup, Restart & Shutdown Lifecycle

### Standard Local Startup Sequence
Start dependencies in bottom-up order:
1. **PostgreSQL:** Confirm service is listening on configured `DATABASE_URL` port (`5432`).
2. **MLflow (`5000`):** `python -m mlflow server --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000`
3. **FastAPI (`8000`):** `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
4. **Streamlit (`8501`):** `python -m streamlit run dashboard/dashboard.py --server.port 8501 --server.address 127.0.0.1 --server.headless true`

### Graceful Shutdown & Restart
- Terminate **Streamlit -> FastAPI -> MLflow** in top-down order.
- Wait for FastAPI's `shutdown_event()` to log scheduler shutdown and release `stockpilot_scheduler.lock`. If FastAPI was killed abruptly on Windows/Unix leaving an orphaned process lock file with no running Uvicorn PID, remove `stockpilot_scheduler.lock` only after verifying no backend Python process holds it.

---

## 2. Health Monitoring & Degraded-Service Triage

ShopSense exposes unauthenticated infrastructure probes plus an admin-authenticated 7-component diagnostic endpoint (`GET /admin/health`) and Streamlit view (`🩺 Integration Status / System Health`).

| Endpoint | Auth | Healthy Response | Purpose |
| :--- | :---: | :--- | :--- |
| `GET /health/live` | Public | `HTTP 200` `{"status": "UP"}` | Process liveness (no DB query). |
| `GET /health/ready` | Public | `HTTP 200` `{"status": "READY"}` / `503` on DB down | Database readiness probe (`SELECT 1`). |
| `GET /admin/health` | `ADMIN` | `IntegrationStatusResponse` | Deep checks across 7 subsystems (masks all DB passwords/paths cleanly). |
| `GET /admin/overview`, `/admin/stats` | `ADMIN` | Counts, GMV, roles, model config paths | Administrative ledger and model readiness summary. |

### Interpreting `/admin/health` States (`HEALTHY`, `DEGRADED`, `UNAVAILABLE`)
1. **Database:** `UNAVAILABLE` if connection fails; `DEGRADED` if `SELECT 1` exceeds `1000 ms`.
2. **Sales API:** Checks registration of `/analytics/revenue`, `/analytics/transactions`, `/analytics/summary` and queries transaction count + GMV.
3. **Forecasting API:**
   - `HEALTHY`: Primary `FORECAST_MODEL_PATH` (`models/forecast.pkl`) exists and passes `.predict([[1]])`.
   - **`DEGRADED` (Expected Default Behavior):** `models/forecast.pkl` is absent, **but fallback `models/inventory_model.pkl` is present and valid** (`"operating via fallback 'models/inventory_model.pkl'"`).
   - `UNAVAILABLE`: Neither artifact loads validly (`FORECAST_MODEL_PATH` missing/corrupt). Run `python track_inventory.py` or set `FORECAST_MODEL_PATH=models/inventory_model.pkl` if strict `HEALTHY` status is desired.
4. **Recommendation API:**
   - `HEALTHY`: Serialized artifact at `RECOMMENDATION_MODEL_PATH` (`models/recommender.pkl`) loads via `joblib`.
   - **`DEGRADED` (Expected Default Behavior):** No `.pkl` artifact exists at `models/recommender.pkl`, **so the dynamic in-memory CF + TF-IDF engine serves live requests** from `products` and `customer_interactions`.
5. **MLflow:** Pings HTTP `/api/2.0/mlflow/experiments/search` & `/registered-models/search` (2.0s timeout) when `MLFLOW_TRACKING_URI` is `http(s)://...`, or opens SQLite read-only (`experiments` & `registered_models` counts) when `sqlite:///...`. Reports `DEGRADED` if tracking responds without Model Registry or `UNAVAILABLE` if unreachable/missing.
6. **Automated Workflows:** Reads scheduler status and latest `workflow_audit_logs` record (`SUCCESS`, `PARTIAL`, `FAILED`).
7. **Backend Application:** Confirms FastAPI process responsiveness and uptime.

---

## 3. ETL Workflows, Quarantine Triage & Data Mart Maintenance

### Bulk CSV Ingestion Lifecycle (`app/services/etl/`)
All ETL API routes (`/etl/*`) require `ADMIN` privileges:
1. **Upload (`POST /etl/batches/upload`):** Streams `.csv` in configurable chunks (default `1000`), computes SHA-256 checksum, creates `etl_batches` row (`CSV_INGEST` or custom `source_system`), validates quantities/prices/FKs, deduplicates via `(source_system, source_transaction_id)`, and optionally decrements stock (`sync_inventory=true`).
2. **Quarantine Inspection (`GET /etl/quarantine`):** Failed rows are stored safely in `etl_quarantine_records` (`VALIDATION_ERROR`, `INVALID_DATA_TYPE`, `MISSING_FOREIGN_KEY`, `MALFORMED_ROW`) without blocking valid rows in the same batch.
3. **Reprocessing (`POST /etl/quarantine/{record_id}/reprocess` or `/etl/batches/{batch_id}/reprocess`):** Operators can supply corrected field overrides via Streamlit (`⚡ ETL & Data Warehouse -> Quarantine Management`) or API to re-validate and commit records.
4. **Reconciliation (`GET /etl/batches/{batch_id}/reconciliation`, `GET /etl/quality-report`):** Confirms source row count equals `committed + duplicates + quarantined` and `discrepancy_amount == 0.00`.
5. **Dimensional Warehouse (`POST /etl/marts/daily-sales/refresh`):** Idempotently upserts `daily_sales_mart` (`date x product_id x vendor_id`), preserving `NULL` COGS visibility.

### Scheduled Workflows (`app/scheduler.py`)
- **`01:30 AM` Daily:** `run_scheduled_daily_mart_refresh()` (`DAILY_MART_CRON_HOUR` / `MINUTE`).
- **`02:00 AM` Daily:** `run_analytical_pipeline()` executing:
  1. Inventory forecasting retraining + MLflow registration (`InventoryForecast` + `models/inventory_model.pkl`)
  2. Customer RFM & K-Means clustering refresh
  3. Item similarity matrix refresh
  4. Revenue KPI checks
  5. Low-stock alert evaluation + structured log warnings
  6. Persistence to `workflow_audit_logs`
- **On-Demand Trigger & Audit:** Admins can run `POST /analytics/pipeline/run` and inspect recent runs via `GET /analytics/pipeline/audit` or the Streamlit **Integration Status / System Health** view.

---

## 4. MLflow Model Tracking & Artifacts

- **Standalone Retraining CLI:**
  ```powershell
  python track_inventory.py
  ```
  Trains chronological holdout baselines + `RandomForestRegressor`, logs `MAE`, `RMSE`, `WAPE`, `R2`, registers version under **`InventoryForecast`**, and writes `models/inventory_model.pkl`.
- **Pipeline Reliability Stress Test (Isolated Sandbox):**
  ```powershell
  python validate_workflow_pipeline.py
  ```
  Executes 100 controlled runs + partial/failed fault injection against isolated SQLite DBs (`data/pipeline_test.db`, `data/test_mlflow_pipe.db`), leaving PostgreSQL untouched.

---

## 5. Authentication, Account Management & Vendor Governance

### User & Token Administration (`ADMIN`)
- **Create Internal / Entity Users:** `POST /auth/admin/users` (supports `ADMIN`, `VENDOR` with `vendor_id`, `CUSTOMER` with `customer_id`).
- **List / Inspect / Modify Roles & Active Status:** `GET /auth/admin/users`, `PATCH /auth/admin/users/{id}/status`, `PATCH /auth/admin/users/{id}/role`.
- **Emergency Session Revocation:** Changing user active status (`is_active=false`), changing roles, changing passwords (`/auth/change-password`), or calling `POST /auth/logout-all` immediately invalidates existing sessions via `token_version` + refresh-token family revocation.
- **Root Admin Password Reset:**
  ```powershell
  python bootstrap_admin.py --email admin@shopsense.internal --password NewStrongPassword123! --force
  ```

### Vendor Onboarding Approval Runbook (`VENDOR` Applications)
1. Vendors registering through `Register as Vendor` (`POST /auth/register-vendor`) start in `PENDING_APPROVAL` (`compliance_status="PENDING_REVIEW"`).
2. Review queue in UI (**Vendor Management -> Pending Applications**) displays Business Name, Owner Name, Email, Category, Phone, Tax/GST ID, and Submission Timestamp.
3. **Approve:** Select commission tier (`TIER_STARTER`, `TIER_STANDARD`, `TIER_PREFERRED`, `TIER_ENTERPRISE`), add optional verification notes, click **Approve Application**, then click **Confirm Approve** (`status="ACTIVE"`, `compliance_status="VERIFIED"`).
4. **Reject:** Enter mandatory verification/rejection feedback notes, click **Reject Application**, and confirm (`status="REJECTED"`, `compliance_status="FLAGGED"`). Rejected feedback is surfaced directly to the vendor on sign-in.
5. **Ongoing Governance (`Lifecycle & Governance` tab / `PUT /vendors/{id}/status`):** Transition vendors between `ACTIVE`/`LEGACY_ACTIVE`, `SUSPENDED` (blocks store operations reversibly), or `TERMINATED` (permanent read-only lock).

---

## 6. Backup, Recovery & Invariant Auditing

### Non-Destructive PostgreSQL Backups (`pg_dump` / `pg_restore`)
```bash
# Create compressed logical backup before upgrades or bulk ETL loads
pg_dump -U postgres -h localhost -F c -f shopsense_backup_$(date +%Y%m%d_%H%M).dump shopsense

# Restore cleanly into a fresh recovery database
pg_restore -U postgres -h localhost -d shopsense_restore --no-owner shopsense_backup_YYYYMMDD_HHMM.dump
```
*(In Docker Compose: `docker compose exec -T db pg_dump -U postgres -F c shopsense > backup.dump`.)*

### Platform Consistency Audit
Run anytime without mutating business tables (writes report to `data/consistency_report.json`):
```powershell
python validate_consistency.py
```
Must pass **12/12 checks (`100.0%`, target `>= 99.0%`)**.

---

## 7. Running Isolated Performance Benchmarks

> **Safety Rule:** Always run performance stress tests using the isolated scripts below — **never** insert synthetic benchmark rows into the production/demo PostgreSQL database.

```powershell
# Phase 1 Vectorized 100K Pandas/NumPy Benchmark -> docs/benchmark_100k_report.md
python benchmarks/run_100k_benchmark.py

# Phase 4 Integrated Relational 100K + Live Localhost Benchmark
# Capture baseline -> run optimized comparison & regenerate docs/phase4_performance_report.md
python benchmarks/phase4_performance_validation.py --mode baseline --rebuild-db
python benchmarks/phase4_performance_validation.py --mode optimized --rebuild-db
```

---

## 8. Troubleshooting Matrix

| Issue | Diagnostic Step | Fix |
| :--- | :--- | :--- |
| **Stale JWT rejected (`401`)** | User role/status/password updated recently (`token_version` mismatch) | Sign out and sign in again to obtain a fresh token pair. |
| **HTTP `403` on Executive BI or `/etl/*`** | Caller signed in as `VENDOR` or `CUSTOMER` | Expected RBAC enforcement; sign in with an `ADMIN` account or use `/analytics/executive/vendor-summary` for vendors. |
| **ETL batch shows `PARTIALLY_COMPLETED`** | Invalid rows isolated cleanly into `etl_quarantine_records` | Open **ETL & Data Warehouse -> Quarantine Management**, review `error_details`, edit fields, and click **Reprocess**. |
| **Duplicate CSV upload committed `0` rows** | Deduplication detected existing `(source_system, source_transaction_id)` keys | Expected idempotency protection preventing double-counted GMV. |
| **Dashboard falls back or shows offline warning** | FastAPI process stopped or port `8000` unreachable | Start `uvicorn app.main:app --host 127.0.0.1 --port 8000` and refresh browser. |
