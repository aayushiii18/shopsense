# ShopSense User Acceptance Testing (UAT) Test Plan

**Document Status:** READY FOR STAKEHOLDER EXECUTION (**Actual UAT Status: PENDING**)  
**Target Release:** ShopSense v1.0.0 (Milestone 4 Final Release Candidate)  
**Target Acceptance Threshold:** **>= 85.0% overall scenario pass rate** with **0 unresolved P0/P1 critical blockers** across Admin, Vendor, and Customer roles.

> **Important Honesty Notice:** This test plan defines the scenarios, acceptance criteria, and evaluation methodology for formal stakeholder testing. **No stakeholder participation, scores, or sign-off results have been recorded or simulated.** Execution status remains **PENDING** until business/operations stakeholders complete the scenarios in [uat_recording_template.md](uat_recording_template.md).

---

## 1. Objectives & Stakeholder Scope

Validate that the integrated ShopSense platform satisfies operational, analytical, role-isolation, and usability expectations from the perspective of real platform users:
1. **Platform Administrator (`ADMIN`)** — marketplace oversight, vendor onboarding governance, Executive BI analytics, safe refunds, ETL/Data Warehouse ops, and system health diagnostics.
2. **Marketplace Seller (`VENDOR`)** — self-service application, status tracking, tenant-scoped product/inventory control, store orders, and settlement ledger.
3. **Marketplace Shopper (`CUSTOMER`)** — registration, catalog browsing, personalized recommendations, purchase history, and strict isolation from admin/vendor consoles.

---

## 2. Entry Criteria & Pre-UAT Environment Readiness

Before starting UAT sessions with stakeholders:
- PostgreSQL database is running with intact baseline + demo accounts (no `test` resets required).
- FastAPI (`http://127.0.0.1:8000`), Streamlit (`http://127.0.0.1:8501`), and MLflow (`http://127.0.0.1:5000`) are healthy (`/health/ready` returns `200 READY`).
- Test accounts prepared cleanly (`ADMIN`, `VENDOR` approved + newly submitted pending test vendor during UAT, `CUSTOMER`).

---

## 3. Acceptance Criteria & Evaluation Process

### Outcome Classification per Scenario
- **PASS:** All expected results occur cleanly with no unhandled errors, inaccurate numbers, or broken permissions.
- **PARTIAL:** Primary workflow completes, but minor cosmetic/UX friction (`P2`/`P3`) exists.
- **FAIL:** Wrong calculations, role breach, crash/HTTP 500, or blocked workflow (`P0`/`P1`).
- **BLOCKED / N/A:** Cannot execute due to external prerequisite.

### Quantitative Acceptance Threshold (>= 85%)
1. **Mandatory Functional Gate:** Zero open **P0 (Blocker/Security Breach)** or **P1 (Major Functional/Accounting Error)** defects across executed scenarios.
2. **Pass Rate Target:** $\frac{\text{Passed Scenarios}}{\text{Total Applicable Scenarios}} \times 100\% \ge 85\%$ across all executed test cases (`>= 14 / 16` Pass when all 16 execute).
3. **Stakeholder Satisfaction Survey:** Average usability score $\ge 4.0 / 5.0$ across Navigation Clarity, Data Trust/COGS Transparency, and Responsiveness.

---

## 4. Structured UAT Scenarios

