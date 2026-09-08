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
    found={};today_iso=(today or date.today()).isoformat()
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if "/event/property-auction-" not in href.lower():continue
        d=_parse_date(_event_card_text(a))
        if d and d<today_iso:continue
        if href not in found or (not found[href] and d):found[href]=d
    return found


def _event_page_date(s):
    root=s.find("main") or s
    text=norm(root.get_text(" ",strip=True))
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
    href=urljoin(event_url,anchor.get("href") or "").split("#",1)[0];node=anchor
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        links={urljoin(event_url,a.get("href") or "").split("#",1)[0] for a in node.find_all("a",href=True) if _is_auction_property_url(urljoin(event_url,a.get("href") or ""))}
        if href in links and len(links)==1:
            image=image_from_soup(node,event_url)
            if image:return image
        if len(links)>1:break
    return None


def _property_links(s,auction_date):
    out={}
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#",1)[0]
        if not _is_auction_property_url(href):continue
        out[href]=(norm(a.get_text(" ",strip=True)),auction_date,_event_card_image(a,BASE))
    return out


def _strip_chrome(text):
    text=norm(text);low=text.lower();cut=len(text)
    for marker in CHROME_MARKERS:
        i=low.find(marker.lower())
        if 0<i<cut:cut=i
    return text[:cut].strip()


def _property_text(s):
    root=s.find("main") or s
    return _strip_chrome(root.get_text(" ",strip=True))


def _is_target(text):
    low=_strip_chrome(text).lower()
    if COMMERCIAL_SIGNAL.search(low):return True
    if DEVELOPMENT_SIGNAL.search(low):return False
    if any(x in low for x in RESIDENTIAL_STRONG):return False
    return False


def _property_type(text):
    low=_strip_chrome(text).lower()
    if "mixed use" in low or "mixed-use" in low or (COMMERCIAL_SIGNAL.search(low) and any(x in low for x in RESIDENTIAL_COMPONENT)):return "Mixed Use"
    if "retail" in low or "shop" in low:return "Retail"
    if "office" in low:return "Office"
    if "industrial" in low or "warehouse" in low or "workshop" in low:return "Industrial"
    if "public house" in low or re.search(r"\bpub\b",low):return "Leisure"
    return "Commercial"


def _money_value(raw):
    try:return float(raw.replace("£","").replace(",",""))
    except Exception:return None


def _current_rent(text):
    text=text or ""
    patterns=(
        r"(?:current(?: gross)? income|current rent|rent reserved)\s*(?:of|is|:)?\s*(£[\d,]+(?:\.\d+)?)\s*(?:rent\s*)?(?:per annum|p\.?a\.?|pa)\b",
        r"(?:producing|generating|let at)\s*(?:of|is|:)?\s*(£[\d,]+(?:\.\d+)?)\s*(?:rent\s*)?(?:per annum|p\.?a\.?|pa)\b",
        r"annual rent\s*(?:of|is|:)?\s*(£[\d,]+(?:\.\d+)?)\b",
        r"rent\s*(?:of|is|:)?\s*(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
    )
    for pat in patterns:
        m=re.search(pat,text,re.I)
        if m:
            v=_money_value(m.group(1))
            if v:return v
    return parse_rent(text)


def _structured(text):
    t=norm(text);low=t.lower();out={}
    both_vacant=bool(re.search(r"\bvacant(?: possession)?\b",low))
    both_let=bool(re.search(r"\b(?:let|leased)\b|\bgenerating\s+£|\bannual rent\b",low))
    if both_vacant and both_let:out["occupation"]="Part let / part vacant"
    elif both_vacant:out["occupation"]="Vacant"
    elif both_let:out["occupation"]="Let"
    out["development_potential"] = True if re.search(r"\b(?:redevelopment|development potential|development opportunity)\b",low) else None
    out["refurbishment"] = True if re.search(r"\b(?:refurbishment|modernisation|modernization)\b",low) else None
    out["asset_management"] = True if re.search(r"\b(?:mixed[- ]use|shop\b|restaurant\b).{0,120}\b(?:flats?|apartments?)\b|\b(?:flats?|apartments?)\b.{0,120}\b(?:shop|restaurant)\b",low) else None
    m=re.search(r"\b(Grade\s+(?:I|II\*?|III)\s+Listed)\b",t,re.I)
    if m:out["listed_status"]=norm(m.group(1)).replace("grade","Grade")
    m=re.search(r"\b(?:Total\s+floor\s+area\s*)?([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft\b",t,re.I)
    if m:out["area_sqft"]=_money_value(m.group(1))
    for pat in (
        r"\b(?:ERV(?:\s+of)?|estimated rental value(?:\s+of)?|potential further(?: income)? of?)\s*£?\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)?\b",
        r"\bERV\s+of\s+(?:the\s+)?(?:apartments?|flats?|units?)\s+is\s+(?:estimated\s+to\s+be\s+)?£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"\bestimated rental value\s+of\s+(?:the\s+)?(?:apartments?|flats?|units?)\s+(?:is\s+)?£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
    ):
        m=re.search(pat,t,re.I)
        if m:
            out["erv"]=_money_value(m.group(1));break
    m=re.search(r"\b(?:lease|tenancy)\s+for\s+(?:a\s+)?(?:term\s+of\s+)?(\d+(?:\.\d+)?\s+years?)\b",t,re.I)
    if m:out["lease_term"]=norm(m.group(1))
    m=re.search(r"\b(?:from|commencing|commenced)\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})\b",t,re.I)
    if m:out["lease_start"]=norm(m.group(1))
    if re.search(r"\bno remaining tenant break clauses?\b",low):out["break_status"]="No remaining tenant break"
    if re.search(r"\bfive year rent review\b|\b5[- ]year rent review\b",low):out["rent_review"]="5-year rent review"
    if re.search(r"\binternal repairing and insuring\b",low):out["fri"]=False
    elif re.search(r"\bfull repairing and insuring\b|\bFRI\b",t,re.I):out["fri"]=True
    m=re.search(r"\b(?:Business Rates:\s*)?RV\s*£?\s*([\d,]+(?:\.\d+)?)\b",t,re.I)
    if m:out["rateable_value"]=_money_value(m.group(1))
    m=re.search(r"\b(?:EPC|Energy Performance Certificate)[^A-G]{0,40}([A-G]\s*\(\s*\d{1,3}\s*\))",t,re.I)
    if m:out["epc"]=re.sub(r"\s+"," ",m.group(1)).replace("( ","(").replace(" )",")").upper()
    return out


