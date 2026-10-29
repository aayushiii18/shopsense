# StockPilot — Retail Management Platform for Inventory Control and Sales Analytics
> **Smarter Stock. Better Decisions.**
*Infosys Springboard Internship Project — Milestones 1 & 2*

---

## 1. Project Overview
**StockPilot** is an intelligent retail management platform featuring inventory analytics, demand forecasting, customer segmentation, and personalized product recommendations. Built with an enterprise-grade backend using **FastAPI**, **PostgreSQL**, **SQLAlchemy**, and **Streamlit**, StockPilot empowers multi-vendor retail platforms to manage catalog operations, audit real-time inventory movements, forecast seasonal demand, segment customer behavior via unsupervised machine learning, and deliver personalized product recommendations.

---

## 2. Core Modules & Implemented Features

### Module 1: Product & Inventory Analytics Engine
- **Centralized Inventory & Catalog Hierarchy:** Centralized product records, pricing, parent category hierarchy, and multi-warehouse movement tracking.
- **Stock Movement Auditing:** Real-time logging of stock events (`RESTOCK`, `SALE`, `ADJUSTMENT`, `TRANSFER`, `RETURN`) with automated inventory balance synchronization.
- **Inventory Turnover & DSI:** Product and catalog-level turnover calculations ($\text{Sales} / \text{Average Stock}$) and Days Sales of Inventory (DSI), with velocity classification (`FAST_MOVING`, `NORMAL`, `SLOW_MOVING`, `DEAD_STOCK`).
- **Time-Series Demand Forecasting:** Forecasting daily product demand using seasonal day-of-week indicators and linear trend components.
  - **Evaluation Rigor:** Evaluated on a chronological 80/20 test holdout with zero lookahead leakage, reporting **MAE**, **RMSE**, and **WAPE** ($R^2 \times 100$ is rejected due to time-series vulnerability).
  - 95% confidence interval bands for forward projections.
- **Low-Stock Alerts & Depletion Projections:** Automated detection of products where $\text{Current Stock} \le \text{Reorder Level}$, calculating daily velocity and days until stockout.
- **Dynamic Replenishment Recommendations:** Calculates Safety Stock ($Z \times \sigma \times \sqrt{L}$), Reorder Points (ROP), and Recommended Order Quantities.

### Module 2: Customer Behavioral Analytics & Segmentation
- **RFM Feature Engineering:** Computes Recency ($R$, days since last purchase), Frequency ($F$, total orders), Monetary ($M$, lifetime spend), and Average Order Value ($AOV$) per customer.
- **K-Means Customer Segmentation:** Standardizes RFM features with `StandardScaler` and clusters customers into distinct business personas:
  - *Champions / VIP* (High monetary, high frequency, recent engagement)
  - *Loyal Regulars* (Steady frequency and moderate-to-high spend)
  - *At-Risk / Lapsed* (Dormant customers with high historical spend)
  - *New / Occasional* (Recent onboarding or low purchase frequency)
- **Silhouette Score Evaluation:** Evaluates cluster cohesion and separation using `sklearn.metrics.silhouette_score`.

### Module 3: Personalized Recommendation Engine
- **Item-Based Collaborative Filtering:** Computes cosine similarity between product vectors derived from customer interactions (views, cart additions, ratings, and purchases).
- **Top-N Personalized Recommendations:** Recommends top unpurchased products with score ranking and clear business rationales (e.g., *"Frequently explored alongside Wireless Headphones"*).
- **Cold-Start Popularity Fallback:** Serves top-selling catalog items when a customer has no prior interaction history.
- **Offline Evaluation (Leave-20%-Out Split):** Evaluates recommendation relevance against chronological held-out interactions, reporting **Precision@K**, **Recall@K**, and **Hit Rate@K**.

### Milestone 1 Baseline (Preserved)
- Multi-vendor registration with input validation (RFC emails, regex phone formats).
- Product registration with foreign-key constraints and price positivity checks.
- Baseline sales aggregation (total revenue, vendor revenue, product performance, summary report).
- Dual-mode Streamlit dashboard with live API and local demo CSV support.

