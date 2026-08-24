
import re, html, sqlite3, time
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta

import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Auction Sniper V3", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

BUILD = "V3.0"
DB = Path("auction_sniper_v3.db")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniper/3.0)"}
TIMEOUT = 10
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")

COMMERCIAL_TERMS = [
    "commercial property","commercial unit","commercial building","commercial investment",
    "retail property","retail unit","retail investment","retail building","retail premises",
    "shop investment","shop and flat","shop with flat","ground floor shop","ground-floor shop",
    "office property","office building","office investment","office premises","office unit",
    "industrial unit","industrial property","industrial investment","warehouse","workshop","factory",
    "trade counter","business premises","business unit","restaurant","takeaway","public house",
    "pub investment","hotel","care home","day nursery","supermarket","pharmacy","showroom",
    "commercial depot","mixed use","mixed-use","commercial/residential","commercial and residential",
    "retail and residential","shopping centre","retail park","leisure investment",
    "advertising display site","ground rent investment"
]
RESIDENTIAL_ONLY = [
    "residential flat","one bedroom flat","two bedroom flat","three bedroom flat",
    "apartment","maisonette","bungalow","detached house","semi-detached",
    "terraced house","end terraced house","family home","dwelling house",
    "retirement flat","studio flat","residential investment","town house",
    "three-bedroom house","two-bedroom house","four-bedroom house"
]

# ---------- persistence ----------
def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS lots(
            source_id TEXT PRIMARY KEY,
            auctioneer TEXT, source_url TEXT, address TEXT, image_url TEXT,
            lot_number TEXT, auction_date TEXT, status TEXT,
            guide_price REAL, annual_rent REAL, gross_yield REAL,
            tenure TEXT, vat_status TEXT, legal_pack_status TEXT, legal_pack_url TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS source_status(
            source TEXT PRIMARY KEY, status TEXT, lots_seen INTEGER, message TEXT
        );
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """)

def replace_snapshot(results):
    with connect() as con:
        con.execute("DELETE FROM lots")
        con.execute("DELETE FROM source_status")
        for source, status, lots, message in results:
            con.execute("INSERT OR REPLACE INTO source_status VALUES (?,?,?,?)",
                        (source, status, len(lots), message))
            for x in lots:
                con.execute("""INSERT OR REPLACE INTO lots VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (x["source_id"],x["auctioneer"],x["source_url"],x["address"],x.get("image_url"),
                 x.get("lot_number"),x.get("auction_date"),x.get("status","Live"),
                 x.get("guide_price"),x.get("annual_rent"),x.get("gross_yield"),
                 x.get("tenure"),x.get("vat_status","UNKNOWN"),x.get("legal_pack_status","NOT FOUND"),
                 x.get("legal_pack_url"),x.get("description","")))

def get_lots():
    with connect() as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute("""
            SELECT * FROM lots
            ORDER BY CASE WHEN auction_date IS NULL THEN 1 ELSE 0 END,
                     auction_date ASC,
                     auctioneer ASC,
                     CASE WHEN lot_number IS NULL THEN 1 ELSE 0 END,
                     lot_number ASC
        """)]

def get_sources():
    with connect() as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute("SELECT * FROM source_status ORDER BY source")]

def count_all():
    with connect() as con:
        return int(con.execute("SELECT COUNT(*) FROM lots").fetchone()[0])

# ---------- shared parsing ----------
def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def norm(text):
    return re.sub(r"\s+"," ",text or "").strip()

def parse_money(v):
    m=MONEY_RE.search(str(v or ""))
    return float(m.group(1).replace(",","")) if m else None

def parse_guide(text):
    for p in [
        r"Guide Price(?:\s*[:*])?\s*(£[\d,]+(?:\.\d+)?)",
        r"Guide(?:\s*[:*])?\s*(£[\d,]+(?:\.\d+)?)",
        r"Available At\s*(£[\d,]+(?:\.\d+)?)",
    ]:
        m=re.search(p,text or "",re.I)
        if m:return parse_money(m.group(1))
    return None

def parse_rent(text):
    vals=[]
    patterns=[
        r"(?:Producing|Currently Producing|Current Gross Income|Current Rent Reserved|Rent(?:al)?(?: Income)?|Investment Let at|Let at|income of|generating|let producing)\s*:?\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b"
    ]
    for p in patterns:
        for m in re.finditer(p,text or "",re.I):
            v=parse_money(m.group(1))
            if v and 500 <= v <= 5_000_000: vals.append(v)
    return max(vals) if vals else None

def commercial(text):
    t=norm(text).lower()
    has_com=any(x in t for x in COMMERCIAL_TERMS)
    has_res=any(x in t for x in RESIDENTIAL_ONLY)
    return has_com and not (has_res and not any(x in t for x in [
        "mixed use","mixed-use","commercial/residential","commercial and residential",
        "shop and flat","shop with flat","retail and residential"
    ]))

