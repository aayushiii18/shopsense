# ShopSense Milestone 4 – Step 12: UAT Execution & Findings Report

**Execution Date:** `2026-11-27` / `2026-11-28` *(DEF-UAT-01, DEF-UAT-02 & DEF-UAT-03 resolved & verified `2026-11-28`)*  
**Target Environment:** Running local ShopSense stack (`Streamlit :8501`, `FastAPI :8000`, `MLflow :5000`, `PostgreSQL` intact)  
**Overall Stakeholder UAT Disposition:** **`PENDING EXTERNAL VALIDATION`** *(Developer-Assisted Functional UAT complete: **`DEF-UAT-01`, `DEF-UAT-02`, and `DEF-UAT-03` all `RESOLVED` / `VERIFIED`**; zero external stakeholder ratings or approvals fabricated).*

---

## 1. Scope & Honesty Boundary

To validate readiness without falsifying stakeholder participation or mutating live PostgreSQL records (`users=8`, `vendors=7`, `products=14`, `customers=61`, `inventory=14`, `transactions=606`, `refunds=0`):
1. **Developer-Assisted Functional UAT** executed all non-destructive UI flows (Chrome WebView on Login Gate & Admin Dashboard/Health + full automated `AppTest` navigation across all `12` Admin, `6` Vendor, and `3` Customer pages) and live authenticated `FastAPI` RBAC/API checks using existing real accounts (`admin@shopsense.com`, `vendor.demo@shopsense.com`, `customer.demo@shopsense.com`).
2. **Database-Mutating Commit Steps** (`UAT-01` new vendor submission, `UAT-03`/`UAT-04` pending vendor status commit, `UAT-05` SKU/stock writes, `UAT-11` real refund commit, `UAT-13` new customer registration) exercised **live UI form/validation/confirmation triggers without committing synthetic rows** (`UAT-02` pending vendor login stayed `BLOCKED` live because `aayushi18@gmail.com` credentials were preserved untouched); full write paths remain verified in isolated SQLite pytest suites.
3. **External Stakeholder Participation, Satisfaction Scores & Formal Sign-Offs** are strictly **PENDING** in [uat_recording_template.md](uat_recording_template.md).

---

## 2. Summary of Developer Functional Outcomes

| Outcome Category | Count | Scenarios |
| :--- | :---: | :--- |
| **PASS (Live Functional & API)** | `8` | `UAT-06`, `UAT-07`, `UAT-08`, `UAT-09`, `UAT-10`, `UAT-12`, `UAT-14`, `UAT-15` *(retested after `DEF-UAT-01` fix)* |
| **PARTIAL (Safe Non-Mutating Scope / Pending Survey)** | `7` | `UAT-01`, `UAT-03`, `UAT-04`, `UAT-05`, `UAT-11`, `UAT-13`, `UAT-16` |
| **BLOCKED (Preserved Unowned Pending Credentials)** | `1` | `UAT-02` *(covered in `tests/test_vendor_onboarding_stage_a.py` / `stage_b.py`)* |
| **FAIL** | `0` | *None (`UAT-15` resolved & verified via `DEF-UAT-01` remediation)* |
| **Stakeholder Acceptance Score** | **PENDING** | Target `>= 85%` upon external stakeholder execution |

---

## 3. Verified Live Evidence Highlights

