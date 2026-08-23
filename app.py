import html,os,sqlite3,time
import streamlit as st
import db
from registry import run_all
st.set_page_config(page_title="Commercial Auction Sniper",page_icon="🎯",layout="wide",initial_sidebar_state="collapsed")
db.init_db()
try:
    if "SAVILLS_EMAIL" in st.secrets:os.environ["SAVILLS_EMAIL"]=str(st.secrets["SAVILLS_EMAIL"])
    if "SAVILLS_PASSWORD" in st.secrets:os.environ["SAVILLS_PASSWORD"]=str(st.secrets["SAVILLS_PASSWORD"])
except Exception:pass
def reset_once():
    con=sqlite3.connect(getattr(db,"DB","auction_sniper.db"))
    con.execute("CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT)")
    k="verified_sources_reset_v7"
    if con.execute("SELECT 1 FROM app_meta WHERE key=?",(k,)).fetchone():con.close();return
    con.execute("DELETE FROM lots")
    try:con.execute("DELETE FROM scans")
    except:pass
    con.execute("INSERT INTO app_meta VALUES (?,?)",(k,"done"));con.commit();con.close()
reset_once()
st.markdown("""<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{padding:.2rem .28rem 1.2rem;max-width:1500px}
.stApp{background:#0b1018;color:#f6f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;background:#121925;border:1px solid #29344a;border-radius:11px;padding:9px 10px;margin-bottom:4px}
.brand{font-size:1.12rem;font-weight:950}.brand b{color:#f2c94c}.sub{font-size:.48rem;color:#96a4b8;margin-top:2px}
.badge{font-size:.43rem;border:1px solid #31875c;color:#9ae6b4;border-radius:999px;padding:4px 5px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
.card{background:#121925;border:1px solid #29344a;border-radius:9px;overflow:hidden}
.card img{width:100%;height:92px;object-fit:cover}.cb{padding:5px}
.src{font-size:.35rem;color:#f2c94c;font-weight:900}.addr{font-size:.55rem;font-weight:850;line-height:1.12;min-height:2.2em;margin:2px 0 4px}
.m{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.m div{background:#171f2d;border-radius:5px;padding:3px}
.m span{display:block;font-size:.29rem;color:#91a0b4}.m b{font-size:.45rem}
.actions{margin-top:4px}.actions a{display:block;text-align:center;background:#f2c94c;color:#171208;padding:4px;border-radius:5px;text-decoration:none;font-size:.37rem;font-weight:900}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr);gap:4px}.card img{height:68px}.brand{font-size:1rem}}
</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div><div class="sub">Verified commercial & mixed-use auction feeds</div></div><div class="badge">COMMERCIAL ONLY</div></div>',unsafe_allow_html=True)
if not db.get_lots(10_000_000,0):
    with st.status("Scanning verified commercial sources…",expanded=False):
        run_all(300000)
with st.expander("⚙️ Filters / refresh",expanded=False):
    c1,c2=st.columns(2);maxp=c1.number_input("Max guide",value=250000,step=5000);miny=c2.number_input("Min GIY",value=10.0,step=.5)
    unknown=st.toggle("Include unknown yield",False)
    if st.button("Refresh",use_container_width=True,type="primary"):run_all(300000);st.rerun()
maxp=locals().get("maxp",250000);miny=locals().get("miny",10.0);unknown=locals().get("unknown",False)
board,sources=st.tabs(["🎯 Lots","📡 Sources"])
with sources:
    for s in db.get_scan_status():
        icon="✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️")
        st.write(f'{icon} **{s["source"]}** — {s["lots_seen"]} lots');st.caption(s["message"] or s["status"])
def money(v):return "—" if v is None else f"£{v:,.0f}"
def pct(v):return "—" if v is None else f"{v:.1f}%"
with board:
    lots=db.get_lots(maxp,miny)
    if not unknown:lots=[x for x in lots if x.get("guide_price") is not None and x.get("gross_yield") is not None]
    st.caption(f"{len(lots)} qualifying commercial / mixed-use lots")
    cards=[]
    for x in lots:
        img=f'<img src="{html.escape(x["image_url"])}">' if x.get("image_url") else ""
        ceil=x["annual_rent"]/.1 if x.get("annual_rent") else None
        cards.append('<div class="card">'+img+'<div class="cb">'
        +f'<div class="src">{html.escape(x["auctioneer"])} · {html.escape(x.get("lot_number") or "")}</div>'
        +f'<div class="addr">{html.escape(x["address"])}</div><div class="m">'
        +f'<div><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
        +f'<div><span>Rent</span><b>{money(x.get("annual_rent"))}</b></div>'
        +f'<div><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
        +f'<div><span>10% max</span><b>{money(ceil)}</b></div></div>'
        +f'<div class="actions"><a target="_blank" href="{html.escape(x["source_url"])}">Original lot ↗</a></div>'
        +'</div></div>')
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