def parse_tenure(text):
    t=(text or "").lower()
    if "virtual freehold" in t:return "Virtual Freehold"
    if "freehold" in t:return "Freehold"
    if "leasehold" in t:return "Leasehold"
    return None

def parse_vat(text):
    t=(text or "").lower()
    if any(x in t for x in ["vat is not applicable","vat-free","vat free","no vat"]):return "NOT APPLICABLE"
    if any(x in t for x in ["vat applicable","vat is applicable","elected to charge vat"]):return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def get_image(soup,base):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag=soup.find("meta",attrs=attrs)
        if tag and tag.get("content"):return urljoin(base,tag["content"])
    return None

def legal_pack(soup,base):
    for a in soup.find_all("a",href=True):
        txt=norm(a.get_text(" ",strip=True)).lower()
        href=a["href"]
        if "legal pack" in txt or "legal documents" in txt:
            return urljoin(base,href),"AVAILABLE"
    return None,"NOT FOUND"

def nearest_card(a,max_chars=2800):
    node=a;best=""
    for _ in range(9):
        node=getattr(node,"parent",None)
        if node is None:break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>len(best) and len(txt)<=max_chars:best=txt
        if len(txt)>max_chars:break
    return best

def detail_page(source,url,seed="",lot_number=None,auction_date=None,force_commercial=False):
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
    except Exception:
        return None
    h1=soup.find("h1")
    title=soup.find("title")
    address=norm(h1.get_text(" ",strip=True)) if h1 else (
        norm(title.get_text(" ",strip=True)).split("|")[0] if title else url
    )
    main=soup.find("main") or soup.find("article")
    text=norm(main.get_text(" ",strip=True)) if main else norm(soup.get_text(" ",strip=True))
    combined=address+" "+seed+" "+text[:12000]
    low=combined.lower()
    if "sold prior" in low or "withdrawn prior" in low:
        return None
    if not force_commercial and not commercial(combined):
        return None
    guide=parse_guide(text) or parse_guide(seed)
    rent=parse_rent(text) or parse_rent(seed)
    lp,lp_status=legal_pack(soup,url)
    return {
        "source_id":source+"|"+url,
        "auctioneer":source,"source_url":url,"address":address,
        "image_url":get_image(soup,url),"lot_number":lot_number,"auction_date":auction_date,
        "status":"Live","guide_price":guide,"annual_rent":rent,
        "gross_yield":round(rent/guide*100,2) if rent and guide else None,
        "tenure":parse_tenure(combined),"vat_status":parse_vat(combined),
        "legal_pack_status":lp_status,"legal_pack_url":lp,
        "description":seed[:800]
    }

def parallel_details(source,candidates,force=False,max_workers=8):
    lots=[]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures=[
            ex.submit(detail_page,source,u,seed,lotno,adate,force)
            for u,seed,lotno,adate in candidates
        ]
        for f in as_completed(futures):
            try:
                lot=f.result()
                if lot:lots.append(lot)
            except Exception:
                pass
    return lots

# ---------- Auction House London ----------
def collect_ahl():
    source="Auction House London"
    url="https://auctionhouselondon.co.uk/commercial-property-for-sale"
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
        seen=set();cands=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if "/lot/" not in href or href in seen:continue
            card=nearest_card(a)
            if not re.search(r"\bLOT\s+\d+[A-Z]?\b",card,re.I):continue
            if not commercial(card):continue
            m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
            seen.add(href)
            cands.append((href,card,f"Lot {m.group(1)}" if m else None,"2026-09-02"))
        lots=parallel_details(source,cands,True)
        return source,"LIVE",lots,f"Commercial-only page · {len(cands)} exact lot links checked"
    except Exception as e:return source,"FAILED",[],str(e)

