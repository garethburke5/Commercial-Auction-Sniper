from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.51-CONTINUOUS-YIELD"','BUILD = "V6.52-SOURCES-FILTERS-IMAGES"',1)

# ---------- clearer filter panel ----------
old='''    with st.popover("Refine properties",use_container_width=True):
        st.caption("Narrow the board only when you want to — all qualifying lots remain visible by default.")
        apply_filters=st.toggle("Use price & yield limits",value=False)
        c1,c2=st.columns(2)
        max_price=c1.number_input("Maximum guide",min_value=0,value=250000,step=5000,format="%d",help="Maximum auction guide price in pounds")
        min_yield=c2.number_input("Minimum GIY",min_value=0.0,value=10.0,step=.5,format="%.1f",help="Minimum gross initial yield percentage")
        source_options=sorted({x["source"] for x in rows})
        chosen=st.multiselect("Auction house",source_options,default=[],placeholder="All auction houses")
        include_unknown=st.toggle("Include unknown rent / yield",value=True)
        if CACHE.exists() and st.button("Reset to verified snapshot",use_container_width=True):
            CACHE.unlink(missing_ok=True)
            st.rerun()
'''
new='''    with st.popover("Refine properties",use_container_width=True):
        st.markdown("**Property filters**")
        st.caption("Leave filters off to see the complete commercial auction board.")
        apply_filters=st.toggle("Apply price & yield filters",value=False)
        st.markdown('<div class="filterSection">PRICE & RETURN</div>',unsafe_allow_html=True)
        max_price=st.number_input("Maximum guide price (£)",min_value=0,value=250000,step=5000,format="%d",disabled=not apply_filters)
        min_yield=st.number_input("Minimum gross yield (%)",min_value=0.0,value=10.0,step=.5,format="%.1f",disabled=not apply_filters)
        st.markdown('<div class="filterSection">AUCTION HOUSE</div>',unsafe_allow_html=True)
        source_options=sorted({x["source"] for x in rows})
        chosen=st.multiselect("Sources",source_options,default=[],placeholder="All auction houses",label_visibility="collapsed")
        include_unknown=st.toggle("Keep properties with unknown rent / yield",value=True,disabled=not apply_filters)
        if CACHE.exists() and st.button("Reset cached listings",use_container_width=True,help="Restore the verified snapshot and rebuild live source data on the next update"):
            CACHE.unlink(missing_ok=True)
            st.rerun()
'''
if old not in s:
    raise SystemExit('refine popover anchor missing')
s=s.replace(old,new,1)

# ---------- source / image repair helpers ----------
anchor='\ndef refresh_market():\n'
if anchor not in s:
    raise SystemExit('refresh_market anchor missing')
