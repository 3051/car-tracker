import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import httpx
from scraper import scrape_listings, get_price_history
from database import init_db, save_listings, load_history, get_latest_listings, get_all_snapshots

@st.cache_data(ttl=86400)
def geocode_suburbs(suburbs: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    with httpx.Client(timeout=10, headers={"User-Agent": "audi-a5-tracker/1.0"}) as client:
        for suburb in suburbs:
            if not suburb or suburb in coords:
                continue
            try:
                r = client.get(
                    "https://photon.komoot.io/api/",
                    params={"q": f"{suburb} Victoria Australia", "limit": 1, "lang": "en"},
                )
                features = r.json().get("features", [])
                if features:
                    lon, lat = features[0]["geometry"]["coordinates"]
                    coords[suburb] = (float(lat), float(lon))
            except Exception:
                pass
    return coords


@st.cache_data(ttl=3600)
def fetch_price_history(listing_ids: tuple[str, ...]) -> dict[str, list[dict]]:
    return get_price_history(list(listing_ids))


def make_sparkline(prices: list[float], dates: list[str] | None = None, width: int = 300, height: int = 52) -> str:
    if len(prices) < 2:
        return ""
    lo, hi = min(prices), max(prices)
    if hi == lo:
        hi = lo + 1
    def sx(i: int) -> float:
        return i / (len(prices) - 1) * width
    def sy(p: float) -> float:
        return height - 4 - (p - lo) / (hi - lo) * (height - 8)
    pts = " ".join(f"{sx(i):.1f},{sy(p):.1f}" for i, p in enumerate(prices))
    area = f"0,{height} {pts} {width},{height}"
    svg = (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        f'<polygon points="{area}" fill="#BB0A21" fill-opacity="0.15"/>'
        f'<polyline points="{pts}" fill="none" stroke="#BB0A21" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )
    label_style = "display:flex;justify-content:space-between;font-size:9px;font-family:monospace;"
    price_row = f'<div style="{label_style}color:#888;margin-bottom:2px;"><span>${prices[0]:,.0f}</span><span>${prices[-1]:,.0f}</span></div>'
    date_row = ""
    if dates and len(dates) >= 2:
        from datetime import datetime
        def fmt(d: str) -> str:
            try: return datetime.strptime(d, "%Y-%m-%d").strftime("%b %d")
            except Exception: return d
        date_row = f'<div style="{label_style}color:#555;margin-top:2px;"><span>{fmt(dates[0])}</span><span>{fmt(dates[-1])}</span></div>'
    return price_row + svg + date_row


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
    .badge-used { background: #555; color: #ccc; }
    .badge-demo { background: #2a4a8a; color: #aac4ff; }
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
    st.markdown("## 🔴 Audi A5 Avant — Demo &amp; Used Petrol Tracker")
    st.caption("Victoria · Sourced from drive.com.au · A5 Avant · TFSI Petrol · Demo &amp; Used")

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh listings now", use_container_width=True):
        with st.spinner("Scraping drive.com.au..."):
            try:
                listings, debug_info = scrape_listings(debug=True)
                if listings:
                    save_listings(listings)
                    st.success(f"✅ Found {len(listings)} listing(s). Saved.")
                    st.rerun()
                else:
                    st.warning("No A5 Avant petrol listings found right now.")
                    with st.expander("🔍 Debug info"):
                        lines = [
                            f"status:            {debug_info.get('status_code')}",
                            f"total_from_api:    {debug_info.get('total_from_api')}",
                            f"listings_found:    {debug_info.get('listings_after_filter')}",
                        ]
                        st.code("\n".join(lines))
            except Exception as e:
                st.error(f"Scrape failed: {e}")

st.divider()

# --- Load data ---
latest = get_latest_listings()
history = load_history()

if not latest:
    st.info("👆 Click **Refresh listings now** to scrape drive.com.au for current A5 Avant TFSI petrol demo &amp; used stock in VIC.")
    st.markdown("""
    **What this app does:**
    - Queries the drive.com.au GraphQL API — no browser needed
    - Filters for: A5 Avant · TFSI Petrol · Demo and Used · Victoria · All dealers
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
        yaxis=dict(showgrid=True, gridcolor="#2a2a2a", tickprefix="$", tickformat=","),
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Listings: Map / List tabs ---
st.markdown("### Current listings")
scraped_at = df["scraped_at"].iloc[0] if "scraped_at" in df.columns else "—"
st.caption(f"Last scraped: {scraped_at}")

listing_ids = tuple(df["stock_no"].dropna().astype(str).tolist())
with st.spinner("Loading price history…"):
    ph = fetch_price_history(listing_ids)

tab_list, tab_map = st.tabs(["List", "Map"])

min_price = prices.min() if len(prices) else None

with tab_list:

    for _, row in df.sort_values("price").iterrows():
        is_best = row.get("price") == min_price
        card_class = "listing-card best" if is_best else "listing-card"
        best_badge = '<span class="badge badge-best">Lowest price</span>' if is_best else ""
        new_badge = '<span class="badge badge-new">New</span>' if row.get("is_new") else ""
        cond = row.get("condition", "Demo")
        cond_badge = f'<span class="badge badge-{"used" if cond == "Used" else "demo"}">{cond}</span>'
        link_html = f'<a href="{row["url"]}" target="_blank">View on drive.com.au ↗</a>' if row.get("url") else ""
        price_str = f"${row['price']:,.0f}" if pd.notna(row.get("price")) else "POA"
        odo_str = f"{int(row['odometer']):,} km" if pd.notna(row.get("odometer")) else "—"

        history = ph.get(str(row.get("stock_no", "")))
        spark_pts = [(pt["price"], pt["date"]) for pt in (history or []) if pt.get("price")]
        spark_html = ""
        if len(spark_pts) >= 2:
            spark_prices = [p for p, _ in spark_pts]
            spark_dates = [d for _, d in spark_pts]
            spark_html = '<div style="margin-top:10px;border-top:1px solid #2a2a2a;padding-top:8px;">' + make_sparkline(spark_prices, spark_dates) + '</div>'

        st.markdown(f"""
        <div class="{card_class}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
                <div>
                    <strong style="font-size:15px">{row.get('dealer','Unknown dealer')}</strong>
                    {cond_badge} {best_badge} {new_badge}
                    <div style="font-size:12px; color:#888; margin-top:4px">{row.get('suburb','')} · {row.get('variant','A5 Avant TFSI Petrol')}</div>
                    <div style="font-size:12px; color:#888">{odo_str} · Auto</div>
                    {f'<div style="font-size:12px; margin-top:4px">{link_html}</div>' if link_html else ''}
                </div>
                <div style="text-align:right">
                    <div style="font-size:24px; font-weight:600; font-family:monospace; color:{'#1D9E75' if is_best else '#f0f0f0'}">{price_str}</div>
                    <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.05em">drive away</div>
                </div>
            </div>
            {spark_html}
        </div>
        """, unsafe_allow_html=True)

with tab_map:
    suburbs = tuple(df["suburb"].dropna().unique().tolist())
    with st.spinner("Geocoding suburbs…"):
        coords = geocode_suburbs(suburbs)
    map_df = df.copy()
    map_df["lat"] = map_df["suburb"].map(lambda s: coords.get(s, (None, None))[0])
    map_df["lon"] = map_df["suburb"].map(lambda s: coords.get(s, (None, None))[1])
    map_df = map_df.dropna(subset=["lat", "lon"])
    if map_df.empty:
        st.info("Could not geocode any suburbs.")
    else:
        map_df["price_str"] = map_df["price"].apply(lambda p: f"${p:,.0f}" if pd.notna(p) else "POA")
        fig_map = px.scatter_mapbox(
            map_df,
            lat="lat", lon="lon",
            hover_name="dealer",
            hover_data={"price_str": True, "suburb": True, "price": False, "lat": False, "lon": False},
            color="price",
            color_continuous_scale=[[0, "#1D9E75"], [0.5, "#BB0A21"], [1, "#660010"]],
            mapbox_style="open-street-map",
            zoom=8,
            center={"lat": -37.85, "lon": 145.05},
            labels={"price_str": "Price", "suburb": "Suburb"},
        )
        fig_map.update_traces(marker_size=14)
        fig_map.update_layout(
            paper_bgcolor="#0f0f0f", font_color="#f0f0f0",
            margin=dict(t=0, b=0, l=0, r=0), height=480,
            coloraxis_colorbar=dict(title="Price ($)", tickprefix="$", tickformat=","),
        )
        sel = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", key="map_select")
        if sel and sel.selection and sel.selection.points:
            sel_row = map_df.iloc[sel.selection.points[0]["point_index"]]
            price_str = f"${sel_row['price']:,.0f}" if pd.notna(sel_row.get("price")) else "POA"
            odo_str = f"{int(sel_row['odometer']):,} km" if pd.notna(sel_row.get("odometer")) else "—"
            cond = sel_row.get("condition", "Demo")
            link_html = f'<a href="{sel_row["url"]}" target="_blank">View on drive.com.au ↗</a>' if sel_row.get("url") else ""
            sel_history = ph.get(str(sel_row.get("stock_no", "")))
            sel_spark_pts = [(pt["price"], pt["date"]) for pt in (sel_history or []) if pt.get("price")]
            sel_spark_html = ""
            if len(sel_spark_pts) >= 2:
                sel_spark_html = '<div style="margin-top:10px;border-top:1px solid #2a2a2a;padding-top:8px;">' + make_sparkline([p for p, _ in sel_spark_pts], [d for _, d in sel_spark_pts]) + '</div>'
            st.markdown(f"""
            <div class="listing-card" style="margin-top:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
                    <div>
                        <strong style="font-size:15px">{sel_row.get('dealer','Unknown')}</strong>
                        <span class="badge badge-{'used' if cond == 'Used' else 'demo'}">{cond}</span>
                        <div style="font-size:12px;color:#888;margin-top:4px">{sel_row.get('suburb','')} · {sel_row.get('variant','')}</div>
                        <div style="font-size:12px;color:#888">{odo_str} · Auto</div>
                        {f'<div style="font-size:12px;margin-top:6px">{link_html}</div>' if link_html else ''}
                    </div>
                    <div style="text-align:right">
                        <div style="font-size:24px;font-weight:600;font-family:monospace;color:#f0f0f0">{price_str}</div>
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.05em">drive away</div>
                    </div>
                </div>
                {sel_spark_html}
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
    st.code("Model: A5\nBody: Avant (Wagon)\nFuel: TFSI Petrol\nCondition: Demo + Used\nState: VIC\nSource: drive.com.au", language=None)

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
    st.caption("DZ Car Tracker — queries [drive.com.au](https://www.drive.com.au) for Audi A5 Avant TFSI petrol listings in VIC.")