# ---------- Savills ----------
def collect_savills():
    source="Savills Auctions"
    base="https://auctions.savills.co.uk"
    current=base+"/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"
    try:
        soup=BeautifulSoup(fetch(current),"lxml")
        lots=[];seen=set()
        anchors=soup.find_all("a",href=True)
        for a in anchors:
            href=urljoin(base,a["href"]).split("?",1)[0].rstrip("/")
            if not re.match(r"^https://auctions\.savills\.co\.uk/auctions/2-september-2026-241/[^/]+$",href,re.I):continue
            if href in seen:continue
            address=norm(a.get_text(" ",strip=True))
            if not address or address.lower() in {"full details","previous lot","next lot","return to catalogue"}:continue

            before=[]
            for s in a.find_all_previous(string=True,limit=45):
                t=norm(str(s))
                if t:before.append(t)
            before.reverse()
            idx=None;lotno=None
            for i in range(len(before)-1,-1,-1):
                m=re.fullmatch(r"Lot\s+(\d+[A-Z]?)",before[i],re.I)
                if m:idx=i;lotno="Lot "+m.group(1);break
            if idx is None:continue
            pre=" ".join(before[idx:])
            if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
                seen.add(href);continue

            after=[]
            for s in a.find_all_next(string=True,limit=60):
                t=norm(str(s))
                if not t:continue
                if after and re.fullmatch(r"Lot\s+\d+[A-Z]?",t,re.I):break
                after.append(t)
            post=" ".join(after)
            guide=parse_guide(pre)
            rent=parse_rent(post)
            lots.append({
                "source_id":source+"|"+href,"auctioneer":source,"source_url":href,
                "address":address,"image_url":None,"lot_number":lotno,"auction_date":"2026-09-02",
                "status":"Live","guide_price":guide,"annual_rent":rent,
                "gross_yield":round(rent/guide*100,2) if rent and guide else None,
                "tenure":parse_tenure(post),"vat_status":parse_vat(post),
                "legal_pack_status":"LOGIN REQUIRED","legal_pack_url":href,
                "description":post[:800]
            })
            seen.add(href)

        known={"Lot 73","Lot 79","Lot 80","Lot 86","Lot 88","Lot 89","Lot 90","Lot 93","Lot 95","Lot 96","Lot 98"}
        found={x["lot_number"] for x in lots}
        validation=len(known & found)
        status="LIVE" if validation>=7 else "FAILED"
        return source,status,lots,f"Savills commercial filter · {len(lots)} lots · validation {validation}/{len(known)}"
    except Exception as e:return source,"FAILED",[],str(e)

# ---------- Bond Wolfe ----------
def collect_bond_wolfe():
    source="Bond Wolfe";base="https://www.bondwolfe.com";url=base+"/auctions/properties/"
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
        seen=set();cands=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(base,a["href"])
            if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I):continue
            href=href.rstrip("/")+"/"
            if href in seen:continue
            card=nearest_card(a)
            seen.add(href)
            cands.append((href,card,None,"2026-09-10"))
        lots=parallel_details(source,cands,False)
        return source,"LIVE",lots,f"10 Sep current catalogue · {len(cands)} exact property links checked"
    except Exception as e:return source,"FAILED",[],str(e)

# ---------- Pugh / BTG ----------
def collect_pugh():
    source="Pugh / BTG Eddisons";base="https://www.pugh-auctions.com"
    try:
        seen=set();cands=[]
        # Current/forthcoming live-stream auction pages are around this result window;
        # scan enough pages to cover 27 Aug but reject every other auction date.
        for page in range(1,16):
            url=base+f"/property-search?include-sold=off&order-results=date-desc&page={page}&style=list"
            try:soup=BeautifulSoup(fetch(url),"lxml")
            except Exception:continue
            for a in soup.find_all("a",href=True):
                href=urljoin(base,a["href"])
                if "/property/" not in href or href in seen:continue
                card=nearest_card(a,3200)
                if "27th August 2026" not in card and "27/08/2026" not in card:continue
                if not commercial(card):continue
                m=re.search(r"^\s*(\d+[A-Z]?)\s*\|",card)
                if not m:m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                seen.add(href)
                cands.append((href,card,f"Lot {m.group(1)}" if m else None,"2026-08-27"))
        lots=parallel_details(source,cands,False)
        return source,"LIVE",lots,f"27 Aug current auction only · {len(cands)} commercial/mixed candidates"
    except Exception as e:return source,"FAILED",[],str(e)

# ---------- Strettons ----------
def collect_strettons():
    source="Strettons";base="https://www.strettons.co.uk";url=base+"/auction-commercial-property/for-sale/"
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
        seen=set();cands=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(base,a["href"])
            if "/auction-commercial-property-for-sale/" not in href or href in seen:continue
            card=nearest_card(a,3200)
            if "10 Sep 26" not in card and "Sep 10 2026" not in card:continue
            m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
            seen.add(href)
            cands.append((href,card,f"Lot {m.group(1)}" if m else None,"2026-09-10"))
        lots=parallel_details(source,cands,True)
        return source,"LIVE",lots,f"Dedicated commercial feed · {len(cands)} exact links checked"
    except Exception as e:return source,"FAILED",[],str(e)

# ---------- source states we intentionally do NOT scrape as live current stock ----------
def collect_allsop():
    return "Allsop Commercial","CATALOGUE PENDING",[],"Next commercial auction 7 Oct 2026; current page contains older/still-available lots, so V3 does not import them as October lots."

