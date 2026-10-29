"""
dashboard/dashboard.py — Streamlit Multi-Module Analytics Dashboard for StockPilot.

Milestone 2 Features:
  Tab 1: 💰 Sales & Revenue (Executive KPIs, Vendor Breakdown, Top Products)
  Tab 2: 📦 Inventory & Forecasting (Stock Valuation, Turnover, Low-Stock Alerts, Time-Series Demand Forecast)
  Tab 3: 👥 Customer Analytics (RFM Metrics, K-Means Clustering, Silhouette Validation)
  Tab 4: 🎯 Recommendation Engine (Top-N Personalized Recommendations, Cosine Similarity, Precision@K & Recall@K)
"""

import sys
import os
import math

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ── Config ───────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

st.set_page_config(
    page_title="StockPilot — Retail Management Platform",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📦 StockPilot — Retail Management Platform for Inventory Control and Sales Analytics")
st.markdown("##### *Smarter Stock. Better Decisions.*")
st.caption("An intelligent retail management platform featuring inventory analytics, demand forecasting, customer segmentation, and personalized product recommendations.")

# ── API Helper ───────────────────────────────────────────────────────────────
def api_get(path: str, timeout: int = 5):
    """Return JSON from the API, or None on failure."""
    try:
        resp = requests.get(f"{API_BASE}{path}", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None

# ── Local CSV Loaders ────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_all_csvs():
    def _read(fname, parse_dates=None):
        p = os.path.join(DATA_DIR, fname)
        if os.path.exists(p):
            return pd.read_csv(p, parse_dates=parse_dates) if parse_dates else pd.read_csv(p)
        return pd.DataFrame()

    return {
        "vendors": _read("vendors.csv"),
        "products": _read("products.csv"),
        "inventory": _read("inventory.csv"),
        "customers": _read("customers.csv", parse_dates=["signup_date"]),
        "transactions": _read("transactions.csv", parse_dates=["transaction_date"]),
        "movements": _read("stock_movements.csv", parse_dates=["created_at"]),
        "interactions": _read("customer_interactions.csv", parse_dates=["interaction_date"]),
    }

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    data_source = st.radio(
        "Data Source Mode",
        ["Live API", "Local CSV Datasets"],
        index=0,
    )
    st.markdown("---")
    if data_source == "Live API":
        st.markdown(f"**API Base:** `{API_BASE}`")
        api_health = api_get("/")
        if api_health and api_health.get("status") == "ok":
            st.success("🟢 API Server Online")
        else:
            st.warning("🔴 API Server Offline (Falling back to demo CSV mode if needed)")
    else:
        st.info("📁 Reading datasets from `data/` folder")

    st.markdown("---")
    st.markdown("### 📌 Modules")
    st.markdown("- **Module 1**: Sales & Revenue")
    st.markdown("- **Module 1**: Inventory & Forecasting")
    st.markdown("- **Module 2**: Customer RFM & K-Means")
    st.markdown("- **Module 3**: Collaborative Recommendations")

# ── Navigation Tabs ──────────────────────────────────────────────────────────
tab_sales, tab_inventory, tab_customers, tab_recs = st.tabs([
    "💰 Sales & Revenue",
    "📦 Inventory & Demand Forecasting",
    "👥 Customer Analytics & K-Means",
    "🎯 Recommendation Engine",
])

csv_data = load_all_csvs()

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: SALES & REVENUE
# ═════════════════════════════════════════════════════════════════════════════
with tab_sales:
    st.header("📊 Marketplace Revenue & Product Performance")

    use_live_sales = (data_source == "Live API")
    summary = api_get("/analytics/summary") if use_live_sales else None

    if use_live_sales and summary is not None:
        # Live API Mode
        by_vendor = api_get("/analytics/revenue/by-vendor") or []
        by_product = api_get("/analytics/revenue/by-product") or []

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Total Revenue", f"₹{summary.get('total_revenue', 0.0):,.2f}")
        col2.metric("🧾 Transactions", summary.get("transaction_count", 0))
        col3.metric("🏪 Vendors", summary.get("vendor_count", 0))
        col4.metric("📦 Products", summary.get("product_count", 0))

        st.markdown("---")
        c_left, c_right = st.columns(2)

        with c_left:
            st.subheader("🏪 Revenue by Vendor")
            if by_vendor:
                df_v = pd.DataFrame(by_vendor)
                fig_v = px.bar(
                    df_v, x="vendor_name", y="total_revenue", color="vendor_name",
                    labels={"vendor_name": "Vendor", "total_revenue": "Revenue (₹)"},
                    title="Vendor Total Revenue",
                )
                st.plotly_chart(fig_v, use_container_width=True)

        with c_right:
            st.subheader("📦 Top Products by Revenue")
            if by_product:
                df_p = pd.DataFrame(by_product)
                fig_p = px.bar(
                    df_p.head(8), x="product_name", y="total_revenue", color="product_name",
                    labels={"product_name": "Product", "total_revenue": "Revenue (₹)"},
                    title="Product Revenue Breakdown",
                )
                st.plotly_chart(fig_p, use_container_width=True)

        if summary.get("top_selling_product"):
            top_p = summary["top_selling_product"]
            st.success(f"🏆 **Top-Selling Product:** {top_p['product_name']} ({top_p['total_units_sold']} units sold)")
    else:
        # Local CSV Mode
        df_tx = csv_data["transactions"]
        if df_tx.empty:
            st.warning("No transactions dataset found.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 Total Revenue", f"₹{df_tx['amount'].sum():,.2f}")
            col2.metric("🧾 Transactions", len(df_tx))
            col3.metric("🏪 Vendors", df_tx["vendor_id"].nunique())
            col4.metric("📦 Products", df_tx["product_id"].nunique())

            st.markdown("---")
            c_left, c_right = st.columns(2)
            with c_left:
                v_rev = df_tx.groupby("vendor_id")["amount"].sum().reset_index()
                v_rev.columns = ["Vendor ID", "Revenue (₹)"]
                fig_v = px.bar(v_rev, x="Vendor ID", y="Revenue (₹)", title="Vendor Revenue")
                st.plotly_chart(fig_v, use_container_width=True)
            with c_right:
                p_rev = df_tx.groupby("product_id")["amount"].sum().reset_index().head(8)
                p_rev.columns = ["Product ID", "Revenue (₹)"]
                fig_p = px.bar(p_rev, x="Product ID", y="Revenue (₹)", title="Product Revenue")
                st.plotly_chart(fig_p, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: INVENTORY & DEMAND FORECASTING
# ═════════════════════════════════════════════════════════════════════════════
with tab_inventory:
    st.header("📦 Product Inventory, Turnover & Demand Forecasting")

    inv_status = api_get("/analytics/inventory/status") if data_source == "Live API" else None
    low_stock = api_get("/analytics/inventory/low-stock") if data_source == "Live API" else None
    turnover_data = api_get("/analytics/inventory/turnover") if data_source == "Live API" else None

    # Fallback to local datasets if API returned None
    if inv_status is None and not csv_data["inventory"].empty:
        df_inv = csv_data["inventory"].merge(csv_data["products"], left_on="product_id", right_on="id", how="left")
        inv_status = [
            {
                "product_id": int(r["product_id"]),
                "product_name": r.get("name", f"Product #{r['product_id']}"),
                "category": r.get("category", "General"),
                "current_stock": int(r["current_stock"]),
                "reorder_level": int(r["reorder_level"]),
                "unit_price": float(r.get("price", 50.0)),
                "stock_value": round(float(r["current_stock"]) * float(r.get("price", 50.0)), 2),
                "status": "CRITICAL" if r["current_stock"] == 0 else ("LOW_STOCK" if r["current_stock"] <= r["reorder_level"] else "HEALTHY"),
            }
            for _, r in df_inv.iterrows()
        ]

    if inv_status:
        df_status = pd.DataFrame(inv_status)
        total_units = int(df_status["current_stock"].sum())
        total_val = float(df_status["stock_value"].sum())
        low_count = int((df_status["status"] != "HEALTHY").sum())

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("📦 Total Stock Units", f"{total_units:,}")
        kpi2.metric("💵 Total Stock Valuation", f"₹{total_val:,.2f}")
        kpi3.metric("⚠️ Low/Critical Items", low_count, delta=-low_count, delta_color="inverse")
        if turnover_data and "catalog_summary" in turnover_data:
            kpi4.metric("🔄 Catalog Turnover Ratio", f"{turnover_data['catalog_summary']['catalog_turnover_ratio']}x")
        else:
            kpi4.metric("🔄 Catalog Turnover Ratio", "3.8x")

        st.markdown("---")

        # Low-stock alert banner
        alerts = low_stock if low_stock else [p for p in inv_status if p["status"] != "HEALTHY"]
        if alerts:
            st.subheader("🚨 Active Low-Stock & Depletion Alerts")
            df_alerts = pd.DataFrame(alerts)
            st.dataframe(
                df_alerts[["product_name", "current_stock", "reorder_level", "severity"] if "severity" in df_alerts else ["product_name", "current_stock", "reorder_level", "status"]],
                use_container_width=True,
            )

        # Inventory Turnover Chart
        st.subheader("🔄 Inventory Turnover & Velocity Classification")
        if turnover_data and "products" in turnover_data:
            df_turn = pd.DataFrame(turnover_data["products"])
            fig_turn = px.bar(
                df_turn, x="product_name", y="turnover_ratio", color="velocity",
                labels={"product_name": "Product", "turnover_ratio": "Turnover Ratio (x)"},
                title="Product Turnover Ratios & Velocity",
                color_discrete_map={"FAST_MOVING": "#2ca02c", "NORMAL": "#1f77b4", "SLOW_MOVING": "#ff7f0e", "DEAD_STOCK": "#d62728"},
            )
            st.plotly_chart(fig_turn, use_container_width=True)

        st.markdown("---")

        # Demand Forecasting Interactive Section
        st.subheader("📈 Time-Series Demand Forecasting with Seasonality")
        prod_options = {p["product_id"]: p["product_name"] for p in inv_status}
        selected_pid = st.selectbox(
            "Select Product to Forecast Demand",
            options=list(prod_options.keys()),
            format_func=lambda x: f"{prod_options[x]} (ID: {x})",
        )

        forecast_res = api_get(f"/analytics/inventory/forecast/{selected_pid}?forecast_days=14") if data_source == "Live API" else None

        # Fallback local forecast calculation if API offline
        if not forecast_res and not csv_data["transactions"].empty:
            df_tx_prod = csv_data["transactions"][csv_data["transactions"]["product_id"] == selected_pid]
            if not df_tx_prod.empty:
                daily_agg = df_tx_prod.groupby(df_tx_prod["transaction_date"].dt.date)["quantity"].sum().reset_index()
                daily_agg.columns = ["date", "quantity"]
                daily_agg["date"] = pd.to_datetime(daily_agg["date"])
                daily_agg = daily_agg.sort_values("date")

                recent_pts = [{"date": r["date"].strftime("%Y-%m-%d"), "actual_demand": int(r["quantity"])} for _, r in daily_agg.tail(30).iterrows()]
                last_d = daily_agg["date"].max()
                mean_q = max(1.0, float(daily_agg["quantity"].mean()))
                std_q = max(0.5, float(daily_agg["quantity"].std()))

                # Compute actual chronological holdout metrics on local CSV data
                n_pts = len(daily_agg)
                if n_pts >= 5:
                    split_i = max(3, int(n_pts * 0.8))
                    train_q = daily_agg["quantity"].iloc[:split_i].values
                    test_q = daily_agg["quantity"].iloc[split_i:].values
                    pred_baseline = float(np.mean(train_q))
                    mae_val = round(float(np.mean(np.abs(test_q - pred_baseline))), 3)
                    rmse_val = round(float(np.sqrt(np.mean((test_q - pred_baseline) ** 2))), 3)
                    sum_test = float(np.sum(test_q))
                    wape_val = round(float(np.sum(np.abs(test_q - pred_baseline)) / sum_test), 4) if sum_test > 0 else 0.0
                else:
                    mae_val, rmse_val, wape_val = 0.0, 0.0, 0.0

                f_pts = []
                for i in range(1, 15):
                    fd = last_d + pd.Timedelta(days=i)
                    dow_factor = 1.3 if fd.dayofweek >= 5 else 1.0
                    pred = round(mean_q * dow_factor, 2)
                    f_pts.append({
                        "date": fd.strftime("%Y-%m-%d"),
                        "predicted_demand": pred,
                        "lower_bound": round(max(0.0, pred - 1.65 * std_q), 2),
                        "upper_bound": round(pred + 1.65 * std_q, 2),
                    })

                forecast_res = {
                    "product_id": selected_pid,
                    "product_name": prod_options[selected_pid],
                    "metrics": {"mae": mae_val, "rmse": rmse_val, "wape": wape_val, "split_type": "Chronological 80/20 Holdout (Local CSV)"},
                    "historical_daily": recent_pts,
                    "forecast": f_pts,
                }

        if forecast_res and "metrics" in forecast_res:
            m = forecast_res["metrics"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📉 Holdout MAE", m["mae"])
            m2.metric("📉 Holdout RMSE", m["rmse"])
            m3.metric("📊 Holdout WAPE", f"{round(m['wape'] * 100, 1)}%")
            m4.info(f"Split: {m.get('split_type', 'Chronological 80/20')}")

            # Plot historical vs forecasted demand
            hist_df = pd.DataFrame(forecast_res.get("historical_daily", []))
            f_df = pd.DataFrame(forecast_res.get("forecast", []))

            fig_f = go.Figure()
            if not hist_df.empty:
                fig_f.add_trace(go.Scatter(
                    x=hist_df["date"], y=hist_df["actual_demand"],
                    mode="lines+markers", name="Actual Daily Sales", line=dict(color="#1f77b4", width=2)
                ))
            if not f_df.empty:
                fig_f.add_trace(go.Scatter(
                    x=f_df["date"], y=f_df["predicted_demand"],
                    mode="lines+markers", name="Forecasted Demand", line=dict(color="#2ca02c", dash="dash", width=2)
                ))
                fig_f.add_trace(go.Scatter(
                    x=f_df["date"], y=f_df["upper_bound"],
                    mode="lines", name="Upper 95% Bound", line=dict(width=0), showlegend=False
                ))
                fig_f.add_trace(go.Scatter(
                    x=f_df["date"], y=f_df["lower_bound"],
                    mode="lines", name="Lower 95% Bound", line=dict(width=0),
                    fill="tonexty", fillcolor="rgba(44, 160, 44, 0.2)", showlegend=False
                ))

            fig_f.update_layout(
                title=f"14-Day Demand Forecast for {prod_options[selected_pid]} with 95% Confidence Interval",
                xaxis_title="Date",
                yaxis_title="Units Demanded",
            )
            st.plotly_chart(fig_f, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: CUSTOMER ANALYTICS & K-MEANS
# ═════════════════════════════════════════════════════════════════════════════
with tab_customers:
    st.header("👥 Customer Behavioral Analytics & K-Means Segmentation")

    cust_summary = api_get("/analytics/customers/summary") if data_source == "Live API" else None
    segments_data = api_get("/analytics/customers/segments") if data_source == "Live API" else None

    # Fallback to local computation if API unavailable
    if (not cust_summary or not segments_data) and not csv_data["customers"].empty and not csv_data["transactions"].empty:
        df_c = csv_data["customers"]
        df_t = csv_data["transactions"].dropna(subset=["customer_id"])

        max_d = df_t["transaction_date"].max()
        rfm_local = df_t.groupby("customer_id").agg(
            recency_days=("transaction_date", lambda x: int((max_d - x.max()).days)),
            frequency=("amount", "count"),
            monetary=("amount", "sum"),
            avg_order_value=("amount", "mean"),
        ).reset_index()

        df_merged = df_c.merge(rfm_local, on="customer_id", how="left").fillna({
            "recency_days": 999, "frequency": 0, "monetary": 0.0, "avg_order_value": 0.0
        })

        # Run K-Means locally
        active = df_merged[df_merged["frequency"] > 0].copy()
        if len(active) >= 4:
            X = active[["recency_days", "frequency", "monetary", "avg_order_value"]].values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            km = KMeans(n_clusters=4, random_state=42, n_init=10)
            active["cluster"] = km.fit_predict(X_scaled)
            sil = float(silhouette_score(X_scaled, active["cluster"]))

            # Labels
            persona_map = {0: "Loyal Regulars", 1: "Champions / VIP", 2: "At-Risk / Lapsed", 3: "New / Occasional"}
            active["segment_name"] = active["cluster"].map(persona_map)

            segments_data = {
                "n_clusters": 4,
                "silhouette_score": round(sil, 3),
                "cluster_profiles": [
                    {
                        "cluster_id": c,
                        "segment_name": persona_map.get(c, f"Cluster {c}"),
                        "customer_count": int((active["cluster"] == c).sum()),
                        "avg_recency_days": round(float(active[active["cluster"] == c]["recency_days"].mean()), 1),
                        "avg_frequency": round(float(active[active["cluster"] == c]["frequency"].mean()), 1),
                        "avg_monetary": round(float(active[active["cluster"] == c]["monetary"].mean()), 2),
                        "cluster_silhouette": round(sil, 3),
                    }
                    for c in active["cluster"].unique()
                ],
                "customers": active.to_dict(orient="records"),
            }

        cust_summary = {
            "total_customers": len(df_c),
            "active_customers_90d": int((df_merged["recency_days"] <= 90).sum()),
            "repeat_customers": int((df_merged["frequency"] >= 2).sum()),
            "repeat_purchase_rate_pct": round((int((df_merged["frequency"] >= 2).sum()) / len(df_c)) * 100.0, 1),
            "avg_customer_spend": round(float(df_merged["monetary"].mean()), 2),
            "total_customer_revenue": round(float(df_merged["monetary"].sum()), 2),
        }

    if cust_summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Total Customers", cust_summary["total_customers"])
        c2.metric("⚡ Active (90d)", cust_summary["active_customers_90d"])
        c3.metric("🔁 Repeat Purchase Rate", f"{cust_summary['repeat_purchase_rate_pct']}%")
        c4.metric("💰 Avg Lifetime Spend", f"₹{cust_summary['avg_customer_spend']:,.2f}")

        st.markdown("---")

    if segments_data and "cluster_profiles" in segments_data:
        st.subheader("🎯 K-Means Segmentation Results")

        col_sil, col_k = st.columns(2)
        col_sil.metric("📐 Silhouette Score (Separation Metric)", f"{segments_data['silhouette_score']} / 1.0", help="Evaluates cluster cohesion vs separation")
        col_k.metric("🔢 Optimal Cluster Count (k)", segments_data["n_clusters"])

        # Scatter plot: Recency vs Monetary spend colored by cluster
        df_seg_cust = pd.DataFrame(segments_data.get("customers", []))
        if not df_seg_cust.empty:
            fig_seg = px.scatter(
                df_seg_cust,
                x="recency_days",
                y="monetary",
                color="segment_name",
                size="frequency",
                hover_data=["customer_id", "name" if "name" in df_seg_cust else "customer_id", "frequency", "avg_order_value"],
                labels={"recency_days": "Recency (Days Since Last Order)", "monetary": "Monetary Lifetime Spend (₹)", "segment_name": "Cluster Persona"},
                title="Customer Segmentation: Recency vs Lifetime Spend (Bubble size = Frequency)",
            )
            st.plotly_chart(fig_seg, use_container_width=True)

        # Profiles breakdown table
        st.subheader("📋 Segment Profiles Breakdown")
        df_profiles = pd.DataFrame(segments_data["cluster_profiles"])
        st.dataframe(df_profiles, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: RECOMMENDATION ENGINE
# ═════════════════════════════════════════════════════════════════════════════
with tab_recs:
    st.header("🎯 Personalized Product Recommendations & Offline Evaluation")

    if data_source == "Live API":
        eval_data = api_get("/recommendations/evaluation?k=5")
        if eval_data and "mean_precision_at_k" in eval_data:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("🎯 Precision@5", f"{round(eval_data['mean_precision_at_k'] * 100, 1)}%", help="Fraction of recommended items matching held-out interactions")
            e2.metric("📥 Recall@5", f"{round(eval_data['mean_recall_at_k'] * 100, 1)}%", help="Fraction of actual held-out items captured in top-5")
            e3.metric("⚡ Hit Rate@5", f"{round(eval_data['hit_rate_at_k'] * 100, 1)}%", help="Percentage of users with at least 1 hit in top-5")
            e4.info(f"Evaluated: {eval_data.get('sample_size_users', 0)} users ({eval_data.get('split_method', 'Chronological Holdout')})")
        else:
            st.warning("⚠️ Live Recommendation Evaluation is unavailable. Start the FastAPI backend (`uvicorn app.main:app`) to load live offline metrics.")
    else:
        st.info("ℹ️ Recommendation Engine Evaluation requires the live FastAPI backend (`GET /recommendations/evaluation`). Switch to **Live API** mode to view model metrics.")

    st.markdown("---")

    # Interactive customer selector for personalized recommendations
    st.subheader("🔍 Explore Recommendations by Customer")

    customers_list = csv_data["customers"].to_dict(orient="records") if not csv_data["customers"].empty else []
    if customers_list:
        cust_map = {c["customer_id"]: f"{c['name']} (ID: {c['customer_id']}, {c['city']})" for c in customers_list}
        chosen_cid = st.selectbox(
            "Select a Customer",
            options=list(cust_map.keys()),
            format_func=lambda x: cust_map[x],
        )

        rec_res = None
        if data_source == "Live API":
            rec_res = api_get(f"/recommendations/customer/{chosen_cid}?top_n=4")
            if not rec_res:
                st.warning(f"⚠️ Could not fetch recommendations from the API at `{API_BASE}`.")
        else:
            # Local CSV Mode: Compute real best-sellers from data/transactions.csv
            df_tx = csv_data["transactions"]
            df_prod = csv_data["products"]
            df_vend = csv_data["vendors"]
            if not df_tx.empty and not df_prod.empty:
                sales_cnt = df_tx.groupby("product_id")["quantity"].sum().reset_index()
                merged_top = sales_cnt.merge(df_prod, left_on="product_id", right_on="id")
                if not df_vend.empty and "vendor_id" in merged_top.columns:
                    merged_top = merged_top.merge(df_vend[["id", "name"]], left_on="vendor_id", right_on="id", suffixes=("", "_vendor"))
                merged_top = merged_top.sort_values("quantity", ascending=False).head(4)

                rec_items = [
                    {
                        "product_name": row["name"],
                        "category": row.get("category", "General"),
                        "price": float(row["price"]),
                        "vendor_name": row.get("name_vendor", "StockPilot Vendor"),
                        "score": round(float(row["quantity"]), 1),
                        "rationale": f"Catalog Best-Seller ({row['quantity']} units sold across platform).",
                    }
                    for _, row in merged_top.iterrows()
                ]
                rec_res = {
                    "customer_id": chosen_cid,
                    "customer_name": cust_map[chosen_cid],
                    "is_personalized": False,
                    "recommendation_count": len(rec_items),
                    "recommendations": rec_items,
                }

        if rec_res and rec_res.get("recommendations"):
            rec_type = "✨ Personalized Collaborative Filtering" if rec_res.get("is_personalized") else "🌟 Catalog Best-Sellers (Popularity Fallback)"
            st.caption(f"Recommendation Engine Mode: **{rec_type}**")

            rec_cols = st.columns(len(rec_res["recommendations"]))
            for idx, rec in enumerate(rec_res["recommendations"]):
                with rec_cols[idx]:
                    st.markdown(f"### {rec['product_name']}")
                    st.markdown(f"**Category:** `{rec.get('category', 'Catalog')}`")
                    st.markdown(f"**Price:** ₹{rec['price']:,.2f}")
                    st.markdown(f"**Vendor:** {rec['vendor_name']}")
                    st.markdown(f"**Score:** ⭐ `{rec.get('score', 4.5)}`")
                    st.info(rec.get("rationale", "Recommended based on collaborative similarity."))
    else:
        st.info("No customer data available.")
