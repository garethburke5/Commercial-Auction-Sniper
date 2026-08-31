import re
from datetime import datetime
from urllib.parse import urljoin
from .core import SourceResult, norm
from .utils import soup, nearest_card, detail_lot

SOURCE="Bond Wolfe"
BASE="https://www.bondwolfe.com"
URL=BASE+"/auctions/properties/"


def _exact_property_image(detail_soup, page_url):
    """Return the Bond Wolfe lot photograph, never the site-wide header image."""
    candidates=[]
    for tag in detail_soup.find_all(["img", "source", "a"]):
        vals=[]
        for attr in ("src", "data-src", "data-lazy-src", "data-original", "href"):
            v=tag.get(attr)
            if v:
                vals.append(v)
        for attr in ("srcset", "data-srcset"):
            ss=tag.get(attr)
            if ss:
                vals.extend(part.strip().split(" ")[0] for part in ss.split(",") if part.strip())
        for v in vals:
            u=urljoin(page_url,v)
            low=u.lower()
            if "cdn.eigpropertyauctions.co.uk/ams/images/" not in low:
                continue
            if any(x in low for x in ("logo","icon","placeholder","map","floorplan","documents/")):
                continue
            score=0
            if "web_large" in low: score+=30
            if "web_medium" in low: score+=25
            if "web_small" in low: score+=10
            if re.search(r"/auction/\d+/\d+_web_",low): score+=20
            candidates.append((score,u))
    if not candidates:
        raw=str(detail_soup).replace("\\/","/")
        for u in re.findall(r'https://cdn\.eigpropertyauctions\.co\.uk/ams/images/[^"\'<>\s]+',raw,re.I):
            low=u.lower()
            if any(x in low for x in ("logo","icon","placeholder","map","floorplan","documents/")):
                continue
            score=(30 if "web_large" in low else 25 if "web_medium" in low else 10 if "web_small" in low else 0)
            candidates.append((score,u))
    if not candidates:
        return None
    candidates.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
    return candidates[0][1]


def _first(patterns, text):
    for pat in patterns:
        m=re.search(pat,text or "",re.I)
        if m:
            return norm(m.group(1))
    return None


def _number(value):
    try:
        return float(str(value).replace(",",""))
    except Exception:
        return None


def _clean_ordinal_date(value):
    return re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b",r"\1",norm(value or ""),flags=re.I)


def _derive_expiry(start, years):
    """Derive expiry only when Bond Wolfe explicitly gives both commencement and fixed term."""
    if not start or not years:
        return None
    raw=_clean_ordinal_date(start)
    for fmt in ("%d %B %Y","%d %b %Y","%d/%m/%Y","%d-%m-%Y","%d.%m.%Y"):
        try:
            d=datetime.strptime(raw,fmt)
            y=d.year+int(float(years))
            try:
                out=d.replace(year=y)
            except ValueError:
                out=d.replace(year=y,day=28)
            return out.strftime("%d %B %Y").lstrip("0")
        except Exception:
            pass
    return None