- **Executive BI (`ADMIN`):** `GMV ₹102,060.55`, `Net Sales ₹101,460.55`, `Gross Profit ₹4,755.00` (`13.3%` COGS coverage cleanly labeled), `AOV ₹168.42`, `606` orders, `60/61` purchasing customers, `98.4%` repeat buyer rate, `₹330,855.10` stock value (`1,100` units). Empty window (`2030`) displayed friendly empty state; invalid range (`Start > End`) triggered HTTP `422` & clear error.
- **Vendor Tenant Isolation (`vendor.demo@shopsense.com`, ID `7`):** Sidebar showed strictly `6` views; `Kapoor Smart Living` rendered `ACTIVE`, `TIER_PREFERRED`, `4` SKUs, `110` stock units (`1` low-stock alert), `₹14,095.00` revenue (`4` orders), `₹12,145.50` net payable payout. Cross-tenant `/analytics/executive/vendor-summary?vendor_id=1` and `/analytics/executive/summary` returned **`403 Forbidden`**.
- **Customer Portal (`customer.demo@shopsense.com`, ID `61`):** Landed directly on `🛍️ Customer Catalog` with `3` sidebar views; search `"Smart"` filtered catalog cleanly; Recommendations displayed Hybrid (`Hit Rate@5 92.7%`, `NDCG@5 0.853`) and CF metrics; Transactions listed `6` personal orders (`₹14,334.97`). Cross-customer `/recommend/1` & `/analytics/customers/clv/1` returned **`403 Forbidden`**.
- **Pending Onboarding Queue (`UAT-03`, `UAT-04`):** `Pending Applications (1)` surfaced `aayushi's store` (`ID: 6`); empty-note rejection blocked with validation error; approve confirmation warning triggered & safely canceled.
- **Exports, Diagnostics & Session Logout (`UAT-10`, `UAT-15` Retest):** `/reports/pdf` (`5,588` bytes `%PDF`) and `/reports/excel` (`28,644` bytes `PK\x03\x04`) generated cleanly; `/admin/health` reported `DEGRADED` (`5/7 Healthy`, `2 Degraded` fallback models: `inventory_model.pkl` & dynamic CF/TF-IDF, `0 Down`). Following `DEF-UAT-01` remediation, live verification on `Streamlit :8501` (Browser WebView + unmocked `AppTest`) and `FastAPI :8000` + PostgreSQL confirmed login persists `refresh_token` without UI/log exposure, `POST /auth/logout` rejects `access_token` payloads (`400`), clicking `🚪 Log Out` transitions DB `refresh_tokens` rows to `is_revoked=True` (verified live on rows `28` & `29` for `vendor.demo@shopsense.com`), and post-logout `/auth/refresh`, `/auth/me`, and `/analytics/executive/vendor-summary` all reject `401`.

- **Dashboard Cold-Load Latency & Deprecation Closure (`UAT-16`, `DEF-UAT-02`, `DEF-UAT-03`):** Consistent Admin `📊 Dashboard` `AppTest` profiling improved cold load from **`18,947.47 ms` -> `6,881.45 ms`** (`2.75x` faster sequential spy; **`6,369.57 ms`** with live parallel prefetch, `2.97x` faster, `-66.4%`, `0` exceptions) and warm rerun from **`5,809.70 ms` -> `2,831.92 ms`** (`2.05x` faster); `/offers/strategy?limit=15` dropped from **`2,302.4 ms` (`ReadTimeout`) -> `648.6 ms`**. Live Chrome verification confirmed `"ShopSense v1.0.0 • Enterprise Edition"` rendered cleanly across `📊 Dashboard` and `💎 Executive BI` with `0` errors and clean `🚪 Log Out`, and `pytest tests/ -q` passed **`305 / 305`** (`0` 1st-party deprecation warnings).

---

## 4. Defects Observed & Remediation Status

1. **`DEF-UAT-01` [P2 Medium — Auth/Session Hygiene]: Streamlit Logout Refresh-Token Handling — `RESOLVED` / `VERIFIED` (`2026-11-28`)**
   - **Original Finding:** `_authenticate_dashboard_user()` in `dashboard/dashboard.py` stored only `access_token` (`st.session_state["auth_token"]`), omitting `refresh_token`. Clicking `🚪 Log Out` previously sent `{"refresh_token": access_token}` to `POST /auth/logout`, revoking only the access JTI while leaving the server `refresh_tokens` row valid.
   - **Remediation Implemented:** Updated `dashboard/dashboard.py` (`_authenticate_dashboard_user()`, `render_login_page()`, `_clear_dashboard_auth_session()`, `_revoke_local_db_logout()`, `_recover_expired_access_logout()`, `_perform_dashboard_logout()`) to persist `refresh_token` securely in `st.session_state` (never exposed in UI/logs), send the real `refresh_token` to `POST /auth/logout` (with automatic refresh+revoke recovery if the access token expired and `/auth/logout-all` fallback only if a legacy session lacks `refresh_token`), clear all local auth/navigation keys on verified revocation, and preserve session + surface an explicit error if server revocation fails. Hardened `AuthService.revoke_refresh_token()` in `app/services/auth/auth_service.py` and `app/routes/auth_routes.py` to enforce token type `'refresh'`, ownership check, and strict `400`/`403`/`404` rejection on invalid logout payloads.
   - **Verification:** Covered by `tests/test_stage7_auth_security.py` (`test_47`, `test_48`), `tests/test_logout_refresh_token_security.py`, `tests/test_vendor_onboarding_stage_b.py`, and live `http://127.0.0.1:8501` / `http://127.0.0.1:8000` + PostgreSQL retest.
