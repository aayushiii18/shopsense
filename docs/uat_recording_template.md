# ShopSense UAT Execution Recording Sheet & Acceptance Summary

> **Verification Separation Notice:**
> - **Section 2A (Below):** Records **Developer-Assisted Functional UAT** executed directly against the running ShopSense application (`FastAPI :8000` + `Streamlit :8501` + `MLflow :5000` + `PostgreSQL`) using existing demo accounts and strict non-destructive database rules.
> - **Sections 2B, 4 & 5 (Stakeholder Execution, Satisfaction Survey & Sign-Offs):** Explicitly marked **`PENDING`** — zero external stakeholder participation, ratings, acceptance percentages, or signatures have been fabricated.

---

## 1. Test Cycle & Environment Metadata

| Field | Entry |
| :--- | :--- |
| **UAT Cycle ID** | `UAT-M4-STEP12` |
| **Application Version** | `ShopSense 1.0.0` (API metadata, `/health/live`, `/admin/health`, and Streamlit sidebar footer aligned at `1.0.0` — `DEF-UAT-03` resolved) |
| **Environment Tested (Dev Pre-UAT)** | `[x] Local Host` (`http://127.0.0.1:8501` UI / `http://127.0.0.1:8000` API / local `PostgreSQL`) |
| **Developer Pre-UAT Date** | `2026-11-27` / `2026-11-28` *(DEF-UAT-01, DEF-UAT-02 & DEF-UAT-03 resolved & retested `2026-11-28`)* |
| **Stakeholder UAT Status** | **`PENDING EXTERNAL VALIDATION`** |

### Accounts Used in Developer Pre-UAT (Existing Accounts — Zero DB Polluting)
| Role Represented | Account Used | Live State Verified? |
| :--- | :--- | :---: |
| **Administrator** | `admin@shopsense.com` (`user_id=1`) | `[x] Executed live (Browser WebView + AppTest + HTTP)` |
| **Vendor Partner (Approved)** | `vendor.demo@shopsense.com` (`vendor_id=7`, `Kapoor Smart Living`) | `[x] Executed live (AppTest + HTTP)` |
| **Customer / Shopper** | `customer.demo@shopsense.com` (`customer_id=61`) | `[x] Executed live (AppTest + HTTP)` |
| **External Business Stakeholders** | *Not yet assigned / executed* | `[ ] PENDING` |

---

## 2A. Developer-Assisted Functional Pre-UAT Execution Log (Live PostgreSQL Preserved)

Summary across 16 scenarios in [uat_test_plan.md](uat_test_plan.md): **8 `PASS`** (including `UAT-15` retested after `DEF-UAT-01` remediation), **7 `PARTIAL` (non-destructive scope enforced — mutating commits verified in isolated pytest or deferred to protect live DB; survey pending)**, **1 `BLOCKED` (unowned pending vendor credentials)**, **0 `FAIL`**.

