import html
import time
import streamlit as st
from db import init_db, get_lots, get_scan_status
from registry import run_all

st.set_page_config(page_title="Commercial Auction Sniper", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")
init_db()

st.markdown('''
<style>
:root{--bg:#0a0e15;--panel:#121824;--panel2:#171f2d;--line:#273247;--text:#f7f8fb;--muted:#9aa8bb;--accent:#f2c94c;--good:#78d6a0;--warn:#f0c75e}
.stApp{background:linear-gradient(180deg,#090d13,#101724);color:var(--text)}
.block-container{max-width:1500px;padding:1rem 1rem 3rem}
.sniper-head{background:linear-gradient(135deg,#151b28,#0f141e);border:1px solid var(--line);border-radius:16px;padding:15px 18px;margin-bottom:12px}
.sniper-title{font-size:1.75rem;font-weight:950;color:var(--text);line-height:1}
.sniper-title span{color:var(--accent)}
.sniper-sub{font-size:.78rem;color:var(--muted);margin-top:6px}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 8px 22px rgba(0,0,0,.20)}
.card img{width:100%;height:145px;object-fit:cover;display:block;background:#1b2432}
.noimg{height:100px;display:grid;place-items:center;color:#75839a;background:linear-gradient(135deg,#1b2432,#111723);font-size:.7rem;font-weight:800}
.cb{padding:11px}
.source{font-size:.62rem;color:var(--accent);font-weight:900;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.addr{font-size:.92rem;font-weight:850;line-height:1.2;color:var(--text);margin:5px 0 9px;min-height:2.2em}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:5px}
.metric{background:var(--panel2);border:1px solid #222d3e;border-radius:8px;padding:6px}
.metric span{display:block;color:var(--muted);font-size:.53rem;margin-bottom:2px}
.metric b{font-size:.74rem;color:var(--text);white-space:nowrap}
.pills{margin-top:8px;display:flex;gap:4px;flex-wrap:wrap}
.pill{font-size:.52rem;border:1px solid #3b4961;border-radius:999px;padding:4px 6px;color:#cbd5e1}
.good{border-color:#2e8b5c;color:#9ae6b4}
.warn{border-color:#8a681d;color:#f1d47a}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}
.actions a{display:block;text-align:center;text-decoration:none;font-size:.62rem;font-weight:900;padding:7px 5px;border-radius:8px;border:1px solid var(--line);color:var(--text);background:#172033}
.actions a.primary{background:var(--accent);color:#191506;border-color:var(--accent)}
@media(max-width:800px){
.block-container{padding:.75rem .55rem 2rem}
.sniper-head{padding:12px 13px}
.sniper-title{font-size:1.45rem}
.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
.card img{height:100px}
.cb{padding:8px}
.source{font-size:.50rem}
.addr{font-size:.72rem;margin:4px 0 6px;min-height:2.3em}
.metrics{grid-template-columns:repeat(2,1fr);gap:3px}
.metric{padding:5px}
.metric span{font-size:.46rem}
.metric b{font-size:.64rem}
.pills{gap:3px;margin-top:6px}
.pill{font-size:.44rem;padding:3px 5px}
.actions{grid-template-columns:1fr;margin-top:6px}
.actions a{font-size:.52rem;padding:6px 4px}
}
</style>
''', unsafe_allow_html=True)

st.markdown('''
<div class="sniper-head">
  <div class="sniper-title">AUCTION <span>SNIPER</span></div>
  <div class="sniper-sub">Commercial & mixed-use only · UK auction intelligence</div>
</div>
''', unsafe_allow_html=True)

all_existing = get_lots(max_price=10_000_000, min_yield=0)
if not all_existing:
    with st.status("Loading live commercial auction lots…", expanded=False) as status:
        try:
            result = run_all(max_guide=300000)
            status.update(label=f"Live scan complete — {result.get('lots_seen',0)} commercial candidates", state="complete")
        except Exception as exc:
            status.update(label="Live scan hit an error", state="error")
            st.error(str(exc))

f1,f2,f3 = st.columns([1,1,1.1])
with f1:
    max_price = st.number_input("Max guide (£)", value=250000, step=5000)
with f2:
    min_yield = st.number_input("Min GIY (%)", value=10.0, step=.5)
with f3:
    st.write("")
    refresh = st.button("🔄 Refresh live lots", type="primary", use_container_width=True)

if refresh:
    with st.spinner("Refreshing commercial auction catalogues…"):
        result = run_all(max_guide=300000)
    st.toast(f"{result.get('lots_seen',0)} commercial candidates seen")
    time.sleep(.4)
    st.rerun()

show_unknown = st.toggle("Include lots with unknown yield", value=False)
board, health = st.tabs(["🎯 Commercial lots", "📡 Sources"])

with health:
    scans = get_scan_status()
    if not scans:
        st.info("No scans yet.")
    else:
        for s in scans:
            icon = "✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️")
            st.write(f'{icon} **{s["source"]}** — {s["status"]} — {s["lots_seen"]} candidates — {s["message"] or ""}')

