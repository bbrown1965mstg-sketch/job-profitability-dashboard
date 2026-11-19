"""Job Profitability Dashboard — dark-mode Streamlit app backed by business_intel.db.

Every metric on the page (KPIs, charts, tables, anomaly flags) is computed
live from the SQLite jobs table; nothing is hardcoded.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DB_PATH = Path(__file__).with_name("business_intel.db")
MARGIN_ALERT_PCT = 15.0  # default; live-adjustable in the sidebar

COLORS = {
    "revenue": "#38BDF8",
    "expenses": "#FB7185",
    "profit": "#34D399",
    "margin": "#A78BFA",
    "labor": "#F59E0B",
    "text": "#E6EDF3",
    "dim": "#9BA6B4",
    "grid": "#1B2130",
    "border": "#232A36",
    "card": "#12161F",
}

CSS = f"""
<style>
    .stApp {{ background: linear-gradient(180deg, #0B0F17 0%, #0D1119 100%); }}
    .block-container {{ padding-top: 1.8rem; padding-bottom: 3rem; max-width: 1280px; }}
    .stApp h1 {{ font-weight: 800; letter-spacing: -0.02em; }}

    /* ---- sidebar ---- */
    section[data-testid="stSidebar"] {{
        background: #0E131C;
        border-right: 1px solid {COLORS["border"]};
    }}
    .sidebar-logo {{
        display: flex; align-items: center; gap: 0.6rem;
        font-size: 1.15rem; font-weight: 800; color: {COLORS["text"]};
        padding: 0.5rem 0 0.1rem 0;
    }}
    .sidebar-logo .logo-chip {{
        background: linear-gradient(135deg, #34D399 0%, #38BDF8 100%);
        width: 2.1rem; height: 2.1rem; border-radius: 9px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem;
    }}

    /* ---- header chips ---- */
    .header-chips {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: -0.2rem; }}
    .chip {{
        background: {COLORS["card"]}; border: 1px solid {COLORS["border"]};
        color: {COLORS["dim"]}; border-radius: 999px;
        padding: 0.18rem 0.7rem; font-size: 0.78rem; font-weight: 600;
    }}
    .chip b {{ color: {COLORS["text"]}; }}

    /* ---- section titles ---- */
    .section-title {{
        display: flex; align-items: center; gap: 0.65rem;
        font-size: 1.05rem; font-weight: 700; color: {COLORS["text"]};
        margin: 2.0rem 0 0.8rem 0;
    }}
    .section-title .num {{
        background: linear-gradient(135deg, #34D399 0%, #38BDF8 100%);
        color: #07121B; font-size: 0.72rem; font-weight: 800;
        border-radius: 7px; padding: 0.14rem 0.42rem;
    }}

    /* ---- KPI cards ---- */
    .kpi-card {{
        position: relative; overflow: hidden;
        background: linear-gradient(180deg, #171C26 0%, {COLORS["card"]} 100%);
        border: 1px solid {COLORS["border"]}; border-radius: 14px;
        padding: 1.0rem 1.1rem 0.9rem 1.3rem;
    }}
    .kpi-accent {{
        position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
    }}
    .kpi-top {{
        display: flex; justify-content: space-between; align-items: center; gap: 0.4rem;
    }}
    .kpi-label {{
        color: {COLORS["dim"]}; font-size: 0.8rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.05em;
    }}
    .kpi-value {{
        color: {COLORS["text"]}; font-size: 1.75rem; font-weight: 800;
        font-variant-numeric: tabular-nums; margin-top: 0.35rem;
    }}
    .kpi-sub {{ color: #6E7A8A; font-size: 0.72rem; margin-top: 0.3rem; }}
    .kpi-delta {{
        font-size: 0.72rem; font-weight: 700; border-radius: 999px; padding: 0.1rem 0.45rem;
    }}
    .kpi-delta.up {{ color: #34D399; background: rgba(52, 211, 153, 0.12); }}
    .kpi-delta.down {{ color: #FB7185; background: rgba(251, 113, 133, 0.12); }}

    /* ---- banners ---- */
    .dash-banner {{
        border-radius: 12px; padding: 0.8rem 1.1rem; font-size: 0.92rem;
        margin: 0.6rem 0 0.4rem 0; border: 1px solid;
    }}
    .dash-banner.alert {{ background: rgba(251, 113, 133, 0.08); border-color: rgba(251, 113, 133, 0.35); }}
    .dash-banner.ok {{ background: rgba(52, 211, 153, 0.07); border-color: rgba(52, 211, 153, 0.30); }}

    /* ---- tables & misc ---- */
    div[data-testid="stDataFrame"] {{ border: 1px solid {COLORS["border"]}; border-radius: 10px; }}
    .footer {{
        color: #55617A; font-size: 0.75rem; text-align: center;
        margin-top: 2.6rem; padding-top: 1rem;
        border-top: 1px solid {COLORS["border"]};
    }}
</style>
"""

st.set_page_config(page_title="Job Profitability Dashboard", page_icon="📊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_jobs() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM jobs ORDER BY date", conn)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    df["month_label"] = df["month"].dt.strftime("%b %Y")
    df["total_expense"] = df["labor_cost"] + df["material_cost"] + df["overhead_allocation"]
    return df


def style_fig(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text"], family="Inter, Segoe UI, sans-serif", size=13),
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    fig.update_yaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    return fig


def fmt_delta(cur: float, prev: float, pct: bool = False) -> tuple[str, str]:
    """Change vs the prior month → (direction class, chip html)."""
    if prev == 0:
        return "", ""
    change = (cur - prev) / abs(prev) * 100
    if abs(change) < 0.05:
        return "", ""
    arrow = "▲" if change > 0 else "▼"
    cls = "up" if change > 0 else "down"
    unit = "pp" if pct else "%"
    return cls, f'<span class="kpi-delta {cls}">{arrow} {abs(change):.1f}{unit}</span>'


def kpi_card(label: str, icon: str, value: str, accent: str, sub: str, delta_html: str) -> str:
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-accent" style="background:{accent}"></div>'
        f'<div class="kpi-top"><span class="kpi-label">{icon}&nbsp;{label}</span>{delta_html}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


df = load_jobs()
if df.empty:
    st.error("No jobs found in business_intel.db — run `python ingest.py` first.")
    st.stop()

# ------------------------------------------------------------------ filters
with st.sidebar:
    st.markdown(
        '<div class="sidebar-logo"><span class="logo-chip">📊</span>JobP&amp;L</div>',
        unsafe_allow_html=True,
    )
    st.caption("Local BI for service jobs")
    st.divider()
    st.header("⚙️ Filters")
    months = sorted(df["month"].unique())
    sel_months = st.multiselect(
        "Month",
        months,
        default=months,
        format_func=lambda m: m.strftime("%b %Y"),
    )
    job_types = sorted(df["job_type"].unique())
    sel_types = st.multiselect("Job type", job_types, default=job_types)
    st.divider()
    alert_pct = st.slider(
        "Margin alert floor (%)",
        min_value=5.0,
        max_value=40.0,
        value=MARGIN_ALERT_PCT,
        step=0.5,
        help=f"Jobs below this profit margin are flagged. Default: {MARGIN_ALERT_PCT:.0f}%.",
    )
    st.button("🔄 Refresh data", on_click=st.cache_data.clear, use_container_width=True)
    if DB_PATH.exists():
        kb = DB_PATH.stat().st_size / 1024
        st.caption(f"📦 business_intel.db • {len(df)} jobs • {kb:.0f} KB")

filtered = df[df["month"].isin(sel_months) & df["job_type"].isin(sel_types)].copy()
if filtered.empty:
    st.warning("No jobs match the current filters.")
    st.stop()

# ------------------------------------------------------------------ header
st.title("📊 Job Profitability Dashboard")
st.markdown(
    f'<div class="header-chips">'
    f'<span class="chip"><b>{len(filtered)}</b> jobs</span>'
    f'<span class="chip"><b>{filtered["date"].min():%b %d}</b> – <b>{filtered["date"].max():%b %d, %Y}</b></span>'
    f'<span class="chip">floor <b>{alert_pct:.0f}%</b> margin</span>'
    f'<span class="chip">live from SQLite</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ------------------------------------------------------------ anomaly banner
anomalies = filtered[filtered["profit_margin"] < alert_pct].sort_values("profit_margin")
if not anomalies.empty:
    leak = anomalies["net_profit"].sum()
    st.markdown(
        f'<div class="dash-banner alert">🚨 <b>Anomaly alert</b> — {len(anomalies)} job(s) below '
        f'{alert_pct:.0f}% profit margin. Net result of these jobs: <b>${leak:,.0f}</b>. '
        f"Review pricing, labor or material costs.</div>",
        unsafe_allow_html=True,
    )
    show = anomalies.assign(
        date=anomalies["date"].dt.strftime("%b %d"),
        revenue=anomalies["revenue"].map("${:,.0f}".format),
        net_profit=anomalies["net_profit"].map("${:,.0f}".format),
        profit_margin=anomalies["profit_margin"].map("{:.1f}%".format),
    ).rename(columns={
        "date": "Date", "client_name": "Client", "job_type": "Job Type",
        "revenue": "Revenue", "net_profit": "Net Profit", "profit_margin": "Margin",
    })
    with st.expander(f"View {len(anomalies)} flagged job(s)", expanded=False):
        st.dataframe(show.set_index("Date"), use_container_width=True)
else:
    st.markdown(
        f'<div class="dash-banner ok">✅ All jobs are at or above the {alert_pct:.0f}% margin floor.</div>',
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------- KPIs
total_revenue = filtered["revenue"].sum()
total_expense = filtered["total_expense"].sum()
net_profit = filtered["net_profit"].sum()
overall_margin = net_profit / total_revenue * 100 if total_revenue else 0.0

# month-over-month deltas (last month in the filter vs the one before it)
sel_months_sorted = sorted(filtered["month"].unique())
if len(sel_months_sorted) >= 2:
    m_last, m_prev = sel_months_sorted[-2:]

    def _month_stat(month, col):
        rows = filtered[filtered["month"] == month]
        if col == "margin":
            return rows["net_profit"].sum() / rows["revenue"].sum() * 100
        return rows[col].sum()

    d_rev = fmt_delta(_month_stat(m_last, "revenue"), _month_stat(m_prev, "revenue"))
    d_exp = fmt_delta(_month_stat(m_last, "total_expense"), _month_stat(m_prev, "total_expense"))
    d_pro = fmt_delta(_month_stat(m_last, "net_profit"), _month_stat(m_prev, "net_profit"))
    d_mar = fmt_delta(_month_stat(m_last, "margin"), _month_stat(m_prev, "margin"), pct=True)
    delta_note = "vs prior month"
else:
    d_rev = d_exp = d_pro = d_mar = ("", "")
    delta_note = f"{len(sel_months_sorted)} month of data"

k1, k2, k3, k4 = st.columns(4, gap="medium")
with k1:
    st.markdown(
        kpi_card("Total Revenue", "💰", f"${total_revenue:,.0f}", COLORS["revenue"],
                 f"{len(filtered)} jobs • {delta_note}", d_rev[1]),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        kpi_card("Total Expenses", "💸", f"${total_expense:,.0f}", COLORS["expenses"],
                 f"{total_expense / total_revenue * 100:.0f}% of revenue" if total_revenue else "—",
                 d_exp[1]),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        kpi_card("Net Profit", "📈", f"${net_profit:,.0f}", COLORS["profit"],
                 "after labor, materials, overhead", d_pro[1]),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        kpi_card("Overall Margin", "🎯", f"{overall_margin:.1f}%", COLORS["margin"],
                 "net profit ÷ revenue", d_mar[1]),
        unsafe_allow_html=True,
    )

# ------------------------------------------------- profitability by job type
st.markdown(
    '<div class="section-title"><span class="num">01</span>Profitability by Job Type</div>',
    unsafe_allow_html=True,
)

by_type = (
    filtered.groupby("job_type")
    .agg(
        jobs=("job_type", "size"),
        revenue=("revenue", "sum"),
        expenses=("total_expense", "sum"),
        net_profit=("net_profit", "sum"),
        avg_margin=("profit_margin", "mean"),
    )
    .reset_index()
    .sort_values("net_profit", ascending=False)
)

type_order = by_type["job_type"].tolist()
fig = go.Figure()
fig.add_bar(name="Revenue", x=type_order, y=by_type["revenue"],
            marker=dict(color=COLORS["revenue"], line=dict(width=0), borderradius=6),
            hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Expenses", x=type_order, y=by_type["expenses"],
            marker=dict(color=COLORS["expenses"], line=dict(width=0), borderradius=6),
            hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Net Profit", x=type_order, y=by_type["net_profit"],
            marker=dict(color=COLORS["profit"], line=dict(width=0), borderradius=6),
            hovertemplate="$%{y:,.0f}<extra></extra>")
fig.update_layout(barmode="group", bargap=0.28, hovermode="x unified")
fig.update_yaxes(tickprefix="$")
st.plotly_chart(style_fig(fig), use_container_width=True, config={"displayModeBar": False})

type_display = by_type.rename(columns={
    "job_type": "Job Type", "jobs": "Jobs", "revenue": "Revenue",
    "expenses": "Expenses", "net_profit": "Net Profit", "avg_margin": "Avg Margin %",
}).set_index("Job Type")
st.dataframe(type_display, use_container_width=True, column_config={
    "Jobs": st.column_config.NumberColumn(format="int"),
    "Revenue": st.column_config.NumberColumn(format="dollar"),
    "Expenses": st.column_config.NumberColumn(format="dollar"),
    "Net Profit": st.column_config.NumberColumn(format="dollar"),
    "Avg Margin %": st.column_config.NumberColumn(format="%.1f%%"),
})

# ------------------------------------------- labor vs revenue efficiency/month
st.markdown(
    '<div class="section-title"><span class="num">02</span>Labor Cost vs. Revenue by Month</div>',
    unsafe_allow_html=True,
)

monthly = (
    filtered.groupby(["month", "month_label"], as_index=False)
    .agg(revenue=("revenue", "sum"), labor_cost=("labor_cost", "sum"))
    .sort_values("month")
)
monthly["labor_pct"] = monthly["labor_cost"] / monthly["revenue"] * 100

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_bar(name="Revenue", x=monthly["month_label"], y=monthly["revenue"],
            marker=dict(color=COLORS["revenue"], line=dict(width=0), borderradius=6),
            hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Labor Cost", x=monthly["month_label"], y=monthly["labor_cost"],
            marker=dict(color=COLORS["labor"], line=dict(width=0), borderradius=6),
            hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_scatter(
    name="Labor % of Revenue", x=monthly["month_label"], y=monthly["labor_pct"],
    mode="lines+markers",
    line=dict(color="#FBBF24", width=3.5, shape="spline", smoothing=0.6),
    marker=dict(size=9, color="#FBBF24", line=dict(color="#0B0F17", width=2)),
    hovertemplate="%{y:.1f}%<extra></extra>",
    secondary_y=True,
)
fig.update_yaxes(title_text="USD", tickprefix="$", secondary_y=False)
fig.update_yaxes(title_text="Labor % of Revenue", ticksuffix="%", secondary_y=True)
st.plotly_chart(style_fig(fig), use_container_width=True, config={"displayModeBar": False})

# ------------------------------------------------------------- top / bottom clients
st.markdown(
    '<div class="section-title"><span class="num">03</span>Client Profitability — Top & Bottom 5</div>',
    unsafe_allow_html=True,
)

by_client = (
    filtered.groupby("client_name")
    .agg(jobs=("job_type", "size"),
         revenue=("revenue", "sum"),
         net_profit=("net_profit", "sum"))
    .reset_index()
)
by_client["margin"] = by_client["net_profit"] / by_client["revenue"] * 100

top5 = by_client.nlargest(5, "net_profit")
bottom5 = by_client.nsmallest(5, "net_profit").sort_values("net_profit")

client_columns = {
    "jobs": st.column_config.NumberColumn("Jobs", format="int"),
    "revenue": st.column_config.NumberColumn("Revenue", format="dollar"),
    "net_profit": st.column_config.NumberColumn("Net Profit", format="dollar"),
    "margin": st.column_config.NumberColumn("Margin %", format="%.1f%%"),
}

c1, c2 = st.columns(2)
with c1:
    st.markdown("**🏆 Top 5 Most Profitable**")
    st.dataframe(
        top5.set_index("client_name").rename(columns={
            "jobs": "Jobs", "revenue": "Revenue", "net_profit": "Net Profit", "margin": "Margin %",
        }),
        use_container_width=True, column_config=client_columns, height=280,
    )
with c2:
    st.markdown("**⚠️ Bottom 5 Least Profitable**")
    st.dataframe(
        bottom5.set_index("client_name").rename(columns={
            "jobs": "Jobs", "revenue": "Revenue", "net_profit": "Net Profit", "margin": "Margin %",
        }),
        use_container_width=True, column_config=client_columns, height=280,
    )

# --------------------------------------------------------------- raw data
with st.expander(f"🔎 All jobs ({len(filtered)})"):
    all_jobs = filtered.drop(columns=["month"]).rename(columns={
        "date": "Date", "client_name": "Client", "job_type": "Job Type",
        "revenue": "Revenue", "labor_hours": "Labor Hrs", "hourly_labor_rate": "Rate",
        "labor_cost": "Labor Cost", "material_cost": "Materials",
        "overhead_allocation": "Overhead", "total_expense": "Total Expenses",
        "net_profit": "Net Profit", "profit_margin": "Margin",
    })
    all_jobs["Date"] = all_jobs["Date"].dt.strftime("%Y-%m-%d")
    st.dataframe(all_jobs.set_index("Date"), use_container_width=True)

st.markdown(
    f'<div class="footer">All metrics computed live from business_intel.db at render time — '
    f"nothing hardcoded • margin floor configurable in the sidebar</div>",
    unsafe_allow_html=True,
)
