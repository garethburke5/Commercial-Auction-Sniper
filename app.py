
import time
import streamlit as st
from db import init_db, get_lots, get_scan_status
from registry import run_all

st.set_page_config(
    page_title="Commercial Auction Sniper",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_db()

# ---------- Styling ----------
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(180deg, #0b0f16 0%, #111827 100%);
        color: #f3f4f6;
    }
    .block-container {
        max-width: 1450px;
        padding-top: 1.2rem;
        padding-bottom: 4rem;
    }
    h1, h2, h3, h4, h5, h6 { color: #f8fafc !important; }
    p, label, .stCaption, .stMarkdown { color: #d1d5db; }

    .sniper-head {
        background: linear-gradient(135deg, #151b28, #0f141e);
        border: 1px solid #273144;
        border-radius: 18px;
        padding: 22px 24px;
        margin-bottom: 16px;
    }
    .sniper-title {
        font-size: 2.3rem;
        font-weight: 900;
        line-height: 1;
        margin: 0 0 8px 0;
        color: #f8fafc;
    }
    .sniper-title span { color: #f2c94c; }
    .sniper-sub {
        color: #9ba8ba;
        font-size: 0.98rem;
        margin: 0;
    }

    div[data-testid="stNumberInput"] > div,
    div[data-testid="stSelectbox"] > div {
        background: #121722;
        border-radius: 12px;
    }

    div[data-testid="stMetric"] {
        background: #171e2b;
        border: 1px solid #273144;
        border-radius: 12px;
        padding: 12px 14px;
    }
    div[data-testid="stMetricLabel"] {
        color: #9ba8ba;
    }
    div[data-testid="stMetricValue"] {
        color: #f8fafc;
    }

    .property-shell {
        background: #121722;
        border: 1px solid #273144;
        border-radius: 18px;
        padding: 14px;
        margin: 0 0 18px 0;
        box-shadow: 0 12px 34px rgba(0,0,0,.18);
    }

    .eyebrow {
        color: #f2c94c;
        font-size: 0.78rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: .5px;
        margin-bottom: 5px;
    }

    .address {
        color: #f8fafc;
        font-size: 1.25rem;
        font-weight: 800;
        line-height: 1.25;
        margin-bottom: 10px;
    }

    .pill {
        display: inline-block;
        border: 1px solid #39465d;
        border-radius: 999px;
        padding: 5px 8px;
        margin: 3px 4px 3px 0;
        color: #cbd5e1;
        font-size: .72rem;
        background: #171e2b;
    }

    .pill-good {
        border-color: #2f855a;
        color: #9ae6b4;
    }

    .pill-warn {
        border-color: #7c5d13;
        color: #f6d365;
    }

    .small-note {
        color: #9ba8ba;
        font-size: .82rem;
        line-height: 1.45;
        margin-top: 10px;
    }

    .source-ok { color: #8ee2ae; font-weight: 700; }
    .source-warn { color: #f6d365; font-weight: 700; }
    .source-bad { color: #ff8a80; font-weight: 700; }

    div.stButton > button {
        border-radius: 10px;
        font-weight: 800;
    }

    div.stLinkButton > a {
        border-radius: 10px;
        font-weight: 800;
    }

    @media (max-width: 768px) {
        .sniper-title { font-size: 2rem; }
        .block-container { padding-left: 1rem; padding-right: 1rem; }
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="sniper-head">
  <div class="sniper-title">AUCTION <span>SNIPER</span></div>
  <div class="sniper-sub">UK commercial & mixed-use auction intelligence · live catalogue scanning</div>
</div>
""", unsafe_allow_html=True)

# ---------- Automatic first scan ----------
initial_lots = get_lots(max_price=10_000_000, min_yield=0)

if not initial_lots:
    with st.status("Scanning live auction catalogues for the first time…", expanded=True) as status:
        st.write("Auction House London")
        st.write("Pugh / BTG Eddisons")
        st.write("Savills Auctions")
        st.write("Allsop Commercial")
        st.write("Acuitus")
        try:
            result = run_all(max_guide=300000)
            status.update(
                label=f"Initial scan complete — {result.get('lots_seen', 0)} candidate lots found",
                state="complete",
                expanded=False,
            )
        except Exception as exc:
            status.update(
                label="Initial scan completed with an error",
                state="error",
                expanded=True,
            )
            st.error(str(exc))

# ---------- Controls ----------
c1, c2, c3, c4 = st.columns([1,1,1,1.2])
with c1:
    max_price = st.number_input("Target max price (£)", value=250000, step=5000)
with c2:
    min_yield = st.number_input("Minimum GIY (%)", value=10.0, step=0.5)
with c3:
    view = st.selectbox("View", ["All", "New / changed", "Watchlist"])
with c4:
    st.write("")
    st.write("")
    refresh = st.button("🔄 Refresh live auctions", type="primary", use_container_width=True)

if refresh:
    with st.spinner("Refreshing auction sources…"):
        result = run_all(max_guide=300000)
    st.success(f"Refresh complete — {result.get('lots_seen',0)} candidate lots seen.")
    time.sleep(0.8)
    st.rerun()

show_unknown = st.toggle("Show unpriced / yield unknown", value=False)

board_tab, source_tab = st.tabs(["🎯 Sniper Board", "📡 Source Health"])

# ---------- Source health ----------
with source_tab:
    scans = get_scan_status()
    if not scans:
        st.info("No scan records yet.")
    else:
        for s in scans:
            if s["status"] == "OK":
                cls = "source-ok"
                icon = "✅"
            elif s["status"] == "CATALOGUE_PENDING":
                cls = "source-warn"
                icon = "⏳"
            else:
                cls = "source-bad"
                icon = "⚠️"

            st.markdown(
                f"""
                <div class="property-shell">
                  <div class="{cls}">{icon} {s["source"]}</div>
                  <div class="small-note">
                    Status: {s["status"]} · Lots seen: {s["lots_seen"]}<br>
                    {s["message"] or ""}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ---------- Sniper board ----------
with board_tab:
    lots = get_lots(max_price=max_price, min_yield=min_yield)

    if not lots:
        st.warning(
            "No lots currently match these filters. "
            "Try lowering the minimum yield or increasing the maximum price, "
            "then press Refresh live auctions."
        )
    else:
        st.caption(f"{len(lots)} candidate lots match the current filters")

    for x in lots:
        if not show_unknown and (x["guide_price"] is None or x["gross_yield"] is None):
            continue

        auctioneer = x["auctioneer"] or "Unknown auctioneer"
        auction_date = x["auction_date"] or "Date TBC"
        lot_no = x["lot_number"] or "Lot TBC"
        status = x["status"] or "Live"

        st.markdown('<div class="property-shell">', unsafe_allow_html=True)
        left, right = st.columns([1.05, 1.95], gap="large")

        with left:
            if x["image_url"]:
                try:
                    st.image(x["image_url"], use_container_width=True)
                except Exception:
                    st.info("Property image unavailable")
            else:
                st.info("Property image unavailable")

        with right:
            st.markdown(
                f'<div class="eyebrow">{auctioneer} · {auction_date} · {lot_no} · {status}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="address">{x["address"]}</div>',
                unsafe_allow_html=True,
            )

            m1, m2, m3, m4 = st.columns(4)

            with m1:
                st.metric(
                    "Guide",
                    f'£{x["guide_price"]:,.0f}' if x["guide_price"] else "UNKNOWN",
                )

            with m2:
                st.metric(
                    "Rent p.a.",
                    f'£{x["annual_rent"]:,.0f}' if x["annual_rent"] else "UNKNOWN",
                )

            with m3:
                st.metric(
                    "GIY",
                    f'{x["gross_yield"]:.1f}%' if x["gross_yield"] is not None else "UNKNOWN",
                )

            ceiling = x["annual_rent"] / 0.10 if x["annual_rent"] else None
            with m4:
                st.metric(
                    "10% ceiling",
                    f'£{ceiling:,.0f}' if ceiling else "UNKNOWN",
                )

            tenure = x["tenure"] or "UNKNOWN"
            vat = x["vat_status"] or "UNKNOWN"
            togc = x["togc_status"] or "UNKNOWN"
            legal = x["legal_pack_status"] or "UNKNOWN"

            pills = [
                ("Tenure", tenure, "good" if "Freehold" in tenure else "warn"),
                ("VAT", vat, "warn" if vat not in ["NOT APPLICABLE","UNKNOWN"] else "good"),
                ("TOGC", togc, "warn" if togc not in ["UNKNOWN","NO"] else "good"),
                ("Legal pack", legal, "good" if legal == "AVAILABLE" else "warn"),
            ]

            pill_html = ""
            for label, value, tone in pills:
                css = "pill-good" if tone == "good" else "pill-warn"
                pill_html += f'<span class="pill {css}">{label}: {value}</span>'

            st.markdown(pill_html, unsafe_allow_html=True)

            b1, b2 = st.columns(2)
            with b1:
                st.link_button(
                    "View original lot ↗",
                    x["source_url"],
                    use_container_width=True,
                )
            with b2:
                if x.get("legal_pack_url"):
                    st.link_button(
                        "Open legal pack ↗",
                        x["legal_pack_url"],
                        use_container_width=True,
                    )

        st.markdown("</div>", unsafe_allow_html=True)
