# ShopSense Deployment & Environment Setup Guide

This guide documents exact, reproducible setup and deployment procedures derived from the current ShopSense repository configuration.

> **Verification Transparency Note:**
> - **Verified directly in Phase 4 & 5:** Native host setup with Python `3.10.6`, PostgreSQL, Uvicorn (`127.0.0.1:8000`), Streamlit (`127.0.0.1:8501`), MLflow tracking (`127.0.0.1:5000`), schema migrations, `bootstrap_admin.py`, `validate_consistency.py`, and full `pytest` regression (`297 passed`).
> - **Automated CI definition:** `.github/workflows/ci.yml` defines PostgreSQL 15 + Python 3.10 initialization, migrations, consistency validation, `pytest`, and Streamlit `AppTest` verification.
> - **Docker Compose status:** Container files (`docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.dashboard`, `docker_entrypoint.py`, `docker-entrypoint.sh`) exist in the repository from Stage 8, **but full `docker compose up` container runtime execution was not executed on this Windows host during Phase 5**. Treat Docker deployment instructions as pre-configured topology requiring a live `docker compose up` smoke check in your target Docker environment.

---

## 1. Prerequisites & Supported Environment

### Native Host Setup (Verified)
- **Python:** `3.10+` (`3.10.6` verified)
- **Database:** PostgreSQL `15+` / `16` running locally or over reachable TCP (`psycopg2-binary` driver)
- **RAM:** Minimum `4 GB` recommended (`7.8 GB` host tested, including 100K isolated benchmarks)
- **Disk:** At least `500 MB` free for Python packages, `mlruns/` artifacts, and logs

### Containerized Setup (Pre-Configured, Pending Target-Host Smoke Test)
- Docker Desktop (Windows/macOS) or Docker Engine `20.10+` with Docker Compose V2

---

## 2. Repository & Python Dependency Setup

```powershell
# Clone repository and switch to main branch
git clone https://github.com/aayushiii18/shopsense.git
cd "Retail Management Platform for Inventory Control and Sales Analytics"

# Create and activate virtual environment (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS equivalent:
# python3 -m venv .venv && source .venv/bin/activate

# Install pinned dependency set
pip install --upgrade pip
pip install -r requirements.txt
```

Key dependencies installed from `requirements.txt` include `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg2-binary`, `pydantic[email]`, `python-dotenv`, `pandas`, `streamlit`, `plotly`, `scikit-learn`, `mlflow`, `apscheduler`, `reportlab`, `openpyxl`, `bcrypt`, `pyjwt`, `pytest`, and `locust`.

---

## 3. PostgreSQL & Environment Variable Configuration

### Step A: Provision PostgreSQL Database
Ensure PostgreSQL is running and create the target database (`shopsense`):

```sql
CREATE DATABASE shopsense;
```

### Step B: Create `.env` from `.env.example`
```powershell
Copy-Item .env.example .env
```

Edit `.env` with secure values before starting services:

```dotenv
# Runtime mode: 'development' allows local conveniences; 'production' forbids SQLite fallback
ENVIRONMENT=development

# Primary PostgreSQL connection URL
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/shopsense

# Isolated SQLite test database used only by pytest/non-prod fallback
TEST_DATABASE_URL=sqlite:///./test_shopsense.db

# Backend & Dashboard networking
API_BASE_URL=http://127.0.0.1:8000

# MLflow tracking URI
MLFLOW_TRACKING_URI=http://127.0.0.1:5000

# Security keys — IMPORTANT: app/core/config.py reads JWT_SECRET_KEY directly;
# backend/config.py & docker-compose.yml reference SECRET_KEY. Set BOTH to the same >=32-byte value!
JWT_SECRET_KEY=replace-with-a-secure-random-key-at-least-32-characters-long
SECRET_KEY=replace-with-a-secure-random-key-at-least-32-characters-long

# Initial Administrator Bootstrap Credentials
ADMIN_EMAIL=admin@shopsense.internal
ADMIN_PASSWORD=ChangeMeToStrongPassword123!
```

> **Production Configuration Rules (`backend/config.py`):**
> When `ENVIRONMENT=production`, `Settings.validate()` raises `ValueError` if `DATABASE_URL` is missing or starts with `sqlite`. Ensure `JWT_SECRET_KEY` and `SECRET_KEY` are never left at default strings in non-local environments.

---

## 4. Database Initialization, Migrations & Admin Bootstrap

All schema scripts are non-destructive (`CREATE TABLE IF NOT EXISTS` / column checks) and preserve existing rows:

```powershell
# 1. Create all 16 SQLAlchemy ORM tables (including Phase 4 transaction/refund indexes on fresh installs)
python create_tables.py

# 2. Apply idempotent incremental migrations safely if upgrading an older schema
python migrate_milestone2.py
python migrate_stage4.py
python migrate_stage6.py
python migrate_stage7.py
python migrate_vendor_onboarding.py

# 3. ONLY for a brand-new empty database (do NOT run if staging/live data already exists if unwanted;
#    seed_data.py checks existing counts before inserting baseline CSV records from data/)
python seed_data.py

# 4. Initialize or verify the root ADMIN account (idempotent; add --force to reset password)
python bootstrap_admin.py --email admin@shopsense.internal --password ChangeMeToStrongPassword123!

# 5. Populate/refresh the Daily Sales Mart warehouse table
python -c "from app.database import SessionLocal; from app.services.etl import refresh_daily_sales_mart; db=SessionLocal(); print(refresh_daily_sales_mart(db, full_rebuild=True)); db.close()"
```

