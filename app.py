import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
from scraper import scrape_listings
from database import init_db, save_listings, load_history, get_latest_listings, get_all_snapshots

st.set_page_config(
    page_title="Audi A5 Avant Tracker",
    page_icon="🚗",
    layout="wide",
)

# --- Styling ---
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #0f0f0f; color: #f0f0f0; }
    [data-testid="stSidebar"] { background: #1a1a1a; }
    .metric-card {
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
    }
    .metric-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-bottom: 4px; }
    .metric-value { font-size: 28px; font-weight: 600; color: #f0f0f0; font-family: monospace; }
    .listing-card {
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 10px;
    }
    .listing-card.best { border-color: #1D9E75; background: #0d2018; }
    .badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 99px; font-weight: 500; }
    .badge-best { background: #1D9E75; color: white; }
    .badge-new { background: #BB0A21; color: white; }
    h1, h2, h3 { color: #f0f0f0 !important; }
    .stButton button { background: #BB0A21 !important; color: white !important; border: none !important; }
    .stButton button:hover { background: #990818 !important; }
    a { color: #4da6ff; }
    [data-testid="stDataFrame"] { background: #1a1a1a; }
</style>
""", unsafe_allow_html=True)

# --- Init DB ---
init_db()

# --- Header ---
col_title, col_btn = st.columns([3, 1])
with col_title:
    st.markdown("## 🔴 Audi A5 Avant — Demo Petrol Tracker")
    st.caption("Victoria · Sourced from autotrader.com.au · A5 Avant · Petrol · Demo/Near-New")

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh listings now", use_container_width=True):
        with st.spinner("Scraping zag.com.au..."):
            try:
                listings, debug_info = scrape_listings(debug=True)
                if listings:
                    save_listings(listings)
                    st.success(f"✅ Found {len(listings)} listing(s). Saved.")
                    st.rerun()
                else:
                    st.warning("No A5 Avant petrol demo listings found right now.")
                    with st.expander("🔍 Debug info"):
                        st.write(f"**Status:** {debug_info.get('status_code')}")
                        st.write(f"**Page title:** {debug_info.get('page_title')}")
                        st.write(f"**Final URL:** {debug_info.get('final_url')}")
                        st.write(f"**Raw stock/details links found:** {debug_info.get('raw_cards_found')}")
                        st.write(f"**After Avant/petrol filter:** {debug_info.get('listings_after_filter')}")
                        if debug_info.get("sample_links"):
                            st.write("**Sample links on page:**")
                            st.code("\n".join(debug_info["sample_links"]))
                        if debug_info.get("html_snippet"):
                            st.write("**Body HTML (first 5000 chars):**")
                            st.code(debug_info["html_snippet"], language="html")
            except Exception as e:
                st.error(f"Scrape failed: {e}")

st.divider()

# --- Load data ---
latest = get_latest_listings()
history = load_history()

if not latest:
    st.info("👆 Click **Refresh listings now** to scrape autotrader.com.au for current A5 Avant petrol demo/near-new stock in Victoria.")
    st.markdown("""
    **What this app does:**
    - Uses a real browser (Playwright) to load autotrader.com.au
    - Filters for: A5 Avant · Petrol · Demo or Near-New · Victoria
    - Saves every snapshot so you can track price changes over time
    - Alerts you when new listings appear or prices drop
    """)
    st.stop()

df = pd.DataFrame(latest)

# --- Stats ---
prices = df["price"].dropna()
col1, col2, col3, col4 = st.columns(4)
for col, label, val in [
    (col1, "Listings", f"{len(df)}"),
    (col2, "Lowest", f"${prices.min():,.0f}" if len(prices) else "—"),
    (col3, "Average", f"${prices.mean():,.0f}" if len(prices) else "—"),
    (col4, "Highest", f"${prices.max():,.0f}" if len(prices) else "—"),
]:
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Chart: price bar ---
if len(df) >= 2:
    min_price = prices.min()
    fig = px.bar(
        df.sort_values("price"),
        x="dealer",
        y="price",
        color="price",
        color_continuous_scale=[[0, "#1D9E75"], [0.3, "#BB0A21"], [1, "#660010"]],
        text="price",
        labels={"dealer": "Dealer", "price": "Drive-away Price ($)"},
        title="Drive-away price by dealer",
    )
    fig.update_traces(
        texttemplate="$%{text:,.0f}",
        textposition="outside",
    )
    fig.update_layout(
        plot_bgcolor="#1a1a1a",
        paper_bgcolor="#0f0f0f",
        font_color="#f0f0f0",
        coloraxis_showscale=False,
        margin=dict(t=40, b=20),
        xaxis_tickangle=-20,
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Price history chart ---
if history and len(history) > len(df):
    hist_df = pd.DataFrame(history)
    hist_df["scraped_at"] = pd.to_datetime(hist_df["scraped_at"])

    st.markdown("### Price history")
    if "vin" in hist_df.columns and hist_df["vin"].notna().any():
        fig2 = px.line(
            hist_df.dropna(subset=["price"]),
            x="scraped_at",
            y="price",
            color="vin",
            markers=True,
            labels={"scraped_at": "Date", "price": "Price ($)", "vin": "VIN"},
            title="Price over time (per vehicle)",
        )
    else:
        agg = hist_df.groupby("scraped_at")["price"].agg(["min", "mean", "max"]).reset_index()
        fig2 = go.Figure()
        for col, name, color in [("min", "Lowest", "#1D9E75"), ("mean", "Average", "#4da6ff"), ("max", "Highest", "#BB0A21")]:
            fig2.add_trace(go.Scatter(x=agg["scraped_at"], y=agg[col], name=name, line=dict(color=color), mode="lines+markers"))
        fig2.update_layout(title="Price range over time")

    fig2.update_layout(
        plot_bgcolor="#1a1a1a",
        paper_bgcolor="#0f0f0f",
        font_color="#f0f0f0",
        margin=dict(t=40, b=20),
        height=300,
    )
    st.plotly_chart(fig2, use_container_width=True)

# --- Listing cards ---
st.markdown("### Current listings")
scraped_at = df["scraped_at"].iloc[0] if "scraped_at" in df.columns else "—"
st.caption(f"Last scraped: {scraped_at}")

min_price = prices.min() if len(prices) else None
for _, row in df.sort_values("price").iterrows():
    is_best = row.get("price") == min_price
    card_class = "listing-card best" if is_best else "listing-card"
    best_badge = '<span class="badge badge-best">Lowest price</span>' if is_best else ""
    new_badge = '<span class="badge badge-new">New</span>' if row.get("is_new") else ""
    link_html = f'<a href="{row["url"]}" target="_blank">View on audi.com.au ↗</a>' if row.get("url") else ""
    price_str = f"${row['price']:,.0f}" if pd.notna(row.get("price")) else "POA"
    odo_str = f"{int(row['odometer']):,} km" if pd.notna(row.get("odometer")) else "—"

    st.markdown(f"""
    <div class="{card_class}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
            <div>
                <strong style="font-size:15px">{row.get('dealer','Unknown dealer')}</strong>
                {best_badge} {new_badge}
                <div style="font-size:12px; color:#888; margin-top:4px">{row.get('suburb','')} · {row.get('variant','A5 Avant TFSI Petrol')}</div>
                <div style="font-size:12px; color:#888">{row.get('colour','—')} · {odo_str} · Auto</div>
                {f'<div style="font-size:12px; margin-top:4px">{link_html}</div>' if link_html else ''}
            </div>
            <div style="text-align:right">
                <div style="font-size:24px; font-weight:600; font-family:monospace; color:{'#1D9E75' if is_best else '#f0f0f0'}">{price_str}</div>
                <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.05em">drive away</div>
                {f'<div style="font-size:11px; color:#888; margin-top:4px">Stock: {row["stock_no"]}</div>' if row.get("stock_no") else ''}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Raw data expander ---
with st.expander("📊 Raw data / export"):
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False)
    st.download_button("Download CSV", csv, "audi_a5_avant_listings.csv", "text/csv")

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.markdown("**Search filters** (read-only — hardcoded for accuracy)")
    st.code("Model: A5\nBody: Avant (Wagon)\nFuel: Petrol\nCondition: Demo / Near-New\nState: VIC\nSource: autotrader.com.au", language=None)

    st.divider()
    st.markdown("### 📅 Scrape history")
    snapshots = get_all_snapshots()
    if snapshots:
        for s in snapshots[-10:][::-1]:
            st.caption(f"🕐 {s['scraped_at']} — {s['count']} listings")
    else:
        st.caption("No history yet")

    st.divider()
    st.markdown("### ℹ️ About")
    st.caption("Scrapes [autotrader.com.au](https://www.autotrader.com.au/cars/audi/a5/) using Playwright. Deploy free on [Streamlit Cloud](https://streamlit.io/cloud) or [Railway](https://railway.app).")
