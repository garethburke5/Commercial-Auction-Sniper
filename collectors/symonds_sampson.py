import re
from datetime import date
from io import BytesIO
from urllib.parse import urljoin, urlparse

from pypdf import PdfReader

from .browser import get_bytes
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, legal_pack, image_from_soup

SOURCE = "Symonds & Sampson"
BASE = "https://auctions.symondsandsampson.co.uk"
AUCTION_HOST = "auctions.symondsandsampson.co.uk"
EVENT_PATH = BASE + "/events/property-auction/symonds-and-sampson-property-auctions"
EVENT_INDEXES = (EVENT_PATH, EVENT_PATH + "?eventdate=upcoming")
DATE_RE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b", re.I)
MONTHS = {name.lower(): i for i, name in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"), 1)}
RESIDENTIAL_STRONG = ("detached house","semi-detached house","terraced house","bungalow","residential flat","bedroom flat","family home","residential property","bedroom house","house for sale")
RESIDENTIAL_COMPONENT = ("flat above","flats above","existing flat","existing flats","vacant flat","vacant flats","residential accommodation","living accommodation","apartment above")
CHROME_MARKERS = ("Office Details", "Arrange a viewing", "Make An Offer", "Request a Viewing", "Broadband & Mobile Coverage", "Property Information Questionnaire", "Important Information", "Contact the Agent", "Contact Us")
COMMERCIAL_SIGNAL = re.compile(
    r"\b(?:mixed[- ]use|commercial\s+(?:property|unit|premises|building|investment|accommodation)|"
    r"ground[- ]floor\s+(?:shop|retail|commercial)|shop\b|retail\s+(?:unit|property|investment|premises)|"
    r"office\s+(?:building|unit|investment|premises|accommodation)|industrial\s+(?:unit|property|building)|"
    r"warehouse|workshop|business\s+premises|business\s+park|public\s+house|pub\b|"
    r"restaurant\s+(?:premises|unit|investment)|hotel\b|leisure\s+(?:property|premises|investment)|"
    r"garage\s+block|garages\b)\b", re.I)
DEVELOPMENT_SIGNAL = re.compile(r"\bdevelopment\s+(?:site|land|plot)\b|\bbuilding\s+plot\b", re.I)


def _fetch(url):
    try:return soup(url,use_browser=False)
    except Exception:return soup(url,use_browser=True)


def _parse_date(text):
    m=DATE_RE.search(norm(text))
    if not m or not MONTHS.get(m.group(2).lower()):return None
    try:return date(int(m.group(3)),MONTHS[m.group(2).lower()],int(m.group(1))).isoformat()
    except ValueError:return None


def _event_card_text(a):
    best=norm(a.get_text(" ",strip=True));node=a
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        c=norm(node.get_text(" ",strip=True))
        if not c or len(c)>2200:break
        links=[x for x in node.find_all("a",href=True) if "/event/property-auction-" in urljoin(BASE,x.get("href") or "").lower()]
        if len(links)==1:
            best=c
            if DATE_RE.search(c):return c
        elif len(links)>1:break
    return best


def _event_links(s,today=None):
    """Discover event URLs even when the index card no longer contains its date.

    The Symonds index markup changes independently of the exact event pages.  A
    URL is therefore discovery evidence; a card date is only an optimisation.
    Exact event pages supply the authoritative fallback date in _discover_events.
    """
    found={}
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if "/event/property-auction-" not in href.lower():continue
        d=_parse_date(_event_card_text(a))
        if href not in found or (not found[href] and d):found[href]=d
    return found


def _event_page_date(s):
    """Read the exact event date from the authoritative event page."""
    root=s.find("main") or s
    text=norm(root.get_text(" ",strip=True))
    # Prefer the labelled event-date block so dates from property cards/footer
    # cannot accidentally become the auction date.
    m=re.search(r"Event\s+Date\s*&\s*Time\s*:?[\s|\-]*(.{0,180})",text,re.I)
    if m:
        d=_parse_date(m.group(1))
        if d:return d
    return _parse_date(text[:5000])


def _discover_events(fetcher=_fetch,today=None):
    today=today or date.today();discovered={};failures=[]
    for url in EVENT_INDEXES:
        try:
            for href,d in _event_links(fetcher(url),today=today).items():
                if href not in discovered or (not discovered[href] and d):discovered[href]=d
        except Exception as exc:failures.append((url,exc))
    found={}
    for href,d in discovered.items():
        if not d:
            try:d=_event_page_date(fetcher(href))
            except Exception as exc:
                failures.append((href,exc));continue
        if d and d>=today.isoformat():found[href]=d
    return found,failures


def _is_auction_property_url(href):
    parsed=urlparse(href or "");host=(parsed.hostname or "").lower();path=(parsed.path or "").lower().rstrip("/")
    return host==AUCTION_HOST and path.startswith("/property/") and len(path.split("/"))>=3


def _event_card_image(anchor,event_url):
    """Take an image only from the DOM block containing exactly this property.

    Event pages can show dozens of properties. Bounding traversal by property-link
    identity prevents a neighbouring lot's photo from being attached to this one.
    """
    href=urljoin(event_url,anchor.get("href") or "").split("#",1)[0];node=anchor
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        links={urljoin(event_url,a.get("href") or "").split("#",1)[0] for a in node.find_all("a",href=True) if _is_auction_property_url(urljoin(event_url,a.get("href") or ""))}
        if len(links)>1:break
        if links and href not in links:break
        try:
            img=_image(node,event_url)
            if img:return img
        except Exception:pass
    return None


def _property_links(s,event_date,event_url=BASE):
    found={}
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if not _is_auction_property_url(href) or href in found:continue
        node=a;text=norm(a.get_text(" ",strip=True))
        for _ in range(5):
            node=getattr(node,"parent",None)
            if node is None:break
            candidate=norm(node.get_text(" ",strip=True))
            links={urljoin(event_url,x.get("href") or "").split("#",1)[0] for x in node.find_all("a",href=True) if _is_auction_property_url(urljoin(event_url,x.get("href") or ""))}
            if len(links)>1:break
            if len(candidate)<=3000 and len(candidate)>len(text):text=candidate
        if text:found[href]=(text,event_date,_event_card_image(a,event_url))
    return found


def _image(s,base):
    bad=("logo","icon","staff","office","map","floorplan","floor-plan","siteplan","site-plan","epc","avatar","placeholder","sprite");candidates=[]
    def add(raw,alt="",bonus=0):
        if not raw:return
        raw=str(raw).replace("\\/","/").strip(' "\'');u=urljoin(base,raw);low=u.lower();alt=(alt or "").lower()
        if any(x in low for x in bad) or any(x in alt for x in ("map","floor plan","floorplan","site plan","epc","logo")):return
        if not re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)",low):return
        score=bonus+(6 if "cdn.webdadi.net" in low else 0)+(4 if re.search(r"[0-9a-f]{8}-[0-9a-f-]{20,}",low,re.I) else 0)+(2 if any(x in low for x in ("property","images","photos","uploads","media")) else 0)+(2 if any(x in low for x in (".jpg",".jpeg",".webp")) else 0)
        if any(x in alt for x in ("property","external","exterior","front elevation","auction")):score+=8
        candidates.append((score,u))
    for attrs in ({"property":"og:image"},{"name":"twitter:image"}):
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"):add(tag.get("content"),bonus=8)
    for img in s.find_all("img"):
        alt=norm(img.get("alt") or "")
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","src"):
            if img.get(attr):add(img.get(attr),alt,5 if any(x in alt.lower() for x in ("property","external","exterior")) else 0)
        for attr in ("srcset","data-srcset"):
            if img.get(attr):
                for part in img.get(attr).split(","):
                    u=part.strip().split(" ")[0]
                    if u:add(u,alt)
    raw=str(s).replace("\\/","/")
    for u in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',raw,re.I):add(u)
    for u in re.findall(r'["\']([^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',raw,re.I):add(u)
    if candidates:
        best={}
        for score,u in candidates:best[u]=max(score,best.get(u,-999))
        return max(best.items(),key=lambda kv:(kv[1],len(kv[0])))[0]
    g=image_from_soup(s,base)
    return g if g and not any(x in g.lower() for x in bad) else None


