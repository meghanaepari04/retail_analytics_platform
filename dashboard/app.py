"""
Retail Analytics Platform — 5-Page Analytics Dashboard
Week 3 Deliverable: Power BI equivalent built with Streamlit + Plotly

Pages:
  1. Executive Summary
  2. Sales & Profitability
  3. Inventory Health
  4. Customer Behavior
  5. Returns & Data Quality
"""

import os
import warnings
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
from datetime import date, timedelta

warnings.filterwarnings("ignore")

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Retail Analytics Platform",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme / CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Dark sidebar */
  [data-testid="stSidebar"] { background: #0f1117; }
  [data-testid="stSidebar"] * { color: #e2e8f0 !important; }

  /* KPI card */
  .kpi-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }
  .kpi-value { font-size: 2rem; font-weight: 700; color: #38bdf8; margin: 0; }
  .kpi-label { font-size: 0.85rem; color: #94a3b8; margin: 4px 0 0 0; }
  .kpi-delta { font-size: 0.8rem; margin-top: 6px; }
  .delta-pos { color: #4ade80; }
  .delta-neg { color: #f87171; }

  /* Section header */
  .section-header {
    font-size: 1.1rem; font-weight: 600; color: #cbd5e1;
    border-left: 3px solid #38bdf8; padding-left: 10px;
    margin: 24px 0 12px 0;
  }

  /* Status badge */
  .badge-ok   { background:#16a34a22; color:#4ade80; border:1px solid #4ade80; border-radius:6px; padding:2px 8px; font-size:0.75rem; }
  .badge-warn { background:#ca8a0422; color:#fbbf24; border:1px solid #fbbf24; border-radius:6px; padding:2px 8px; font-size:0.75rem; }
  .badge-err  { background:#dc262622; color:#f87171; border:1px solid #f87171; border-radius:6px; padding:2px 8px; font-size:0.75rem; }

  /* Main background */
  .main { background-color: #0d1117; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ── DB Connection ─────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_engine():
    host     = os.getenv("DB_HOST", "localhost")
    port     = os.getenv("DB_PORT", "5432")
    dbname   = os.getenv("DB_NAME", "retail_analytics")
    user     = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url, pool_pre_ping=True)

@st.cache_data(ttl=300, show_spinner=False)
def query(_engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with _engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ── Helper formatters ─────────────────────────────────────────────────────────
def fmt_currency(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"

def fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{v:.1f}%"

def kpi_card(label: str, value: str, delta: str | None = None, positive: bool = True):
    delta_html = ""
    if delta:
        cls = "delta-pos" if positive else "delta-neg"
        arrow = "▲" if positive else "▼"
        delta_html = f'<p class="kpi-delta {cls}">{arrow} {delta}</p>'
    return f"""
    <div class="kpi-card">
      <p class="kpi-value">{value}</p>
      <p class="kpi-label">{label}</p>
      {delta_html}
    </div>"""

PLOTLY_THEME = dict(
    template="plotly_dark",
)

COLOR_SEQ = px.colors.qualitative.Bold


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(engine):
    st.sidebar.image("https://img.icons8.com/fluency/96/shop.png", width=60)
    st.sidebar.title("🛒 Retail Analytics")
    st.sidebar.caption("Week 3 Dashboard — v1.0")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigate",
        ["📊 Executive Summary",
         "💰 Sales & Profitability",
         "📦 Inventory Health",
         "👥 Customer Behavior",
         "↩️ Returns & Data Quality"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.markdown("**Global Filters**")

    regions_df = query(engine, "SELECT DISTINCT region FROM dw.dim_store ORDER BY 1")
    all_regions = regions_df["region"].tolist()
    selected_regions = st.sidebar.multiselect("Region", all_regions, default=all_regions)

    cats_df = query(engine, "SELECT DISTINCT category FROM dw.dim_product WHERE is_current ORDER BY 1")
    all_cats = cats_df["category"].tolist()
    selected_cats = st.sidebar.multiselect("Category", all_cats, default=all_cats)

    date_range = st.sidebar.date_input(
        "Date Range",
        value=(date(2025, 1, 1), date(2026, 10, 17)),
        min_value=date(2023, 1, 1),
        max_value=date(2026, 12, 31),
    )

    st.sidebar.divider()
    st.sidebar.caption("Data refreshed at end of each ETL run.")

    return page, selected_regions, selected_cats, date_range


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Executive Summary
# ══════════════════════════════════════════════════════════════════════════════
def page_executive(engine, regions, cats, date_range):
    st.title("📊 Executive Summary")

    start, end = date_range[0], date_range[-1]
    region_clause = "'" + "','".join(regions) + "'"
    cat_clause    = "'" + "','".join(cats) + "'"

    # KPI aggregates
    kpi_sql = f"""
        SELECT
            SUM(net_revenue)                           AS net_revenue,
            SUM(gross_profit)                          AS gross_profit,
            ROUND(SUM(gross_profit)/NULLIF(SUM(net_revenue),0)*100,2) AS margin_pct,
            SUM(orders)                                AS total_orders,
            ROUND(SUM(net_revenue)/NULLIF(SUM(orders),0),2) AS aov,
            SUM(units_sold)                            AS units_sold
        FROM rpt.rpt_sales_daily
        WHERE sale_date BETWEEN :start AND :end
          AND region IN ({region_clause})
    """
    kpi = query(engine, kpi_sql, {"start": start, "end": end}).iloc[0]

    # Return rate
    rr_sql = f"""
        SELECT
            COALESCE(SUM(fr.returned_qty),0)::FLOAT /
            NULLIF(SUM(fs.quantity),0) * 100 AS return_rate
        FROM dw.fact_sales fs
        JOIN dw.dim_date dd ON fs.date_key = dd.date_key
        JOIN dw.dim_store ds ON fs.store_key = ds.store_key
        LEFT JOIN dw.fact_returns fr ON fs.product_key = fr.product_key
        WHERE dd.date BETWEEN :start AND :end
          AND ds.region IN ({region_clause})
    """
    rr_df = query(engine, rr_sql, {"start": start, "end": end})
    return_rate = rr_df["return_rate"].iloc[0] if not rr_df.empty else 0

    # Active customers
    ac_sql = f"""
        SELECT COUNT(DISTINCT fs.customer_key) AS active_customers
        FROM dw.fact_sales fs
        JOIN dw.dim_date dd ON fs.date_key = dd.date_key
        JOIN dw.dim_store ds ON fs.store_key = ds.store_key
        WHERE dd.date BETWEEN :start AND :end
          AND ds.region IN ({region_clause})
    """
    ac = query(engine, ac_sql, {"start": start, "end": end}).iloc[0]["active_customers"]

    # ── KPI Row
    cols = st.columns(7)
    kpi_data = [
        ("Net Revenue",      fmt_currency(kpi["net_revenue"])),
        ("Gross Profit",     fmt_currency(kpi["gross_profit"])),
        ("Margin %",         fmt_pct(kpi["margin_pct"])),
        ("Total Orders",     f"{int(kpi['total_orders']):,}"),
        ("Avg Order Value",  fmt_currency(kpi["aov"])),
        ("Return Rate",      fmt_pct(return_rate)),
        ("Active Customers", f"{int(ac):,}"),
    ]
    for col, (label, value) in zip(cols, kpi_data):
        col.markdown(kpi_card(label, value), unsafe_allow_html=True)

    st.divider()

    # ── Monthly Revenue & Profit Trend
    trend_sql = f"""
        SELECT year, month, month_name,
               SUM(net_revenue) as net_revenue,
               SUM(gross_profit) as gross_profit
        FROM rpt.rpt_sales_monthly_region_category
        WHERE region IN ({region_clause})
          AND category IN ({cat_clause})
          AND (year > :sy OR (year = :sy AND month >= :sm))
          AND (year < :ey OR (year = :ey AND month <= :em))
        GROUP BY 1,2,3 ORDER BY 1,2
    """
    trend = query(engine, trend_sql, {
        "sy": start.year, "sm": start.month,
        "ey": end.year,   "em": end.month,
    })
    if not trend.empty:
        trend["period"] = trend["year"].astype(str) + "-" + trend["month"].astype(str).str.zfill(2)
        fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
        fig_trend.add_trace(go.Bar(x=trend["period"], y=trend["net_revenue"],
                                   name="Net Revenue", marker_color="#38bdf8"), secondary_y=False)
        fig_trend.add_trace(go.Scatter(x=trend["period"], y=trend["gross_profit"],
                                       name="Gross Profit", line=dict(color="#4ade80", width=2)),
                            secondary_y=True)
        fig_trend.update_layout(title="Monthly Revenue & Profit Trend",
                                height=380, **PLOTLY_THEME,
                                legend=dict(orientation="h", y=1.1))
        fig_trend.update_yaxes(title_text="Net Revenue ($)", secondary_y=False)
        fig_trend.update_yaxes(title_text="Gross Profit ($)", secondary_y=True)
        st.plotly_chart(fig_trend, use_container_width=True)

    col1, col2 = st.columns(2)

    # ── Revenue by Region (map-style bar)
    reg_sql = f"""
        SELECT region, SUM(net_revenue) as revenue, SUM(gross_profit) as profit
        FROM rpt.rpt_sales_monthly_region_category
        WHERE region IN ({region_clause})
        GROUP BY 1 ORDER BY revenue DESC
    """
    reg_df = query(engine, reg_sql)
    with col1:
        st.markdown('<p class="section-header">Revenue by Region</p>', unsafe_allow_html=True)
        if not reg_df.empty:
            fig_reg = px.bar(reg_df, x="revenue", y="region", orientation="h",
                             color="profit", color_continuous_scale="Blues",
                             labels={"revenue": "Net Revenue", "region": ""},
                             **PLOTLY_THEME)
            fig_reg.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_reg, use_container_width=True)

    # ── Top / Bottom 5 Categories
    cat_sql = f"""
        SELECT category, SUM(net_revenue) as revenue, SUM(gross_profit) as profit,
               ROUND(SUM(gross_profit)/NULLIF(SUM(net_revenue),0)*100,2) as margin_pct
        FROM rpt.rpt_sales_monthly_region_category
        WHERE category IN ({cat_clause})
        GROUP BY 1 ORDER BY revenue DESC
    """
    cat_df = query(engine, cat_sql)
    with col2:
        st.markdown('<p class="section-header">Top 5 / Bottom 5 Categories</p>', unsafe_allow_html=True)
        if not cat_df.empty:
            top5    = cat_df.head(5).assign(rank="Top 5")
            bottom5 = cat_df.tail(5).assign(rank="Bottom 5")
            combined = pd.concat([top5, bottom5])
            fig_cat = px.bar(combined, x="revenue", y="category", color="rank",
                             color_discrete_map={"Top 5": "#4ade80", "Bottom 5": "#f87171"},
                             orientation="h", **PLOTLY_THEME)
            fig_cat.update_layout(height=300, showlegend=True,
                                  legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_cat, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Sales & Profitability
# ══════════════════════════════════════════════════════════════════════════════
def page_sales(engine, regions, cats, date_range):
    st.title("💰 Sales & Profitability")
    start, end = date_range[0], date_range[-1]
    region_clause = "'" + "','".join(regions) + "'"
    cat_clause    = "'" + "','".join(cats) + "'"

    col1, col2 = st.columns(2)

    # Revenue by Channel
    ch_sql = f"""
        SELECT channel_name, SUM(net_revenue) as revenue, SUM(gross_profit) as profit
        FROM rpt.rpt_sales_daily
        WHERE sale_date BETWEEN :start AND :end AND region IN ({region_clause})
        GROUP BY 1 ORDER BY revenue DESC
    """
    ch_df = query(engine, ch_sql, {"start": start, "end": end})
    with col1:
        st.markdown('<p class="section-header">Revenue by Channel</p>', unsafe_allow_html=True)
        if not ch_df.empty:
            fig = px.pie(ch_df, values="revenue", names="channel_name",
                         hole=0.45, color_discrete_sequence=COLOR_SEQ, **PLOTLY_THEME)
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)

    # Margin by Category
    mc_sql = f"""
        SELECT category, SUM(net_revenue) as revenue,
               ROUND(SUM(gross_profit)/NULLIF(SUM(net_revenue),0)*100,2) as margin_pct
        FROM rpt.rpt_sales_monthly_region_category
        WHERE category IN ({cat_clause}) AND region IN ({region_clause})
        GROUP BY 1 ORDER BY margin_pct DESC
    """
    mc_df = query(engine, mc_sql)
    with col2:
        st.markdown('<p class="section-header">Margin % by Category</p>', unsafe_allow_html=True)
        if not mc_df.empty:
            fig = px.bar(mc_df, x="category", y="margin_pct",
                         color="margin_pct", color_continuous_scale="RdYlGn",
                         labels={"margin_pct": "Margin %", "category": ""},
                         **PLOTLY_THEME)
            fig.update_layout(height=320, showlegend=False,
                              xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    # Scatter: Revenue vs Margin % per product
    st.markdown('<p class="section-header">Revenue vs Margin % (Product Scatter)</p>', unsafe_allow_html=True)
    scatter_sql = f"""
        SELECT product_name, category, net_revenue, margin_pct, units_sold, gross_profit
        FROM rpt.rpt_profitability_product
        WHERE category IN ({cat_clause})
        ORDER BY net_revenue DESC LIMIT 200
    """
    scatter_df = query(engine, scatter_sql)
    if not scatter_df.empty:
        fig_s = px.scatter(scatter_df, x="net_revenue", y="margin_pct",
                           size="units_sold", color="category",
                           hover_name="product_name",
                           labels={"net_revenue": "Net Revenue ($)", "margin_pct": "Margin %"},
                           color_discrete_sequence=COLOR_SEQ, **PLOTLY_THEME)
        fig_s.add_hline(y=0, line_dash="dash", line_color="#f87171",
                        annotation_text="Break-even", annotation_position="bottom right")
        fig_s.update_layout(height=450)
        st.plotly_chart(fig_s, use_container_width=True)

    col3, col4 = st.columns(2)

    # Top 20 products
    top_sql = f"""
        SELECT product_name, category, net_revenue, margin_pct, units_sold
        FROM rpt.rpt_profitability_product
        WHERE category IN ({cat_clause})
        ORDER BY net_revenue DESC LIMIT 20
    """
    top_df = query(engine, top_sql)
    with col3:
        st.markdown('<p class="section-header">Top 20 Products by Revenue</p>', unsafe_allow_html=True)
        st.dataframe(top_df.style.format({"net_revenue": "${:,.0f}", "margin_pct": "{:.1f}%",
                                           "units_sold": "{:,.0f}"}),
                     hide_index=True, use_container_width=True)

    # Loss-making products
    loss_sql = f"""
        SELECT product_name, category, gross_profit, margin_pct, net_revenue
        FROM rpt.rpt_profitability_product
        WHERE gross_profit < 0 AND category IN ({cat_clause})
        ORDER BY gross_profit LIMIT 20
    """
    loss_df = query(engine, loss_sql)
    with col4:
        st.markdown('<p class="section-header">⚠️ Loss-Making Products</p>', unsafe_allow_html=True)
        if loss_df.empty:
            st.success("No loss-making products in the selected filters.")
        else:
            st.dataframe(loss_df.style.format({"gross_profit": "${:,.0f}",
                                               "margin_pct": "{:.1f}%",
                                               "net_revenue": "${:,.0f}"}),
                         hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Inventory Health
# ══════════════════════════════════════════════════════════════════════════════
def page_inventory(engine, regions, cats, date_range):
    st.title("📦 Inventory Health")
    region_clause = "'" + "','".join(regions) + "'"
    cat_clause    = "'" + "','".join(cats) + "'"

    # KPIs
    inv_kpi_sql = f"""
        SELECT
            COUNT(*) FILTER(WHERE is_stockout)               AS stockouts,
            COUNT(*) FILTER(WHERE is_overstock)              AS overstocks,
            COUNT(*) FILTER(WHERE is_dead_stock)             AS dead_stock,
            ROUND(AVG(days_of_cover) FILTER(WHERE days_of_cover IS NOT NULL AND days_of_cover < 999), 1) AS avg_cover,
            SUM(CASE WHEN is_overstock THEN available * 1 ELSE 0 END) AS overstock_units
        FROM rpt.rpt_inventory_health
        WHERE region IN ({region_clause})
          AND category IN ({cat_clause})
    """
    inv_kpi = query(engine, inv_kpi_sql).iloc[0]

    cols = st.columns(5)
    kpi_data = [
        ("Stockouts", str(int(inv_kpi["stockouts"] or 0))),
        ("Overstocks", str(int(inv_kpi["overstocks"] or 0))),
        ("Dead Stock Items", str(int(inv_kpi["dead_stock"] or 0))),
        ("Avg Days of Cover", str(inv_kpi["avg_cover"] or "N/A")),
        ("Overstock Units", f"{int(inv_kpi['overstock_units'] or 0):,}"),
    ]
    for col, (label, value) in zip(cols, kpi_data):
        col.markdown(kpi_card(label, value), unsafe_allow_html=True)

    st.divider()

    col1, col2 = st.columns(2)

    # Stockout heatmap by region x category
    heat_sql = f"""
        SELECT region, category,
               COUNT(*) FILTER(WHERE is_stockout) as stockout_count,
               COUNT(*) as total
        FROM rpt.rpt_inventory_health
        WHERE region IN ({region_clause})
          AND category IN ({cat_clause})
        GROUP BY 1,2
    """
    heat_df = query(engine, heat_sql)
    with col1:
        st.markdown('<p class="section-header">Stockout Heatmap (Store × Category)</p>', unsafe_allow_html=True)
        if not heat_df.empty:
            pivot = heat_df.pivot_table(index="region", columns="category",
                                         values="stockout_count", fill_value=0)
            fig_h = px.imshow(pivot, color_continuous_scale="YlOrRd",
                              text_auto=True, aspect="auto", **PLOTLY_THEME)
            fig_h.update_layout(height=320)
            st.plotly_chart(fig_h, use_container_width=True)

    # Inventory turnover by category
    turn_sql = f"""
        SELECT ih.category,
               ROUND(AVG(ih.days_of_cover) FILTER(WHERE ih.days_of_cover IS NOT NULL), 1) as avg_days_cover,
               COUNT(*) FILTER(WHERE is_stockout) as stockouts,
               COUNT(*) FILTER(WHERE is_overstock) as overstocks
        FROM rpt.rpt_inventory_health ih
        WHERE ih.region IN ({region_clause})
          AND ih.category IN ({cat_clause})
        GROUP BY 1 ORDER BY avg_days_cover
    """
    turn_df = query(engine, turn_sql)
    with col2:
        st.markdown('<p class="section-header">Days of Cover by Category</p>', unsafe_allow_html=True)
        if not turn_df.empty:
            fig_t = px.bar(turn_df, x="category", y="avg_days_cover",
                           color="avg_days_cover", color_continuous_scale="RdYlGn_r",
                           labels={"avg_days_cover": "Avg Days of Cover"},
                           **PLOTLY_THEME)
            fig_t.add_hline(y=90, line_dash="dash", line_color="#fbbf24",
                            annotation_text="Overstock threshold (90d)")
            fig_t.update_layout(height=320, showlegend=False, xaxis_tickangle=-30)
            st.plotly_chart(fig_t, use_container_width=True)

    # Reorder candidates table
    st.markdown('<p class="section-header">🚨 Reorder Candidates (Available ≤ Reorder Level)</p>', unsafe_allow_html=True)
    reorder_sql = f"""
        SELECT product_name, category, store_name, region,
               available, reorder_level, days_of_cover, lead_time_days
        FROM rpt.rpt_inventory_health
        WHERE available <= reorder_level AND NOT is_stockout
          AND region IN ({region_clause})
          AND category IN ({cat_clause})
        ORDER BY days_of_cover LIMIT 50
    """
    reorder_df = query(engine, reorder_sql)
    if reorder_df.empty:
        st.success("No reorder candidates under current filters.")
    else:
        st.dataframe(reorder_df.style.format({
            "available": "{:,.0f}", "reorder_level": "{:,.0f}",
            "days_of_cover": "{:.1f}", "lead_time_days": "{:.0f}"
        }), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — Customer Behavior
# ══════════════════════════════════════════════════════════════════════════════
def page_customers(engine, regions, cats, date_range):
    st.title("👥 Customer Behavior")
    region_clause = "'" + "','".join(regions) + "'"

    # KPIs
    cust_kpi_sql = f"""
        SELECT
            COUNT(*) AS total_customers,
            COUNT(*) FILTER(WHERE frequency >= 2) AS repeat_customers,
            ROUND(COUNT(*) FILTER(WHERE frequency >= 2)::NUMERIC / NULLIF(COUNT(*),0)*100,1) as repeat_rate,
            ROUND(AVG(monetary),2) AS avg_clv
        FROM rpt.rpt_customer_rfm
        WHERE region IN ({region_clause})
    """
    ck = query(engine, cust_kpi_sql).iloc[0]

    churn_sql = f"""
        SELECT COUNT(*) as churn_risk
        FROM rpt.rpt_customer_rfm
        WHERE recency_days > 90 AND m_score >= 4 AND region IN ({region_clause})
    """
    churn_count = query(engine, churn_sql).iloc[0]["churn_risk"]

    cols = st.columns(4)
    for col, (label, value) in zip(cols, [
        ("Total Customers",  f"{int(ck['total_customers']):,}"),
        ("Repeat Rate",      fmt_pct(ck["repeat_rate"])),
        ("Avg CLV",          fmt_currency(ck["avg_clv"])),
        ("Churn Risk (High-Value)", str(int(churn_count))),
    ]):
        col.markdown(kpi_card(label, value), unsafe_allow_html=True)

    st.divider()

    col1, col2 = st.columns(2)

    # RFM segment distribution
    rfm_sql = f"""
        SELECT rfm_segment, COUNT(*) as customers, ROUND(AVG(monetary),2) as avg_spend
        FROM rpt.rpt_customer_rfm
        WHERE region IN ({region_clause})
        GROUP BY 1 ORDER BY customers DESC
    """
    rfm_df = query(engine, rfm_sql)
    with col1:
        st.markdown('<p class="section-header">RFM Segment Distribution</p>', unsafe_allow_html=True)
        if not rfm_df.empty:
            fig_rfm = px.pie(rfm_df, values="customers", names="rfm_segment",
                             hole=0.4, color_discrete_sequence=COLOR_SEQ, **PLOTLY_THEME)
            fig_rfm.update_layout(height=360)
            st.plotly_chart(fig_rfm, use_container_width=True)

    # CLV by segment
    with col2:
        st.markdown('<p class="section-header">Avg CLV by Segment</p>', unsafe_allow_html=True)
        if not rfm_df.empty:
            fig_clv = px.bar(rfm_df.sort_values("avg_spend", ascending=True),
                             x="avg_spend", y="rfm_segment", orientation="h",
                             color="avg_spend", color_continuous_scale="Blues",
                             labels={"avg_spend": "Avg Spend ($)", "rfm_segment": ""},
                             **PLOTLY_THEME)
            fig_clv.update_layout(height=360, showlegend=False)
            st.plotly_chart(fig_clv, use_container_width=True)

    # Cohort retention heatmap
    st.markdown('<p class="section-header">Cohort Retention Matrix (12 Months)</p>', unsafe_allow_html=True)
    cohort_sql = """
        SELECT cohort_month, months_since::INT as months_since, retention_pct
        FROM rpt.rpt_customer_cohorts
        WHERE months_since <= 12
        ORDER BY 1, 2
    """
    cohort_df = query(engine, cohort_sql)
    if not cohort_df.empty:
        cohort_df["cohort_month"] = cohort_df["cohort_month"].astype(str).str[:7]
        pivot = cohort_df.pivot_table(index="cohort_month", columns="months_since",
                                       values="retention_pct", fill_value=0)
        fig_coh = px.imshow(pivot, color_continuous_scale="Blues",
                            text_auto=".1f", aspect="auto",
                            labels={"color": "Retention %", "x": "Months Since Signup"},
                            **PLOTLY_THEME)
        fig_coh.update_layout(height=500)
        st.plotly_chart(fig_coh, use_container_width=True)

    # Churn-risk table
    st.markdown('<p class="section-header">⚠️ High-Value Churn Risk (90+ days inactive, top 20% CLV)</p>',
                unsafe_allow_html=True)
    churn_tbl_sql = f"""
        SELECT customer_name, region, segment, rfm_segment,
               recency_days, monetary, clv_simple
        FROM rpt.rpt_customer_rfm
        WHERE recency_days > 90 AND m_score >= 4
          AND region IN ({region_clause})
        ORDER BY clv_simple DESC LIMIT 25
    """
    churn_tbl = query(engine, churn_tbl_sql)
    if churn_tbl.empty:
        st.success("No high-value churn-risk customers in selected region.")
    else:
        st.dataframe(churn_tbl.style.format({
            "monetary": "${:,.0f}", "clv_simple": "${:,.0f}", "recency_days": "{:.0f}"
        }), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — Returns & Data Quality
# ══════════════════════════════════════════════════════════════════════════════
def page_returns_dq(engine, regions, cats, date_range):
    st.title("↩️ Returns & Data Quality")
    region_clause = "'" + "','".join(regions) + "'"
    cat_clause    = "'" + "','".join(cats) + "'"

    tab1, tab2 = st.tabs(["↩️ Returns Analysis", "🔬 Data Quality Scorecard"])

    # ── Returns Tab
    with tab1:
        col1, col2 = st.columns(2)

        # Return rate by category
        ret_cat_sql = f"""
            SELECT category, SUM(return_count) as returns,
                   SUM(total_refund) as refund_total,
                   ROUND(AVG(return_rate_pct),2) as avg_return_rate
            FROM rpt.rpt_returns_analysis
            WHERE category IN ({cat_clause})
            GROUP BY 1 ORDER BY avg_return_rate DESC
        """
        ret_cat_df = query(engine, ret_cat_sql)
        with col1:
            st.markdown('<p class="section-header">Return Rate by Category</p>', unsafe_allow_html=True)
            if not ret_cat_df.empty:
                fig = px.bar(ret_cat_df, x="category", y="avg_return_rate",
                             color="avg_return_rate", color_continuous_scale="Reds",
                             labels={"avg_return_rate": "Return Rate %"},
                             **PLOTLY_THEME)
                fig.update_layout(height=320, showlegend=False, xaxis_tickangle=-30)
                st.plotly_chart(fig, use_container_width=True)

        # Return reasons breakdown
        reason_sql = f"""
            SELECT reason_group, return_reason, SUM(return_count) as returns,
                   SUM(total_refund) as refund_total
            FROM rpt.rpt_returns_analysis
            WHERE category IN ({cat_clause})
            GROUP BY 1,2 ORDER BY returns DESC LIMIT 15
        """
        reason_df = query(engine, reason_sql)
        with col2:
            st.markdown('<p class="section-header">Return Reasons Breakdown</p>', unsafe_allow_html=True)
            if not reason_df.empty:
                fig = px.treemap(reason_df, path=["reason_group", "return_reason"],
                                 values="returns", color="refund_total",
                                 color_continuous_scale="Reds", **PLOTLY_THEME)
                fig.update_layout(height=320)
                st.plotly_chart(fig, use_container_width=True)

        # Abnormal return rate products
        st.markdown('<p class="section-header">Products with Abnormal Return Rate (> 15%)</p>',
                    unsafe_allow_html=True)
        abnormal_sql = f"""
            SELECT product_name, category, return_rate_pct,
                   return_count, total_refund, units_sold
            FROM rpt.rpt_returns_analysis
            WHERE return_rate_pct > 15 AND category IN ({cat_clause})
              AND return_count > 3
            ORDER BY return_rate_pct DESC LIMIT 30
        """
        abnormal_df = query(engine, abnormal_sql)
        if abnormal_df.empty:
            st.info("No products with return rate > 15% in current filters.")
        else:
            st.dataframe(abnormal_df.style.format({
                "return_rate_pct": "{:.1f}%", "total_refund": "${:,.0f}",
                "units_sold": "{:,.0f}"
            }), hide_index=True, use_container_width=True)

    # ── DQ Scorecard Tab
    with tab2:
        st.markdown('<p class="section-header">Data Quality Scorecard — Last ETL Run</p>',
                    unsafe_allow_html=True)

        # Latest run
        run_sql = """
            SELECT run_id, started_at, finished_at, status,
                   rows_read, rows_loaded, rows_rejected
            FROM ops.etl_run_log ORDER BY started_at DESC LIMIT 1
        """
        run_df = query(engine, run_sql)
        if not run_df.empty:
            r = run_df.iloc[0]
            c1, c2, c3, c4 = st.columns(4)
            status_badge = (
                '<span class="badge-ok">✅ SUCCESS</span>' if r["status"] == "SUCCESS"
                else '<span class="badge-err">❌ FAILED</span>'
            )
            c1.markdown(f"**Run Status**<br>{status_badge}", unsafe_allow_html=True)
            c2.markdown(f"**Rows Read**<br>{int(r['rows_read'] or 0):,}", unsafe_allow_html=True)
            c3.markdown(f"**Rows Loaded**<br>{int(r['rows_loaded'] or 0):,}", unsafe_allow_html=True)
            reject_rate = (r["rows_rejected"] or 0) / max(r["rows_read"] or 1, 1) * 100
            c4.markdown(
                f"**Rows Rejected**<br>{int(r['rows_rejected'] or 0):,} "
                f"({reject_rate:.1f}%)", unsafe_allow_html=True
            )

        st.divider()

        # DQ results
        dq_sql = """
            SELECT dr.table_name, dr.rule_name,
                   dr.failed_count, dr.total_count,
                   ROUND(dr.failed_count::NUMERIC/NULLIF(dr.total_count,0)*100,2) AS fail_pct,
                   dr.severity
            FROM ops.dq_results dr
            WHERE dr.run_id = (SELECT MAX(run_id) FROM ops.dq_results)
            ORDER BY dr.severity DESC, fail_pct DESC
        """
        dq_df = query(engine, dq_sql)
        if not dq_df.empty:
            # Color severity
            def color_severity(val):
                if val == "CRITICAL":
                    return "background-color: #7f1d1d; color: #fca5a5"
                if val == "WARNING":
                    return "background-color: #78350f; color: #fcd34d"
                return "background-color: #14532d; color: #86efac"

            styled = dq_df.style.applymap(color_severity, subset=["severity"]) \
                          .format({"fail_pct": "{:.2f}%", "failed_count": "{:,}",
                                   "total_count": "{:,}"})
            st.dataframe(styled, hide_index=True, use_container_width=True)

            # Summary bar
            fig_dq = px.bar(dq_df, x="rule_name", y="fail_pct",
                            color="severity",
                            color_discrete_map={"CRITICAL": "#f87171",
                                                "WARNING": "#fbbf24",
                                                "INFO": "#4ade80"},
                            labels={"fail_pct": "Fail %", "rule_name": "DQ Rule"},
                            **PLOTLY_THEME)
            fig_dq.add_hline(y=1, line_dash="dash", line_color="#fbbf24",
                             annotation_text="1% threshold")
            fig_dq.update_layout(height=350, xaxis_tickangle=-30)
            st.plotly_chart(fig_dq, use_container_width=True)
        else:
            st.info("No DQ results found. Run the ETL pipeline first.")

        # Reject records sample
        st.markdown('<p class="section-header">Recent Reject Records (sample)</p>', unsafe_allow_html=True)
        rej_sql = """
            SELECT source_table, reason_code, source_key,
                   LEFT(raw_payload::TEXT, 120) AS payload_preview
            FROM ops.reject_records
            ORDER BY created_at DESC LIMIT 20
        """
        rej_df = query(engine, rej_sql)
        if rej_df.empty:
            st.success("No reject records in the database.")
        else:
            st.dataframe(rej_df, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    try:
        engine = get_engine()
        # Test connectivity
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        st.error(f"❌ Cannot connect to database: {e}")
        st.info("Set DB_HOST, DB_NAME, DB_USER, DB_PASSWORD environment variables.")
        st.stop()

    page, regions, cats, date_range = render_sidebar(engine)

    if not regions:
        st.warning("Please select at least one region in the sidebar.")
        return
    if not cats:
        st.warning("Please select at least one category in the sidebar.")
        return
    if len(date_range) < 2:
        st.warning("Please select a date range.")
        return

    if page == "📊 Executive Summary":
        page_executive(engine, regions, cats, date_range)
    elif page == "💰 Sales & Profitability":
        page_sales(engine, regions, cats, date_range)
    elif page == "📦 Inventory Health":
        page_inventory(engine, regions, cats, date_range)
    elif page == "👥 Customer Behavior":
        page_customers(engine, regions, cats, date_range)
    else:
        page_returns_dq(engine, regions, cats, date_range)


if __name__ == "__main__":
    main()