def collect_acuitus():
    source="Acuitus";url="https://www.acuitus.co.uk/find-a-property/?which=sales"
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
        txt=norm(soup.get_text(" ",strip=True))
        # Acuitus is inherently commercial; include early lots if exact property anchors are visible.
        cands=[];seen=set()
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            card=nearest_card(a,3500)
            if href in seen or not re.search(r"£[\d,]+",card):continue
            if "17 September" not in card and "September 2026" not in card:continue
            seen.add(href);cands.append((href,card,None,"2026-09-17"))
        if not cands:
            return source,"CATALOGUE PENDING",[],"17 Sep auction; full catalogue due 28 Aug. No parsable current early lots on this response."
        lots=parallel_details(source,cands,True)
        return source,"LIVE",lots,f"17 Sep early catalogue · {len(lots)} lots"
    except Exception as e:return source,"FAILED",[],str(e)

COLLECTORS=[collect_ahl,collect_savills,collect_bond_wolfe,collect_pugh,collect_strettons,collect_allsop,collect_acuitus]

def scan_all():
    results=[]
    with ThreadPoolExecutor(max_workers=len(COLLECTORS)) as ex:
        futures={ex.submit(fn):fn.__name__ for fn in COLLECTORS}
        for f in as_completed(futures):
            try:results.append(f.result())
            except Exception as e:results.append((futures[f],"FAILED",[],str(e)))
    replace_snapshot(results)
    return results

# ---------- UI ----------
init_db()

st.markdown("""
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1500px;padding:.25rem .28rem 1.3rem!important}
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

# Never block page load for minutes. Existing snapshot opens immediately.
if count_all()==0:
    st.warning("No V3 snapshot yet. Tap 'Scan current auctions' below to populate the board.")

srcs=get_sources()
st.markdown(
    '<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div>'
    '<div class="sub">Current UK commercial & mixed-use auction opportunities · '+BUILD+'</div></div>'
    f'<div class="badge">{count_all()} lots · {sum(1 for s in srcs if s["status"]=="LIVE")} live sources</div></div>',
    unsafe_allow_html=True
)

with st.expander("🔄 Data & source refresh",expanded=(count_all()==0)):
    if st.button("Scan current auctions",type="primary",use_container_width=True):
        with st.spinner("Scanning verified current sources in parallel…"):
            scan_all()
        st.rerun()

with st.expander("⚙️ Optional filters",expanded=False):
    apply_filters=st.toggle("Apply price / yield filters",value=False)
    c1,c2=st.columns(2)
    max_price=c1.number_input("Maximum guide (£)",min_value=0,value=250000,step=5000)
    min_yield=c2.number_input("Minimum GIY (%)",min_value=0.0,value=10.0,step=.5)
    auctioneers=sorted({x["auctioneer"] for x in get_lots()})
    chosen=st.multiselect("Auction houses",auctioneers,default=[])
    include_unknown=st.toggle("Keep properties with unknown rent/yield",value=True)

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])

with sources_tab:
    for s in get_sources():
        icon="✅" if s["status"]=="LIVE" else ("⏳" if "PENDING" in s["status"] else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(s["source"])}</b> — {html.escape(s["status"])} — {s["lots_seen"]} lots<br><small>{html.escape(s["message"] or "")}</small></div>',unsafe_allow_html=True)

def money(v):return "Unknown" if v is None else f"£{v:,.0f}"
def pct(v):return "Unknown" if v is None else f"{v:.1f}%"

with lots_tab:
    lots=get_lots()

    # DEFAULT = ALL CURRENT COMMERCIAL/MIXED-USE PROPERTIES.
    if chosen:
        lots=[x for x in lots if x["auctioneer"] in chosen]
    if apply_filters:
        filtered=[]
        for x in lots:
            if x.get("guide_price") is not None and x["guide_price"]>max_price:continue
            if x.get("gross_yield") is None:
                if not include_unknown:continue
            elif x["gross_yield"]<min_yield:continue
            filtered.append(x)
        lots=filtered

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL current properties"))

    cards=[]
    for x in lots:
        img=f'<img src="{html.escape(x["image_url"])}">' if x.get("image_url") else '<div class="noimg">NO IMAGE</div>'
        ceiling=x["annual_rent"]/.10 if x.get("annual_rent") else None
        meta=" · ".join(v for v in [
            x.get("auction_date"),x.get("tenure"),
            ("VAT "+x["vat_status"]) if x.get("vat_status")!="UNKNOWN" else None,
            "Legal pack" if x.get("legal_pack_status")=="AVAILABLE" else None
        ] if v)
        cards.append(
            '<div class="card">'+img+'<div class="cb">'
            +f'<div class="src">{html.escape(x["auctioneer"])} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'
            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("annual_rent"))}</b></div>'
            +f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
            +f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div></div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +f'<a class="action" target="_blank" href="{html.escape(x["source_url"])}">Original lot ↗</a>'
            +'</div></div>'
        )
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