def money(v):
    return "—" if v is None else f"£{v:,.0f}"

def pct(v):
    return "—" if v is None else f"{v:.1f}%"

def pill(label, value, good=False):
    klass = "pill good" if good else "pill warn"
    return f'<span class="{klass}">{html.escape(label)}: {html.escape(str(value))}</span>'

with board:
    lots = get_lots(max_price=max_price, min_yield=min_yield)
    if not show_unknown:
        lots = [x for x in lots if x.get("guide_price") is not None and x.get("gross_yield") is not None]

    if not lots:
        st.warning("No commercial lots currently match these filters. Try lowering the minimum yield or press Refresh.")
    else:
        st.caption(f"{len(lots)} commercial / mixed-use candidates")
        cards = []
        for x in lots:
            image = x.get("image_url")
            image_html = f'<img src="{html.escape(image)}" alt="">' if image else '<div class="noimg">PROPERTY IMAGE</div>'
            ceiling = x["annual_rent"] / .10 if x.get("annual_rent") else None
            tenure = x.get("tenure") or "UNKNOWN"
            vat = x.get("vat_status") or "UNKNOWN"
            togc = x.get("togc_status") or "UNKNOWN"
            legal = x.get("legal_pack_status") or "UNKNOWN"

            pills = "".join([
                pill("Tenure", tenure, "Freehold" in tenure),
                pill("VAT", vat, vat == "NOT APPLICABLE"),
                pill("TOGC", togc, togc in ["UNKNOWN","NO"]),
                pill("Pack", legal, legal == "AVAILABLE"),
            ])

            legal_link = ""
            if x.get("legal_pack_url"):
                legal_link = f'<a href="{html.escape(x["legal_pack_url"])}" target="_blank">Legal pack ↗</a>'

            card = (
                '<div class="card">'
                + image_html +
                '<div class="cb">'
                + f'<div class="source">{html.escape(x.get("auctioneer") or "Auction")} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'
                + f'<div class="addr">{html.escape(x.get("address") or "Address unavailable")}</div>'
                + '<div class="metrics">'
                + f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
                + f'<div class="metric"><span>Rent</span><b>{money(x.get("annual_rent"))}</b></div>'
                + f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
                + f'<div class="metric"><span>10% max</span><b>{money(ceiling)}</b></div>'
                + '</div>'
                + f'<div class="pills">{pills}</div>'
                + '<div class="actions">'
                + f'<a class="primary" href="{html.escape(x["source_url"])}" target="_blank">Original lot ↗</a>'
                + legal_link
                + '</div></div></div>'
            )
            cards.append(card)

        st.markdown('<div class="cards">' + "".join(cards) + '</div>', unsafe_allow_html=True)
