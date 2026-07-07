#!/usr/bin/env python3
"""
Apostille Research — Streamlit Dashboard
Run: streamlit run dashboard.py
"""

import csv
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

OUTPUT_DIR = Path("output")


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_latest_csv() -> pd.DataFrame:
    csvs = sorted(OUTPUT_DIR.glob("results_*.csv"), reverse=True)
    if not csvs:
        return pd.DataFrame()
    df = pd.read_csv(csvs[0])
    return df


@st.cache_data(ttl=300)
def load_diff_history() -> list[dict]:
    diff_file = OUTPUT_DIR / "diff_history.json"
    if not diff_file.exists():
        return []
    try:
        return json.loads(diff_file.read_text())
    except Exception:
        return []


def format_serp_position(pos):
    if isinstance(pos, (int, float)) and pos > 0:
        if pos <= 3:
            return f"🥇 #{int(pos)}"
        if pos <= 5:
            return f"🥈 #{int(pos)}"
        return f"#{int(pos)}"
    return "—"


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Apostille Competitor Research",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📄 Apostille Competitor Research Dashboard")

df = load_latest_csv()
if df.empty:
    st.warning(
        "No results found. Run `python main.py` first to generate competitor data."
    )
    st.stop()

csvs = sorted(OUTPUT_DIR.glob("results_*.csv"), reverse=True)
run_date = csvs[0].stem.replace("results_", "") if csvs else "unknown"
st.caption(f"Data from run: **{run_date}** | {len(df)} competitors")


# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    min_kw = st.slider("Min keywords ranking in", 1, 22, 1)
    max_pos = st.slider("Max avg SERP position", 1, 100, 50)

    show_cols = st.multiselect(
        "Columns to display",
        options=df.columns.tolist(),
        default=[c for c in [
            "Rank", "Domain", "# Keywords Ranking", "Best SERP Position",
            "Avg SERP Position", "Marketing Strategy", "Primary Offer",
            "Trust Signals", "Pricing Transparency",
        ] if c in df.columns],
    )

    st.divider()
    st.header("Quick links")
    st.markdown("- [Run full scan](terminal://python3 main.py)")
    st.markdown("- [output/ folder](output/)")


# ── Apply filters ─────────────────────────────────────────────────────────────

filtered = df.copy()
if "# Keywords Ranking" in filtered.columns:
    filtered = filtered[
        filtered["# Keywords Ranking"].fillna(0).astype(int) >= min_kw
    ]
if "Avg SERP Position" in filtered.columns:
    filtered = filtered[
        filtered["Avg SERP Position"].fillna(999).astype(float) <= max_pos
    ]


# ── KPI cards ─────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Competitors", len(df))
col2.metric("After Filters", len(filtered))

if "Best SERP Position" in df.columns:
    top_domain = df.loc[df["Best SERP Position"].idxmin(), "Domain"] if not df.empty else "—"
    col3.metric("Dominant Player", top_domain)

if "Pricing Transparency" in df.columns:
    pricing_yes = df["Pricing Transparency"].astype(str).str.contains("Yes|Partial", na=False).sum()
    col4.metric("Show Pricing", f"{pricing_yes}/{len(df)}")


# ── Main table ────────────────────────────────────────────────────────────────

st.subheader("Competitor Table")

display_cols = [c for c in show_cols if c in filtered.columns]
if display_cols:
    st.dataframe(
        filtered[display_cols].reset_index(drop=True),
        use_container_width=True,
        height=420,
    )
else:
    st.dataframe(filtered.reset_index(drop=True), use_container_width=True, height=420)


# ── SERP presence chart ───────────────────────────────────────────────────────

st.subheader("Keyword Coverage — Top 20 Competitors")
if "# Keywords Ranking" in df.columns and "Domain" in df.columns:
    chart_df = (
        df[["Domain", "# Keywords Ranking"]]
        .nlargest(20, "# Keywords Ranking")
        .set_index("Domain")
    )
    st.bar_chart(chart_df)


# ── Trust signals section ─────────────────────────────────────────────────────

if "Trust Signals" in df.columns:
    st.subheader("Trust & Social Proof Landscape")
    trust_df = df[["Domain", "Trust Signals", "Social Proof"]].dropna(subset=["Trust Signals"])
    st.dataframe(trust_df.reset_index(drop=True), use_container_width=True)


# ── Pricing intelligence ──────────────────────────────────────────────────────

if "Pricing Transparency" in df.columns:
    st.subheader("Pricing Transparency")
    price_counts = df["Pricing Transparency"].value_counts().rename("Count")
    st.bar_chart(price_counts)


# ── Competitor detail card ────────────────────────────────────────────────────

st.subheader("Competitor Deep-Dive")
if "Domain" in df.columns:
    selected = st.selectbox("Select a competitor", df["Domain"].tolist())
    row = df[df["Domain"] == selected].iloc[0]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**URL:** [{row.get('URL', '')}]({row.get('URL', '')})")
        st.markdown(f"**Keywords:** {row.get('# Keywords Ranking', '—')} | Best pos: {row.get('Best SERP Position', '—')}")
        st.markdown(f"**Marketing Strategy:** {row.get('Marketing Strategy', '—')}")
        st.markdown(f"**Primary Offer:** {row.get('Primary Offer', '—')}")
        st.markdown(f"**Pricing:** {row.get('Pricing Transparency', '—')}")
    with col_b:
        st.markdown(f"**Trust Signals:** {row.get('Trust Signals', '—')}")
        st.markdown(f"**Social Proof:** {row.get('Social Proof', '—')}")
        st.markdown(f"**Value Proposition:** {row.get('Value Proposition', '—')}")
        st.markdown(f"**What to Learn:** {row.get('What to Learn', '—')}")
        st.markdown(f"**Our Advantage:** {row.get('Our Competitive Advantage', '—')}")

    with st.expander("Full AI Analysis"):
        for col in ["Marketing Strategy", "Primary Offer", "Key Headlines",
                    "Value Proposition", "Workflow Logic", "Cold Email Signals",
                    "Form Analysis", "Content Marketing", "What They Can Improve",
                    "Future Ideas"]:
            val = row.get(col)
            if val and str(val) not in ("nan", ""):
                st.markdown(f"**{col}:** {val}")


# ── Weekly diff history ───────────────────────────────────────────────────────

history = load_diff_history()
if history:
    st.subheader("Weekly Diff History")
    hist_df = pd.DataFrame([
        {
            "Date": h["date"],
            "New Competitors": len(h.get("new_competitors", [])),
            "Dropped": len(h.get("dropped_competitors", [])),
            "Rank Changes": len(h.get("rank_changes", [])),
            "Summary": h.get("summary", ""),
        }
        for h in history
    ])
    st.dataframe(hist_df, use_container_width=True)


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Apostille Research Tool — powered by Serper + Firecrawl + OpenRouter. "
    "Re-run: `python main.py --all-extras` for full analysis."
)
