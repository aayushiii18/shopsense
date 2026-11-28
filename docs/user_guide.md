# ShopSense User Guide

Welcome to **ShopSense (`Smarter Stock. Better Decisions.`)** — your role-based multi-vendor retail analytics and marketplace workspace running on Streamlit (`http://127.0.0.1:8501`).

---

## 1. Signing In & Registering

When opening ShopSense, unauthenticated visitors see the **Secure Portal Access** gate with three tabs:

1. **Sign In:**
   - Enter your registered **Email Address** and **Password** (toggle **Show password** if needed).
   - Click **Sign In to ShopSense**. You are redirected automatically to your role-specific workspace (`🛍️ Customer Catalog` for Customers; `📊 Dashboard` for Admins and Vendors).
2. **Register (Customer Self-Service):**
   - Enter an **Email Address** and **Password (minimum 8 characters)** and click **Create Customer Account**.
   - Switch to **Sign In** to log in immediately as a Customer.
3. **Register as Vendor (Store Application):**
   - Complete **Owner Name**, **Business / Store Name**, **Email**, **Phone Number**, **Vendor Category** (with custom option when `Other` is selected), optional **Tax / GST ID**, **Password**, and **Confirm Password**.
   - Click **Submit Vendor Application**. New vendor applications enter **`PENDING_APPROVAL`** status awaiting administrator review. While pending, you can sign in to view your application status and feedback, while store product and inventory write controls remain locked until approved.

---

## 2. Administrator Guide (12 Workspace Views)

Administrators have access to all 12 Midnight Navy sidebar views:

### 📊 Dashboard & Reports
- High-level marketplace KPIs (**Total Revenue / GMV**, **Total Transactions**, **Active Vendors** with pending count badge, **Catalog Items**), COGS coverage margin indicators, and quick-navigation tiles.
- Download formatted **Executive PDF Report** (`shopsense_executive_report.pdf`) and **Excel Workbook** (`shopsense_executive_report.xlsx`) directly from the **Quick Governance & Export** card.

### 💎 Executive BI (`ADMIN` Only)
- Powered by centralized SQL-aggregated Phase 2 Executive Analytics APIs (`/analytics/executive/*`).
- **Interactive Controls:** Enable **Filter Date Range** (`Start Date` / `End Date`), toggle **Trend Granularity** (`Monthly` vs `Daily`), and adjust **Top Vendors / SKUs** (`5`, `10`, `25`, `50`).
- **Insights Displayed:**
  - **KPI Cards:** GMV, Net Sales, COGS-guarded Gross Profit (clearly labeled with exact % cost coverage or omitted if 0%), Total Transactions, AOV, Active/Repeat Customer metrics, and Inventory Valuation.
  - **Period-over-Period Comparison:** Compares custom date windows against immediately preceding equal-length periods, or compares latest active month vs previous month cleanly (shows insufficient-data notice if baseline history does not exist).
  - **Interactive Charts:** Revenue/Order trends, Vendor Revenue Share leaderboard with commission & payouts, Product Performance table, and Inventory Health/DSI breakdown.

### 🏢 Vendor Management (Admin Workflows)
- **⏳ Pending Applications Tab:** View pending applicant details, enter **Verification Feedback / Audit Notes**, select **Commission Tier** (`TIER_STARTER`, `TIER_STANDARD`, `TIER_PREFERRED`, `TIER_ENTERPRISE`), and approve or reject with an explicit confirmation prompt (rejection requires audit notes).
- **📋 Vendor Directory / ➕ Register Vendor / ✏️ Edit Vendor:** Search and filter by lifecycle status (`PENDING_APPROVAL`, `ACTIVE`, `LEGACY_ACTIVE`, `SUSPENDED`, `REJECTED`, `TERMINATED`), add vendors directly, or edit active profiles (`TERMINATED` accounts are locked read-only).
- **🛡️ Lifecycle & Governance / 💰 Settlement Ledger:** Suspend/reactivate/terminate stores and audit vendor commissions, refunds deducted, and net payouts.

