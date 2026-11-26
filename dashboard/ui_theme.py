"""
dashboard/ui_theme.py — ShopSense Enterprise UI Theme, Layout Components & Chart Styling.

Provides:
  - Light-mode enterprise canvas (#F5F7FA) with deep dark-teal sidebar (#0B2B2C)
    and teal/turquoise accent tokens (#0D9488 / #14B8A6 / #2DD4BF).
  - Consistent rounded cards, badges, KPI tiles, hero banners, and login showcase HTML.
  - Unified light Plotly chart theme helper (`style_chart`).
"""

import html
from typing import Iterable, Optional

TEAL_PALETTE = [
    "#0D9488",
    "#14B8A6",
    "#0F3D3E",
    "#0284C7",
    "#6366F1",
    "#F59E0B",
    "#10B981",
]


def style_chart(
    fig,
    height: Optional[int] = None,
    show_legend: Optional[bool] = None,
    title: Optional[str] = None,
):
    """Apply unified clean light-mode enterprise Plotly layout to any figure."""
    layout_kwargs = dict(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(
            family="Plus Jakarta Sans, Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            color="#1E293B",
            size=12,
        ),
        hoverlabel=dict(bgcolor="#0F172A", font_color="#FFFFFF", bordercolor="#0D9488"),
        margin=dict(l=20, r=20, t=44, b=28),
    )
    existing_title = getattr(getattr(fig.layout, "title", None), "text", None)
    if title is not None:
        layout_kwargs["title"] = dict(text=title, font=dict(color="#0F172A", size=15))
    elif existing_title:
        layout_kwargs["title_font"] = dict(color="#0F172A", size=15)
    else:
        # Prevent Plotly.js from rendering literal "undefined" when title is unset
        layout_kwargs["title"] = dict(text="")
    if height is not None:
        layout_kwargs["height"] = height
    if show_legend is not None:
        layout_kwargs["showlegend"] = show_legend

    fig.update_layout(**layout_kwargs)
    fig.update_xaxes(gridcolor="#F1F5F9", linecolor="#E2E8F0", tickfont=dict(color="#475569", size=11), automargin=True)
    fig.update_yaxes(gridcolor="#F1F5F9", linecolor="#E2E8F0", tickfont=dict(color="#475569", size=11), automargin=True)
    return fig