### A. Authentication, Onboarding & Vendor Approval Workflow

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-01** | Anonymous / Prospective Vendor | Login-First Gate & Self-Service Vendor Registration | 1. Open `http://127.0.0.1:8501` unauthenticated.<br>2. Attempt to access dashboards.<br>3. Select **Register as Vendor** tab, fill Owner Name, Business Name, unique Email, Phone, Category, optional Tax/GST ID, matching Passwords (`>=8` chars), and click **Submit Vendor Application**. | Dashboard modules are inaccessible prior to login. Success banner displays assigned Vendor ID and explicit status **`PENDING_APPROVAL` — awaiting admin approval**; vendor is NOT auto-activated. |
| **UAT-02** | Pending Vendor | Pending Vendor Sign-In & Onboarding Guardrails | 1. Sign in with the pending vendor credentials from `UAT-01`.<br>2. Open **Vendor Management**.<br>3. Attempt to inspect **Product Management** / **Inventory Management** or query `/analytics/executive/summary`. | Pending status banner appears clearly. Product/inventory mutation remains locked until admin approval; Admin Executive routes return `403 Forbidden`. |
| **UAT-03** | Admin | Vendor Onboarding Review & Confirmed Approval | 1. Sign in as `ADMIN`.<br>2. Open **Vendor Management -> Pending Applications**.<br>3. Select the pending vendor from `UAT-01`, review submitted fields, pick Commission Tier, enter notes, click **Approve Application**, then click **Confirm Approve**. | Application leaves Pending Queue, vendor transitions to **`ACTIVE`** / `VERIFIED`, and approval feedback message displays clearly. |
| **UAT-04** | Admin & Vendor | Vendor Rejection with Mandatory Notes & Status Feedback | 1. Submit a second test vendor application.<br>2. Sign in as `ADMIN` -> **Pending Applications**.<br>3. Attempt rejection with empty notes, then enter rejection notes and click **Confirm Reject**.<br>4. Sign in as rejected vendor. | Empty rejection note is blocked with clear validation error. Confirmed reject sets `REJECTED`/`FLAGGED`, and vendor sees administrator feedback upon sign-in. |

### B. Vendor Operations & Strict Tenant Isolation

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-05** | Approved Vendor | Tenant Product Catalog & Store Inventory Management | 1. Sign in as approved vendor.<br>2. Navigate to **Product Management** and verify only own store SKUs appear.<br>3. Add a new SKU or update price; navigate to **Inventory Management** and log a `RESTOCK` movement. | Vendor sees only own store catalog and stock; restock increments `current_stock` and appends an immutable `stock_movements` audit entry. |
| **UAT-06** | Approved Vendor | Vendor Settlements & Tenant Data Isolation | 1. Open **Vendor Management -> My Settlements** and **Transactions**.<br>2. Verify orders belong only to the signed-in vendor.<br>3. Call `GET /analytics/executive/vendor-summary?vendor_id=<OTHER_ID>` using the vendor's Bearer token (or inspect Swagger `/docs`). | UI displays strictly the vendor's own orders, net sales, commission rate, and payout. Cross-tenant API query is rejected with **`HTTP 403 Forbidden`**. |

### C. Admin Executive BI Dashboard & Core Analytics

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-07** | Admin | Executive BI Overview & Partial/Zero COGS Honesty | 1. Sign in as `ADMIN` and select **💎 Executive BI**.<br>2. Inspect Hero pills, KPI cards (GMV, Net Sales, Gross Profit, AOV, Orders, Customers, Inventory Valuation), and COGS coverage badge.<br>3. Compare GMV and transaction count against **📊 Dashboard** and **💳 Transactions**. | Values match backend APIs with zero discrepancy (`validate_consistency` invariant). Partial or 0% COGS coverage is explicitly disclosed without fabricated margins. |
| **UAT-08** | Admin | Executive BI Date-Range Filtering, Granularity & Empty Window | 1. Enable **Filter Date Range**, pick a valid historical range, switch **Trend Granularity** between `Monthly` and `Daily`, and change **Top Vendors / SKUs**.<br>2. Pick a future empty date range (`2030-01-01` to `2030-01-31`).<br>3. Pick invalid `Start Date > End Date`. | Charts and period-over-period deltas refresh dynamically; empty window shows friendly empty-state notice (`0` txns) without crash; invalid range shows clear date validation error. |
| **UAT-09** | Admin | Demand Forecasting & Inventory Replenishment | 1. Open **📈 Demand Forecasting**, select an active product, inspect holdout `MAE`/`RMSE`/`WAPE` and 14-day confidence chart.<br>2. Open **📋 Inventory Management** and review Low-Stock alerts and Safety Stock / ROP replenishment table. | Interactive forecast chart renders without NaNs/exceptions; low-stock items highlight `CRITICAL`/`WARNING` severity accurately. |
| **UAT-10** | Admin | Customer Analytics & Exportable Executive Reports | 1. Open **👥 Customer Analytics** and inspect RFM metrics, K-Means clusters/silhouette, Churn risk, Cohorts, and CLV.<br>2. Return to **📊 Dashboard** and click **Export PDF Report** and **Export Excel Report**. | Customer charts load smoothly; PDF (`shopsense_executive_report.pdf`) and XLSX (`shopsense_executive_report.xlsx`) download validly with non-zero size. |

