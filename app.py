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
MARGIN_ALERT_PCT = 15.0

COLORS = {
    "revenue": "#38BDF8",
    "expenses": "#FB7185",
    "profit": "#34D399",
    "labor": "#F59E0B",
    "text": "#E6EDF3",
    "grid": "#232A36",
}

CSS = """
<style>
.block-container { padding-top: 1.4rem; max-width: 1280px; }
div[data-testid="stMetric"] {
    background: linear-gradient(180deg, #171C26 0%, #12161F 100%);
    border: 1px solid #232A36; border-radius: 14px;
    padding: 16px 18px 12px 18px;
}
div[data-testid="stMetricLabel"] p { color: #9BA6B4 !important; font-size: 0.85rem; }
div[data-testid="stMetricValue"] { font-weight: 700; }
.section-title {
    font-size: 1.05rem; font-weight: 700; color: #E6EDF3;
    border-left: 4px solid #34D399; padding-left: 0.65rem;
    margin: 1.6rem 0 0.7rem 0;
}
div[data-testid="stDataFrame"] { border: 1px solid #232A36; border-radius: 10px; }
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
        font=dict(color=COLORS["text"], family="Inter, Segoe UI, sans-serif"),
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    fig.update_yaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    return fig


df = load_jobs()
if df.empty:
    st.error("No jobs found in business_intel.db — run `python ingest.py` first.")
    st.stop()

# ------------------------------------------------------------------ filters
with st.sidebar:
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
    st.button("🔄 Refresh data", on_click=st.cache_data.clear)

filtered = df[df["month"].isin(sel_months) & df["job_type"].isin(sel_types)].copy()
if filtered.empty:
    st.warning("No jobs match the current filters.")
    st.stop()

# ------------------------------------------------------------------ header
st.title("📊 Job Profitability Dashboard")
st.caption(
    f"{len(filtered)} jobs • {filtered['date'].min():%b %d} – {filtered['date'].max():%b %d, %Y} "
    "• all metrics computed live from SQLite"
)

# ------------------------------------------------------------ anomaly banner
anomalies = filtered[filtered["profit_margin"] < MARGIN_ALERT_PCT].sort_values("profit_margin")
if not anomalies.empty:
    leak = anomalies["net_profit"].sum()
    st.error(
        f"⚠️ **Anomaly alert — {len(anomalies)} job(s) below {MARGIN_ALERT_PCT:.0f}% profit margin.** "
        f"Net result of these jobs: **${leak:,.0f}**. Review pricing, labor or material costs.",
        icon="🚨",
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
    st.success(f"✅ All jobs are at or above the {MARGIN_ALERT_PCT:.0f}% margin floor.", icon="✔️")

# ------------------------------------------------------------------- KPIs
total_revenue = filtered["revenue"].sum()
total_expense = filtered["total_expense"].sum()
net_profit = filtered["net_profit"].sum()
overall_margin = net_profit / total_revenue * 100 if total_revenue else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("💰 Total Revenue", f"${total_revenue:,.0f}")
k2.metric("💸 Total Expenses", f"${total_expense:,.0f}")
k3.metric("📈 Net Profit", f"${net_profit:,.0f}")
k4.metric("🎯 Overall Margin", f"{overall_margin:.1f}%")

# ------------------------------------------------- profitability by job type
st.markdown('<div class="section-title">Profitability by Job Type</div>', unsafe_allow_html=True)

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
            marker_color=COLORS["revenue"], hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Expenses", x=type_order, y=by_type["expenses"],
            marker_color=COLORS["expenses"], hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Net Profit", x=type_order, y=by_type["net_profit"],
            marker_color=COLORS["profit"], hovertemplate="$%{y:,.0f}<extra></extra>")
fig.update_layout(barmode="group")
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
st.markdown('<div class="section-title">Labor Cost vs. Revenue by Month</div>', unsafe_allow_html=True)

monthly = (
    filtered.groupby(["month", "month_label"], as_index=False)
    .agg(revenue=("revenue", "sum"), labor_cost=("labor_cost", "sum"))
    .sort_values("month")
)
monthly["labor_pct"] = monthly["labor_cost"] / monthly["revenue"] * 100

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_bar(name="Revenue", x=monthly["month_label"], y=monthly["revenue"],
            marker_color=COLORS["revenue"], hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_bar(name="Labor Cost", x=monthly["month_label"], y=monthly["labor_cost"],
            marker_color=COLORS["labor"], hovertemplate="$%{y:,.0f}<extra></extra>")
fig.add_scatter(
    name="Labor % of Revenue", x=monthly["month_label"], y=monthly["labor_pct"],
    mode="lines+markers", line=dict(color="#FBBF24", width=3),
    marker=dict(size=8), hovertemplate="%{y:.1f}%<extra></extra>",
    secondary_y=True,
)
fig.update_yaxes(title_text="USD", tickprefix="$", secondary_y=False)
fig.update_yaxes(title_text="Labor % of Revenue", ticksuffix="%", secondary_y=True)
st.plotly_chart(style_fig(fig), use_container_width=True, config={"displayModeBar": False})

# ------------------------------------------------------------- top / bottom clients
st.markdown('<div class="section-title">Client Profitability — Top & Bottom 5</div>', unsafe_allow_html=True)

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