---

## 3. Technology Stack

- **Language:** Python 3.10+
- **Web Framework:** FastAPI 0.111+ / Uvicorn (ASGI)
- **Database & ORM:** PostgreSQL 16/18 / SQLAlchemy 2.0 / `psycopg2-binary`
- **Data Validation & Settings:** Pydantic 2.x (with Email-Validator) / `python-dotenv`
- **Machine Learning & Analytics:** Scikit-Learn 1.7+, Pandas 2.2+, NumPy
- **Interactive Dashboard:** Streamlit / Plotly
- **Testing & QA:** Pytest 8.2+ / HTTPX / Pytest-Asyncio

---

## 4. Directory Structure

```text
Retail Management Platform for Inventory Control and Sales Analytics/
├── app/
│   ├── models/
│   │   ├── __init__.py                # Exports all models
│   │   ├── vendor.py                  # Vendor ORM model
│   │   ├── product.py                 # Product ORM model (category hierarchy, FK -> vendors)
│   │   ├── inventory.py               # Inventory model (1:1 with product, reorder_level)
│   │   ├── transaction.py             # Transaction model (amount, customer_id FK)
│   │   ├── customer.py                # Customer ORM model (RFM entity)
│   │   ├── stock_movement.py          # StockMovement audit log
│   │   └── customer_interaction.py    # Customer interaction records
│   ├── schemas/
│   │   ├── vendor_schema.py           # Vendor Pydantic schemas
│   │   ├── product_schema.py          # Product Pydantic schemas
│   │   ├── inventory_schema.py        # Stock movement schemas
│   │   ├── customer_schema.py         # Customer & RFM schemas
│   │   └── recommendation_schema.py   # Recommendation schemas
│   ├── routes/
│   │   ├── vendor_routes.py            # /vendors endpoints
│   │   ├── product_routes.py           # /products endpoints
│   │   ├── analytics_routes.py         # /analytics sales endpoints
│   │   ├── inventory_routes.py         # /analytics/inventory & /inventory endpoints
│   │   ├── customer_routes.py          # /analytics/customers endpoints
│   │   └── recommendation_routes.py    # /recommendations endpoints
│   ├── services/
│   │   ├── inventory_service.py       # Turnover, forecasting, replenishment logic
│   │   ├── customer_service.py        # RFM extraction, K-Means, silhouette score
│   │   └── recommendation_service.py  # Collaborative filtering, Precision@K
│   ├── database.py                    # SQLAlchemy engine & session factory
│   └── main.py                        # FastAPI application entry point
├── dashboard/
│   └── dashboard.py                   # 4-Tab Streamlit interactive analytics dashboard
├── data/
│   ├── vendors.csv                    # 5 vendors dataset
│   ├── products.csv                   # 10 products with category hierarchy
│   ├── inventory.csv                  # 10 inventory records
│   ├── customers.csv                  # 60 customers with geographic distribution
│   ├── transactions.csv               # 600 transactions over 12 months with seasonality
│   ├── stock_movements.csv            # 440 stock movement records
│   └── customer_interactions.csv      # 1,342 customer interactions
├── tests/
│   ├── conftest.py                    # Pytest fixtures and isolated SQLite DB setup
│   ├── test_vendors.py                # Vendor registration tests (25 tests)
│   ├── test_products.py               # Product catalog tests (14 tests)
│   ├── test_inventory.py              # Inventory model defaults & constraints (7 tests)
│   ├── test_analytics.py              # Baseline revenue analytics tests (10 tests)
│   ├── test_inventory_analytics.py    # Module 1: Inventory & forecasting tests (12 tests)
│   ├── test_customer_analytics.py     # Module 2: RFM & K-Means tests (6 tests)
│   └── test_recommendations.py        # Module 3: Collaborative filtering tests (6 tests)
├── create_tables.py                   # Creates all database tables
├── migrate_milestone2.py              # Idempotent DDL schema migration
├── generate_datasets.py               # Generates synthetic datasets
├── seed_data.py                       # Idempotent database seeder
├── requirements.txt                   # Complete dependencies manifest
├── .env.example                       # Environment template
└── README.md                          # Platform documentation
```