def _main_property_text(s):
    h=s.find("h1") or s.find("h2")
    if not h:return _classification_text(norm((s.find("main") or s).get_text(" ",strip=True))[:14000])
    pieces=[]
    for node in [h]+list(h.find_all_next(limit=220)):
        if getattr(node,"name",None) in {"h1","h2","h3","h4","p","li","dt","dd"}:
            v=norm(node.get_text(" ",strip=True))
            if any(v.lower()==m.lower() or v.lower().startswith(m.lower()+" ") for m in CHROME_MARKERS):break
            if v and v not in pieces:pieces.append(v)
        if len(" ".join(pieces))>14000:break
    return _classification_text(norm(" ".join(pieces))[:14000])


def _brochure_links(s,base):
    scored=[]
    for a in s.find_all("a",href=True):
        href=urljoin(base,a.get("href") or "").split("#",1)[0];label=norm(a.get_text(" ",strip=True)+" "+href).lower();score=0
        if "brochure" in label:score+=10
        if "particular" in label:score+=9
        if href.lower().split("?")[0].endswith(".pdf"):score+=5
        if score and href.startswith("http"):scored.append((score,href))
    out=[]
    for _score,u in sorted(scored,key=lambda x:-x[0]):
        if u not in out:out.append(u)
    return out[:3]


