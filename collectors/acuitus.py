import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card, legal_pack

SOURCE="Acuitus"
BASE="https://www.acuitus.co.uk"
URL=BASE+"/find-a-property/?which=sales"
AUCTION_DATE="2026-09-17"


def _num(v):
    try: return float(str(v).replace(",", ""))
    except Exception: return None


def _section(text,name,next_names):
    tail="|".join(re.escape(x) for x in next_names)
    m=re.search(rf"{re.escape(name)}\s+(.+?)(?=(?:{tail})\s+|Tenancy & Accommodation|Contacts|Useful Links|$)",text or "",re.I)
    return norm(m.group(1)) if m else None


def _is_commercial_card(card):
    low=(card or "").lower()
    commercial=("retail","office","industrial","warehouse","mixed use","mixed-use","development","bank","restaurant","petrol station","ground rent","self storage","leisure","hotel","care home","commercial")
    if not any(x in low for x in commercial): return False
    pure_res=("shared ownership houses","residential only","residential investment")
    return not (any(x in low for x in pure_res) and not any(x in low for x in ("retail","office","industrial","warehouse","mixed use","mixed-use","commercial","development")))


def _property_image(ds, href):
    pm=re.search(r"/property/(\d+)/?",href,re.I)
    pid=pm.group(1) if pm else None
    scored=[]
    for img in ds.find_all("img"):
        raw=img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src")
        if not raw: continue
        u=urljoin(href,raw)
        low=u.lower()
        if any(x in low for x in ("logo","favicon","icon","sprite","placeholder","avatar","social","acuitus-logo")): continue
        score=0
        if pid and re.search(rf"/uploads/[^/]*-{re.escape(pid)}/",low): score+=100
        if "/uploads/" in low: score+=20
        if any(x in low for x in ("1600x900","1200x","1024x","800x450")): score+=8
        if any(x in low for x in ("128x72","thumbnail","thumb")): score-=8
        alt=norm(img.get("alt") or "").lower()
        if any(x in alt for x in ("property","lot","building","street")): score+=4
        if score>0: scored.append((score,u))
    if not scored: return None
    scored.sort(key=lambda x:x[0],reverse=True)
    return scored[0][1]