| ID | Dev Functional Status | Method & Scope | Observed Evidence & Non-Destructive Guard Notes |
| :--- | :---: | :--- | :--- |
| **UAT-01** | `PARTIAL` | Browser WebView + AppTest | Unauthenticated gate blocks all dashboard tabs (`has_nav_radio_before_auth=False`), shows `🟢 Backend API Ready`, `Sign In`, `Register`, and `Register as Vendor` with all required application inputs. Actual submit skipped to keep PostgreSQL `vendors=7` intact (`POST /auth/register-vendor` covered by `test_vendor_onboarding_stage_b.py`). |
| **UAT-02** | `BLOCKED` | Live DB Preservation | Pending vendor #6 (`aayushi18@gmail.com` / `aayushi's store`) belongs to an existing user record; password not guessed or reset. Pending guardrails verified in `test_vendor_onboarding_stage_a.py` / `stage_b.py` and visible in Admin queue (`UAT-03`). |
| **UAT-03** | `PARTIAL` | AppTest (`Admin`) | `Pending Applications (1)` renders `aayushi's store` (`ID: 6`, `Owner: Aayushi`). Clicking `Approve Application` triggers confirmation prompt (`Confirm Application APPROVE`), and `Cancel` cleanly aborts without changing vendor status (`PENDING_APPROVAL` preserved). |
| **UAT-04** | `PARTIAL` | AppTest (`Admin`) | Clicking `Reject Application` with blank notes raises `"Verification/rejection feedback notes are required before rejecting an application."`. Rejection confirmation not committed to preserve vendor #6 state. |
| **UAT-05** | `PARTIAL` | AppTest (`Vendor #7`) | Signed in as `vendor.demo@shopsense.com` (`Kapoor Smart Living`): `Product Management` shows strictly `4` store SKUs (`100.0/100` catalog quality score); `Inventory Management` shows `110` units / `₹246,090.00` value (`3` Healthy, `1` Low Stock alert). SKU/movement writes skipped to protect DB. |
| **UAT-06** | `PASS` | AppTest + HTTP (`Vendor #7`) | `Vendor Management` shows `ACTIVE`, `TIER_PREFERRED`, `Net Sales: ₹13,495.00`, `Commission: ₹1,349.50`, `Payable Payout: ₹12,145.50`. UI sidebar hides `Executive BI` & `ETL` (only 6 Vendor views). Live HTTP returns `200` on `/vendor-summary`, **`403`** on `/vendor-summary?vendor_id=1`, and **`403`** on `/analytics/executive/summary`. |
| **UAT-07** | `PASS` | Browser + AppTest + HTTP | Admin `💎 Executive BI` loads `16` KPI cards (`0` exceptions): `GMV ₹102,060.55`, `Net Sales ₹101,460.55`, `Gross Profit ₹4,755.00` (`13.3%` COGS coverage matching `📊 Dashboard`), `AOV ₹168.42`, `606` orders, `60/61` customers (`98.4%` repeat), `₹330,855.10` stock value. |
| **UAT-08** | `PASS` | AppTest + HTTP (`Admin`) | `2024-01-01..2024-12-31` filter + `Daily` granularity toggle execute cleanly (`0` errors); future `2030-01-01..2030-01-31` returns `0` txns with friendly empty-state banner; invalid `2025-12-01..2024-01-01` triggers HTTP `422` and UI error `"Invalid Date Filter: Start Date cannot be after End Date."`. |
| **UAT-09** | `PASS` | AppTest (`Admin`) | `📈 Demand Forecasting` (`3` metrics, 0 exceptions) and `📋 Inventory Management` (`4` metrics, `1` reorder alert, 0 exceptions) render cleanly. |
| **UAT-10** | `PASS` | Browser + AppTest + HTTP | `👥 Customer Analytics` renders `20` KPI/ML cards cleanly (`0` exceptions). Both PDF (`5,588` bytes) and Excel (`28,644` bytes) export buttons appear enabled on `📊 Dashboard`, and live `/reports/pdf` (`%PDF`) & `/reports/excel` (`PK\x03\x04`) endpoints return valid files. |
| **UAT-11** | `PARTIAL` | AppTest (`Admin`) | Submitting `Safe Refund Terminal` with empty Audit Reason cleanly enforces `"Audit reason is required for processing refunds."`. Real refund insertion skipped so `refunds=0` in PostgreSQL stays intact. |
| **UAT-12** | `PASS` | AppTest (`Admin`) | `⚡ ETL & Data Warehouse` renders `10` KPI cards cleanly across Batch Monitoring (`0` uploaded batches), Quarantine, Data Quality, and Daily Sales Mart (`547` mart rows verified intact). |
| **UAT-13** | `PARTIAL` | AppTest (`Customer #61`) | Customer sign-in lands on `🛍️ Customer Catalog` with strictly `3` Customer views (`Catalog`, `Recommendations`, `Transactions`). Keyword search `"Smart"` filters catalog cards cleanly (`0` exceptions). New registration submit skipped to keep `users=8` / `customers=61` intact. |
| **UAT-14** | `PASS` | AppTest + HTTP (`Customer #61`) | `🎯 Recommendations` renders Hybrid (`Hit Rate@5 92.7%`, `NDCG@5 0.853`) and CF metrics (`0` exceptions); `💳 Transactions` shows `6` customer orders (`₹14,334.97`, `₹2,389.16` AOV). Live API enforces **`403`** on `/recommend/1` & `/analytics/customers/clv/1` vs `200` on `61`. |
| **UAT-15** | `PASS` *(Retested `2026-11-28`)* | Browser + AppTest + HTTP + PG | `🩺 System Health` renders `5/7 Healthy`, `2 Degraded` accurately. **Retest after `DEF-UAT-01` fix:** Login stores real `refresh_token` in session state without UI/log exposure; clicking `🚪 Log Out` posts `refresh_token` to `POST /auth/logout` (backend now rejects `access_token` with `400`), live PostgreSQL `refresh_tokens` transitions to `is_revoked=True` (verified live on Chrome & `AppTest` sessions), local session state clears cleanly, and post-logout `/auth/refresh` & `/auth/me` & protected routes reject `401`. Server logout errors preserve local session and display clear alert. |
| **UAT-16** | `PARTIAL` *(Tech checks `PASS`; Survey `PENDING EXTERNAL VALIDATION`)* | Browser + AppTest + Profiler | Midnight Navy / Electric Violet styling, hero cards, Plotly charts, and navigation verified across all `21` role-views (`0` exceptions; live Chrome check `2026-11-28` confirmed `ShopSense v1.0.0 • Enterprise Edition`, `0` errors). **`DEF-UAT-02` & `DEF-UAT-03` Resolved:** Admin `📊 Dashboard` cold load improved `18,947.47 ms -> 6,369.57 ms` (`2.97x` parallel) / `6,881.45 ms` (`2.75x` sequential spy), warm rerun `5,809.70 ms -> 2,831.92 ms`, `0` 1st-party deprecation warnings (`305 / 305` pytest passed). **Stakeholder usability survey remains `PENDING EXTERNAL VALIDATION`.** |

