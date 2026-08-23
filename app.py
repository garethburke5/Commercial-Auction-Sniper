import html,time
import streamlit as st
import db
from registry import run_all
st.set_page_config(page_title="Auction Sniper",page_icon="🎯",layout="wide",initial_sidebar_state="collapsed")
db.init_db()
st.markdown("""<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}.block-container{max-width:1500px;padding:.25rem .3rem 1.5rem!important}.stApp{background:#0b1018;color:#f6f7fb}.hero{display:flex;align-items:center;justify-content:space-between;gap:8px;background:linear-gradient(135deg,#131b28,#0d131d);border:1px solid #29344a;border-radius:11px;padding:9px 10px;margin-bottom:4px}.brand{font-size:1.12rem;font-weight:950;line-height:1}.brand b{color:#f2c94c}.sub{font-size:.48rem;color:#95a3b7;margin-top:3px}.count{font-size:.46rem;color:#9ae6b4;border:1px solid #2d865b;border-radius:999px;padding:4px 6px}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin-top:5px}.card{background:#121925;border:1px solid #29344a;border-radius:9px;overflow:hidden}.card img{width:100%;height:90px;object-fit:cover;background:#172131}.noimg{height:60px;display:grid;place-items:center;background:#172131;color:#718095;font-size:.38rem}.cb{padding:5px}.src{font-size:.34rem;color:#f2c94c;font-weight:900;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.addr{font-size:.54rem;line-height:1.15;font-weight:850;min-height:2.3em;margin:2px 0 4px}.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.metric{background:#171f2d;border-radius:5px;padding:3px}.metric span{display:block;color:#8e9db1;font-size:.28rem}.metric b{font-size:.44rem}.meta{font-size:.30rem;color:#a9b6c8;margin-top:3px;line-height:1.3}.action{display:block;text-align:center;text-decoration:none;background:#f2c94c;color:#171208;border-radius:5px;padding:4px;margin-top:4px;font-size:.36rem;font-weight:900}div[data-testid="stExpander"]{border:1px solid #29344a;background:#111824;border-radius:9px;margin-bottom:4px}div[data-testid="stExpander"] summary{font-size:.68rem;font-weight:800}div[data-testid="stTabs"] button{font-size:.65rem}@media(max-width:800px){.block-container{padding:.15rem .2rem 1.2rem!important}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.card img{height:66px}.brand{font-size:1rem}}
</style>""",unsafe_allow_html=True)
if db.count_all()==0:
    with st.status("Scanning verified commercial sources…",expanded=False) as status:
        result=run_all(300000);status.update(label=f"Scan complete · {result['lots_seen']} commercial candidates",state="complete")
sources=db.get_sources();total=db.count_all();live=sum(1 for s in sources if s["status"]=="OK")
st.markdown(f'<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div><div class="sub">Verified UK commercial & mixed-use auction opportunities</div></div><div class="count">{total} lots · {live} sources</div></div>',unsafe_allow_html=True)
with st.expander("⚙️ Filters & live refresh",expanded=False):
    c1,c2=st.columns(2);max_price=c1.number_input("Maximum guide (£)",value=250000,step=5000);min_yield=c2.number_input("Minimum GIY (%)",value=10.0,step=.5);include_unknown=st.toggle("Include lots where rent/yield is unknown",value=True)
    if st.button("🔄 Rebuild current commercial snapshot",type="primary",use_container_width=True):
        with st.spinner("Scanning all sources…"):run_all(300000)
        st.toast("Current snapshot rebuilt");time.sleep(.25);st.rerun()
max_price=locals().get("max_price",250000);min_yield=locals().get("min_yield",10.0);include_unknown=locals().get("include_unknown",True)
lots_tab,sources_tab=st.tabs(["🎯 Lots","📡 Sources"])
with sources_tab:
    for s in db.get_sources():
        icon="✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️");st.write(f'{icon} **{s["source"]}** — {s["lots_seen"]} lots');st.caption(s["message"] or s["status"])
def money(v):return "Unknown" if v is None else f"£{v:,.0f}"
def pct(v):return "Unknown" if v is None else f"{v:.1f}%"
with lots_tab:
    lots=db.get_lots(max_price=max_price,min_yield=min_yield,include_unknown=include_unknown);st.caption(f"{len(lots)} matching commercial / mixed-use lots");cards=[]
    for x in lots:
        img=f'<img src="{html.escape(x["image_url"])}" alt="">' if x.get("image_url") else '<div class="noimg">NO IMAGE</div>';ceiling=x["annual_rent"]/.10 if x.get("annual_rent") else None;details=" · ".join(v for v in [x.get("tenure"),f'VAT {x["vat_status"]}' if x.get("vat_status") and x["vat_status"]!="UNKNOWN" else None,"Legal pack" if x.get("legal_pack_status")=="AVAILABLE" else None] if v)
        cards.append('<div class="card">'+img+'<div class="cb">'+f'<div class="src">{html.escape(x["auctioneer"])} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'+f'<div class="addr">{html.escape(x["address"])}</div>'+'<div class="metrics">'+f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'+f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("annual_rent"))}</b></div>'+f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'+f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div>'+'</div>'+f'<div class="meta">{html.escape(details)}</div>'+f'<a class="action" target="_blank" href="{html.escape(x["source_url"])}">Original lot ↗</a>'+'</div></div>')
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