def _area(text):
    pairs=(
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    m=re.search(pairs[0],text,re.I)
    if m: return _num(m.group(1)),_num(m.group(2))
    m=re.search(pairs[1],text,re.I)
    if m: return _num(m.group(2)),_num(m.group(1))
    m=re.search(r"(?:approximately|approx\.?|extending to|comprising)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",text,re.I)
    if m:
        sqft=_num(m.group(1)); return sqft, round(sqft/10.7639,2) if sqft else None
    m=re.search(r"(?:approximately|approx\.?|extending to|comprising)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",text,re.I)
    if m:
        sqm=_num(m.group(1)); return round(sqm*10.7639,2) if sqm else None, sqm
    return None,None


def _fallback_type(text):
    for pat,label in (
        (r"mixed[- ]use","Mixed use"),(r"retail|shop|high street","Retail"),(r"office","Office"),
        (r"industrial|warehouse|trade counter","Industrial"),(r"ground rent","Ground rent"),
        (r"hotel|hostel","Hotel"),(r"care home","Care facility"),(r"public house|\bpub\b","Pub"),
        (r"restaurant|cafe|takeaway","Restaurant / leisure"),(r"development site|development opportunity","Development"),
    ):
        if re.search(pat,text,re.I): return label
    return "Commercial"


def _rich_lot(href, card):
    ds=soup(href,use_browser=False)
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))
    combined=norm(card+" "+text)
    h1=ds.find("h1")
    address=norm(h1.get_text(" ",strip=True)) if h1 else None
    if not address:
        title=ds.find("title")
        address=norm(title.get_text(" ",strip=True)).split("|")[0] if title else href

    m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",combined,re.I)
    lotno="Lot "+m.group(1) if m else None
    guide=parse_guide(text) or parse_guide(card)
    rent=None
    rm=re.search(r"\bRent\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s*Annum|p\.?a\.?|pa)",combined,re.I)
    if rm: rent=_num(rm.group(1))
    elif not re.search(r"\bVacant\b",text[:2200],re.I): rent=parse_rent(combined)

    lp_url,lp_status=legal_pack(ds,href)
    lot=Lot(source=SOURCE,url=href,address=address,lot_number=lotno,auction_date=AUCTION_DATE,
        image_url=_property_image(ds,href),guide_price=guide,annual_rent=rent,
        tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_status=lp_status,
        legal_pack_url=lp_url,status="Live",description=text[:9000])

    sector=_section(text,"Sector",["Auction Venue","Property Information","Location"])
    lot.property_type=sector[:120] if sector else _fallback_type(combined)
    tenure=_section(text,"Tenure",["Description","VAT","EPC","Tenancy & Accommodation"])
    if tenure:
        lot.tenure=parse_tenure(tenure) or lot.tenure
        gm=re.search(r"ground rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:pa|p\.a\.|per annum)",tenure,re.I)
        if gm: lot.ground_rent=_num(gm.group(1))
        exp=re.search(r"expiring in\s+(20\d{2}|21\d{2})",tenure,re.I)
        if exp: lot.lease_expiry=exp.group(1)

    lot.area_sqft,lot.area_sqm=_area(combined)
    sm=re.search(r"([\d.]+)\s*acres?\b",combined,re.I)
    if sm: lot.site_area_acres=_num(sm.group(1))
    epc=re.search(r"\bEPC\s+(?:Rating\s+)?([A-G])\b",combined,re.I)
    if epc: lot.epc=epc.group(1).upper()

    if re.search(r"VAT is not applicable|VAT free investment|VAT-free investment",combined,re.I): lot.vat_status="NOT APPLICABLE"
    elif re.search(r"VAT is applicable|elected for VAT",combined,re.I): lot.vat_status="APPLICABLE"

    if rent is not None:
        lot.occupation="Part-let / part-vacant" if re.search(r"\bpart(?:ly)?[- ]vacant|vacant (?:unit|floor|part)",combined,re.I) else "Tenanted"
    elif re.search(r"\bvacant(?: possession)?\b|offered with vacant possession",combined[:4500],re.I):
        lot.occupation="Vacant"
    elif re.search(r"Tenancy & Accommodation|Tenant\s+Term\s+Rent|\blet to\b|\bleased to\b",combined,re.I):
        lot.occupation="Tenanted"

    tenants=[]
    for tm in re.finditer(r"\b([A-Z][A-Z0-9 '&().-]{3,80}(?:LIMITED|LTD|PLC))\b",combined):
        name=norm(tm.group(1))
        if name not in tenants: tenants.append(name)
    if tenants: lot.tenant=" / ".join(tenants[:3])
    if not lot.tenant:
        tm=re.search(r"(?:let|leased) to\s+([A-Z][A-Za-z0-9 '&().,-]{2,80}?)(?:\s+on\s+|\s+for\s+|\s+at\s+|\.|,)",combined)
        if tm: lot.tenant=norm(tm.group(1))

    if re.search(r"asset management opportunit|asset management potential|repositioning opportunit|re-letting potential|reletting potential",combined,re.I): lot.asset_management=True
    if re.search(r"development potential|development opportunity|redevelop|subject to planning|planning permission|lapsed.*consent",combined,re.I): lot.development_potential=True
    if re.search(r"residential conversion|conversion to residential|upper floors.*residential|residential accommodation",combined,re.I): lot.residential_conversion=True
    if re.search(r"refurbish|refurbishment",combined,re.I): lot.refurbishment=True

    pm=re.search(r"(\d{1,4})\s+(?:car\s+)?parking spaces?",combined,re.I)
    if pm: lot.parking=f"{pm.group(1)} parking spaces"
    elif re.search(r"rear loading|parking|car park",combined,re.I): lot.parking="Parking/loading mentioned"

    situation=_section(text,"Situation",["Tenure","Description","VAT","EPC"])
    situation_text=situation or combined[:4500]
    if re.search(r"prominent|prime|city centre|town centre|high street|frontage",situation_text,re.I): lot.pitch="Prominent/central commercial location"
    near=re.search(r"Nearby occupiers include\s+(.+?)(?:\.|Tenure|Description|$)",situation_text,re.I)
    if near: lot.nearby_occupiers=norm(near.group(1))[:300]

    return lot.finalise()


def collect():
    try:
        s=soup(URL,use_browser=False)
        seen,targets=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if not re.search(r"/property/\d+/?",href,re.I): continue
            href=href.split("?",1)[0]
            if href in seen: continue
            card=nearest_card(a,4200)
            if "17/09/2026" not in card and "17 September 2026" not in card and "17th September 2026" not in card: continue
            if not _is_commercial_card(card): continue
            seen.add(href);targets.append((href,card))
        if not targets:
            s=soup(URL,use_browser=True)
            for a in s.find_all("a",href=True):
                href=urljoin(BASE,a["href"])
                if not re.search(r"/property/\d+/?",href,re.I): continue
                href=href.split("?",1)[0]
                if href in seen: continue
                card=nearest_card(a,4200)
                if not _is_commercial_card(card): continue
                seen.add(href);targets.append((href,card))
        lots=[];failures=0
        for href,card in targets:
            try: lots.append(_rich_lot(href,card))
            except Exception as e:
                failures+=1;print("ACUITUS_DETAIL_FAIL",href,repr(e))
        status="LIVE" if lots and failures==0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE,status,lots,
            f"17 Sep source-labelled commercial/mixed-use: {len(targets)} candidates; {len(lots)} enriched; {failures} failures",
            expected_count=len(targets),discovered_count=len(targets),
            authoritative_snapshot=bool(status=="LIVE" and failures==0),scope_dates=(AUCTION_DATE,),
        )
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))