def _brochure_text(s,base,binary_fetcher=get_bytes):
    chunks=[]
    for href in _brochure_links(s,base):
        try:
            raw=binary_fetcher(href)
            if not raw.startswith(b"%PDF"):continue
            reader=PdfReader(BytesIO(raw))
            for page in reader.pages[:24]:
                try:
                    t=page.extract_text() or ""
                    if t:chunks.append(t)
                except Exception:pass
                if sum(len(x) for x in chunks)>24000:break
            if chunks:break
        except Exception:continue
    return norm(" ".join(chunks))[:24000]


def _classification_text(text):
    value=norm(text);lowered=value.lower();cuts=[]
    for marker in CHROME_MARKERS:
        p=lowered.find(marker.lower())
        if p>0:cuts.append(p)
    if cuts:value=value[:min(cuts)]
    return norm(value)


def _is_target(text):
    """Auction Sniper is commercial/mixed-use, not a generic development-land feed."""
    clean=_classification_text(text);low=" "+clean.lower()+" "
    if COMMERCIAL_SIGNAL.search(clean):return True
    # A pure house/building plot or residential development site is outside scope.
    if any(x in low for x in RESIDENTIAL_STRONG) or DEVELOPMENT_SIGNAL.search(clean) or re.search(r"\b\d+\s+bedroom\s+house\b",low):return False
    return False


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
    sqft=sqm=acres=None;vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²|square feet)\b",text,re.I):
        v=float(m.group(1).replace(",",""))
        if 50<=v<=2_000_000:vals.append(v)
    if vals:sqft=max(vals)
    vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²|square metres)\b",text,re.I):
        v=float(m.group(1).replace(",",""))
        if 5<=v<=200_000:vals.append(v)
    if vals:sqm=max(vals)
    m=re.search(r"([\d.]+)\s*acres?\b",text,re.I)
    if m:acres=float(m.group(1))
    return sqft,sqm,acres


def _has_residential_component(text):
    low=_classification_text(text).lower();return any(x in low for x in RESIDENTIAL_COMPONENT) or bool(re.search(r"\b(?:two|three|four|five|\d+)\s+(?:existing\s+|vacant\s+)?flats?\b",low))