def _rich_detail(lot, ds):
    """Populate source-labelled Bond Wolfe particulars from the exact lot page."""
    main=ds.find("main") or ds
    text=norm(main.get_text(" ",strip=True))

    lm=re.search(r"\bLot\s+(\d+[A-Z]?)\s+(?:Commercial Investment|Commercial Vacant|Mixed Use|Commercial)",text,re.I)
    if lm:
        lot.lot_number="Lot "+lm.group(1)

    # Guide must come from the exact lot header, not related-property cards/footer examples.
    gm=re.search(r"Guide price\*?\s*£\s*([\d,]+(?:\.\d+)?)",text,re.I)
    if gm:
        lot.guide_price=_number(gm.group(1))

    area_sqm=area_sqft=None
    pairs=re.findall(r"([\d,]+(?:\.\d+)?)\s*sq\.?m\.?\s*\(([\d,]+(?:\.\d+)?)\s*sq\.?ft\.?(?:\s*approx\.?)?\)",text,re.I)
    if pairs:
        sqm_vals=[_number(a) for a,_b in pairs if _number(a)]
        sqft_vals=[_number(b) for _a,b in pairs if _number(b)]
        if sqm_vals and sqft_vals:
            area_sqm=sum(sqm_vals)
            area_sqft=sum(sqft_vals)
    else:
        # Some Bond Wolfe pages print imperial first, e.g. 2028 sq ft (188.4 sqm).
        reverse_pairs=re.findall(r"([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft\s*\(([\d,]+(?:\.\d+)?)\s*sq\.?m\.?\)",text,re.I)
        if reverse_pairs:
            sqft_vals=[_number(a) for a,_b in reverse_pairs if _number(a)]
            sqm_vals=[_number(b) for _a,b in reverse_pairs if _number(b)]
            if sqm_vals and sqft_vals:
                area_sqm=sum(sqm_vals); area_sqft=sum(sqft_vals)
        else:
            m=re.search(r"Accommodation\s+[^.]{0,180}?([\d,]+(?:\.\d+)?)\s*sq\.?ft",text,re.I)
            if m:
                area_sqft=_number(m.group(1)); area_sqm=area_sqft/10.7639 if area_sqft else None
    if area_sqft:
        lot.area_sqft=round(area_sqft,2)
        lot.area_sqm=round(area_sqm,2) if area_sqm else None

    epc=_first([
        r"Energy Performance Rating\s+([A-G](?:\s*\([0-9]+\))?)\b",
        r"Energy Performance Certificate\s+([A-G](?:\s*\([0-9]+\))?)\b",
    ],text)
    if epc:
        lot.epc=epc.rstrip(".")

    tenure=_first([r"\bTenure\s+(Freehold|Leasehold|Long Leasehold|Virtual Freehold)\b"],text)
    if tenure:
        lot.tenure=tenure.title()

    # Current whole-property income outranks any component rent. Addenda outrank
    # the original particulars because Bond Wolfe explicitly uses them to correct income.
    total_rent=_first([
        r"Addendum:\s*Please note the current rental income is\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:PA|p\.?a\.?|per annum)",
        r"Current rental income\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:PA|p\.?a\.?|per annum)",
        r"Current gross income:\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:PA|p\.?a\.?|per annum)",
        r"Total Income:\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:PA|p\.?a\.?|per annum)",
    ],text)
    if total_rent:
        lot.annual_rent=_number(total_rent)

    # Lease Details may be separate from Tenancy Details on mixed-use lots.
    lease_details=_first([
        r"Lease Details\s+(.+?)(?=Tenancy Details|Value Added Tax|Rights of way|Auctioneer(?:'s|’s) Note|Pre-auction Offers|Viewings|DISCLAIMER|$)",
    ],text)
    tenancy=_first([
        r"Tenancy Details\s+(.+?)(?=Value Added Tax|Rights of way|Auctioneer(?:'s|’s) Note|Pre-auction Offers|Viewings|DISCLAIMER|$)",
    ],text)
    primary=lease_details or tenancy
    if primary:
        start=_first([
            r"(?:with effect from|from)\s+(\d{1,2}(?:st|nd|rd|th)?[./-]\d{1,2}[./-]20\d{2})",
            r"(?:with effect from|from)\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        ],primary)
        if start:
            lot.lease_start=start

        expiry=_first([
            r"expir(?:es|ing|y)\s+(?:on\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
            r"expir(?:es|ing|y)\s+(?:on\s+)?(\d{1,2}[./-]\d{1,2}[./-]20\d{2})",
        ],primary)
        if expiry:
            lot.lease_expiry=expiry

        term=_first([r"(?:on|for|by way of)\s+(?:a\s+)?(?:term\s+of\s+)?(\d+(?:\.\d+)?\s*years?)\s+lease"],primary)
        if term:
            lot.lease_term=term
            if not lot.lease_expiry and start:
                years=re.search(r"\d+(?:\.\d+)?",term)
                derived=_derive_expiry(start,years.group(0) if years else None)
                if derived:
                    lot.lease_expiry=derived

        tenant=_first([
            r"lease to\s+(.+?)(?=,|\s+with effect|\s+from|\s+for|[.;])",
            r"(?:let|leased)\s+to\s+(.+?)(?=\s+(?:for|from|on|at a rental|at a rent|paying)|[.;])",
            r"Tenant\s*[:\-]\s*(.+?)(?=[.;])",
        ],primary)
        if tenant and len(tenant)<120:
            lot.tenant=tenant

        review=_first([
            r"(subject to\s+\d+\s*year\s+reviews?)",
            r"(subject to\s+reviews?[^.;]{0,90})",
            r"(rent review[^.;]{0,140})",
            r"(index[- ]linked rent review[^.;]{0,120})",
        ],primary)
        if review:
            lot.rent_review=review

    # If no whole-property income was stated, use the single tenancy rent only.
    if not total_rent and tenancy:
        rent=_first([
            r"rental figure of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
            r"rent(?:al)?(?: figure)?(?: of| at)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)",
        ],tenancy)
        if rent:
            lot.annual_rent=_number(rent)

    mixed=bool(re.search(r"\bMixed Use\b|mixed use investment|mixed-use investment",text,re.I))
    flat_numbers=set(re.findall(r"\bFlat\s+(\d+)\b",(tenancy or ""),re.I))
    flat_count=len(flat_numbers)
    vacant_flats=len(re.findall(r"Flat\s+\d+\s*-\s*Vacant",tenancy or "",re.I))
    if mixed:
        lot.property_type="Mixed use"
        lot.occupation="Multi-let" if flat_count or lease_details else "Tenanted"

        occupiers=[]
        for pat in (r"license to\s+(.+?)(?=\s+with effect|\s+for a term|[.;])",
                    r"lease to\s+(.+?)(?=\s+with effect|\s+for a term|[.;])",
                    r"trading as\s+(.+?)(?=,|\.| and \d|$)"):
            for m in re.finditer(pat,tenancy or text,re.I):
                name=norm(m.group(1)).strip("'\"“”")
                if name and len(name)<80 and name.lower() not in {x.lower() for x in occupiers}:
                    occupiers.append(name)
        if occupiers:
            lot.tenant=" / ".join(occupiers[:3]) + (f" + {flat_count} flats" if flat_count else "")
        elif lot.tenant and flat_count:
            lot.tenant=f"{lot.tenant} + {flat_count} flats"

        if vacant_flats:
            lot.occupation=f"Part-let / {vacant_flats} flat{'s' if vacant_flats != 1 else ''} vacant"
        if re.search(r"tenant of flat\s+\d+\s+has served notice",text,re.I):
            lot.occupation="Multi-let; one flat under notice"
    elif tenancy or lease_details:
        lot.occupation="Tenanted"

    if re.search(r"vacant possession|commercial vacant",text,re.I) and not tenancy and not lease_details:
        lot.occupation="Vacant"

    if not lot.property_type:
        if re.search(r"retail investment|retail unit|retail property",text,re.I):
            lot.property_type="Retail"
        elif re.search(r"industrial|warehouse|workshop",text,re.I):
            lot.property_type="Industrial"
        elif re.search(r"office",text,re.I):
            lot.property_type="Office"

    if re.search(r"rear surfaced parking|parking and loading area|rear parking",text,re.I):
        lot.parking="Rear parking/loading area"

    if re.search(r"busy pedestrianised|prominent position|highly sought[- ]after|popular location|prominent location",text,re.I):
        phrase=_first([
            r"(prominent position[^.]{0,100})",
            r"(busy pedestrianised [^.]{0,100})",
            r"(highly sought[- ]after [^.]{0,90})",
        ],text)
        lot.pitch=phrase or "Established/prominent location"

    if re.search(r"full repairing and insuring|\bFRI\b",text,re.I):
        lot.fri=True
    if not lot.rent_review:
        review=_first([r"(rent review[^.]{0,140})",r"(index[- ]linked rent review[^.]{0,120})"],text)
        if review:
            lot.rent_review=review

    brk=_first([
        r"(option to break on\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"(option to break on\s+\d{1,2}(?:st|nd|rd|th)?[./-]\d{1,2}[./-]20\d{2})",
        r"((?:tenant|landlord)[^.;]{0,40}break[^.;]{0,120})",
        r"(break option[^.;]{0,120})",
    ],text)
    if brk:
        lot.break_clause=brk

    # VAT language that explicitly sends the buyer to the legal pack is not
    # evidence of VAT being payable; retain it as VERIFY.
    if re.search(r"whether or not VAT will be chargeable[^.]{0,100}refer to the Legal Pack",text,re.I):
        lot.vat_status="MENTIONED - VERIFY"

    lot.development_potential=True if re.search(r"development potential|development opportunity|subject to planning",text,re.I) else lot.development_potential
    lot.asset_management=True if re.search(r"asset management opportunity|asset management potential|further asset management potential",text,re.I) else lot.asset_management
    lot.refurbishment=True if re.search(r"potential for refurbishment|refurbishment potential|offer the potential for refurbishment",text,re.I) else lot.refurbishment

    lot.description=text[:5000]
    return lot.finalise()


def collect():
    try:
        s=soup(URL,use_browser=True)
        seen,lots=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I):
                continue
            href=href.rstrip("/")+"/"
            if href in seen: continue
            seen.add(href)
            card=nearest_card(a)
            lot=detail_lot(SOURCE,href,seed=card,auction_date="2026-09-10",force_commercial=False,use_browser=True)
            if lot:
                try:
                    ds=soup(href,use_browser=False)
                    exact=_exact_property_image(ds,href)
                    if exact:
                        lot.image_url=exact
                    lot=_rich_detail(lot,ds)
                except Exception as e:
                    print("BOND_WOLFE_RICH_DETAIL_FAIL",href,repr(e))
                lots.append(lot.finalise())
        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,f"10 Sep exact property URLs: {len(lots)} commercial/mixed-use lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
