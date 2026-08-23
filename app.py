import html
import os
import sqlite3
import time
import streamlit as st
import db
from registry import run_all

st.set_page_config(
    page_title="Commercial Auction Sniper",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)
db.init_db()

# Make Streamlit Secrets available to the collector without exposing them in GitHub.
try:
    if "SAVILLS_EMAIL" in st.secrets:
        os.environ["SAVILLS_EMAIL"] = str(st.secrets["SAVILLS_EMAIL"])
    if "SAVILLS_PASSWORD" in st.secrets:
        os.environ["SAVILLS_PASSWORD"] = str(st.secrets["SAVILLS_PASSWORD"])
except Exception:
    pass

# One-time purge for previous contaminated scans.
def purge_once():
    db_path = getattr(db, "DB", "auction_sniper.db")
    con = sqlite3.connect(db_path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT)")
        marker = "strict_commercial_reset_v5"
        if con.execute("SELECT 1 FROM app_meta WHERE key=?", (marker,)).fetchone():
            return False
        con.execute("DELETE FROM lots")
        try:
            con.execute("DELETE FROM scans")
        except Exception:
            pass
        con.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES (?,?)", (marker, "done"))
        con.commit()
        return True
    finally:
        con.close()

purged = purge_once()

st.markdown("""
<style>
/* Remove Streamlit's large blank mobile chrome at the top. */
header[data-testid="stHeader"],
div[data-testid="stToolbar"],
.stAppToolbar,
#MainMenu {display:none !important;}
.block-container{padding-top:.35rem !important;}

:root{
--panel:#121824;--panel2:#171f2d;--line:#273247;
--text:#f7f8fb;--muted:#9aa8bb;--accent:#f2c94c;
}
.stApp{background:linear-gradient(180deg,#090d13,#101724);color:var(--text)}
.block-container{max-width:1500px;padding-left:.45rem;padding-right:.45rem;padding-bottom:2rem}

.hero{
display:flex;justify-content:space-between;align-items:center;gap:10px;
background:linear-gradient(135deg,#151b28,#0d131d);
border:1px solid var(--line);border-radius:13px;
padding:11px 12px;margin:0 0 7px 0
}
.brand{font-size:1.35rem;font-weight:950;color:var(--text);line-height:1}
.brand span{color:var(--accent)}
.tag{font-size:.62rem;color:var(--muted);margin-top:4px}
.hero-badge{
font-size:.58rem;font-weight:850;color:#9ae6b4;
border:1px solid #2e8b5c;border-radius:999px;padding:5px 7px;white-space:nowrap
}

.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:6px}
.card{
background:var(--panel);border:1px solid var(--line);border-radius:11px;
overflow:hidden;box-shadow:0 5px 14px rgba(0,0,0,.17)
}
.card img{width:100%;height:110px;object-fit:cover;display:block;background:#1b2432}
.noimg{height:75px;display:grid;place-items:center;color:#75839a;background:#1b2432;font-size:.52rem;font-weight:800}
.cb{padding:7px}
.source{font-size:.47rem;color:var(--accent);font-weight:900;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.addr{font-size:.68rem;font-weight:850;line-height:1.16;color:var(--text);margin:3px 0 6px;min-height:2.25em}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:2px}
.metric{background:var(--panel2);border:1px solid #222d3e;border-radius:6px;padding:4px}
.metric span{display:block;color:var(--muted);font-size:.38rem;margin-bottom:1px}
.metric b{font-size:.54rem;color:var(--text);white-space:nowrap}
.pills{margin-top:5px;display:flex;gap:2px;flex-wrap:wrap}
.pill{font-size:.36rem;border:1px solid #3b4961;border-radius:999px;padding:2px 4px;color:#cbd5e1}
.good{border-color:#2e8b5c;color:#9ae6b4}
.warn{border-color:#8a681d;color:#f1d47a}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:3px;margin-top:5px}
.actions a{
display:block;text-align:center;text-decoration:none;font-size:.43rem;font-weight:900;
padding:5px 3px;border-radius:6px;border:1px solid var(--line);color:var(--text);background:#172033
}
.actions a.primary{background:var(--accent);color:#191506;border-color:var(--accent)}

div[data-testid="stExpander"]{
border:1px solid var(--line);border-radius:10px;background:#101722;margin-bottom:5px
}
div[data-testid="stExpander"] summary{font-size:.72rem;font-weight:800}

@media(max-width:800px){
.block-container{padding:.2rem .22rem 1.5rem}
.hero{padding:9px 9px;border-radius:10px;margin-bottom:4px}
.brand{font-size:1.08rem}.tag{font-size:.50rem}.hero-badge{font-size:.46rem;padding:4px 5px}
.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin-top:4px}
.card img{height:70px}.cb{padding:5px}.source{font-size:.34rem}.addr{font-size:.53rem;margin:2px 0 4px}
.metrics{grid-template-columns:repeat(2,1fr);gap:2px}.metric{padding:3px}.metric span{font-size:.31rem}.metric b{font-size:.46rem}
.pill{font-size:.30rem;padding:2px 3px}.actions{grid-template-columns:1fr}.actions a{font-size:.36rem;padding:4px 2px}
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div>
    <div class="brand">AUCTION <span>SNIPER</span></div>
    <div class="tag">Commercial & mixed-use auction opportunities</div>
  </div>
  <div class="hero-badge">COMMERCIAL ONLY</div>
</div>
""", unsafe_allow_html=True)