def _has_commercial_component(text):return bool(COMMERCIAL_SIGNAL.search(_classification_text(text)))
def _property_type(text):
    clean=_classification_text(text);low=clean.lower()
    if "mixed use" in low or "mixed-use" in low or (_has_commercial_component(clean) and _has_residential_component(clean)):return "Mixed Use"
    for label,pat in (("Public House",r"\bpublic house\b|\bpub\b"),("Retail",r"\bshop\b|\bretail\s+(?:unit|property|investment|premises)\b"),("Office",r"\boffice\s+(?:building|unit|investment|premises|accommodation)\b"),("Industrial",r"\bindustrial\s+(?:unit|property|building)\b|\bwarehouse\b|\bworkshop\b|\bbusiness park\b"),("Development",r"\bdevelopment (?:site|land|plot)\b|\bbuilding plot\b|\bredevelopment potential\b"),("Garages",r"\bgarages\b|\bgarage block\b"),("Commercial",r"\bcommercial\s+(?:property|unit|premises|building|investment|accommodation)\b")):
        if re.search(pat,clean,re.I):return label
    return "Commercial / Development"


def _current_rent(text):
    patterns=(r"(?:total\s+)?current\s+(?:rent(?:al)?|income)\s*(?:reserved\s*)?(?:of\s*)?£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum)",r"generat(?:e|es|ing)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:rent(?:al)?\s*)?(?:p\.?a\.?|pa|per annum)",r"(?:shop|retail unit|commercial unit|restaurant|office)[^.;]{0,100}?\blet\s+(?:at|for|by way of[^.;]{0,60}?at)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum)",r"\blet\s+(?:at|for)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum)",r"annual\s+rent\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)")
    for pat in patterns:
        for m in re.finditer(pat,text,re.I):
            prefix=text[max(0,m.start()-100):m.start()]
            if re.search(r"potential(?:ly)?|could\s+generate|estimated|when\s+let|fully[- ]let|further\s*$|erv\b",prefix,re.I):continue
            return float(m.group(1).replace(",",""))
    return None


def _detail(url,seed,event_date,fetcher=_fetch,brochure_reader=_brochure_text,card_image=None):
    s=fetcher(url);page_text=_main_property_text(s);brochure=""
    if len(page_text)<5000 or re.search(r"refer to (?:the )?brochure|further information",page_text,re.I):
        try:brochure=brochure_reader(s,url)
        except Exception:brochure=""
    text=norm(page_text+" "+brochure)[:24000];combined=norm(seed+" "+text)
    if not _is_target(combined):return None
    guide=parse_guide(norm(seed+" "+page_text))
    if guide is None:
        m=re.search(r"Guide(?: Price)?\s*[:\-]?\s*£+\s*([\d,]+(?:\.\d+)?)",norm(seed+" "+page_text),re.I)
        if m:guide=float(m.group(1).replace(",",""))
    rent=_current_rent(combined)
    if rent is None:
        generic=parse_rent(combined)
        if generic and not re.search(r"potential(?:ly)?[^.]{0,120}£|further\s+£|fully[- ]let income|when let",combined,re.I):rent=generic
    lp_url,lp_status=legal_pack(s,url)
    lot=Lot(source=SOURCE,url=url,address=_address(s,url),auction_date=event_date,image_url=_image(s,url) or card_image,guide_price=guide,annual_rent=rent,tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_status=lp_status,legal_pack_url=lp_url,property_type=_property_type(combined),description=text)
    lot.area_sqft,lot.area_sqm,lot.site_area_acres=_area(combined)
    has_vacant=bool(re.search(r"\bvacant\b|vacant possession",combined,re.I));has_income=bool(rent or re.search(r"\blet to\b|\blet at\b|\btenant\b|\btenanted\b|\bproducing\s+£|\brental income\b|generat(?:e|es|ing)\s+£|annual rent of £",combined,re.I))
    if has_vacant and has_income:lot.occupation="Part let / part vacant"
    elif has_vacant:lot.occupation="Vacant"
    elif has_income:lot.occupation="Tenanted"
    if re.search(r"redevelopment potential|development potential|development opportunity|subject to planning|planning permission|building plot",combined,re.I):lot.development_potential=True
    if re.search(r"in need of (?:some |comprehensive )?renovation|partly[- ]refurbished|refurbish|refurbishment|modernisation",combined,re.I):lot.refurbishment=True
    if _has_residential_component(combined) and re.search(r"convert|conversion|redevelop|development|refurbish",combined,re.I):lot.residential_conversion=True
    if _has_residential_component(combined) and _has_commercial_component(combined):lot.asset_management=True
    if re.search(r"Grade\s+II\*?\s+Listed",combined,re.I):lot.listed_status="Grade II Listed"
    pm=re.search(r"parking for\s+(\d+)\s+(?:cars|vehicles)",combined,re.I)
    if pm:lot.parking=f"Parking for {pm.group(1)} vehicles"
    elif re.search(r"multi[- ](?:vehicle|car) garage|\bcar park\b|\bparking\b|garage/workshop/store",combined,re.I):lot.parking="Car park / parking / garage mentioned"
    erv=re.search(r"(?:ERV|estimated rental value)[^£]{0,90}£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum)?",combined,re.I)
    if erv:lot.erv=float(erv.group(1).replace(",",""))
    lm=re.search(r"(?:commercial )?lease(?: for)?\s+(?:a\s+)?(\d+(?:\.\d+)?)\s*year\s+term\s+from\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",combined,re.I)
    if lm:lot.lease_term=lm.group(1)+" years";lot.lease_start=lm.group(2)
    if re.search(r"no remaining tenant break clauses?|without (?:a )?break",combined,re.I):lot.break_status="No remaining tenant break"
    if re.search(r"(?:five|5)\s+year\s+rent review",combined,re.I):lot.rent_review="5-year rent review"
    if re.search(r"internal repairing and insuring",combined,re.I):lot.fri=False
    elif re.search(r"full repairing and insuring|\bFRI\b",combined,re.I):lot.fri=True
    rv=re.search(r"(?:Business Rates:?\s*)?RV\s*£\s*([\d,]+)",combined,re.I)
    if rv:lot.rateable_value=float(rv.group(1).replace(",",""))
    epc=re.search(r"(?:Ground Floor Restaurant|Commercial|Shop|Office)[^.;]{0,80}?\b([A-G])\s*\((\d{1,3})\)",combined,re.I)
    if epc:lot.epc=f"{epc.group(1).upper()} ({epc.group(2)})"
    return lot.finalise()


