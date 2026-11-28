# ShopSense Milestone 4 – Step 12: UAT Execution & Findings Report

**Execution Date:** `2026-11-27` / `2026-11-28`  
**Target Environment:** Running local ShopSense stack (`Streamlit :8501`, `FastAPI :8000`, `MLflow :5000`, `PostgreSQL` intact)  
**Overall Stakeholder UAT Disposition:** **PENDING EXTERNAL STAKEHOLDER EXECUTION** *(Developer-Assisted Functional UAT complete with 3 real defects logged for remediation prior to sign-off).*

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
| **PASS (Live Functional & API)** | `7` | `UAT-06`, `UAT-07`, `UAT-08`, `UAT-09`, `UAT-10`, `UAT-12`, `UAT-14` |
| **PARTIAL (Safe Non-Mutating Scope / Pending Survey)** | `7` | `UAT-01`, `UAT-03`, `UAT-04`, `UAT-05`, `UAT-11`, `UAT-13`, `UAT-16` |
| **BLOCKED (Preserved Unowned Pending Credentials)** | `1` | `UAT-02` *(covered in `tests/test_vendor_onboarding_stage_a.py` / `stage_b.py`)* |
| **FAIL (Real Defect Observed)** | `1` | `UAT-15` *(UI logout fails to revoke `refresh_token` -> `DEF-UAT-01`)* |
| **Stakeholder Acceptance Score** | **PENDING** | Target `>= 85%` upon external stakeholder execution |

---

## 3. Verified Live Evidence Highlights

- **Executive BI (`ADMIN`):** `GMV ₹102,060.55`, `Net Sales ₹101,460.55`, `Gross Profit ₹4,755.00` (`13.3%` COGS coverage cleanly labeled), `AOV ₹168.42`, `606` orders, `60/61` purchasing customers, `98.4%` repeat buyer rate, `₹330,855.10` stock value (`1,100` units). Empty window (`2030`) displayed friendly empty state; invalid range (`Start > End`) triggered HTTP `422` & clear error.
- **Vendor Tenant Isolation (`vendor.demo@shopsense.com`, ID `7`):** Sidebar showed strictly `6` views; `Kapoor Smart Living` rendered `ACTIVE`, `TIER_PREFERRED`, `4` SKUs, `110` stock units (`1` low-stock alert), `₹14,095.00` revenue (`4` orders), `₹12,145.50` net payable payout. Cross-tenant `/analytics/executive/vendor-summary?vendor_id=1` and `/analytics/executive/summary` returned **`403 Forbidden`**.
- **Customer Portal (`customer.demo@shopsense.com`, ID `61`):** Landed directly on `🛍️ Customer Catalog` with `3` sidebar views; search `"Smart"` filtered catalog cleanly; Recommendations displayed Hybrid (`Hit Rate@5 92.7%`, `NDCG@5 0.853`) and CF metrics; Transactions listed `6` personal orders (`₹14,334.97`). Cross-customer `/recommend/1` & `/analytics/customers/clv/1` returned **`403 Forbidden`**.
- **Pending Onboarding Queue (`UAT-03`, `UAT-04`):** `Pending Applications (1)` surfaced `aayushi's store` (`ID: 6`); empty-note rejection blocked with validation error; approve confirmation warning triggered & safely canceled.
- **Exports & Diagnostics (`UAT-10`, `UAT-15`):** `/reports/pdf` (`5,588` bytes `%PDF`) and `/reports/excel` (`28,644` bytes `PK\x03\x04`) generated cleanly; `/admin/health` reported `DEGRADED` (`5/7 Healthy`, `2 Degraded` fallback models: `inventory_model.pkl` & dynamic CF/TF-IDF, `0 Down`).

---

## 4. Defects Observed & Remediation Recommendations

1. **`DEF-UAT-01` [P2 Medium — Auth/Session Hygiene]: Streamlit Logout Leaves Refresh Token Unrevoked**
   - **Finding:** `_authenticate_dashboard_user()` in `dashboard/dashboard.py` persists only `access_token` (`st.session_state["auth_token"]`), omitting `refresh_token`. Clicking `🚪 Log Out` sends `{"refresh_token": access_token}` to `POST /auth/logout` — blacklisting the access JTI (`401` on `/auth/me`), while the refresh token stays valid (`200` on `/auth/refresh`). *(Direct `POST /auth/logout` with the actual `refresh_token` revokes both as designed: `401` on `/auth/refresh` & `/auth/me`.)*
   - **Remediation:** Save `refresh_token` into `st.session_state` on login and submit it to `POST /auth/logout` upon `🚪 Log Out`.
2. **`DEF-UAT-02` [P2 Medium — Cold Page Load UX]: Initial `📊 Dashboard` Synchronous Fan-Out Latency**
   - **Finding:** Cold initial render of `📊 Dashboard` invokes 10+ synchronous cross-module calls sequentially (taking ~15–30s on initial cold run, hitting a 30s `AppTest` timeout in one second cold run).
   - **Remediation:** Consolidate `📊 Dashboard` KPIs behind a cached summary fetch (`@st.cache_data(ttl=60)`) or fetch heavy Forecasting/Customer cards lazily.
3. **`DEF-UAT-03` [P3 Cosmetic]: Version Tag Mismatch & Deprecation Warnings**
   - **Finding:** Sidebar caption renders `ShopSense v2.0` vs backend `1.0.0`, and Streamlit logs emit `use_container_width` deprecation warnings. Documentation was aligned cleanly (`Sign Out` -> `🚪 Log Out`).
   - **Remediation:** Align footer version tag and replace `use_container_width=True` with `width="stretch"`.

---

## 5. Remaining External Stakeholder UAT Requirements

1. Remediate **`DEF-UAT-01`** (recommended before sign-off) and optionally `DEF-UAT-02` / `DEF-UAT-03`.
2. Conduct supervised walkthrough sessions with real **Admin**, **Vendor**, and **Customer** stakeholders using [uat_test_plan.md](uat_test_plan.md) (executing full onboarding submission/approval in a dedicated UAT schema or disposable vendor record) and complete [uat_recording_template.md](uat_recording_template.md) (`>= 85%` pass target, zero open `P0`/`P1`).
