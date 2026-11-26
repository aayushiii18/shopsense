"""
dashboard/executive_bi.py — ShopSense Milestone 4 Phase 3: Admin-Only Executive BI Dashboard.

Consumes Phase 2 Executive Analytics APIs exclusively (`GET /analytics/executive/summary`,
`GET /analytics/executive/trends`, `GET /analytics/executive/vendors`) without duplicating
KPI calculations in Streamlit. Matches the Midnight Navy, Electric Violet, Sky Blue, Cool White,
Emerald, and Amber ShopSense design identity.
"""

from __future__ import annotations

from datetime import date
import html
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from dashboard.ui_theme import (
    BRAND_CONTINUOUS_SCALE,
    BRAND_PALETTE,
    render_hero_banner_html,
    style_chart,
)


def _extract_error_message(resp) -> str:
    """Format HTTP error detail safely without exposing internal stack traces."""
    try:
        payload = resp.json()
        detail = payload.get("detail", resp.text)
        return f"HTTP {resp.status_code}: {detail}"
    except Exception:
        return f"HTTP {resp.status_code}: Unable to retrieve executive analytics."


def _fetch_endpoint_json(
    api_base: str,
    endpoint_path: str,
    headers: Dict[str, str],
    params: Dict[str, Any],
    timeout: float = 5.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """
    Call one Phase 2 Executive API endpoint with URL-encoded query parameters.
    Returns `(json_data, error_message, connection_failed)`.
    """
    clean_params = {k: v for k, v in params.items() if v is not None}
    qs = urlencode(clean_params)
    url = f"{api_base.rstrip('/')}{endpoint_path}"
    if qs:
        url = f"{url}?{qs}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.json(), None, False
        return None, _extract_error_message(resp), False
    except Exception as exc:
        return None, f"Connection failed: {exc}", True


def fetch_executive_dashboard_data(
    *,
    api_base: str,
    headers: Dict[str, str],
    live_api: bool,
    api_online: bool,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    granularity: str = "monthly",
    top_n: int = 10,
    vendor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch centralized Executive Summary, Trends, and Vendor/Product Drilldown from
    Phase 2 Executive Analytics APIs. Falls back to direct `executive_service` calls
    ONLY when running offline/without a live API connection or tokenless AppTest harness.
    Never swallows genuine HTTP 4xx/5xx API errors.
    """
    common_params: Dict[str, Any] = {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
    summary_params = {**common_params, "top_n": int(top_n), "vendor_id": vendor_id}
    trends_params = {**common_params, "granularity": granularity, "vendor_id": vendor_id}
    vendors_params = {**common_params, "skip": 0, "limit": int(top_n)}

    if live_api and api_online and headers:
        summary, err_s, conn_fail_s = _fetch_endpoint_json(
            api_base, "/analytics/executive/summary", headers, summary_params
        )
        if err_s and not conn_fail_s:
            return {"_error": err_s, "_source": "api"}
        if summary is not None:
            trends, err_t, conn_fail_t = _fetch_endpoint_json(
                api_base, "/analytics/executive/trends", headers, trends_params
            )
            if err_t and not conn_fail_t:
                return {"_error": err_t, "_source": "api"}
            vendors, err_v, conn_fail_v = _fetch_endpoint_json(
                api_base, "/analytics/executive/vendors", headers, vendors_params
            )
            if err_v and not conn_fail_v:
                return {"_error": err_v, "_source": "api"}
            if trends is not None and vendors is not None:
                return {
                    "summary": summary,
                    "trends": trends,
                    "vendors": vendors,
                    "_source": "api",
                }

    # Direct service delegation ONLY when API/token unavailable in local DB/offline mode
    from app.database import SessionLocal
    from app.services import executive_service

    db = SessionLocal()
    try:
        try:
            summary = executive_service.get_executive_summary(
                db, start_date=start_date, end_date=end_date, vendor_id=vendor_id, top_n=int(top_n)
            )
            trends = executive_service.get_executive_trends(
                db, granularity=granularity, start_date=start_date, end_date=end_date, vendor_id=vendor_id
            )
            vendors = executive_service.get_executive_vendors_and_products(
                db, start_date=start_date, end_date=end_date, skip=0, limit=int(top_n)
            )
            return {
                "summary": summary,
                "trends": trends,
                "vendors": vendors,
                "_source": "service_fallback",
            }
        except ValueError as exc:
            return {"_error": str(exc), "_source": "service_fallback"}
        except Exception as exc:
            return {"_error": f"Executive analytics service error: {exc}", "_source": "service_fallback"}
    finally:
        db.close()


def _fmt_delta(pct: Optional[float], suffix: str = "% vs prior") -> Optional[str]:
    """Format signed period comparison delta string for `st.metric`."""
    if pct is None:
        return None
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}{suffix}"


def _render_period_comparison_panel(comparison: Dict[str, Any]) -> None:
    """Render comparative window KPIs or honest insufficient-data callout."""
    st.subheader("⚖️ Period-over-Period Performance Comparison")
    if not comparison.get("comparison_supported"):
        note = comparison.get("note") or "Insufficient comparative baseline data for the selected scope."
        st.info(f"ℹ️ {note}")
        return

    cur_lbl = html.escape(str(comparison.get("current_period_label") or "Current Period"))
    prev_lbl = html.escape(str(comparison.get("previous_period_label") or "Previous Period"))
    comp_note = html.escape(str(comparison.get("note") or ""))

    st.markdown(
        f"""
        <div class="sp-card" style="padding:14px 18px; border-left:4px solid #8B5CF6;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span class="sp-badge badge-violet" style="margin-right:8px;">PERIOD COMPARISON</span>
                    <strong style="color:#0F172A;">{cur_lbl}</strong>
                    <span style="color:#64748B; margin:0 6px;">vs</span>
                    <strong style="color:#334155;">{prev_lbl}</strong>
                </div>
                <span style="font-size:0.82rem; color:#475569;">{comp_note}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Current Period GMV",
        f"₹{float(comparison.get('current_gmv') or 0.0):,.2f}",
        delta=_fmt_delta(comparison.get("gmv_change_pct")),
    )
    c2.metric(
        "Current Period Net Sales",
        f"₹{float(comparison.get('current_net_sales') or 0.0):,.2f}",
        delta=_fmt_delta(comparison.get("net_sales_change_pct")),
    )
    c3.metric(
        "Current Period Orders",
        f"{int(comparison.get('current_transactions') or 0):,}",
        delta=_fmt_delta(comparison.get("transactions_change_pct")),
    )
    c4.metric(
        "Current Period AOV",
        f"₹{float(comparison.get('current_aov') or 0.0):,.2f}",
        delta=_fmt_delta(comparison.get("aov_change_pct")),
    )


def _render_kpi_cards(
    financials: Dict[str, Any],
    comparison: Dict[str, Any],
    customers: Dict[str, Any],
    sales_growth: Dict[str, Any],
    inventory_health: Dict[str, Any],
) -> None:
    """Render primary and secondary executive KPI rows using strictly API values."""
    cmp_ok = bool(comparison.get("comparison_supported"))
    gmv_delta = _fmt_delta(comparison.get("gmv_change_pct")) if cmp_ok else None
    net_delta = _fmt_delta(comparison.get("net_sales_change_pct")) if cmp_ok else None
    aov_delta = _fmt_delta(comparison.get("aov_change_pct")) if cmp_ok else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "💰 Gross Merchandise Value (GMV)",
        f"₹{float(financials.get('gross_sales_gmv', 0.0)):,.2f}",
        delta=gmv_delta,
    )
    k2.metric(
        "📈 Net Sales (After Discounts/Refunds)",
        f"₹{float(financials.get('net_sales', 0.0)):,.2f}",
        delta=net_delta,
    )

    has_cost = bool(financials.get("has_cost_data"))
    cov_pct = float(financials.get("cogs_coverage_pct", 0.0))
    if has_cost and financials.get("gross_profit_reported") is not None:
        profit_val = f"₹{float(financials['gross_profit_reported']):,.2f}"
        margin_val = financials.get("gross_margin_pct_reported")
        cov_tag = "Full COGS" if financials.get("cost_coverage_complete") else f"Partial ({cov_pct:.1f}% COGS)"
        profit_delta = f"{float(margin_val):.1f}% margin • {cov_tag}" if margin_val is not None else cov_tag
        k3.metric("💎 Gross Profit (Reported Items)", profit_val, delta=profit_delta, delta_color="off")
    else:
        k3.metric("💎 Gross Profit (Reported Items)", "N/A (No Cost Data)", delta="0.0% COGS coverage", delta_color="off")

    k4.metric(
        "🧾 Average Order Value (AOV)",
        f"₹{float(financials.get('avg_order_value', 0.0)):,.2f}",
        delta=aov_delta or f"{int(financials.get('total_transactions', 0)):,} orders",
        delta_color="normal" if aov_delta else "off",
    )

    # Explicit coverage transparency banner when COGS data is missing or partial
    cov_msg = financials.get("coverage_status") or ""
    if not has_cost:
        st.warning(f"⚠️ **Incomplete Cost Coverage Guardrail:** {cov_msg}")
    elif financials.get("is_partial_profit"):
        st.info(f"ℹ️ **Partial Cost Coverage Notice:** {cov_msg}")

    c1, c2, c3, c4 = st.columns(4)
    total_tx = int(financials.get("total_transactions", 0))
    total_units = int(financials.get("total_units_sold", 0))
    c1.metric(
        "🛒 Orders & Units Volume",
        f"{total_tx:,}",
        delta=f"{total_units:,} units sold",
        delta_color="off",
    )

    reg_cust = customers.get("total_registered_customers")
    purch_cust = int(customers.get("purchasing_customers", 0))
    active_90d = int(customers.get("active_customers_90d", 0))
    cust_display = f"{purch_cust:,} / {int(reg_cust):,}" if reg_cust is not None else f"{purch_cust:,}"
    c2.metric(
        "👥 Purchasing / Registered Customers",
        cust_display,
        delta=f"{active_90d:,} active (90d window)",
        delta_color="off",
    )

    rep_rate = customers.get("repeat_purchase_rate_pct")
    avg_spend = float(customers.get("avg_customer_spend", 0.0))
    c3.metric(
        "🔁 Repeat Buyer Rate",
        f"{float(rep_rate):.1f}%" if rep_rate is not None else "N/A",
        delta=f"Avg Spend: ₹{avg_spend:,.2f}",
        delta_color="off",
    )

    latest_mom = sales_growth.get("latest_mom_growth_pct")
    latest_period = sales_growth.get("latest_period")
    mom_val = f"{float(latest_mom):+.2f}%" if latest_mom is not None else "Baseline"
    stock_val = float(inventory_health.get("total_stock_valuation", 0.0))
    c4.metric(
        "🚀 Latest MoM Growth & Stock Value",
        mom_val,
        delta=f"{latest_period or 'N/A'} • Stock: ₹{stock_val:,.0f}",
        delta_color="off",
    )


