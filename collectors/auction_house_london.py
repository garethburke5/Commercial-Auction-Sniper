import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin
from .core import SourceResult, norm
from .utils import soup, nearest_card, detail_lot

SOURCE = "Auction House London"
URL = "https://auctionhouselondon.co.uk/auction/september-2-3-2026"


def _num(v):
    try: return float(str(v).replace(",", ""))
    except Exception: return None


def _first(patterns,text):
    for pat in patterns:
        m=re.search(pat,text or "",re.I)
        if m: return norm(m.group(1))
    return None


def _derive_expiry(start, years):
    if not start or not years: return None
    raw=re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b",r"\1",norm(start),flags=re.I)
    for fmt in ("%d %B %Y","%d %b %Y","%d/%m/%Y"):
        try:
            d=datetime.strptime(raw,fmt); y=d.year+int(float(years))
            try: out=d.replace(year=y)
            except ValueError: out=d.replace(year=y,day=28)
            return out.strftime("%d %B %Y").lstrip("0")
        except Exception: pass
    return None


def _section(text,name,next_names):
    tail="|".join(re.escape(x) for x in next_names)
    return _first([rf"{re.escape(name)}\s+(.+?)(?=(?:{tail})\s+|Financial Tools|Legal Pack|Additional Fees|Similar Properties|$)"],text)


def _ahl_commercial_text(text):
    """AHL-specific classifier for catalogue cards or exact lot pages."""
    low=" "+norm(text).lower()+" "
    strong=(
        " commercial property "," retail property "," industrial development ",
        " industrial property "," industrial building "," commercial investment ",
        " commercial unit "," commercial building "," commercial premises ",
        " retail investment "," retail unit "," shop investment "," shop unit ",
        " office "," warehouse "," workshop "," restaurant "," public house ",
        " hotel "," care home "," business premises "," mixed use "," mixed-use ",
        " commercial/residential "," commercial / residential "," vaults "," tunnels ",
        " secure yard "," garage block "," storage unit ",
    )
    if any(x in low for x in strong): return True
    if re.search(r"\b(?:land|development)\b",low) and re.search(r"\b(?:industrial|commercial|retail|office|warehouse|workshop|business|garage|storage|yard|vault|tunnel)\b",low):
        return True
    return False


def _ahl_exact_is_commercial(ds):
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))
    return _ahl_commercial_text(text[:6000])