### 📦 Product & 📋 Inventory Management
- Add new products (with optional `cost_price`, category, and vendor assignment) or update catalog pricing.
- Monitor real-time stock status (**HEALTHY**, **LOW_STOCK**, **CRITICAL**), inventory turnover / Days Sales of Inventory (DSI), safety-stock replenishment recommendations, and log **Stock Movements** (`RESTOCK`, `SALE`, `RETURN`, `ADJUSTMENT`).

### 💳 Transactions & Safe Refund Terminal
- Search all platform orders by product or vendor name and inspect basket value metrics.
- Issue full or partial **Safe Refunds** (`Admin Only`) by entering Transaction ID, Refund Amount (`₹`), mandatory Audit Reason, and optional **Restock Inventory** with returned unit count (automatically uses idempotency keys to prevent duplicate refunds).

### 👥 Customer Analytics, 📈 Demand Forecasting & 🎯 Recommendations
- **Customer Analytics:** Explore customer KPIs, RFM behavioral metrics, K-Means segmentation personas & silhouette score, L2-regularized Logistic Regression **Churn Risk**, Signup **Cohort Retention**, **12-Month Predictive CLV**, and **Conversion Funnel**.
- **Demand Forecasting:** Pick any product to inspect chronological 80/20 holdout evaluation (`MAE`, `RMSE`, `WAPE`) and 14-day daily demand forecasts with 95% confidence bands.
- **Recommendations:** Switch between **Hybrid Recommender** (tune Collaborative Filtering weight `α` vs TF-IDF content similarity) with holdout `Hit Rate@5` / `NDCG@5`, and classic **Collaborative Filtering**.

### 🛍️ Customer Catalog, ⚡ ETL & Data Warehouse & 🩺 System Health
- Preview verified marketplace products in the shopper storefront.
- Upload transaction CSVs under **Bulk Ingestion**, inspect **Batch Monitoring** reconciliation deltas, resolve invalid rows under **Quarantine Management**, run platform **Data Quality**, and trigger/refresh **Data Warehouse Marts**.
- Check 7-component runtime diagnostics, APScheduler job schedule, manual pipeline run trigger, and workflow audit logs in **Integration Status / System Health**.

---

## 3. Vendor Guide (6 Tenant-Scoped Views)

Signed-in Vendors see only their store's permitted sections (`📊 Dashboard`, `🏢 Vendor Management`, `📦 Product Management`, `📋 Inventory Management`, `💳 Transactions`, `🛍️ Customer Catalog`):

- **Application Status Banner:** Pending, rejected, suspended, or terminated accounts display clear status banners and administrator feedback notes at the top of the workspace. Product/inventory editing unlocks only when vendor status is `ACTIVE` or `LEGACY_ACTIVE`.
- **Vendor Profile & Settlements (`🏢 Vendor Management`):** Edit your own store contact info, owner name, category, Tax/GST ID, and address; inspect your store's commission rate and net settlement ledger in **My Settlements**.
- **Catalog, Inventory & Orders:** Add or update your store's products, record warehouse restocks/adjustments, review low-stock warnings for your SKUs, and filter orders placed on your store (`Transactions`). Attempts to query other vendors via API are blocked (`403 Forbidden`).

---

## 4. Customer Guide (3 Shopper Views)

Signed-in Customers access a streamlined shopping & self-service experience (`🛍️ Customer Catalog`, `🎯 Recommendations`, `💳 Transactions`):

- **🛍️ Customer Catalog:** Browse approved marketplace products from verified active sellers, filter by **Category**, or search by keyword.
- **🎯 Recommendations:** View personalized product recommendations tailored to your own `customer_id` using Hybrid (CF + TF-IDF Content) and Collaborative Filtering models (with stock availability verified and automatic best-seller cold-start recommendations for new shoppers).
- **💳 Transactions:** Review your own purchase history, basket totals, and order receipts.

---

## 5. Signing Out

Use the **🚪 Log Out** control in the bottom of the left sidebar (or call `POST /auth/logout` / `POST /auth/logout-all`) to revoke your active session cleanly and return to the Login gate.
