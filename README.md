# ShopSense — Multi-Vendor E-Commerce Analytics Platform
**Retail Management Platform for Inventory Control and Sales Analytics**  
*Infosys Springboard Internship Project — Milestone 1 (Weeks 1–2)*

---

## 1. Project Overview
**ShopSense** is a backend and analytics foundation designed for multi-vendor retail platforms. It allows multiple independent vendors to register and list products, tracks transactions and inventory stock, and provides real-time analytical reporting on sales, revenues, and top-performing products.

---

## 2. Objectives & Implemented Features (Milestone 1)

- **Vendor Management & Registration:**
  - Automated input validation (Pydantic models with RFC-compliant email formatting, lowercase email normalization, regex-validated phone formats, and non-empty name enforcement).
  - Duplicate email protection (application-level verification with PostgreSQL unique constraint enforcement returning `HTTP 409 Conflict`).
  - Vendor retrieval and paginated listing endpoints.

- **Product Catalog Management:**
  - Product registration tied to an existing vendor foreign key.
  - Verification that referenced vendors exist (`HTTP 404 Not Found` if vendor does not exist).
  - Price positivity validation (`price > 0`) at both Pydantic schema level and database `CheckConstraint` level.
  - Product retrieval and vendor-filtered product listing endpoints.

- **Relational Data Modeling:**
  - Fully mapped SQLAlchemy 2.0 ORM models for `vendors`, `products`, `inventory`, and `transactions`:
    - `vendors` (`id`, `name`, `email`, `phone`, `address`, `created_at`)
    - `products` (`id`, `name`, `description`, `price`, `category`, `vendor_id`, `created_at`)
    - `inventory` (`inventory_id`, `product_id`, `current_stock`, `warehouse`, `reorder_level`, `updated_at`)
    - `transactions` (`transaction_id`, `product_id`, `vendor_id`, `quantity`, `unit_price`, `amount`, `transaction_date`)
  - Integrity constraints: foreign keys (`CASCADE` on products/inventory, `RESTRICT` on transactions), unique constraints (vendor email, 1-to-1 inventory product ID), and check constraints for positive quantities, non-negative stock levels, and positive transaction amounts.

- **Sales Analytics:**
  - Total marketplace revenue and total transaction count.
  - Vendor-wise revenue aggregation and unit sales (Pandas-powered groupby, sorted descending).
  - Product-wise revenue aggregation and unit sales (sorted descending).
  - Identification of top-selling products by quantity sold.
  - Marketplace executive summary endpoint (`/analytics/summary`).
  - Graceful boundary handling for empty datasets (returning clean zeros and empty collections without raising exceptions).

- **Multi-Source Analytics Dashboard:**
  - Interactive Streamlit dashboard with Plotly charts.
  - Dual data source: Live FastAPI REST API with automatic fallback to local CSV dataset (`data/transactions.csv`).

- **Automated Testing Suite:**
  - 56 comprehensive unit and integration tests using `pytest` and FastAPI `TestClient`.
  - Isolated test fixtures using SQLite in-memory/file configuration to ensure zero side-effects on production/development databases.

---

## 3. Technology Stack

- **Language:** Python 3.10+
- **Web Framework:** FastAPI 0.111+ / Uvicorn (ASGI)
- **Database & ORM:** PostgreSQL 16+ / SQLAlchemy 2.0 / `psycopg2-binary`
- **Data Validation & Settings:** Pydantic 2.x (with Email-Validator) / `python-dotenv`
- **Data Processing & Analytics:** Pandas 2.2+
- **Interactive Dashboard:** Streamlit / Plotly
- **Testing & QA:** Pytest 8.2+ / HTTPX / Pytest-Asyncio

---

## 4. Directory Structure

```text
Retail Management Platform for Inventory Control and Sales Analytics/
├── app/
│   ├── models/
│   │   ├── __init__.py        # Re-exports Vendor, Product, Inventory, Transaction
│   │   ├── vendor.py          # Vendor ORM model
│   │   ├── product.py         # Product ORM model (FK -> vendors.id)
│   │   ├── inventory.py       # Inventory ORM model (inventory_id, current_stock, warehouse, reorder_level)
│   │   └── transaction.py     # Transaction ORM model (transaction_id, amount, FKs -> products, vendors)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── vendor_schema.py   # VendorCreate & VendorResponse schemas
│   │   └── product_schema.py  # ProductCreate & ProductResponse schemas
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── vendor_routes.py    # /vendors endpoints
│   │   ├── product_routes.py   # /products endpoints
│   │   └── analytics_routes.py # /analytics endpoints
│   ├── database.py            # SQLAlchemy engine, session maker, get_db() dependency
│   ├── main.py                # FastAPI application entry point
│   └── __init__.py
├── dashboard/
│   └── dashboard.py           # Streamlit analytics dashboard
├── data/
│   └── transactions.csv       # Sample baseline transaction data (transaction_id, amount)
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures and isolated SQLite DB setup
│   ├── test_vendors.py        # Vendor registration & validation tests (25 tests)
│   ├── test_products.py       # Product catalog & constraint tests (14 tests)
│   ├── test_inventory.py      # Inventory model defaults & transaction amount tests (7 tests)
│   └── test_analytics.py      # Analytics logic & empty-data tests (10 tests)
├── create_tables.py           # Script to create tables in PostgreSQL
├── requirements.txt           # Project dependencies
├── .env.example               # Environment variable template
├── .gitignore                 # Excludes .env, *.db, caches, virtual environments
└── README.md                  # Project documentation
```