def _render_trends_section(trends_payload: Dict[str, Any], granularity: str) -> None:
    """Render interactive Daily / Monthly sales & order trajectory Plotly charts."""
    st.subheader(f"📈 Executive Sales & Revenue Trends ({granularity.title()})")
    series = trends_payload.get("series") or []
    if not series:
        st.info("No chronological transactions match the active filter window.")
        return

    df_t = pd.DataFrame(series)
    col_l, col_r = st.columns(2)
    with col_l:
        fig_rev = go.Figure()
        fig_rev.add_trace(
            go.Bar(
                x=df_t["period"],
                y=df_t["gmv"],
                name="Gross GMV (₹)",
                marker_color=BRAND_PALETTE[0],
                hovertemplate="%{x}<br>GMV: ₹%{y:,.2f}<extra></extra>",
            )
        )
        fig_rev.add_trace(
            go.Scatter(
                x=df_t["period"],
                y=df_t["net_sales"],
                name="Net Sales (₹)",
                mode="lines+markers",
                line=dict(color=BRAND_PALETTE[1], width=3),
                marker=dict(size=7, color=BRAND_PALETTE[2]),
                hovertemplate="%{x}<br>Net Sales: ₹%{y:,.2f}<extra></extra>",
            )
        )
        fig_rev.update_layout(
            title=f"{granularity.title()} GMV vs Net Sales",
            xaxis_title="Period",
            yaxis_title="Revenue (₹)",
            barmode="group",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        style_chart(fig_rev, height=340)
        st.plotly_chart(fig_rev, use_container_width=True)

    with col_r:
        fig_ord = go.Figure()
        fig_ord.add_trace(
            go.Bar(
                x=df_t["period"],
                y=df_t["orders"],
                name="Order Count",
                marker_color=BRAND_PALETTE[6],
                hovertemplate="%{x}<br>Orders: %{y:,}<extra></extra>",
            )
        )
        fig_ord.add_trace(
            go.Scatter(
                x=df_t["period"],
                y=df_t["avg_order_value"],
                name="AOV (₹)",
                mode="lines+markers",
                yaxis="y2",
                line=dict(color=BRAND_PALETTE[0], width=2.5, dash="dot"),
                marker=dict(size=6, color=BRAND_PALETTE[1]),
                hovertemplate="%{x}<br>AOV: ₹%{y:,.2f}<extra></extra>",
            )
        )
        fig_ord.update_layout(
            title=f"{granularity.title()} Order Volume & AOV",
            xaxis_title="Period",
            yaxis=dict(title="Orders"),
            yaxis2=dict(title="AOV (₹)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        style_chart(fig_ord, height=340)
        st.plotly_chart(fig_ord, use_container_width=True)


def _render_vendors_and_products_section(
    vendors_overview: Dict[str, Any],
    products_overview: Dict[str, Any],
    drilldown_payload: Dict[str, Any],
) -> None:
    """Render Vendor Performance Ranking + Revenue Share and Product Performance Drilldowns."""
    vendor_rows = drilldown_payload.get("vendors") or vendors_overview.get("top_vendors") or []
    product_rows = drilldown_payload.get("products") or products_overview.get("top_products") or []

    st.subheader("🏢 Vendor Performance Ranking & Revenue Contribution")
    v_col1, v_col2 = st.columns([1.15, 1.35])
    with v_col1:
        if vendor_rows:
            df_v = pd.DataFrame(vendor_rows).sort_values("gross_revenue", ascending=True)
            fig_v = px.bar(
                df_v,
                x="gross_revenue",
                y="vendor_name",
                orientation="h",
                text="market_share_pct",
                color="gross_revenue",
                color_continuous_scale=BRAND_CONTINUOUS_SCALE,
                labels={"gross_revenue": "Gross Revenue (₹)", "vendor_name": "Vendor", "market_share_pct": "Share (%)"},
                title="Vendor Revenue Contribution & Market Share",
                hover_data={"order_count": True, "units_sold": True, "vendor_payout": ":,.2f"},
            )
            fig_v.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            style_chart(fig_v, height=330, show_legend=False)
            fig_v.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("No vendor sales activity in selected date window.")

    with v_col2:
        if vendor_rows:
            disp_v = pd.DataFrame(vendor_rows)[
                [
                    "rank",
                    "vendor_name",
                    "status",
                    "commission_tier",
                    "gross_revenue",
                    "net_sales",
                    "platform_commission",
                    "vendor_payout",
                    "market_share_pct",
                    "order_count",
                ]
            ].rename(
                columns={
                    "rank": "Rank",
                    "vendor_name": "Vendor",
                    "status": "Status",
                    "commission_tier": "Tier",
                    "gross_revenue": "GMV (₹)",
                    "net_sales": "Net Sales (₹)",
                    "platform_commission": "Commission (₹)",
                    "vendor_payout": "Payout (₹)",
                    "market_share_pct": "Share %",
                    "order_count": "Orders",
                }
            )
            st.dataframe(disp_v, use_container_width=True, hide_index=True)
        else:
            st.info("Vendor leaderboard is empty for the current filters.")

    st.markdown("---")
    st.subheader("📦 Top Products Performance & Cost Coverage")
    p_col1, p_col2 = st.columns([1.1, 1.4])
    with p_col1:
        if product_rows:
            df_p = pd.DataFrame(product_rows).head(10).sort_values("gross_revenue", ascending=True)
            fig_p = px.bar(
                df_p,
                x="gross_revenue",
                y="product_name",
                orientation="h",
                color_discrete_sequence=[BRAND_PALETTE[0]],
                labels={"gross_revenue": "Gross Revenue (₹)", "product_name": "Product"},
                title="Top Selling Products by Revenue",
                hover_data={"units_sold": True, "category": True, "stock_status": True},
            )
            style_chart(fig_p, height=330, show_legend=False)
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info("No product transactions recorded in the selected scope.")

    with p_col2:
        if product_rows:
            formatted_rows = []
            for p in product_rows:
                profit_str = (
                    f"₹{float(p['gross_profit_reported']):,.2f}"
                    if p.get("has_cost_data") and p.get("gross_profit_reported") is not None
                    else "N/A (No Cost)"
                )
                margin_str = (
                    f"{float(p['gross_margin_pct']):.1f}%"
                    if p.get("has_cost_data") and p.get("gross_margin_pct") is not None
                    else "—"
                )
                formatted_rows.append({
                    "Product": p["product_name"],
                    "Category": p["category"],
                    "Vendor": p["vendor_name"],
                    "GMV (₹)": round(float(p["gross_revenue"]), 2),
                    "Net Sales (₹)": round(float(p["net_sales"]), 2),
                    "Units": int(p["units_sold"]),
                    "Gross Profit": profit_str,
                    "Margin %": margin_str,
                    "Stock": int(p["current_stock"]),
                    "Stock Status": p["stock_status"],
                })
            st.dataframe(pd.DataFrame(formatted_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No product performance rows available for display.")


def _render_inventory_health_section(inv: Dict[str, Any]) -> None:
    """Render Inventory Health overview donut + valuation/DSI summary cards."""
    st.subheader("📋 Marketplace Inventory Health Overview")
    i_left, i_right = st.columns([1.05, 1.45])
    with i_left:
        total_skus = int(inv.get("total_skus", 0))
        if total_skus > 0:
            inv_df = pd.DataFrame([
                {"Status": "HEALTHY", "Count": int(inv.get("healthy_skus", 0))},
                {"Status": "LOW_STOCK", "Count": int(inv.get("low_stock_skus", 0))},
                {"Status": "CRITICAL", "Count": int(inv.get("critical_out_of_stock_skus", 0))},
            ])
            inv_df = inv_df[inv_df["Count"] > 0]
            if not inv_df.empty:
                fig_inv = px.pie(
                    inv_df,
                    names="Status",
                    values="Count",
                    hole=0.52,
                    color="Status",
                    title="SKU Stock Health Distribution",
                    color_discrete_map={
                        "HEALTHY": BRAND_PALETTE[2],
                        "LOW_STOCK": BRAND_PALETTE[4],
                        "CRITICAL": "#EF4444",
                    },
                )
                style_chart(fig_inv, height=290)
                st.plotly_chart(fig_inv, use_container_width=True)
            else:
                st.info("No active inventory quantities recorded.")
        else:
            st.info("No catalog SKUs found for inventory health assessment.")

    with i_right:
        r1c1, r1c2 = st.columns(2)
        r1c1.metric("📦 Total Physical Units", f"{int(inv.get('total_current_stock', 0)):,}", delta=f"{total_skus} tracked SKUs", delta_color="off")
        r1c2.metric("🏦 Inventory Stock Valuation", f"₹{float(inv.get('total_stock_valuation', 0.0)):,.2f}")

        r2c1, r2c2 = st.columns(2)
        r2c1.metric("⚡ Annualized Turnover Ratio", f"{float(inv.get('catalog_turnover_ratio', 0.0)):.2f}x")
        r2c2.metric("⏱️ Days Sales of Inventory (DSI)", f"{float(inv.get('catalog_dsi_days', 0.0)):.1f} days")

        healthy_cnt = int(inv.get("healthy_skus", 0))
        low_cnt = int(inv.get("low_stock_skus", 0))
        crit_cnt = int(inv.get("critical_out_of_stock_skus", 0))
        st.markdown(
            f"""
            <div class="sp-card" style="padding:14px 18px; margin-top:8px;">
                <div class="sp-card-title">SKU Health Breakdown</div>
                <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:6px;">
                    <span class="sp-badge badge-healthy">Healthy: {healthy_cnt}</span>
                    <span class="sp-badge badge-warning">Low Stock Alerts: {low_cnt}</span>
                    <span class="sp-badge badge-critical">Critical / Out-of-Stock: {crit_cnt}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_executive_bi_dashboard(
    *,
    current_role: str,
    api_base: str,
    auth_headers_fn: Callable[[], Dict[str, str]],
    live_api: bool,
    api_online: bool,
) -> None:
    """Render the complete Admin-only Executive BI Dashboard powered by Phase 2 APIs."""
    if str(current_role).upper() != "ADMIN":
        st.error("🔒 Access Denied: Administrator privileges are required to view Executive BI Analytics.")
        return

    # Filter & Controls Bar
    with st.container():
        f1, f2, f3, f4, f5 = st.columns([1.2, 1.15, 1.15, 1.0, 0.9])
        with f1:
            use_date_filter = st.checkbox(
                "Filter Date Range",
                value=False,
                key="exec_bi_use_date_filter",
                help="Enable custom inclusive Start Date and End Date filtering.",
            )
        with f2:
            start_dt_val = st.date_input(
                "Start Date",
                value=date(2024, 1, 1),
                key="exec_bi_start_date",
                disabled=not use_date_filter,
            )
        with f3:
            end_dt_val = st.date_input(
                "End Date",
                value=date.today(),
                key="exec_bi_end_date",
                disabled=not use_date_filter,
            )
        with f4:
            granularity_label = st.selectbox(
                "Trend Granularity",
                ["Monthly", "Daily"],
                index=0,
                key="exec_bi_granularity",
            )
        with f5:
            top_n_val = st.selectbox(
                "Top Vendors / SKUs",
                [5, 10, 25, 50],
                index=1,
                key="exec_bi_top_n",
            )

    active_start = start_dt_val if use_date_filter else None
    active_end = end_dt_val if use_date_filter else None
    granularity_param = granularity_label.lower()

    if use_date_filter and active_start and active_end and active_start > active_end:
        st.error("Invalid Date Filter: Start Date cannot be after End Date.")
        return

    with st.spinner("Loading Executive BI metrics from ShopSense Analytics API..."):
        bundle = fetch_executive_dashboard_data(
            api_base=api_base,
            headers=auth_headers_fn(),
            live_api=live_api,
            api_online=api_online,
            start_date=active_start,
            end_date=active_end,
            granularity=granularity_param,
            top_n=int(top_n_val),
        )

    if bundle.get("_error"):
        st.error(f"❌ Executive Analytics API Error: {bundle['_error']}")
        return

    if bundle.get("_source") == "service_fallback":
        st.info("ℹ️ Backend HTTP API is in local fallback mode — displaying live service calculations.")

    summary = bundle["summary"]
    trends_payload = bundle["trends"]
    drilldown_payload = bundle["vendors"]

    financials = summary["financials"]
    comparison = summary["period_comparison"]
    customers = summary["customers"]
    vendors_overview = summary["vendors"]
    products_overview = summary["products"]
    inventory_health = summary["inventory_health"]
    sales_growth = summary["sales_growth"]

    window_label = (
        f"{active_start.isoformat()} → {active_end.isoformat()}"
        if use_date_filter and active_start and active_end
        else "All Historical Data"
    )
    cov_badge = (
        f"COGS Coverage: {float(financials.get('cogs_coverage_pct', 0.0)):.1f}%"
        if financials.get("has_cost_data")
        else "COGS Coverage: Unrecorded (0%)"
    )

    st.markdown(
        render_hero_banner_html(
            tag="💎 Executive Business Intelligence • Admin Only",
            title="Executive Performance & Financial Command Center",
            subtitle=(
                "Unified SQL-aggregated platform intelligence spanning Gross Merchandise Value, net sales, "
                "cost-guarded margins, period-over-period trajectories, vendor market share, and inventory turnover."
            ),
            pills=[
                f"Window: {window_label}",
                f"GMV: ₹{float(financials.get('gross_sales_gmv', 0.0)):,.2f}",
                f"Orders: {int(financials.get('total_transactions', 0)):,}",
                cov_badge,
            ],
        ),
        unsafe_allow_html=True,
    )

    _render_kpi_cards(financials, comparison, customers, sales_growth, inventory_health)
    st.markdown("---")
    _render_period_comparison_panel(comparison)
    st.markdown("---")

    if int(financials.get("total_transactions", 0)) == 0:
        st.info(
            "📭 No marketplace transactions were recorded for the selected date range. "
            "Adjust Start Date / End Date filters above to inspect historical performance."
        )
    else:
        _render_trends_section(trends_payload, granularity_param)
        st.markdown("---")
        _render_vendors_and_products_section(vendors_overview, products_overview, drilldown_payload)
        st.markdown("---")

    _render_inventory_health_section(inventory_health)