*(Note: If upgrading an existing database created before Milestone 4 Phase 4 and needing the new Phase 4 performance indexes manually without recreating tables, run `CREATE INDEX IF NOT EXISTS` on `transactions(transaction_date)`, `(vendor_id, transaction_date)`, `(product_id, transaction_date)`, `(customer_id, transaction_date)`, and `refunds(status, transaction_id)`.)*

---

## 5. Starting Services Locally (Three-Process Stack)

Open three terminals with your virtual environment activated:

**Terminal 1 — MLflow Tracking Server (Port `5000`):**
```powershell
python -m mlflow server --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000
```

**Terminal 2 — FastAPI Backend Server (Port `8000`):**
```powershell
# Single-worker execution recommended so APScheduler lock ownership stays deterministic
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
*(Optional: add `--reload` during local code iteration; set `DISABLE_BACKGROUND_SCHEDULER=true` if running multiple backend workers behind a process manager.)*

**Terminal 3 — Streamlit Interactive Dashboard (Port `8501`):**
```powershell
python -m streamlit run dashboard/dashboard.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
```

### Initial Model Training (Optional if `models/inventory_model.pkl` is not yet trained on your data)
```powershell
python track_inventory.py
```

---

## 6. Post-Startup Health Verification

Verify each service responds cleanly:

```powershell
# Quick Python health probe
python -c "import requests; print({s: requests.get(u, timeout=3).json() if s!='ui' and s!='mlflow' else requests.get(u, timeout=3).status_code for s,u in [('live','http://127.0.0.1:8000/health/live'), ('ready','http://127.0.0.1:8000/health/ready'), ('ui','http://127.0.0.1:8501/_stcore/health'), ('mlflow','http://127.0.0.1:5000/')]})"
```

Or open in a browser:
- **Streamlit Dashboard (Login Page):** `http://127.0.0.1:8501`
- **FastAPI Interactive Swagger Docs:** `http://127.0.0.1:8000/docs`
- **MLflow UI:** `http://127.0.0.1:5000`

Check platform consistency invariants (12 checks):
```powershell
python validate_consistency.py
```

---

## 7. Docker Compose Setup (Reference Topology — Unverified on Host in Phase 5)

`docker-compose.yml` defines four networked services (`shopsense-network`) with persistent named volumes (`shopsense-postgres-data`, `shopsense-mlflow-data`):

| Service | Container | Build / Image | Host Port | Healthcheck |
| :--- | :--- | :--- | :---: | :--- |
| `db` | `shopsense-db` | `postgres:15-alpine` | `5432` | `pg_isready` |
| `mlflow` | `shopsense-mlflow` | `Dockerfile.backend` (`mlflow server`) | `5000` | `curl -f http://localhost:5000/` |
| `backend` | `shopsense-backend` | `Dockerfile.backend` (`docker_entrypoint.py` + `uvicorn`) | `8000` | `curl -f http://localhost:8000/docs` |
| `dashboard` | `shopsense-dashboard` | `Dockerfile.dashboard` (`streamlit run`) | `8501` | `curl -f http://localhost:8501/_stcore/health` |

> **Important Configuration Notes Before Running Compose:**
> 1. In `docker-compose.yml`, `backend` passes `SECRET_KEY` and `MLFLOW_TRACKING_URI=http://mlflow:5000`. Add `JWT_SECRET_KEY: ${JWT_SECRET_KEY:-...}` to `backend.environment` (or set both in `.env` and map cleanly) before production container deployment.
> 2. `docker_entrypoint.py` automatically runs `Base.metadata.create_all`, Stage 7 & vendor onboarding migrations, seeds CSV data **only if `vendors` count is `0`**, refreshes `daily_sales_mart` if empty, and runs `bootstrap_admin_user`.

Commands (run in Docker-enabled environment and verify health before sign-off):
```bash
docker compose up --build -d
docker compose ps
docker compose logs -f backend
```

---

## 8. Safe Shutdown, Restart & Troubleshooting

### Safe Shutdown
1. Stop Streamlit (`Ctrl+C` in Terminal 3).
2. Stop FastAPI (`Ctrl+C` in Terminal 2) — triggers `shutdown_event()` which calls `stop_scheduler()` and cleanly releases/removes `stockpilot_scheduler.lock`.
3. Stop MLflow (`Ctrl+C` in Terminal 1).
*(Docker equivalent: `docker compose down` preserves `postgres_data` and `mlflow_data`; avoid `-v` unless intentionally destroying volumes.)*

### Common Startup & Runtime Issues
| Symptom | Likely Cause | Resolution |
| :--- | :--- | :--- |
| `DATABASE_URL ... is required in production` | `ENVIRONMENT=production` set without `DATABASE_URL` or using `sqlite://` | Set a valid `postgresql://` URL in `.env`. |
| `stockpilot_scheduler.lock` blocks test/secondary worker | Live FastAPI Uvicorn server holds OS lock (`test_scheduler_pipeline.py` tests lock acquisition) | Stop local Uvicorn before running `pytest`, or set `DISABLE_BACKGROUND_SCHEDULER=true` for extra workers. |
| Dashboard shows `Local DB Auth Mode` pill on login page | Streamlit started before FastAPI or wrong `API_BASE_URL` | Verify Uvicorn is listening on `8000` and `API_BASE_URL=http://127.0.0.1:8000`. |
| `/admin/health` shows Forecasting or Recommendation `DEGRADED` | `models/forecast.pkl` / `models/recommender.pkl` missing while fallback engines work | Expected unless custom `.pkl` paths are configured; see `docs/operations_manual.md` Section 2. |