if purged:
    st.toast("Old contaminated lot cache cleared")

# First scan automatically after purge / clean deploy.
existing = db.get_lots(max_price=10_000_000, min_yield=0)
if not existing:
    with st.status("Scanning commercial auction sources…", expanded=False) as status:
        try:
            result = run_all(max_guide=300000)
            status.update(label=f"Scan complete · {result.get('lots_seen',0)} candidates", state="complete")
        except Exception as exc:
            status.update(label="Scan failed", state="error")
            st.error(str(exc))

# Keep filters off the initial screen. Open only when needed.
with st.expander("⚙️ Filters & refresh", expanded=False):
    f1,f2 = st.columns(2)
    with f1:
        max_price = st.number_input("Maximum guide (£)", value=250000, step=5000)
    with f2:
        min_yield = st.number_input("Minimum GIY (%)", value=10.0, step=.5)
    show_unknown = st.toggle("Include unknown yield", value=False)
    if st.button("🔄 Refresh live commercial lots", type="primary", use_container_width=True):
        with st.spinner("Refreshing…"):
            result = run_all(max_guide=300000)
        st.toast(f"{result.get('lots_seen',0)} candidates seen")
        time.sleep(.25)
        st.rerun()

# Defaults when expander not touched.
max_price = locals().get("max_price", 250000)
min_yield = locals().get("min_yield", 10.0)
show_unknown = locals().get("show_unknown", False)

board, health = st.tabs(["🎯 Lots", "📡 Sources"])

with health:
    scans = db.get_scan_status()
    if not scans:
        st.info("No scan results yet.")
    for s in scans:
        icon = "✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️")
        st.write(f'{icon} **{s["source"]}** — {s["status"]} — {s["lots_seen"]} lots')
        if s["message"]:
            st.caption(s["message"])

def money(v):
    return "—" if v is None else f"£{v:,.0f}"

def pct(v):
    return "—" if v is None else f"{v:.1f}%"

def pill(label,value,good=False):
    cls="good" if good else "warn"
    return f'<span class="pill {cls}">{html.escape(label)}: {html.escape(str(value))}</span>'

with board:
    lots = db.get_lots(max_price=max_price, min_yield=min_yield)
    if not show_unknown:
        lots = [x for x in lots if x.get("guide_price") is not None and x.get("gross_yield") is not None]

    if not lots:
        st.warning("No matching commercial/mixed-use lots yet.")
    else:
        st.caption(f"{len(lots)} qualifying commercial / mixed-use lots")
        cards=[]
        for x in lots:
            image=x.get("image_url")
            image_html=f'<img src="{html.escape(image)}" alt="">' if image else '<div class="noimg">PROPERTY IMAGE</div>'
            ceiling=x["annual_rent"]/.10 if x.get("annual_rent") else None
            tenure=x.get("tenure") or "UNKNOWN"
            vat=x.get("vat_status") or "UNKNOWN"
            togc=x.get("togc_status") or "UNKNOWN"
            legal=x.get("legal_pack_status") or "UNKNOWN"

            pills="".join([
                pill("Tenure",tenure,"Freehold" in tenure),
                pill("VAT",vat,vat=="NOT APPLICABLE"),
                pill("TOGC",togc,togc in ["UNKNOWN","NO"]),
                pill("Pack",legal,legal=="AVAILABLE"),
            ])
            legal_link=f'<a href="{html.escape(x["legal_pack_url"])}" target="_blank">Legal pack ↗</a>' if x.get("legal_pack_url") else ""

            cards.append(
                '<div class="card">'+image_html+'<div class="cb">'
                +f'<div class="source">{html.escape(x.get("auctioneer") or "Auction")} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'
                +f'<div class="addr">{html.escape(x.get("address") or "Address unavailable")}</div>'
                +'<div class="metrics">'
                +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
                +f'<div class="metric"><span>Rent</span><b>{money(x.get("annual_rent"))}</b></div>'
                +f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
                +f'<div class="metric"><span>10% max</span><b>{money(ceiling)}</b></div>'
                +'</div>'
                +f'<div class="pills">{pills}</div>'
                +'<div class="actions">'
                +f'<a class="primary" href="{html.escape(x["source_url"])}" target="_blank">Original ↗</a>'
                +legal_link
                +'</div></div></div>'
            )
        st.markdown('<div class="cards">'+"".join(cards)+'</div>', unsafe_allow_html=True)
