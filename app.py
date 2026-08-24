
import json, html
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Auction Sniper",page_icon="🎯",layout="wide",initial_sidebar_state="collapsed")

DATA=Path("data/properties.json")

def load():
    if not DATA.exists():
        return {"generated_at":None,"properties":[],"source_health":[]}
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at":None,"properties":[],"source_health":[]}

snap=load()
props=snap["properties"]
health=snap["source_health"]

st.markdown("""
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1500px;padding:.25rem .28rem 1.2rem!important}
.stApp{background:#090e16;color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#131b28,#0d131d);border:1px solid #29354b;border-radius:12px;padding:10px;margin-bottom:5px}
.brand{font-size:1.08rem;font-weight:950}.brand b{color:#f2c94c}.sub{font-size:.46rem;color:#94a3b8;margin-top:3px}
.badge{font-size:.42rem;border:1px solid #2e8b5c;color:#9ae6b4;border-radius:999px;padding:4px 6px;white-space:nowrap}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}
.card{background:#121925;border:1px solid #29354b;border-radius:9px;overflow:hidden}
.card img{width:100%;height:92px;object-fit:cover}.noimg{height:58px;display:grid;place-items:center;background:#172131;color:#718095;font-size:.35rem}
.cb{padding:5px}.src{font-size:.32rem;color:#f2c94c;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.addr{font-size:.53rem;font-weight:850;line-height:1.14;min-height:2.3em;margin:2px 0 4px}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.metric{background:#171f2d;border-radius:5px;padding:3px}
.metric span{display:block;color:#8f9db0;font-size:.27rem}.metric b{font-size:.42rem}
.meta{font-size:.28rem;color:#a8b5c7;margin-top:3px;line-height:1.25}.action{display:block;text-align:center;text-decoration:none;background:#f2c94c;color:#171208;border-radius:5px;padding:4px;margin-top:4px;font-size:.35rem;font-weight:900}
.statusrow{padding:7px 8px;border:1px solid #29354b;background:#111824;border-radius:8px;margin-bottom:5px}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.card img{height:67px}.brand{font-size:.98rem}}
</style>
""",unsafe_allow_html=True)

live=sum(1 for s in health if s["status"]=="LIVE")
st.markdown(
    '<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div>'
    '<div class="sub">Verified UK commercial & mixed-use auctions</div></div>'
    f'<div class="badge">{len(props)} lots · {live} live sources</div></div>',
    unsafe_allow_html=True
)

with st.expander("⚙️ Optional filters",expanded=False):
    apply_filters=st.toggle("Apply price / yield filters",value=False)
    c1,c2=st.columns(2)
    max_price=c1.number_input("Maximum guide (£)",min_value=0,value=250000,step=5000)
    min_yield=c2.number_input("Minimum GIY (%)",min_value=0.0,value=10.0,step=.5)
    source_options=sorted({x["source"] for x in props})
    chosen=st.multiselect("Auction houses",source_options,default=[])
    include_unknown=st.toggle("Keep properties with unknown rent/yield",value=True)

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])

with sources_tab:
    if snap["generated_at"]:
        st.caption("Snapshot: "+snap["generated_at"])
    for s in health:
        icon="✅" if s["status"]=="LIVE" else ("⏳" if "PENDING" in s["status"] else "⚠️")
        st.markdown(
            f'<div class="statusrow">{icon} <b>{html.escape(s["source"])}</b> — '
            f'{html.escape(s["status"])} — {s["lots_seen"]} lots<br>'
            f'<small>{html.escape(s["message"] or "")}</small></div>',
            unsafe_allow_html=True
        )

def money(v): return "Unknown" if v is None else f"£{v:,.0f}"
def pct(v): return "Unknown" if v is None else f"{v:.1f}%"

with lots_tab:
    lots=list(props)

    if chosen:
        lots=[x for x in lots if x["source"] in chosen]

    # DEFAULT = ALL current commercial/mixed-use properties.
    if apply_filters:
        out=[]
        for x in lots:
            gp=x.get("guide_price")
            gy=x.get("gross_yield")
            if gp is not None and gp>max_price:
                continue
            if gy is None:
                if not include_unknown:
                    continue
            elif gy<min_yield:
                continue
            out.append(x)
        lots=out

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL current properties"))

    cards=[]
    for x in lots:
        img=f'<img src="{html.escape(x["image_url"])}">' if x.get("image_url") else '<div class="noimg">NO IMAGE</div>'
        ceiling=x["annual_rent"]/.10 if x.get("annual_rent") else None
        meta=" · ".join(v for v in [
            x.get("auction_date"),x.get("tenure"),
            ("VAT "+x["vat_status"]) if x.get("vat_status") and x["vat_status"]!="UNKNOWN" else None,
            "Legal pack" if x.get("legal_pack_status")=="AVAILABLE" else None,
            "STALE" if x.get("status")=="STALE SOURCE" else None
        ] if v)
        cards.append(
            '<div class="card">'+img+'<div class="cb">'
            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'
            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("annual_rent"))}</b></div>'
            +f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
            +f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div></div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +f'<a class="action" target="_blank" href="{html.escape(x["url"])}">Original lot ↗</a>'
            +'</div></div>'
        )
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
