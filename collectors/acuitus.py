import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card, image_from_soup, legal_pack

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
    if not any(x in low for x in commercial):
        return False
    pure_res=("shared ownership houses","residential only","residential investment")
    if any(x in low for x in pure_res) and not any(x in low for x in ("retail","office","industrial","warehouse","mixed use","mixed-use","commercial","development")):
        return False
    return True


def _rich_lot(href, card):
    ds=soup(href,use_browser=False)
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))
    h1=ds.find("h1")
    address=norm(h1.get_text(" ",strip=True)) if h1 else None
    if not address:
        title=ds.find("title")
        address=norm(title.get_text(" ",strip=True)).split("|")[0] if title else href

    lotno=None
    m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
    if m: lotno="Lot "+m.group(1)

    guide=parse_guide(text) or parse_guide(card)
    rent=None
    rm=re.search(r"\bRent\s*£\s*([\d,]+(?:\.\d+)?)\s*per\s*Annum",text,re.I)
    if rm: rent=_num(rm.group(1))
    elif not re.search(r"\bVacant\b",text[:1800],re.I): rent=parse_rent(text)

    lp_url,lp_status=legal_pack(ds,href)
    lot=Lot(
        source=SOURCE,url=href,address=address,lot_number=lotno,auction_date=AUCTION_DATE,
        image_url=image_from_soup(ds,href),guide_price=guide,annual_rent=rent,
        tenure=parse_tenure(text),vat_status=parse_vat(text),legal_pack_status=lp_status,
        legal_pack_url=lp_url,status="Live",description=text[:6000]
    )

    sector=_section(text,"Sector",["Auction Venue","Property Information","Location"])
    if sector: lot.property_type=sector[:120]

    tenure=_section(text,"Tenure",["Description","VAT","EPC","Tenancy & Accommodation"])
    if tenure:
        lot.tenure=parse_tenure(tenure) or lot.tenure
        gm=re.search(r"ground rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:pa|p\.a\.|per annum)",tenure,re.I)
        if gm: lot.ground_rent=_num(gm.group(1))
        exp=re.search(r"expiring in\s+(20\d{2}|21\d{2})",tenure,re.I)
        if exp: lot.lease_expiry=exp.group(1)

    total=re.search(r"Total approximate floor area\s+.*?([\d,]+(?:\.\d+)?)\s+\(?([\d,]+(?:\.\d+)?)\)?",text,re.I)
    if total:
        lot.area_sqm=_num(total.group(1)); lot.area_sqft=_num(total.group(2))
    else:
        m=re.search(r"total floor area of approx\.?\s*([\d,]+(?:\.\d+)?)\s*sq\s*m\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*ft\)",text,re.I)
        if m: lot.area_sqm=_num(m.group(1)); lot.area_sqft=_num(m.group(2))

    epc=re.search(r"\bEPC\s+(?:Rating\s+)?([A-G])\b",text,re.I)
    if epc: lot.epc=epc.group(1).upper()

    if re.search(r"VAT is not applicable|VAT free investment|VAT-free investment",text,re.I): lot.vat_status="NOT APPLICABLE"
    elif re.search(r"VAT is applicable|elected for VAT",text,re.I): lot.vat_status="APPLICABLE"

    headline=text[:2200]
    if re.search(r"\bVacant\b",headline,re.I) and not rent:
        lot.occupation="Vacant"
    elif re.search(r"Tenancy & Accommodation|Tenant\s+Term\s+Rent",text,re.I):
        if re.search(r"\bVACANT\b",text,re.I): lot.occupation="Part-let / part-vacant"
        else: lot.occupation="Tenanted"

    tenants=[]
    for m in re.finditer(r"\b([A-Z][A-Z0-9 '&().-]{3,80}(?:LIMITED|LTD|PLC))\b",text):
        name=norm(m.group(1))
        if name not in tenants: tenants.append(name)
    if tenants: lot.tenant=" / ".join(tenants[:3])

    if re.search(r"asset management opportunit|asset management potential",text,re.I): lot.asset_management=True
    if re.search(r"development potential|development opportunity|subject to planning|planning permission",text,re.I): lot.development_potential=True
    if re.search(r"residential conversion|conversion to residential|upper floors.*residential",text,re.I): lot.residential_conversion=True
    if re.search(r"refurbishment",text,re.I): lot.refurbishment=True
    if re.search(r"rear loading|parking|car park",text,re.I): lot.parking="Parking/loading mentioned"

    situation=_section(text,"Situation",["Tenure","Description","VAT","EPC"])
    if situation:
        if re.search(r"prominent|prime|city centre|town centre|high street",situation,re.I): lot.pitch="Prominent/central commercial location"
        near=re.search(r"Nearby occupiers include\s+(.+?)(?:\.|Tenure|Description|$)",situation,re.I)
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
            if "17/09/2026" not in card and "17 September 2026" not in card and "17th September 2026" not in card:
                continue
            if not _is_commercial_card(card): continue
            seen.add(href); targets.append((href,card))

        if not targets:
            s=soup(URL,use_browser=True)
            for a in s.find_all("a",href=True):
                href=urljoin(BASE,a["href"])
                if not re.search(r"/property/\d+/?",href,re.I): continue
                href=href.split("?",1)[0]
                if href in seen: continue
                card=nearest_card(a,4200)
                if not _is_commercial_card(card): continue
                seen.add(href); targets.append((href,card))

        lots=[]; failures=0
        for href,card in targets:
            try:
                lots.append(_rich_lot(href,card))
            except Exception as e:
                failures+=1
                print("ACUITUS_DETAIL_FAIL",href,repr(e))
        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,f"17 Sep source-labelled commercial/mixed-use: {len(targets)} candidates; {len(lots)} enriched; {failures} failures")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