---

## 5. Quickstart & Installation

### Step 1: Clone & Set Up Environment
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Environment Configuration
Copy `.env.example` to `.env` and configure your PostgreSQL database connection:
```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/shopsense
TEST_DATABASE_URL=sqlite:///./test_shopsense.db
```

### Step 3: Run Database Migrations & Data Ingestion
```powershell
# 1. Apply schema migration
python migrate_milestone2.py

# 2. Seed database from synthetic datasets
python seed_data.py
```

### Step 4: Start the FastAPI Backend
```powershell
uvicorn app.main:app --reload
```
Interactive API docs available at: `http://127.0.0.1:8000/docs`

### Step 5: Launch the Streamlit Dashboard
```powershell
streamlit run dashboard/dashboard.py
```
Open `http://localhost:8501` to explore the 4-tab interactive dashboard.

---

## 6. API Reference (Milestone 2 Additions)

| Category | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Sales** | `GET` | `/analytics/summary` | Combined executive sales summary |
| **Sales** | `GET` | `/analytics/revenue/by-vendor` | Vendor revenue and units sold |
| **Sales** | `GET` | `/analytics/revenue/by-product` | Product revenue and units sold |
| **Inventory** | `GET` | `/analytics/inventory/status` | Current stock, valuation, and status badges |
| **Inventory** | `GET` | `/analytics/inventory/turnover` | Inventory turnover ratios and DSI by product |
| **Inventory** | `GET` | `/analytics/inventory/low-stock` | Low-stock alerts and depletion days |
| **Inventory** | `GET` | `/analytics/inventory/replenishment` | Replenishment quantities, ROP, and safety stock |
| **Inventory** | `GET` | `/analytics/inventory/forecast/{id}` | 14-day demand forecast with MAE, RMSE, WAPE |
| **Inventory** | `POST`| `/inventory/movements` | Log stock movement (inbound restock, sale, etc.) |
| **Customer** | `GET` | `/analytics/customers/summary` | Customer lifetime value and repeat purchase rate |
| **Customer** | `GET` | `/analytics/customers/rfm` | Recency, Frequency, Monetary, and AOV metrics |
| **Customer** | `GET` | `/analytics/customers/segments` | K-Means clustering and silhouette score |
| **Recommendations** | `GET` | `/recommendations/customer/{id}` | Personalized Top-N product recommendations |
| **Recommendations** | `GET` | `/recommendations/popular` | Global top-selling products (cold-start) |
| **Recommendations** | `GET` | `/recommendations/evaluation` | Offline Precision@K, Recall@K, and Hit Rate |

---

## 7. Automated Test Suite (85 Passing Tests)

Run the full test suite with verbose output:
```powershell
python -m pytest tests/ -v
```

All 85 tests execute against an isolated SQLite database, guaranteeing zero side-effects on production or development PostgreSQL instances:
- `test_vendors.py` (25 tests) — RFC email validation, phone regex, duplicate rejection, pagination.
- `test_products.py` (14 tests) — Product creation, FK verification, positive price constraints.
- `test_inventory.py` (7 tests) — Inventory defaults, constraints, 1-to-1 unique product constraint.
- `test_analytics.py` (10 tests) — Total revenue, vendor breakdown, product ranking, empty data safety.
- `test_inventory_analytics.py` (17 tests) — Turnover, stock movements, low-stock alerts, demand forecast, regression lookback tests.
- `test_customer_analytics.py` (6 tests) — Customer KPIs, RFM metrics, K-Means clustering, silhouette score.
- `test_recommendations.py` (6 tests) — Popularity fallback, collaborative filtering, Precision@K / Recall@K.