def _image(s,url):
    candidates=[]
    for img in s.find_all("img"):
        for attr in ("data-src","data-lazy-src","src"):
            src=img.get(attr)
            if not src:continue
            full=urljoin(url,src);low=full.lower();alt=norm(img.get("alt") or "").lower()
            if any(x in low for x in ("logo","agent","team","icon","avatar","map","plan")) and "property" not in low:continue
            score=0
            if "property" in low:score+=5
            if any(x in low for x in ("front","exterior","main","hero")):score+=4
            if "property" in alt or "exterior" in alt:score+=3
            if "plan" in low or "plan" in alt:score-=6
            candidates.append((score,full))
    return max(candidates,key=lambda x:x[0])[1] if candidates else image_from_soup(s,url)


def _brochure_links(s,url):
    out=[]
    for a in s.find_all("a",href=True):
        href=urljoin(url,a.get("href") or "")
        label=norm(a.get_text(" ",strip=True)).lower()
        if href.lower().endswith(".pdf") and any(x in label or x in href.lower() for x in ("brochure","particular","auction")):out.append(href)
    return out


def _pdf_text(url):
    raw=get_bytes(url);r=PdfReader(BytesIO(raw))
    return norm(" ".join((p.extract_text() or "") for p in r.pages))


def _detail(url,seed,auction_date,image_hint=None,fetcher=None,brochure_reader=None):
    fetcher=fetcher or _fetch
    s=fetcher(url);text=_property_text(s)
    if not _is_target(text):return None
    enriched=text
    if len(text)<900:
        if brochure_reader is not None:
            try:
                ptext=norm(brochure_reader(s,url))
                if ptext:enriched=norm(text+" "+ptext)
            except Exception:pass
        else:
            for pdf in _brochure_links(s,url):
                try:
                    ptext=_pdf_text(pdf)
                    if ptext:enriched=norm(text+" "+ptext)
                except Exception:pass
    h=s.find("h1");address=norm(h.get_text(" ",strip=True)) if h else seed or url
    ml=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
    lp_url,lp_status=legal_pack(s,url)
    rent=_current_rent(enriched);guide=parse_guide(text) or parse_guide(enriched);facts=_structured(enriched)
    return Lot(source=SOURCE,url=url,address=address,lot_number=("Lot "+ml.group(1) if ml else None),auction_date=auction_date,image_url=_image(s,url) or image_hint,guide_price=guide,annual_rent=rent,tenure=parse_tenure(enriched),vat_status=parse_vat(enriched),legal_pack_status=lp_status,legal_pack_url=lp_url,status="Live",description=enriched[:1200],property_type=_property_type(enriched),occupation=facts.get("occupation"),area_sqft=facts.get("area_sqft"),erv=facts.get("erv"),lease_term=facts.get("lease_term"),lease_start=facts.get("lease_start"),break_status=facts.get("break_status"),rent_review=facts.get("rent_review"),fri=facts.get("fri"),rateable_value=facts.get("rateable_value"),epc=facts.get("epc"),development_potential=facts.get("development_potential"),refurbishment=facts.get("refurbishment"),asset_management=facts.get("asset_management"),listed_status=facts.get("listed_status")).finalise()


def collect():
    events,failures=_discover_events();lots=[]
    for event_url,auction_date in events.items():
        try:
            s=_fetch(event_url)
            for url,(seed,d,image_hint) in _property_links(s,auction_date).items():
                try:
                    lot=_detail(url,seed,d,image_hint)
                    if lot:lots.append(lot)
                except Exception:continue
        except Exception as exc:failures.append((event_url,exc))
    note="; ".join(f"{u}: {e}" for u,e in failures[:4]) if failures else ""
    return SourceResult(source=SOURCE,status=("LIVE" if lots else "FAILED"),lots=lots,message=note,discovered_count=len(lots),expected_count=None)