2. **`DEF-UAT-02` [P2 Medium — Cold Page Load UX]: Initial `📊 Dashboard` Synchronous Fan-Out Latency — `RESOLVED` / `VERIFIED` (`2026-11-28`)**
   - **Original Finding:** Profiled baseline Admin `📊 Dashboard` cold load at `18,947.47 ms` (`18.95 s`, `23` HTTP calls, `5,809.70 ms` warm rerun): `/offers/strategy?limit=15` (`2,302.4 ms`) exceeded the `1.0s` `api_get` timeout and triggered duplicate in-process Stage 5 ML execution + eager `sklearn` imports inside Streamlit alongside duplicate per-render `/vendors/` & `/analytics/inventory/status` fetches and sequential HTTP calls.
   - **Remediation Implemented:** Added shared precomputed context helpers in `app/services/hybrid_recommender.py` (`_prepare_hybrid_context`), `app/services/clv_service.py` (`precomputed_churn` + grouped lookup), and `app/services/offer_service.py` (`2,302.4 ms -> 648.6 ms`); lazy-imported `sklearn` inside CSV fallback (`dashboard/dashboard.py`); added per-run memoization (`_RUN_CACHE`) without stale cross-tenant TTL; removed redundant live-mode ML fallbacks; bumped `api_get` timeouts (`2.5s`/`4.0s`); and added thread-safe live-API parallel prefetch (`_prefetch_admin_dashboard_endpoints`).
   - **Verification:** Parity test `test_shared_ml_context_parity_matches_direct_calls` (`tests/test_stage5_intelligence.py`), full suite **`305 / 305 passed`**, and live profiler measurement (`18,947.47 ms -> 6,881.45 ms` sequential spy / **`6,369.57 ms` parallel** cold; `5,809.70 ms -> 2,831.92 ms` warm).
3. **`DEF-UAT-03` [P3 Cosmetic]: Version Tag Mismatch & Deprecation Warnings — `RESOLVED` / `VERIFIED` (`2026-11-28`)**
   - **Original Finding:** Sidebar caption rendered `ShopSense v2.0` vs backend `1.0.0`, Streamlit logged `use_container_width` deprecations, and FastAPI logged `@app.on_event("startup"/"shutdown")` warnings.
   - **Remediation Implemented:** Dynamically sourced `APP_VERSION` from `backend.config.get_settings().version` in `dashboard/dashboard.py` (`ShopSense v1.0.0 • Enterprise Edition`), migrated all `78` `use_container_width=True` widget calls (`71` in `dashboard/dashboard.py`, `7` in `dashboard/executive_bi.py`) to `width="stretch"`, and migrated `app/main.py` to `@asynccontextmanager lifespan` while preserving `startup_event`/`shutdown_event` compatibility (`backend/api/main.py`). *(Dependency-internal `starlette.testclient`, `mlflow`, and `sklearn` convergence notices remain upstream.)*
   - **Verification:** `test_11_version_caption_consistency_and_no_v2_mismatch`, `0` 1st-party deprecation warnings across **`305 / 305`** pytest run, and live Chrome sidebar check (`"ShopSense v1.0.0 • Enterprise Edition"`).

---

## 5. Remaining External Stakeholder UAT Requirements (`PENDING EXTERNAL VALIDATION`)

1. *(Completed `2026-11-28`: All technical UAT defects **`DEF-UAT-01`**, **`DEF-UAT-02`**, and **`DEF-UAT-03`** are **`RESOLVED`** & **`VERIFIED`**.)*
2. Conduct supervised walkthrough sessions with real **Admin**, **Vendor**, and **Customer** stakeholders using [uat_test_plan.md](uat_test_plan.md) (executing full onboarding submission/approval in a dedicated UAT schema or disposable vendor record) and complete [uat_recording_template.md](uat_recording_template.md) (`>= 85%` pass target, `>= 4.0 / 5.0` usability score, formal signatures).