def get_global_css(authenticated: bool = True) -> str:
    """Return global CSS matching the dark-teal sidebar + crisp light enterprise canvas."""
    hide_sidebar_css = (
        """
        section[data-testid="stSidebar"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        """
        if not authenticated
        else ""
    )

    bg_rule = (
        "background: radial-gradient(circle at top right, rgba(20, 184, 166, 0.12), transparent 46%), "
        "linear-gradient(135deg, #F5F7FA 0%, #EAF3F3 100%);"
        if not authenticated
        else "background-color: #F5F7FA;"
    )

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    {hide_sidebar_css}

    html, body, [class*="css"], .stApp {{
        font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    .stApp {{
        {bg_rule}
        color: #0F172A;
    }}

    /* Clean top header chrome */
    header[data-testid="stHeader"] {{
        background-color: rgba(245, 247, 250, 0.9) !important;
        backdrop-filter: blur(8px);
        height: 3.1rem !important;
    }}

    .block-container,
    [data-testid="stMainBlockContainer"] {{
        padding-top: {'3.5rem' if not authenticated else '4.5rem'} !important;
        padding-bottom: 2.5rem !important;
        max-width: 1460px !important;
    }}

    /* ── Dark Forest-Teal Sidebar ─────────────────────────────────────────── */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #092627 0%, #0D3233 100%) !important;
        border-right: 1px solid #134445 !important;
    }}
    section[data-testid="stSidebar"] * {{
        color: #E2F1F0;
    }}
    section[data-testid="stSidebar"] hr {{
        border-color: rgba(148, 192, 190, 0.18) !important;
        margin: 0.85rem 0 !important;
    }}
    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
        color: #8FB8B5 !important;
    }}
    section[data-testid="stSidebar"] code,
    section[data-testid="stSidebar"] .stCaption code {{
        background: rgba(255, 255, 255, 0.14) !important;
        color: #5EEAD4 !important;
        border: 1px solid rgba(94, 234, 212, 0.28) !important;
        border-radius: 6px !important;
        padding: 2px 7px !important;
        font-size: 0.78rem !important;
    }}

    /* Sidebar Navigation Radio -> Pill Buttons */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px !important;
        padding: 8px 12px !important;
        margin-bottom: 4px !important;
        transition: all 0.16s ease;
        cursor: pointer;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {{
        background: rgba(20, 184, 166, 0.12) !important;
        border-color: rgba(45, 212, 191, 0.22) !important;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"],
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {{
        background: linear-gradient(90deg, rgba(20, 184, 166, 0.24) 0%, rgba(13, 148, 136, 0.14) 100%) !important;
        border: 1px solid rgba(45, 212, 191, 0.42) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {{
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] input[type="radio"] {{
        accent-color: #2DD4BF !important;
    }}
    section[data-testid="stSidebar"] .stButton > button {{
        background: rgba(255, 255, 255, 0.08) !important;
        color: #F8FAFC !important;
        border: 1px solid rgba(148, 192, 190, 0.28) !important;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(20, 184, 166, 0.22) !important;
        border-color: #2DD4BF !important;
    }}

    /* ── Typography ──────────────────────────────────────────────────────── */
    h1, h2, h3, h4, h5 {{
        color: #0F172A !important;
        letter-spacing: -0.02em;
    }}
    .ss-hero h2,
    .ss-login-brand h2 {{
        color: #FFFFFF !important;
    }}

    /* ── Cards, Hero & Metric Tiles ──────────────────────────────────────── */
    .sp-card {{
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        transition: box-shadow 0.18s ease, transform 0.18s ease;
    }}
    .sp-card:hover {{
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.07);
    }}
    .sp-card-title {{
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748B;
        margin-bottom: 6px;
    }}
    .sp-card-value {{
        font-size: 1.7rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.15;
    }}
    .sp-card-sub {{
        font-size: 0.82rem;
        color: #64748B;
        margin-top: 6px;
    }}

    /* Dark Teal Hero Banner (Reference Screenshot Match) */
    .ss-hero {{
        background: linear-gradient(135deg, #0B2E30 0%, #114749 55%, #135D5E 100%);
        border: 1px solid #1A6264;
        border-radius: 16px;
        padding: 26px 28px;
        margin-bottom: 18px;
        color: #FFFFFF;
        box-shadow: 0 10px 25px rgba(11, 46, 48, 0.16);
    }}
    .ss-hero-tag {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(45, 212, 191, 0.16);
        border: 1px solid rgba(45, 212, 191, 0.35);
        color: #99F6E4;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 999px;
        margin-bottom: 12px;
    }}
    .ss-hero h2 {{
        color: #FFFFFF !important;
        font-size: 1.65rem !important;
        font-weight: 800 !important;
        margin: 0 0 8px 0 !important;
    }}
    .ss-hero p {{
        color: #CBD5E1;
        font-size: 0.94rem;
        line-height: 1.5;
        margin: 0 0 14px 0;
        max-width: 780px;
    }}
    .ss-hero-pills {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }}
    .ss-hero-pill {{
        background: rgba(15, 23, 42, 0.28);
        border: 1px solid rgba(255, 255, 255, 0.14);
        color: #E2F1F0;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 5px 12px;
        border-radius: 999px;
    }}

    /* Quick Action Strip Cards */
    .ss-quick-tile {{
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
    }}
    .ss-icon-box {{
        width: 38px;
        height: 38px;
        border-radius: 10px;
        background: #E6F7F5;
        color: #0D9488;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.15rem;
        flex-shrink: 0;
        border: 1px solid #CCFBF1;
    }}

    /* Native Metric Styling */
    div[data-testid="stMetric"] {{
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }}
    div[data-testid="stMetric"] label {{
        color: #64748B !important;
        font-weight: 700 !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: #0F172A !important;
        font-weight: 800 !important;
        font-size: 1.7rem !important;
    }}

    /* Top Header Pills */
    .ss-pill {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        white-space: nowrap !important;
        width: 100%;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #334155;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
    }}
    .ss-pill-online {{
        background: #ECFDF5;
        border-color: #A7F3D0;
        color: #047857;
    }}
    .ss-pill-offline {{
        background: #FEF3C7;
        border-color: #FDE68A;
        color: #B45309;
    }}
    .ss-user-chip {{
        display: flex;
        align-items: center;
        gap: 10px;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 999px;
        padding: 4px 14px 4px 6px;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
    }}
    .ss-avatar {{
        width: 30px;
        height: 30px;
        border-radius: 999px;
        background: linear-gradient(135deg, #0D9488 0%, #0F3D3E 100%);
        color: #FFFFFF;
        font-weight: 700;
        font-size: 0.78rem;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}

    /* Status Badges */
    .sp-badge {{
        display: inline-block;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        text-align: center;
        letter-spacing: 0.02em;
    }}
    .badge-healthy {{ background-color: #DCFCE7; color: #15803D; border: 1px solid #86EFAC; }}
    .badge-warning {{ background-color: #FEF3C7; color: #B45309; border: 1px solid #FCD34D; }}
    .badge-critical {{ background-color: #FEE2E2; color: #B91C1C; border: 1px solid #FCA5A5; }}
    .badge-teal {{ background-color: #CCFBF1; color: #0F766E; border: 1px solid #5EEAD4; }}

    /* Login Showcase Panel */
    .ss-login-brand {{
        background: linear-gradient(145deg, #092627 0%, #0E3B3D 55%, #115E59 100%);
        border: 1px solid #1A6264;
        border-radius: 20px;
        padding: 36px 34px;
        color: #FFFFFF;
        box-shadow: 0 16px 36px rgba(11, 46, 48, 0.18);
    }}
    .ss-login-feature {{
        background: rgba(255, 255, 255, 0.07);
        border: 1px solid rgba(148, 192, 190, 0.22);
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }}

    /* Primary Teal Buttons */
    .stButton > button {{
        background: linear-gradient(135deg, #0D9488 0%, #0F766E 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 9px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.1rem !important;
        transition: all 0.18s ease-in-out !important;
        box-shadow: 0 2px 6px rgba(13, 148, 136, 0.22) !important;
    }}
    .stButton > button:hover:not(:disabled) {{
        background: linear-gradient(135deg, #0F766E 0%, #115E59 100%) !important;
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.35) !important;
        transform: translateY(-1px);
    }}
    .stButton > button:disabled {{
        background: #CBD5E1 !important;
        color: #64748B !important;
        box-shadow: none !important;
    }}

    /* Form & Tabs polish */
    div[data-testid="stForm"] {{
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
    }}
    button[data-baseweb="tab"] {{
        font-weight: 600 !important;
        color: #475569 !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: #0D9488 !important;
    }}
    div[data-baseweb="tab-highlight"] {{
        background-color: #0D9488 !important;
    }}
    </style>
    """


def render_brand_logo_html(subtitle: str = "MARKETPLACE ANALYTICS") -> str:
    """Render clean ShopSense sidebar brand header with vector store icon."""
    safe_sub = html.escape(subtitle)
    return f"""
    <div style="display:flex; align-items:center; gap:11px; padding:4px 2px 10px 2px;">
        <div style="width:38px; height:38px; border-radius:11px; background:linear-gradient(135deg,#14B8A6,#0D9488); display:flex; align-items:center; justify-content:center; box-shadow:0 4px 12px rgba(20,184,166,0.35); flex-shrink:0;">
            <span style="font-size:1.25rem;">🏬</span>
        </div>
        <div>
            <div style="font-size:1.28rem; font-weight:800; color:#FFFFFF; line-height:1.1; letter-spacing:-0.02em;">Shop<span style="color:#2DD4BF;">Sense</span></div>
            <div style="font-size:0.65rem; font-weight:700; letter-spacing:0.12em; color:#7EA8A6; margin-top:2px;">{safe_sub}</div>
        </div>
    </div>
    """


def render_login_showcase_html() -> str:
    """Render left showcase panel for the Login Page First."""
    return """
    <div class="ss-login-brand">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:20px;">
            <div style="width:44px; height:44px; border-radius:12px; background:linear-gradient(135deg,#2DD4BF,#0D9488); display:flex; align-items:center; justify-content:center; font-size:1.4rem;">🏬</div>
            <div>
                <div style="font-size:1.55rem; font-weight:800; color:#FFFFFF; letter-spacing:-0.02em;">Shop<span style="color:#5EEAD4;">Sense</span></div>
                <div style="font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; color:#99F6E4; font-weight:700;">Enterprise Retail Intelligence</div>
            </div>
        </div>
        <div style="color:#FFFFFF !important; font-size:1.75rem !important; font-weight:800 !important; line-height:1.25; margin:0 0 12px 0 !important;">
            Unified Multi-Vendor Commerce, Inventory Control &amp; Analytics
        </div>
        <p style="color:#CBE5E3; font-size:0.95rem; line-height:1.55; margin-bottom:22px;">
            Sign in with your role-protected workspace credentials to manage marketplace governance, real-time stock replenishment, customer cohorts, and AI recommendations.
        </p>
        <div class="ss-login-feature">
            <div style="font-weight:700; color:#FFFFFF; font-size:0.92rem;">👑 Administrator Control Plane</div>
            <div style="color:#A7CBC8; font-size:0.82rem; margin-top:2px;">Vendor onboarding approvals, platform revenue margins, ETL data warehouse, and live system diagnostics.</div>
        </div>
        <div class="ss-login-feature">
            <div style="font-weight:700; color:#FFFFFF; font-size:0.92rem;">🏢 Vendor Storefront Portal</div>
            <div style="color:#A7CBC8; font-size:0.82rem; margin-top:2px;">Tenant-isolated catalog, warehouse inventory alerts, settlement payouts, and approval status tracking.</div>
        </div>
        <div class="ss-login-feature">
            <div style="font-weight:700; color:#FFFFFF; font-size:0.92rem;">👤 Customer Storefront &amp; Insights</div>
            <div style="color:#A7CBC8; font-size:0.82rem; margin-top:2px;">Approved marketplace catalog discovery, personalized hybrid recommendations, and order receipts.</div>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:18px;">
            <span class="ss-hero-pill">JWT + RBAC Security</span>
            <span class="ss-hero-pill">PostgreSQL + FastAPI</span>
            <span class="ss-hero-pill">MLflow &amp; Forecasting</span>
        </div>
    </div>
    """


def render_hero_banner_html(tag: str, title: str, subtitle: str, pills: Iterable[str]) -> str:
    """Render dark-teal rounded hero banner card with dynamic metric pills."""
    pills_html = "".join(f'<span class="ss-hero-pill">{html.escape(str(p))}</span>' for p in pills if p)
    return f"""
    <div class="ss-hero">
        <div class="ss-hero-tag">{html.escape(tag)}</div>
        <h2>{html.escape(title)}</h2>
        <p>{html.escape(subtitle)}</p>
        <div class="ss-hero-pills">{pills_html}</div>
    </div>
    """


def render_quick_tile_html(icon: str, title: str, subtitle: str) -> str:
    """Render compact white intelligence highlight card matching screenshot strip."""
    return f"""
    <div class="ss-quick-tile">
        <div class="ss-icon-box">{html.escape(icon)}</div>
        <div>
            <div style="font-weight:700; font-size:0.9rem; color:#0F172A; line-height:1.2;">{html.escape(title)}</div>
            <div style="font-size:0.78rem; color:#64748B; margin-top:2px;">{html.escape(subtitle)}</div>
        </div>
    </div>
    """


def render_product_card_html(category: str, name: str, price: float, vendor_name: str, badge_text: str = "Approved Seller") -> str:
    """Render light-mode storefront product card."""
    return f"""
    <div class="sp-card" style="padding:18px; min-height:175px; display:flex; flex-direction:column; justify-content:space-between;">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px;">
                <span class="sp-badge badge-teal">{html.escape(str(category or 'Retail'))}</span>
                <span style="font-size:0.74rem; color:#15803D; font-weight:600;">✓ {html.escape(badge_text)}</span>
            </div>
            <div style="font-size:1.05rem; font-weight:700; color:#0F172A; line-height:1.3; margin-bottom:8px;">{html.escape(str(name))}</div>
        </div>
        <div style="border-top:1px solid #F1F5F9; padding-top:10px; display:flex; justify-content:space-between; align-items:baseline;">
            <span style="font-size:1.35rem; font-weight:800; color:#0D9488;">₹{float(price):,.2f}</span>
            <span style="font-size:0.78rem; color:#64748B;">Sold by <strong style="color:#334155;">{html.escape(str(vendor_name))}</strong></span>
        </div>
    </div>
    """


def render_recommendation_card_html(
    name: str,
    category: str,
    price: float,
    vendor_name: str,
    rec_type: str,
    score: float,
    rationale: str,
) -> str:
    """Render modern light-mode recommendation showcase card."""
    return f"""
    <div class="sp-card" style="border-top: 3px solid #0D9488; min-height:220px; display:flex; flex-direction:column; justify-content:space-between;">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:8px;">
                <span class="sp-badge badge-teal">{html.escape(str(category or 'Catalog'))}</span>
                <span class="sp-badge badge-healthy">★ {float(score):.2f}</span>
            </div>
            <div style="font-size:1.02rem; font-weight:700; color:#0F172A; margin-bottom:4px;">{html.escape(str(name))}</div>
            <div style="font-size:1.25rem; font-weight:800; color:#0D9488; margin-bottom:4px;">₹{float(price):,.2f}</div>
            <div style="font-size:0.78rem; color:#64748B; margin-bottom:10px;">Vendor: <strong style="color:#334155;">{html.escape(str(vendor_name))}</strong> &bull; <code>{html.escape(str(rec_type))}</code></div>
        </div>
        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:8px 10px; font-size:0.8rem; color:#334155;">
            {html.escape(str(rationale))}
        </div>
    </div>
    """