---

## 2B. External Stakeholder UAT Execution Log (`PENDING`)

| Scenario ID | Stakeholder Role | Stakeholder Status | Tester Name | Feedback / Sign-Off |
| :--- | :--- | :---: | :--- | :--- |
| **UAT-01 – UAT-16** | Admin / Vendor / Customer Stakeholders | **`PENDING`** | *Awaiting assignment* | *No external stakeholder sessions conducted yet.* |

---

## 3. Defect & Observation Log

| Defect ID | Linked Scenario | Severity | Observed Issue & Reproduction | Remediation Recommendation | Status |
| :--- | :--- | :---: | :--- | :--- | :---: |
| **`DEF-UAT-01`** | `UAT-15` | **P2 (Medium — Auth Session Hygiene)** | `dashboard/dashboard.py` (`_authenticate_dashboard_user`) stored `access_token` only and dropped `refresh_token`, causing `🚪 Log Out` to submit `access_token` to `/auth/logout` without revoking server `refresh_tokens`. Backend also previously ignored non-refresh token types on `/auth/logout`. | Persisted `refresh_token` in `st.session_state`, updated `_perform_dashboard_logout()` to submit real `refresh_token` to `/auth/logout`, hardened server `AuthService.revoke_refresh_token()` (`400`/`403`/`404` checks), added expired-access rotation recovery, and blocked false local session wipe on server failure (`tests/test_logout_refresh_token_security.py`, `tests/test_stage7_auth_security.py` `test_47`/`test_48`, live `:8501`/`:8000`/PG verified). | **RESOLVED & VERIFIED (`2026-11-28`)** |
| **`DEF-UAT-02`** | `UAT-16` | **P2 (Medium — Initial Page Latency)** | Baseline cold Admin `📊 Dashboard` load took `18,947.47 ms` (`18.95 s`, `23` HTTP calls, `5,809.70 ms` warm rerun): `/offers/strategy?limit=15` (`2,302.4 ms`) hit the `1.0s` `api_get` timeout and triggered duplicate in-process ML computation + eager `sklearn` imports alongside duplicate `/vendors/` & `/analytics/inventory/status` calls. | Optimized `hybrid_recommender.py` (`_prepare_hybrid_context`), `clv_service.py` (`precomputed_churn` + `groupby`), and `offer_service.py` (`2,302.4 ms -> 648.6 ms`), lazy-imported `sklearn`, added `_RUN_CACHE` per-run deduplication, guarded live ML fallbacks, bumped timeouts, and added thread-safe live parallel HTTP prefetch: cold load **`6,881.45 ms`** seq / **`6,369.57 ms`** parallel (`2.97x` faster); warm rerun **`2,831.92 ms`** (`2.05x` faster); parity verified in `test_stage5_intelligence.py`. | **RESOLVED & VERIFIED (`2026-11-28`)** |
| **`DEF-UAT-03`** | `UAT-16`, `README` | **P3 (Low / Cosmetic)** | Sidebar footer rendered `ShopSense v2.0 • Enterprise Edition` while `backend/config.py`, `/health/live`, and `/admin/overview` reported `1.0.0`. Streamlit logged `use_container_width` deprecations and FastAPI logged `@app.on_event` deprecations. *(UI logout wording also aligned to `🚪 Log Out`.)* | Dynamically sourced `APP_VERSION` (`1.0.0`) from `backend.config.get_settings().version`, replaced all `78` `use_container_width=True` calls (`71` in `dashboard.py`, `7` in `executive_bi.py`) with `width="stretch"`, and migrated `app/main.py` to `@asynccontextmanager lifespan` (`backend/api/main.py` compatible). Verified via `test_11_version_caption_consistency_and_no_v2_mismatch`, live Chrome, and `0` 1st-party deprecation warnings across `305 / 305` pytest run. | **RESOLVED & VERIFIED (`2026-11-28`)** |