insert=r'''

def _v652_money(text):
    m=re.search(r"£\s*([\d,]+(?:\.\d+)?)",text or "")
    return float(m.group(1).replace(",","")) if m else None


def _v652_data_image(image_url, referer=None):
    if not image_url: return None
    if str(image_url).startswith("data:image/"): return image_url
    try:
        h=dict(HEADERS)
        if referer: h["Referer"]=referer
        r=requests.get(image_url,headers=h,timeout=10)
        ct=(r.headers.get("content-type") or "").split(";")[0].lower()
        if r.ok and ct.startswith("image/") and 500 < len(r.content) < 1800000:
            return f"data:{ct};base64,"+base64.b64encode(r.content).decode("ascii")
    except Exception:
        pass
    return image_url


def _v652_hero(url, source=""):
    try:
        raw=fetch(url)
        soup=BeautifulSoup(raw,"lxml")
        candidates=[]
        for sel,attr in [
            ('meta[property="og:image"]','content'),('meta[name="twitter:image"]','content'),
            ('meta[property="twitter:image"]','content')]:
            t=soup.select_one(sel)
            if t and t.get(attr): candidates.append(urljoin(url,t.get(attr)))
        for img in soup.find_all("img"):
            for attr in ("data-src","data-lazy-src","data-original","src"):
                v=img.get(attr)
                if v: candidates.append(urljoin(url,v))
            ss=img.get("srcset") or img.get("data-srcset")
            if ss:
                for part in ss.split(","):
                    v=part.strip().split(" ")[0]
                    if v: candidates.append(urljoin(url,v))
        # Strettons embeds gallery URLs in JSON/script rather than ordinary img tags.
        for m in re.findall(r'https?:\\?/\\?/[^"\'<> ]+?(?:jpg|jpeg|png|webp)(?:\?[^"\'<> ]*)?',raw,re.I):
            candidates.append(m.replace('\\/','/'))
        clean=[]
        for c in candidates:
            lc=c.lower()
            if any(x in lc for x in ("logo","favicon","avatar","staff","agent","icon","sprite","placeholder","google")):
                continue
            if c not in clean: clean.append(c)
        src=(source or "").lower()
        if "strettons" in src:
            clean.sort(key=lambda u:(0 if ("amazonaws.com/i/api_sources" in u.lower() or "_web_" in u.lower()) else 1, len(u)))
        elif "acuitus" in src:
            clean.sort(key=lambda u:(0 if any(x in u.lower() for x in ("property","upload","media","image")) else 1, len(u)))
        return clean[0] if clean else None
    except Exception:
        return None


def _v652_exact_row(url, source, date=None, fallback_text=""):
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,"lxml"); text=norm(soup.get_text(" ",strip=True))
        h1=soup.find("h1")
        title=norm(h1.get_text(" ",strip=True)) if h1 else ""
        if source=="Pattinson":
            tt=norm(soup.title.get_text(" ",strip=True)) if soup.title else ""
            if " | Auction Property" in tt: title=tt.split(" | Auction Property",1)[0]
            if not re.search(r"Starting\s+bid|Auction Property|online auction",text,re.I): return None
        if source=="Clive Emson" and not re.search(r"LOT\s*\d+|AVAILABLE AT|GUIDE PRICE|auction",text,re.I): return None
        if not title: title=fallback_text[:180] or "Property"
        gm=re.search(r"(?:Starting\s+bid|Guide(?:\s+Price)?\*?|AVAILABLE AT)\s*£?\s*([\d,]+)",text,re.I)
        guide=float(gm.group(1).replace(",","")) if gm else _v652_money(fallback_text)
        rm=re.search(r"(?:Rent|producing|rental income|let at|at a rent of)\s*£?\s*([\d,]+)\s*(?:p\.?a\.?|per annum|pa)",text,re.I)
        rent=float(rm.group(1).replace(",","")) if rm else None
        tenure="Freehold" if re.search(r"\bFreehold\b",text,re.I) else "Leasehold" if re.search(r"\bLeasehold\b",text,re.I) else None
        lm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",text,re.I)
        lot=("Lot "+lm.group(1).upper()) if lm else ("Online auction" if source=="Pattinson" else "Lot TBC")
        img=_v652_hero(url,source)
        if img and source in ("Strettons","Acuitus"):
            img=_v652_data_image(img,url)
        return dict(source=source,lot=lot,date=date,address=title,guide=guide,rent=rent,tenure=tenure,vat="UNKNOWN",url=url,desc=text[:900],image=img)
    except Exception:
        return None


def _pattinson_current():
    base="https://www.pattinson.co.uk/commercial/property-search?searchType=CommercialSale"
    links=[]
    for page in range(1,7):
        try:
            u=base+(f"&page={page}" if page>1 else "")
            soup=BeautifulSoup(fetch(u),"lxml")
            before=len(links)
            for a in soup.find_all("a",href=True):
                href=urljoin(u,a["href"])
                if re.search(r"pattinson\.co\.uk/property/\d+",href) and href not in links:
                    node=a
                    for _ in range(4):
                        if node.parent: node=node.parent
                    card=norm(node.get_text(" ",strip=True))
                    if re.search(r"Starting\s+Bid|Current\s+Bid",card,re.I): links.append(href)
            if page>1 and len(links)==before: break
        except Exception:
            continue
    rows=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(_v652_exact_row,u,"Pattinson",None,"") for u in links[:120]]
        for f in as_completed(futs):
            r=f.result()
            if r: rows.append(r)
    return _clean_rows(rows)


def _clive_emson_current():
    url="https://www.cliveemson.co.uk/properties/commerical-property-auctions"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            node=a
            for _ in range(5):
                if node.parent: node=node.parent
            card=norm(node.get_text(" ",strip=True))
            if re.search(r"\bLOT\s*\d+\b",card,re.I) and "cliveemson.co.uk" in href and href not in links:
                if href.rstrip('/') not in (url.rstrip('/'),"https://www.cliveemson.co.uk/properties"):
                    links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Clive Emson",None,"") for u in links[:40]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _strettons_current():
    url="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if "/auction-commercial-property-for-sale/" in href and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Strettons","2026-09-10","") for u in links[:40]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _acuitus_current():
    url="https://www.acuitus.co.uk/find-a-property/?clear=y"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if re.search(r"acuitus\.co\.uk/property/\d+/?",href) and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Acuitus","2026-09-17","") for u in links[:20]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


@st.cache_data(ttl=21600,show_spinner=False)
def _v652_repair_priority_images(rows_tuple):
    rows=[dict(x) for x in rows_tuple]
    targets=[i for i,r in enumerate(rows) if r.get("source") in ("Strettons","Acuitus")]
    def one(i):
        r=rows[i]; img=r.get("image")
        if not img or not str(img).startswith("data:image/"):
            if not img: img=_v652_hero(r.get("url") or "",r.get("source") or "")
            if img: img=_v652_data_image(img,r.get("url"))
        return i,img
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(one,i) for i in targets]
        for f in as_completed(futs):
            i,img=f.result()
            if img: rows[i]["image"]=img
    return rows
'''
s=s.replace(anchor,insert+anchor,1)

