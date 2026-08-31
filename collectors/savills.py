import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup

SOURCE = "Savills Auctions"
BASE = "https://auctions.savills.co.uk"
CURRENT = BASE + "/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"

KNOWN = {"Lot 73","Lot 75","Lot 76","Lot 77","Lot 78","Lot 79","Lot 80","Lot 86","Lot 88","Lot 89","Lot 90","Lot 93","Lot 95","Lot 96","Lot 98"}

def _strings_before(a, limit=50):
    vals=[]
    for s in a.find_all_previous(string=True, limit=limit):
        t=norm(str(s))
        if t: vals.append(t)
    vals.reverse()
    return vals

def _strings_after(a, limit=70):
    vals=[]
    for s in a.find_all_next(string=True, limit=limit):
        t=norm(str(s))
        if not t: continue
        if vals and re.fullmatch(r"Lot\s+\d+[A-Z]?", t, re.I):
            break
        vals.append(t)
    return vals

def _first(patterns,text):
    for pat in patterns:
        m=re.search(pat,text or "",re.I)
        if m:
            return norm(m.group(1))
    return None

def _money(v):
    try: return float(str(v).replace(",",""))
    except Exception: return None

def _savills_detail(href, lotno, fallback_address, fallback_guide, fallback_rent):
    ds=soup(href,use_browser=True)
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))
    low=text.lower()
    h1=ds.find("h1")
    address=norm(h1.get_text(" ",strip=True)) if h1 else fallback_address

    guide=parse_guide(text) or fallback_guide
    rent=parse_rent(text) or fallback_rent

    labelled_tenure=_first([r"\bTenure\s+(Freehold|Long Leasehold|Leasehold)\b"],text)
    tenure=(labelled_tenure.title() if labelled_tenure else parse_tenure(text))

    # Prefer explicit total/GIA figures. Never let a smaller floor/component figure
    # override an explicitly published overall accommodation figure.
    area_sqft=area_sqm=None
    for pat in [
        r"(?:Accommodation\s+)?([\d,]+(?:\.\d+)?)\s*sq\s*m\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*ft\)",
        r"(?:Total\s+GIA|totalling|amounting to an approx\.?|entire property amounting to an approx\.?)\s*([\d,]+(?:\.\d+)?)\s*sq\s*ft",
        r"\b([\d,]+(?:\.\d+)?)\s*sq\s*ft\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*m\)",
    ]:
        m=re.search(pat,text,re.I)
        if not m: continue
        if len(m.groups())==2:
            a=_money(m.group(1)); b=_money(m.group(2))
            if "sq m" in m.group(0).lower().split("(")[0]: area_sqm,area_sqft=a,b
            else: area_sqft,area_sqm=a,b
        else:
            area_sqft=_money(m.group(1)); area_sqm=(area_sqft/10.7639 if area_sqft else None)
        break

    tenant=_first([
        r"The property is let to\s+(.+?)\s+on\s+(?:a|an)\s+[^.]{0,80}?lease",
        r"Let to\s+(.+?)\s+on\s+(?:a|an)\s+[^.]{0,80}?lease",
        r"fully let to\s+(.+?),?\s+(?:long-standing tenants?[^,]*,?\s+)?on\s+(?:a|an)\s+[^.]{0,80}?lease",
    ],text)
    if tenant:
        tenant=re.sub(r"\s*\(t/a[^)]*\)","",tenant,flags=re.I).strip()

    lease_expiry=_first([
        r"(?:lease\s+)?expir(?:es|ing|y)\s+(\d{1,2}\.\d{1,2}\.20\d{2})",
        r"(?:lease\s+)?expir(?:es|ing|y)\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
        r"until\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    ],text)
    lease_term=_first([r"on\s+(?:a|an)\s+(\d+\s+year)\s+lease",r"(\d+\s+Year)\s+Lease"],text)

    fri=True if re.search(r"full repairing and insuring|effective full repairing and insuring|\bFRI\b",text,re.I) else None

    break_clause=None; break_status=None
    if re.search(r"break option[^.]{0,80}not exercised|break option has\s+not\s+been\s+exercised",text,re.I):
        break_status="Break passed / not exercised"
        break_clause=_first([r"(August\s+20\d{2}\s+break option[^.]{0,80}not exercised)",r"(break option[^.]{0,100}not exercised)"],text) or break_status
    else:
        break_clause=_first([r"(?:tenant(?:'s)?\s+)?break(?: option| clause)?\s+([^.;]{4,100})"],text)

    rent_review=_first([
        r"(rent review in the 5th year to the higher of open market rent or increased in line with RPI)",
        r"(Index Linked Rent Reviews?)",
        r"(rent review[^.]{0,130})",
    ],text)

    ervm=re.search(r"\bERV\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)?",text,re.I)
    erv=_money(ervm.group(1)) if ervm else None

    site_area=None
    sm=re.search(r"(?:Total\s+)?site area(?: of)?\s*([\d.]+)\s*acres?",text,re.I)
    if sm: site_area=_money(sm.group(1))

    parking=_first([
        r"(?:parking|car park)[^.]{0,90}?(?:up to|approximately|approx\.?|for an approx\.?)\s*(\d+)\s*(?:cars|vehicles|car parking spaces)",
        r"(?:approximately|approx\.?)\s*(\d+)\s+(?:dedicated\s+)?(?:on site\s+)?car parking spaces",
    ],text)
    if parking: parking=f"Approx. {parking} spaces"

    property_type=None
    if re.search(r"retail warehouse",text,re.I): property_type="Retail warehouse"
    elif re.search(r"mixed[- ]use",text,re.I): property_type="Mixed use"
    elif re.search(r"retail unit",text,re.I): property_type="Retail"

    development=bool(re.search(r"development potential|potential to develop",text,re.I))
    asset_management=bool(re.search(r"asset management potential",text,re.I))
    refurbishment=bool(re.search(r"total refurbishment|in need of (?:total )?refurbishment|modernisation",text,re.I))
    residential_conversion=bool(re.search(r"potential to convert[^.]{0,100}residential|convert the upper parts to residential",text,re.I))
    listed_status="Grade II listed" if re.search(r"Grade\s+II\s+listed",text,re.I) else None

    covenant_rating=_first([r"D&B Rating\s*-?\s*([A-Z0-9]+)"],text)
    covenant_risk=_first([r"D&B Rating\s*-?\s*[A-Z0-9]+\s*\(([^)]+)\)"],text)
    covenant_turnover=_first([r"Turnover\s*\(20\d{2}\)\s*-?\s*£\s*([\d.]+\s*[mb])"],text)
    if covenant_turnover: covenant_turnover="£"+covenant_turnover
    guarantors="Personal guarantors" if re.search(r"personal guarantors?|personal guarantees",text,re.I) else None

    pitch=None
    if re.search(r"prime pedestrianised pitch|principal pedestrianised retail pitch|high footfall pedestrianised pitch",text,re.I):
        pitch="Prime pedestrianised pitch"
    elif re.search(r"popular local parade|popular parade|prominent pitch",text,re.I):
        pitch="Popular/prominent parade"

    nearby=None
    nm=re.search(r"nearby occupiers include\s+(.+?)(?:\.|$)",text,re.I)
    if nm: nearby=norm(nm.group(1))[:220]

    occupation="Vacant" if re.search(r"vacant possession|\bvacant\b",text,re.I) else ("Tenanted" if tenant or rent else None)
    vat=parse_vat(text)

    return Lot(
        source=SOURCE,url=href,address=address,lot_number=lotno,auction_date="2026-09-02",
        image_url=image_from_soup(ds,href),guide_price=guide,annual_rent=rent,tenure=tenure,
        vat_status=vat,legal_pack_status="LOGIN REQUIRED",legal_pack_url=href,description=text[:5000],
        area_sqft=area_sqft,area_sqm=area_sqm,site_area_acres=site_area,tenant=tenant,
        lease_term=lease_term,lease_expiry=lease_expiry,break_clause=break_clause,break_status=break_status,
        rent_review=rent_review,fri=fri,erv=erv,property_type=property_type,occupation=occupation,
        parking=parking,development_potential=development or None,asset_management=asset_management or None,
        refurbishment=refurbishment or None,residential_conversion=residential_conversion or None,
        listed_status=listed_status,covenant_rating=covenant_rating,covenant_risk=covenant_risk,
        covenant_turnover=covenant_turnover,guarantors=guarantors,pitch=pitch,nearby_occupiers=nearby
    ).finalise()

def collect():
    try:
        s=soup(CURRENT,use_browser=True)
        lots,seen=[],set()
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"]).split("?",1)[0].rstrip("/")
            if not re.match(r"^https://auctions\.savills\.co\.uk/auctions/2-september-2026-241/[^/]+$",href,re.I): continue
            if href in seen: continue
            address=norm(a.get_text(" ",strip=True))
            if not address or address.lower() in {"full details","previous lot","next lot","return to catalogue"}: continue
            before=_strings_before(a); idx=None; lotno=None
            for i in range(len(before)-1,-1,-1):
                m=re.fullmatch(r"Lot\s+(\d+[A-Z]?)",before[i],re.I)
                if m: idx=i; lotno="Lot "+m.group(1); break
            if idx is None: continue
            pre=" ".join(before[idx:])
            if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower(): seen.add(href); continue
            post=" ".join(_strings_after(a))
            try:
                lot=_savills_detail(href,lotno,address,parse_guide(pre),parse_rent(post))
            except Exception:
                lot=Lot(source=SOURCE,url=href,address=address,lot_number=lotno,auction_date="2026-09-02",
                        guide_price=parse_guide(pre),annual_rent=parse_rent(post),tenure=parse_tenure(post),
                        vat_status=parse_vat(post),legal_pack_status="LOGIN REQUIRED",legal_pack_url=href,
                        description=post[:1200]).finalise()
            lots.append(lot); seen.add(href)
        found={x.lot_number for x in lots}; matched=len(KNOWN & found)
        status="LIVE" if matched>=9 else "FAILED"
        return SourceResult(SOURCE,status,lots,f"Exact Savills detail pages parsed: {len(lots)} lots; sanity check {matched}/{len(KNOWN)}")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