---

## 4. Stakeholder Usability & Satisfaction Survey (`PENDING`)

*Do not populate until actual external Admin, Vendor, and Customer participants evaluate the platform.*

| Evaluation Criterion | Admin Rating (1–5) | Vendor Rating (1–5) | Customer Rating (1–5) | Mean Score (Target >= 4.0) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Portal navigation & role clarity | `__` | `__` | `__` | `Pending` | `PENDING` |
| Visual clarity & chart readability | `__` | `__` | `__` | `Pending` | `PENDING` |
| Onboarding & approval workflow ease | `__` | `__` | `N/A` | `Pending` | `PENDING` |
| Financial / COGS KPI trustworthiness | `__` | `__` | `N/A` | `Pending` | `PENDING` |
| Perceived responsiveness & error clarity | `__` | `__` | `__` | `Pending` | `PENDING` |

---

## 5. Final Acceptance Calculation & Sign-Off Summary

- **Developer Functional Pre-UAT Outcome:** **Pass (Non-Destructive Scope; All Open Defects `DEF-UAT-01`, `DEF-UAT-02`, `DEF-UAT-03` `RESOLVED` / `VERIFIED`)** — All `21` role-views across `ADMIN`, `VENDOR`, and `CUSTOMER` rendered with `0` exceptions; RBAC/tenant isolation, Executive BI filtering, COGS transparency, forecasting, recommendations, PDF/Excel exports, logout token revocation, cold-load latency optimization, version alignment (`1.0.0`), and PostgreSQL preservation passed cleanly (`305 / 305` full pytest suite).
- **External Stakeholder Acceptance Rate (%):** **`PENDING EXTERNAL VALIDATION` (`0%` fabricated; Target `>= 85.0%` upon stakeholder execution)**

### Formal Disposition
- `[ ]` **ACCEPTED** (`>= 85%` stakeholder pass rate, zero open `P0`/`P1` defects)
- `[ ]` **CONDITIONALLY ACCEPTED**
- `[ ]` **REJECTED**
- `[x]` **PENDING EXTERNAL STAKEHOLDER UAT EXECUTION**

| Stakeholder Role | Printed Name | Signature / Initials | Decision (`Approve / Hold`) | Date |
| :--- | :--- | :--- | :--- | :--- |
| **Business / Admin Stakeholder** | `____________________` | `____________` | `PENDING` | `____-__-__` |
| **Vendor Operations Representative** | `____________________` | `____________` | `PENDING` | `____-__-__` |
| **Customer Representative** | `____________________` | `____________` | `PENDING` | `____-__-__` |
| **Technical Lead / Delivery Owner** | `____________________` | `____________` | `PENDING` | `____-__-__` |