def _rich_detail(lot, ds):
    """Auction House London exact-page enrichment; labelled particulars outrank generic/cache facts."""
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))
    text=re.split(r"\bSimilar Properties\b",text,1,flags=re.I)[0]

    lm=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
    if lm: lot.lot_number="Lot "+lm.group(1)

    gm=re.search(r"(?:Guide Price\s*)?£\s*([\d,]+(?:\.\d+)?)\s*(?:-\s*£\s*([\d,]+(?:\.\d+)?)|\+)?(?:\s*Guide Price)?",text,re.I)
    if gm: lot.guide_price=_num(gm.group(1))

    tenure_sec=_section(text,"Tenure",["Location","Accommodation","Planning","Tenancy","VAT","EPC Rating","Exterior","Note"])
    if tenure_sec:
        tm=re.search(r"\b(Freehold|Leasehold)\b",tenure_sec,re.I)
        if tm: lot.tenure=tm.group(1).title()
        yrs=_first([r"approximately\s+(\d+(?:\.\d+)?)\s+years? unexpired"],tenure_sec)
        if yrs: lot.lease_term=f"Approximately {yrs} years unexpired"
        gr=_first([r"(?:passing )?ground rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?)"],tenure_sec)
        if gr: lot.ground_rent=_num(gr)
        elif re.search(r"peppercorn ground rent",tenure_sec,re.I): lot.ground_rent=0.0

    accom=_section(text,"Accommodation",["Exterior","Planning","Tenancy","VAT","EPC Rating","Note"])
    if accom:
        pairs=re.findall(r"([\d,]+(?:\.\d+)?)\s*sq\s*m\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*ft\)",accom,re.I)
        if pairs:
            vals=[(_num(a),_num(b)) for a,b in pairs]
            # Prefer an explicit total/GIA pair if present, otherwise sum components.
            total_pair=None
            for m in re.finditer(r"(?:G\.?I\.?A\.?|Total)[^\d]{0,40}([\d,]+(?:\.\d+)?)\s*sq\s*m\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*ft\)",accom,re.I):
                total_pair=(_num(m.group(1)),_num(m.group(2)))
            if total_pair:
                lot.area_sqm,lot.area_sqft=total_pair
            elif len(vals)==1:
                lot.area_sqm,lot.area_sqft=vals[0]
            else:
                lot.area_sqm=round(sum(a for a,b in vals if a),2); lot.area_sqft=round(sum(b for a,b in vals if b),2)
        else:
            sqm=[_num(x) for x in re.findall(r"(?:G\.I\.A\.?\s*)?(?:Approximately\s*)?([\d,]+(?:\.\d+)?)\s*sq\s*m",accom,re.I)]
            if sqm:
                lot.area_sqm=round(sum(sqm),2); lot.area_sqft=round(lot.area_sqm*10.7639,0)

    epc=_first([r"EPC Rating\s+([A-G])\b",r"Energy Performance Rating\s+([A-G])\b"],text)
    if epc: lot.epc=epc.upper()

    tenancy=_section(text,"Tenancy",["VAT","EPC Rating","Planning","Joint Agent","Note"])
    headline=text[:min(len(text),2200)]
    vacant=bool(re.search(r"\bVacant\b",headline,re.I))

    current=_first([
        r"Fully Let Producing\s*£\s*([\d,]+(?:\.\d+)?)\s*Per Annum",
        r"Let Producing\s*£\s*([\d,]+(?:\.\d+)?)\s*Per Annum",
        r"at a rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
        r"rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
    ],tenancy or headline)
    if vacant:
        lot.annual_rent=None; lot.occupation="Vacant"
    elif current:
        lot.annual_rent=_num(current); lot.occupation="Tenanted"

    if tenancy and not vacant:
        tenant=_first([
            r"(?:let|leased) to\s+(.+?)\s+for a term",
            r"(?:let|leased) to\s+(.+?)\s+(?:on|at a rent|commencing)",
        ],tenancy)
        if tenant and len(tenant)<120: lot.tenant=tenant
        start=_first([r"commencing\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",r"from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})"],tenancy)
        term=_first([r"term of\s+(\d+(?:\.\d+)?\s*years?)"],tenancy)
        if start: lot.lease_start=start
        if term:
            lot.lease_term=term
            y=re.search(r"\d+(?:\.\d+)?",term)
            if start and y: lot.lease_expiry=_derive_expiry(start,y.group(0))
        if re.search(r"\bFRI\b|full repairing and insuring",tenancy,re.I): lot.fri=True
        review=_first([r"(\d+[- ]yearly RPI index linked reviews?)",r"(RPI index linked reviews?[^.;]{0,80})",r"(rent reviews?[^.;]{0,100})"],tenancy)
        if review: lot.rent_review=review
        br=_first([r"(Tenant(?:'s)? break clause\s+20\d{2})",r"(break clause[^.;]{0,80})"],tenancy)
        if br: lot.break_clause=br
        if re.search(r"did not exercise (?:their )?break clause",tenancy,re.I):
            lot.break_status="PASSED"; lot.break_clause="Break not exercised"

    vat=_section(text,"VAT",["EPC Rating","Joint Agent","Note"])
    if vat:
        if re.search(r"VAT is applicable",vat,re.I): lot.vat_status="APPLICABLE"
        if re.search(r"TOGC available",vat,re.I): lot.vat_status="APPLICABLE - TOGC AVAILABLE"
        if re.search(r"not applicable|no VAT",vat,re.I): lot.vat_status="NOT APPLICABLE"

    planning=_section(text,"Planning",["Tenancy","VAT","EPC Rating","Joint Agent","Note"])
    if planning:
        lot.development_potential=True
        if re.search(r"planning permission|permission was granted|approved",planning,re.I):
            lot.asset_management=True
        if re.search(r"HMO|House in Multiple Occupation",planning,re.I):
            lot.residential_conversion=True
            lot.property_type=lot.property_type or "Commercial / HMO development"

    if re.search(r"Potential for Development",headline,re.I): lot.development_potential=True
    if re.search(r"potential for conversion to residential|convert to (?:an? )?\w*\s*residential",text,re.I): lot.residential_conversion=True
    if re.search(r"refurbish|refurbishment",text,re.I): lot.refurbishment=True

    if re.search(r"secure yard|yard area",text,re.I): lot.parking="Secure yard / parking" if re.search(r"parking",text,re.I) else "Secure yard"
    elif re.search(r"\bparking\b",text,re.I): lot.parking="Parking"

    if not lot.property_type:
        if re.search(r"Industrial Development|industrial building|warehouse",headline,re.I): lot.property_type="Industrial"
        elif re.search(r"Retail Property|retail unit|high street",headline,re.I): lot.property_type="Retail"
        elif re.search(r"office",headline,re.I): lot.property_type="Office"
        elif re.search(r"vaults|tunnels",headline,re.I): lot.property_type="Vaults / commercial storage"

    if re.search(r"prominent|busy|city centre|town centre",text,re.I): lot.pitch="Prominent/established commercial location"

    lot.description=text[:6000]
    return lot.finalise()