def collect():
    try:
        events,index_failures=_discover_events()
        if not events:
            detail="; ".join(f"{u}: {type(e).__name__}" for u,e in index_failures) or "no route exception"
            return SourceResult(SOURCE,"FAILED",[],f"No future Symonds & Sampson property-auction events could be parsed from either public event index ({detail}).")
        candidates={};published=set();pending=set();event_failures=0
        for event_url,event_date in events.items():
            try:
                links=_property_links(_fetch(event_url),event_date,event_url)
                if links:published.add(event_date);candidates.update(links)
                else:pending.add(event_date)
            except Exception as exc:event_failures+=1;print("SYMONDS_EVENT_FAIL",event_url,repr(exc))
        lots=[];detail_failures=0
        for href,(seed,event_date,card_image) in candidates.items():
            try:
                lot=_detail(href,seed,event_date,card_image=card_image)
                if lot:lots.append(lot)
            except Exception as exc:detail_failures+=1;print("SYMONDS_DETAIL_FAIL",href,repr(exc))
        status="DEGRADED" if event_failures and lots else "FAILED" if event_failures else "LIVE" if lots or published else "CATALOGUE PENDING"
        images=sum(1 for x in lots if x.image_url)
        msg=f"All-future Symonds & Sampson sweep: {len(events)} future event(s) discovered; {len(published)} published catalogue(s), {len(pending)} pending; {len(candidates)} genuine auction property pages inspected; {len(lots)} commercial/mixed-use lots published (pure residential/development-only lots excluded); property photos {images}/{len(lots)}; {detail_failures} detail failures; {event_failures} event failures; {len(index_failures)} index-route failures."
        return SourceResult(SOURCE,status,lots,msg,discovered_count=len(lots),authoritative_snapshot=bool(status=="LIVE" and not detail_failures and published),scope_dates=tuple(sorted(published)))
    except Exception as exc:return SourceResult(SOURCE,"FAILED",[],f"Symonds & Sampson collection failed: {type(exc).__name__}: {exc}")