---

## 5. Prerequisites

- Python 3.10 or higher
- PostgreSQL 14, 15, 16, or 18 running locally or accessible via network
- Git

---

## 6. Installation Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd "Retail Management Platform for Inventory Control and Sales Analytics"
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   # Windows PowerShell:
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   *(Or on Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`)*

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

---

## 7. Environment Configuration

Copy the example environment configuration:

```powershell
Copy-Item .env.example .env
```

Open `.env` in an editor and set your local PostgreSQL credentials:

```env
DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<database_name>
TEST_DATABASE_URL=sqlite:///./test_shopsense.db
```

> **Security Note:** Never commit `.env` or files containing plain-text credentials to version control. `.env` is listed in `.gitignore`.

---

## 8. PostgreSQL Setup

1. Open your PostgreSQL prompt (`psql`) or pgAdmin.
2. Create the project database:
   ```sql
   CREATE DATABASE shopsense;
   ```
3. Update `DATABASE_URL` in `.env` to point to `shopsense`.

---

## 9. Database Table Creation

Once `.env` is configured with valid credentials, run the table creation script:

```powershell
python create_tables.py
```

Expected output:
```text
Creating tables...
Done. Tables created (or already existed):
  - vendors
  - products
  - inventory
  - transactions
```

---

## 10. Starting the FastAPI Application

Start the development server with Uvicorn:

```powershell
uvicorn app.main:app --reload
```

Server will start on: `http://127.0.0.1:8000`

---

## 11. API Documentation

Interactive Swagger and OpenAPI documentation is generated automatically:

- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc UI:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI JSON:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

### Available Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API health check |
| `POST` | `/vendors/` | Register new vendor (enforces unique email, phone regex) |
| `GET` | `/vendors/` | List vendors with pagination (`skip`, `limit`) |
| `GET` | `/vendors/{vendor_id}` | Retrieve vendor by ID |
| `POST` | `/products/` | Register product (checks valid `vendor_id`, positive price) |
| `GET` | `/products/` | List products (supports optional `vendor_id` filtering) |
| `GET` | `/products/{product_id}` | Retrieve product by ID |
| `GET` | `/analytics/revenue/total` | Total marketplace revenue and transaction count |
| `GET` | `/analytics/revenue/by-vendor` | Vendor revenue breakdown and units sold |
| `GET` | `/analytics/revenue/by-product` | Product revenue breakdown and units sold |
| `GET` | `/analytics/top-selling-product` | Product with highest cumulative units sold |
| `GET` | `/analytics/summary` | Combined executive dashboard report |

---

## 12. Starting the Streamlit Dashboard

In a separate terminal, launch the Streamlit dashboard:

```powershell
streamlit run dashboard/dashboard.py
```

- **URL:** [http://localhost:8501](http://localhost:8501)
- **Data Source Modes:**
  - **Live API mode:** Queries the running FastAPI instance (`http://127.0.0.1:8000`).
  - **Local CSV mode:** Reads fallback demo records from `data/transactions.csv`.

---

## 13. Running Automated Tests

Run the full test suite with verbose output:

```powershell
python -m pytest tests/ -v
```

All 56 tests execute against an isolated SQLite test database configured in `tests/conftest.py`. No live PostgreSQL connection is required to run the automated test suite.

---

## 14. Milestone 1 Completion Status

- [x] Vendor registration & validation
- [x] Product catalog registration
- [x] SQLAlchemy ORM models (vendors, products, inventory, transactions)
- [x] Database table creation script (`create_tables.py`)
- [x] Sales analytics (total revenue, vendor-wise, product-wise, top-selling product, summary)
- [x] FastAPI REST endpoints with documentation
- [x] Baseline marketplace reporting & Streamlit visualization
- [x] Automated test suite (56/56 passing)

---

## 15. Known Limitations & Future Improvements (Planned for Subsequent Milestones)

- **Authentication & RBAC:** Currently, vendor registration is open; JWT-based authentication and role-based access control (Admin vs. Vendor) are planned for Milestone 2.
- **Inventory Updates on Sale:** Current transactions record sales; automated decrements to inventory stock and low-stock alerts will be expanded in Milestone 2.
- **CSV Data Ingestion Pipeline:** An automated background job to import historical CSV records into PostgreSQL transactions will be integrated.