def collect():
    try:
        # Current AHL catalogue cards contain a reliable property class. Classify
        # there first so we do not hammer all 235 exact pages or lose commercial
        # lots to rate limiting before enrichment starts.
        s=soup(URL,use_browser=False)
        seen,targets=set(),[]
        all_exact=0
        for a in s.find_all("a",href=True):
            href=urljoin(URL,a["href"])
            if "/lot/" not in href or href in seen: continue
            seen.add(href); all_exact+=1
            card=nearest_card(a,5200)
            low=card.lower()
            if "sold prior" in low or "withdrawn" in low: continue
            if not _ahl_commercial_text(card): continue
            m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
            targets.append((href,card,f"Lot {m.group(1)}" if m else None))

        # If static catalogue markup is incomplete, use the browser-rendered page.
        if not targets:
            s=soup(URL,use_browser=True)
            seen=set(); all_exact=0
            for a in s.find_all("a",href=True):
                href=urljoin(URL,a["href"])
                if "/lot/" not in href or href in seen: continue
                seen.add(href); all_exact+=1
                card=nearest_card(a,5200)
                if not _ahl_commercial_text(card): continue
                m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
                targets.append((href,card,f"Lot {m.group(1)}" if m else None))

        lots=[]; failures=0; exact_rejected=0

        def hydrate(item):
            href,card,lotno=item
            last_error=None
            # A small commercial target set can be retried safely. Direct HTML is
            # preferred; browser rendering is the fallback for AHL anti-bot/JS pages.
            for use_browser in (False, True):
                try:
                    ds=soup(href,use_browser=use_browser)
                    if not _ahl_exact_is_commercial(ds):
                        if use_browser: return "REJECTED",None
                        continue
                    lot=detail_lot(SOURCE,href,seed=card,lot_number=lotno,auction_date="2026-09-02",force_commercial=True,strict_commercial=False,use_browser=use_browser)
                    if not lot: continue
                    return "OK",_rich_detail(lot,ds)
                except Exception as e:
                    last_error=e
            print("AHL_HYDRATE_FAIL",href,repr(last_error))
            return "FAILED",None

        # Keep concurrency deliberately modest: the previous 10-way exact-page
        # sweep produced 42 fetch/parser failures on AHL.
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures=[ex.submit(hydrate,x) for x in targets]
            for f in as_completed(futures):
                try:
                    kind,lot=f.result()
                    if kind=="OK" and lot: lots.append(lot.finalise())
                    elif kind=="REJECTED": exact_rejected+=1
                    else: failures+=1
                except Exception: failures+=1

        status="LIVE" if lots else "FAILED"
        msg=f"Sep 2/3 catalogue {all_exact} exact URLs; {len(targets)} commercial card candidates; {len(lots)} enriched lots; {exact_rejected} exact-page rejects; {failures} fetch/parser failures"
        return SourceResult(SOURCE,status,lots,msg)
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
