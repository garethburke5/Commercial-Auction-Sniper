import re
from datetime import date
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, legal_pack, image_from_soup

SOURCE = "Symonds & Sampson"
BASE = "https://auctions.symondsandsampson.co.uk"
EVENTS = BASE + "/events/property-auction/symonds-and-sampson-property-auctions?eventdate=upcoming"
DATE_RE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b", re.I)
MONTHS = {name.lower(): i for i, name in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"), 1)}
COMMERCIAL_EXTRA = ("public house","pub","commercial","mixed use","mixed-use","retail","shop","office","industrial","warehouse","workshop","business park","business premises","restaurant","hotel","leisure","investment property","commercial premises","commercial building","garages","garage block")
RESIDENTIAL_STRONG = ("detached house","semi-detached house","terraced house","bungalow","residential flat","bedroom flat","family home","residential property","bedroom house","house for sale")

def _fetch(url):
    try: return soup(url, use_browser=False)
    except Exception: return soup(url, use_browser=True)

def _parse_date(text):
    m=DATE_RE.search(norm(text))
    if not m or not MONTHS.get(m.group(2).lower()): return None
    try: return date(int(m.group(3)),MONTHS[m.group(2).lower()],int(m.group(1))).isoformat()
    except ValueError: return None

def _event_card_text(a):
    best=norm(a.get_text(" ",strip=True)); node=a
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None: break
        c=norm(node.get_text(" ",strip=True))
        if not c or len(c)>2200: break
        links=[x for x in node.find_all("a",href=True) if "/event/property-auction-" in urljoin(BASE,x.get("href") or "").lower()]
        if len(links)==1:
            best=c
            if DATE_RE.search(c): return c
        elif len(links)>1: break
    return best

def _event_links(s,today=None):
    today=today or date.today(); found={}
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if "/event/property-auction-" not in href.lower(): continue
        d=_parse_date(_event_card_text(a))
        if d and d>=today.isoformat(): found[href]=d
    return found

def _property_links(s,event_date):
    found={}
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if "/property/" not in href.lower() or href in found: continue
        text=norm(a.get_text(" ",strip=True))
        if text: found[href]=(text,event_date)
    return found

def _image(s,base):
    bad=("logo","icon","staff","office","map","floorplan","epc","avatar","placeholder","sprite"); candidates=[]
    for attrs in ({"property":"og:image"},{"name":"twitter:image"}):
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"): candidates.append(urljoin(base,tag.get("content")))
    for img in s.find_all("img"):
        alt=norm(img.get("alt") or "").lower()
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","src"):
            if img.get(attr): candidates.append(urljoin(base,img.get(attr)))
        for attr in ("srcset","data-srcset"):
            if img.get(attr):
                for part in img.get(attr).split(","):
                    u=part.strip().split(" ")[0]
                    if u: candidates.append(urljoin(base,u))
        if "property" in alt or "auction" in alt:
            for attr in ("src","data-src","data-lazy-src"):
                if img.get(attr): candidates.insert(0,urljoin(base,img.get(attr)))
    raw=str(s).replace("\\/","/")
    candidates += re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',raw,re.I)
    seen=set(); scored=[]
    for u in candidates:
        if not u or u in seen: continue
        seen.add(u); low=u.lower()
        if any(x in low for x in bad): continue
        score=(6 if "cdn.webdadi.net" in low else 0)+(4 if re.search(r"[0-9a-f]{8}-[0-9a-f-]{20,}",low,re.I) else 0)+(2 if any(x in low for x in ("property","images","photos","uploads","media")) else 0)+(2 if any(x in low for x in (".jpg",".jpeg",".webp")) else 0)
        scored.append((score,u))
    if scored:
        scored.sort(reverse=True)
        if scored[0][0]>0: return scored[0][1]
    g=image_from_soup(s,base)
    return g if g and not any(x in g.lower() for x in bad) else None

def _main_property_text(s):
    h=s.find("h1") or s.find("h2")
    if not h: return norm((s.find("main") or s).get_text(" ",strip=True))[:12000]
    pieces=[]
    for node in [h]+list(h.find_all_next(limit=160)):
        if getattr(node,"name",None) in {"h1","h2","h3","h4","p","li"}:
            v=norm(node.get_text(" ",strip=True))
            if v and v not in pieces: pieces.append(v)
        if len(" ".join(pieces))>12000: break
    return norm(" ".join(pieces))[:12000]

def _is_target(text):
    low=" "+norm(text).lower()+" "
    if is_commercial(text) or any(x in low for x in COMMERCIAL_EXTRA): return True
    if any(x in low for x in RESIDENTIAL_STRONG) or re.search(r"\b\d+\s+bedroom\s+house\b",low): return False
    return bool(re.search(r"\bdevelopment (?:site|land|plot)\b|\bbuilding plot\b",low))

def _address(s,url):
    h=s.find("h1")
    if h:
        v=re.sub(r"^#?\s*","",norm(h.get_text(" ",strip=True)))
        if len(v)>=6:return v
    t=s.find("title")
    if t:
        v=re.sub(r"\s*\|.*$","",norm(t.get_text(" ",strip=True)))
        if len(v)>=6:return v
    return url

def _area(text):
    sqft=sqm=acres=None
    m=re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b",text,re.I)
    if m:sqft=float(m.group(1).replace(",",""))
    m=re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\b",text,re.I)
    if m:sqm=float(m.group(1).replace(",",""))
    m=re.search(r"([\d.]+)\s*acres?\b",text,re.I)
    if m:acres=float(m.group(1))
    return sqft,sqm,acres

def _property_type(text):
    low=text.lower()
    for label,markers in (("Mixed Use",("mixed use","mixed-use")),("Public House",("public house","grade ii listed pub"," pub ")),("Retail",("retail","shop")),("Office",("office",)),("Industrial",("industrial","warehouse","workshop","business park")),("Development",("development site","development land","building plot","redevelopment potential")),("Garages",("garages","garage block")),("Commercial",("commercial",))):
        if any(x in low for x in markers): return label
    return "Commercial / Development"

def _detail(url,seed,event_date,fetcher=_fetch):
    s=fetcher(url); text=_main_property_text(s); combined=norm(seed+" "+text)
    if not _is_target(combined): return None
    guide=parse_guide(combined)
    if guide is None:
        m=re.search(r"Guide(?: Price)?\s*£+\s*([\d,]+(?:\.\d+)?)",combined,re.I)
        if m: guide=float(m.group(1).replace(",",""))
    # Symonds often phrases income as 'generating £22,500 rent pa'; parse_rent
    # does not always recognise that order, so explicitly recover disclosed income.
    rent=parse_rent(combined)
    if rent is None:
        patterns=(r"generat(?:e|es|ing)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:rent(?:al)?\s*)?(?:p\.?a\.?|per annum|pa)\b",r"(?:rent(?:al)?\s+income|income|producing)\D{0,20}£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)?")
        for p in patterns:
            m=re.search(p,combined,re.I)
            if m:
                rent=float(m.group(1).replace(",","")); break
    lp_url,lp_status=legal_pack(s,url)
    lot=Lot(source=SOURCE,url=url,address=_address(s,url),auction_date=event_date,image_url=_image(s,url),guide_price=guide,annual_rent=rent,tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_status=lp_status,legal_pack_url=lp_url,property_type=_property_type(combined),description=text)
    lot.area_sqft,lot.area_sqm,lot.site_area_acres=_area(combined)
    has_vacant=bool(re.search(r"\bvacant\b|vacant possession",combined,re.I)); has_income=bool(rent or re.search(r"\blet to\b|\btenant\b|\btenanted\b|\bproducing\s+£|\brental income\b|generat(?:e|es|ing)\s+£",combined,re.I))
    if has_vacant and has_income: lot.occupation="Part let / part vacant"
    elif has_vacant: lot.occupation="Vacant"
    elif has_income: lot.occupation="Tenanted"
    if re.search(r"redevelopment potential|development potential|development opportunity|subject to planning|planning permission|building plot",combined,re.I): lot.development_potential=True
    if re.search(r"in need of (?:some )?renovation|refurbish|refurbishment",combined,re.I): lot.refurbishment=True
    # Flats above a commercial unit are mixed-use evidence, not merely a possible conversion.
    if re.search(r"\b\d+\s+(?:vacant\s+)?flats?\b|flats? above|residential accommodation|living accommodation",combined,re.I): lot.residential_conversion=True
    if re.search(r"Grade\s+II\*?\s+Listed",combined,re.I): lot.listed_status="Grade II Listed"
    pm=re.search(r"parking for\s+(\d+)\s+(?:cars|vehicles)",combined,re.I)
    if pm: lot.parking=f"Parking for {pm.group(1)} vehicles"
    elif re.search(r"\bcar park\b|\bparking\b",combined,re.I): lot.parking="Car park / parking mentioned"
    return lot.finalise()

def collect():
    try:
        index=_fetch(EVENTS); events=_event_links(index)
        if not events:return SourceResult(SOURCE,"FAILED",[],"No future Symonds & Sampson property-auction events could be parsed.")
        candidates={}; published=set(); pending=set(); event_failures=0
        for event_url,event_date in events.items():
            try:
                links=_property_links(_fetch(event_url),event_date)
                if links: published.add(event_date); candidates.update(links)
                else: pending.add(event_date)
            except Exception as exc: event_failures+=1; print("SYMONDS_EVENT_FAIL",event_url,repr(exc))
        lots=[]; detail_failures=0
        for href,(seed,event_date) in candidates.items():
            try:
                lot=_detail(href,seed,event_date)
                if lot:lots.append(lot)
            except Exception as exc:detail_failures+=1;print("SYMONDS_DETAIL_FAIL",href,repr(exc))
        status="DEGRADED" if event_failures and lots else "FAILED" if event_failures else "LIVE" if lots or published else "CATALOGUE PENDING"
        msg=f"All-future Symonds & Sampson sweep: {len(events)} future event(s); {len(published)} published catalogue(s), {len(pending)} pending; {len(candidates)} property pages inspected; {len(lots)} commercial/mixed-use/development lots published; {detail_failures} detail failures; {event_failures} event failures."
        return SourceResult(SOURCE,status,lots,msg,discovered_count=len(lots),authoritative_snapshot=bool(status=="LIVE" and not detail_failures and published),scope_dates=tuple(sorted(published)))
    except Exception as exc:return SourceResult(SOURCE,"FAILED",[],f"Symonds & Sampson collection failed: {type(exc).__name__}: {exc}")