### D. Safe Refunds & ETL / Data Warehouse Operations

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-11** | Admin | Safe Refund Terminal (Idempotency & Stock Guard) | 1. Open **💳 Transactions**.<br>2. Inspect **Safe Refund Terminal**, verify validation when Audit Reason is empty or `Restock Inventory` checked with `0` units.<br>3. (Optional in UAT sandbox/test txn) Submit a valid partial refund with audit reason. | Validation prevents empty reason / 0-unit restock; valid refund processes once with unique idempotency key and updates transaction/net sales state cleanly. |
| **UAT-12** | Admin | ETL Bulk CSV Monitoring, Quality & Daily Mart Refresh | 1. Open **⚡ ETL & Data Warehouse**.<br>2. Inspect **Batch Monitoring**, **Data Quality & Reconciliation**, and **Data Warehouse Mart** tabs.<br>3. Run or review **Daily Sales Mart** status. | Batch reconciliation displays record counts & zero monetary discrepancy; Daily Sales Mart reflects database transactions accurately. |

### E. Customer Experience & Access Boundaries

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-13** | Customer | Self-Service Registration, Sign-In & Catalog Showcase | 1. On login page, open **Register** tab, create a new customer (`>=8` char password), then **Sign In**.<br>2. Verify sidebar only shows `Customer Catalog`, `Recommendations`, and `Transactions`.<br>3. Filter catalog by Category and Keyword. | Customer signs in cleanly; Admin/Vendor pages are absent from sidebar; catalog displays only approved/operational vendor products matching filters. |
| **UAT-14** | Customer | Personalized Hybrid Recommendations & Order History | 1. Open **🎯 Recommendations**, adjust Collaborative Weight `α`, inspect Hybrid recommendations (`with stock check`), and switch to **Collaborative Filtering**.<br>2. Open **💳 Transactions**. | Recommendations load cleanly (cold-start popularity fallback for brand-new shoppers); Transactions tab shows strictly own orders (`0` leak of other buyers). |

### F. Security, Operational Diagnostics & Usability

| ID | Role | Scenario | Exact Test Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **UAT-15** | Admin / Security | System Health Diagnostics & Session Termination | 1. Open **🩺 Integration Status / System Health**, inspect 7 components and APScheduler jobs.<br>2. Click **🚪 Log Out** in sidebar.<br>3. Attempt to reuse an old access or refresh JWT after logout. | All DB & API checks surface accurate status without leaking DB passwords; **🚪 Log Out** returns to Login gate and revokes both access and refresh tokens cleanly. |
| **UAT-16** | All Roles | Visual Hierarchy, Typography, Chart Legibility & Response Time | 1. Navigate across all visible tabs on `ADMIN`, `VENDOR`, and `CUSTOMER` sessions at standard desktop width (`>= 1280px`).<br>2. Evaluate Midnight Navy / Electric Violet readability, badge contrast, empty states, and interaction latency. | Cohesive ShopSense branding across roles, zero clipped labels or broken Plotly charts, smooth response times (< 1–2s typical page load). |