# Add Clive Emson to refresh jobs.
old='''        "Pattinson": _pattinson_current,
        "Pugh / BTG Eddisons": _pugh_current_commercial,
'''
new='''        "Pattinson": _pattinson_current,
        "Clive Emson": _clive_emson_current,
        "Pugh / BTG Eddisons": _pugh_current_commercial,
'''
if old not in s:
    raise SystemExit('jobs Pattinson anchor missing')
s=s.replace(old,new,1)

# Repair Strettons/Acuitus delivery on ordinary app load, not only after Refresh.
old='''rows,health,updated=load_rows()
st.markdown('''
new='''rows,health,updated=load_rows()
try:
    rows=_v652_repair_priority_images(tuple(tuple(sorted(r.items())) for r in rows))
except Exception:
    pass
st.markdown('''
# tuple(dict items) needs conversion inside helper; swap helper implementation to accept encoded tuple.
# Simpler: don't inject this call; cached collector refresh is the authoritative route.
# Remove if present to avoid type mismatch.
if old in s:
    pass

# Source audit visibility.
s=s.replace('''    "Acuitus": 7,
    "Auction House Wales": 6,''','''    "Acuitus": 7,
    "Pattinson": 1,
    "Clive Emson": 1,
    "Auction House Wales": 6,''',1)

# Make Target Yield legible and popover calmer.
css='''
/* V6.52 refinement polish */
.yieldIntegratedLabel.left span{font-size:.60rem!important;font-weight:900!important;letter-spacing:.01em!important}
.yieldIntegratedLabel.left b{font-size:.70rem!important;font-weight:1000!important;margin-top:2px!important}
.filterSection{font-size:.60rem;font-weight:950;letter-spacing:.10em;color:#66778c;margin:12px 0 5px;border-top:1px solid #dce2e9;padding-top:10px}
div[data-testid="stPopoverBody"]{min-width:360px!important;padding:16px 18px!important}
div[data-testid="stPopoverBody"] label p{font-size:.78rem!important;line-height:1.25!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"]{height:auto!important;margin:0 0 8px!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"]>div{height:38px!important;border-radius:7px!important;box-shadow:none!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"] input{height:38px!important;border-radius:7px 0 0 7px!important}
@media(max-width:650px){div[data-testid="stPopoverBody"]{min-width:300px!important;padding:13px!important}.yieldIntegratedLabel.left span{font-size:.50rem!important}.yieldIntegratedLabel.left b{font-size:.58rem!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.52 source/filter/image repairs applied')
