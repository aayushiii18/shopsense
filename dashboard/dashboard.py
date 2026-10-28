"""
dashboard/dashboard.py — Streamlit analytics dashboard for ShopSense.

Run:
    streamlit run dashboard/dashboard.py

The dashboard fetches live data from the FastAPI backend (must be running).
It falls back to the local data/transactions.csv if the API is unreachable.
"""

import sys
import os

# Allow imports from the project root when running via `streamlit run`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# ── Config ───────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "transactions.csv")

st.set_page_config(
    page_title="ShopSense Analytics",
    page_icon="🛍️",
    layout="wide",
)

st.title("🛍️ ShopSense — Sales Analytics Dashboard")
st.caption("Retail Management Platform for Inventory Control and Sales Analytics")

# ── Helper: fetch from API ────────────────────────────────────────────────────

def api_get(path: str):
    """Return JSON from the API, or None on failure."""
    try:
        resp = requests.get(f"{API_BASE}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Data Source")
    data_source = st.radio(
        "Choose data source",
        ["Live API", "Local CSV (demo)"],
        index=0,
    )
    st.markdown("---")
    st.markdown("**API base URL**")
    st.code(API_BASE)


# ── Load data ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_csv() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()
    return pd.read_csv(CSV_PATH, parse_dates=["transaction_date"])


def load_from_api() -> dict:
    return {
        "summary": api_get("/analytics/summary"),
        "by_vendor": api_get("/analytics/revenue/by-vendor"),
        "by_product": api_get("/analytics/revenue/by-product"),
    }


# ── Render dashboard ──────────────────────────────────────────────────────────

if data_source == "Live API":
    data = load_from_api()

    if not data or data.get("summary") is None:
        st.error(
            "❌ Could not connect to the ShopSense API at " f"`{API_BASE}`.\n\n"
            "**Next steps:**\n"
            "1. Start the API server: `uvicorn app.main:app --reload`\n"
            "2. Or switch to **'Local CSV (demo)'** in the sidebar to view sample data."
        )
        st.stop()
    else:
        summary = data["summary"]
        st.success(" Connected to live ShopSense API")

        # KPI row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Total Revenue", f"₹{summary.get('total_revenue', 0.0):,.2f}")
        col2.metric("🧾 Transactions", summary["transaction_count"])
        col3.metric("🏪 Vendors", summary["vendor_count"])
        col4.metric("📦 Products", summary["product_count"])

        st.markdown("---")

        # Revenue by vendor
        if data["by_vendor"]:
            vendor_df = pd.DataFrame(data["by_vendor"])
            st.subheader("📊 Revenue by Vendor")
            fig_vendor = px.bar(
                vendor_df,
                x="vendor_name",
                y="total_revenue",
                color="vendor_name",
                labels={"vendor_name": "Vendor", "total_revenue": "Revenue (₹)"},
                title="Vendor-wise Total Revenue",
            )
            st.plotly_chart(fig_vendor, use_container_width=True)

        # Revenue by product
        if data["by_product"]:
            product_df = pd.DataFrame(data["by_product"])
            st.subheader("📦 Revenue by Product")
            fig_product = px.bar(
                product_df.head(10),
                x="product_name",
                y="total_revenue",
                color="product_name",
                labels={"product_name": "Product", "total_revenue": "Revenue (₹)"},
                title="Top 10 Products by Revenue",
            )
            st.plotly_chart(fig_product, use_container_width=True)

        # Top-selling product callout
        if summary.get("top_selling_product"):
            top = summary["top_selling_product"]
            st.success(
                f"🏆 **Top-selling product:** {top['product_name']} "
                f"({top['total_units_sold']} units sold)"
            )
        if summary.get("top_vendor_by_revenue"):
            tv = summary["top_vendor_by_revenue"]
            st.info(
                f"🥇 **Top vendor by revenue:** {tv['vendor_name']} "
                f"(₹{tv['total_revenue']:,.2f})"
            )

else:
    # ── Local CSV demo mode ───────────────────────────────────────────────────
    df = load_csv()
    if df.empty:
        st.warning("No CSV data found at data/transactions.csv.")
        st.stop()

    st.info("📁 Showing demo data from `data/transactions.csv`")

    col1, col2 = st.columns(2)
    col1.metric("💰 Total Revenue", f"₹{df['amount'].sum():,.2f}")
    col2.metric("🧾 Transactions", len(df))

    st.markdown("---")

    # Vendor revenue from CSV (uses vendor_id since names aren't in CSV)
    st.subheader("📊 Revenue by Vendor ID (demo)")
    vendor_rev = df.groupby("vendor_id")["amount"].sum().reset_index()
    vendor_rev.columns = ["Vendor ID", "Revenue (₹)"]
    fig_v = px.bar(vendor_rev, x="Vendor ID", y="Revenue (₹)", title="Vendor Revenue")
    st.plotly_chart(fig_v, use_container_width=True)

    # Product revenue from CSV
    st.subheader("📦 Revenue by Product ID (demo)")
    prod_rev = df.groupby("product_id")["amount"].sum().reset_index()
    prod_rev.columns = ["Product ID", "Revenue (₹)"]
    fig_p = px.bar(prod_rev, x="Product ID", y="Revenue (₹)", title="Product Revenue")
    st.plotly_chart(fig_p, use_container_width=True)

    # Top-selling product
    top_product_id = df.groupby("product_id")["quantity"].sum().idxmax()
    top_units = df.groupby("product_id")["quantity"].sum().max()
    st.success(f"🏆 **Top-selling product ID:** {top_product_id} ({top_units} units sold)")

    st.subheader("📋 Raw Transactions")
    st.dataframe(df, use_container_width=True)
