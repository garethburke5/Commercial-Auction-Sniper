import html,time,os
import streamlit as st
import db
from registry import run_all

st.set_page_config(page_title="Auction Sniper",page_icon="🎯",layout="wide",initial_sidebar_state="collapsed")
db.init_db()

# Credentials live in Streamlit Secrets, never GitHub.
try:
    if "SAVILLS_EMAIL" in st.secrets:
        os.environ["SAVILLS_EMAIL"] = str(st.secrets["SAVILLS_EMAIL"])
    if "SAVILLS_PASSWORD" in st.secrets:
        os.environ["SAVILLS_PASSWORD"] = str(st.secrets["SAVILLS_PASSWORD"])
except Exception:
    pass

st.markdown("""
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1500px;padding:.2rem .25rem 1.2rem!important}
.stApp{background:#0b1018;color:#f6f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:8px;background:linear-gradient(135deg,#131b28,#0d131d);border:1px solid #29344a;border-radius:11px;padding:9px 10px;margin-bottom:4px}
.brand{font-size:1.08rem;font-weight:950;line-height:1}.brand b{color:#f2c94c}.sub{font-size:.47rem;color:#95a3b7;margin-top:3px}.count{font-size:.43rem;border:1px solid #2e8b5c;color:#9ae6b4;border-radius:999px;padding:4px 5px;white-space:nowrap}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin-top:4px}.card{background:#121925;border:1px solid #29344a;border-radius:9px;overflow:hidden}.card img{width:100%;height:88px;object-fit:cover;background:#172131}.noimg{height:58px;display:grid;place-items:center;background:#172131;color:#718095;font-size:.36rem}.cb{padding:5px}.src{font-size:.33rem;color:#f2c94c;font-weight:900;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.addr{font-size:.53rem;font-weight:850;line-height:1.14;min-height:2.3em;margin:2px 0 4px}.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.metric{background:#171f2d;border-radius:5px;padding:3px}.metric span{display:block;color:#8f9db0;font-size:.27rem}.metric b{font-size:.43rem}.meta{font-size:.29rem;color:#a8b5c7;margin-top:3px;line-height:1.25}.action{display:block;text-align:center;text-decoration:none;background:#f2c94c;color:#171208;border-radius:5px;padding:4px;margin-top:4px;font-size:.36rem;font-weight:900}
div[data-testid="stExpander"]{border:1px solid #29344a;background:#111824;border-radius:9px;margin-bottom:4px}div[data-testid="stExpander"] summary{font-size:.67rem;font-weight:800}div[data-testid="stTabs"] button{font-size:.64rem}
@media(max-width:800px){.block-container{padding:.15rem .2rem 1rem!important}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.card img{height:66px}.brand{font-size:.98rem}}
</style>
""",unsafe_allow_html=True)

def rebuild():
    with st.spinner("Scanning verified commercial sources…"):
        return run_all(300000)

if db.count_all()==0:
    with st.status("Building current commercial snapshot…",expanded=False) as status:
        result=run_all(300000)
        status.update(label=f"Scan complete · {result['lots_seen']} commercial candidates",state="complete")

sources=db.get_sources(); total=db.count_all(); healthy=sum(1 for s in sources if s["status"]=="OK")
st.markdown(f'''<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div><div class="sub">Verified UK commercial & mixed-use auction opportunities</div></div><div class="count">{total} lots · {healthy} sources</div></div>''',unsafe_allow_html=True)

with st.expander("⚙️ Filters & refresh",expanded=False):
    c1,c2=st.columns(2)
    max_price=c1.number_input("Maximum guide (£)",value=250000,step=5000)
    min_yield=c2.number_input("Minimum GIY (%)",value=10.0,step=.5)
    include_unknown=st.toggle("Include unknown rent/yield",value=True)
    if st.button("🔄 Rebuild current snapshot",type="primary",use_container_width=True):
        rebuild();st.toast("Current commercial snapshot rebuilt");time.sleep(.2);st.rerun()

max_price=locals().get("max_price",250000);min_yield=locals().get("min_yield",10.0);include_unknown=locals().get("include_unknown",True)
lots_tab,sources_tab=st.tabs(["🎯 Lots","📡 Sources"])
with sources_tab:
    rows=db.get_sources()
    if not rows: st.info("No source scan has completed yet.")
    for s in rows:
        icon="✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️")
        st.write(f'{icon} **{s["source"]}** — {s["lots_seen"]} lots')
        st.caption(s["message"] or s["status"])

def money(v): return "Unknown" if v is None else f"£{v:,.0f}"
def pct(v): return "Unknown" if v is None else f"{v:.1f}%"

with lots_tab:
    lots=db.get_lots(max_price,min_yield,include_unknown)
    st.caption(f"{len(lots)} matching commercial / mixed-use lots")
    cards=[]
    for x in lots:
        image=f'<img src="{html.escape(x["image_url"])}" alt="">' if x.get("image_url") else '<div class="noimg">NO IMAGE</div>'
        ceiling=x["annual_rent"]/.10 if x.get("annual_rent") else None
        details=" · ".join(v for v in [x.get("tenure"),f'VAT {x["vat_status"]}' if x.get("vat_status")!="UNKNOWN" else None,"Legal pack" if x.get("legal_pack_status")=="AVAILABLE" else None] if v)
        cards.append('<div class="card">'+image+'<div class="cb">'+f'<div class="src">{html.escape(x["auctioneer"])} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'+f'<div class="addr">{html.escape(x["address"])}</div>'+'<div class="metrics">'+f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'+f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("annual_rent"))}</b></div>'+f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'+f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div>'+'</div>'+f'<div class="meta">{html.escape(details)}</div>'+f'<a class="action" target="_blank" href="{html.escape(x["source_url"])}">Original lot ↗</a>'+'</div></div>')
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
