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

    area_sqm=area_sqft=None
    pairs=re.findall(r"([\d,]+(?:\.\d+)?)\s*sq\.?m\.?\s*\(([\d,]+(?:\.\d+)?)\s*sq\.?ft\.?(?:\s*approx\.?)?\)",text,re.I)
    if pairs:
        sqm_vals=[_number(a) for a,_b in pairs if _number(a)]
        sqft_vals=[_number(b) for _a,b in pairs if _number(b)]
        if sqm_vals and sqft_vals:
            area_sqm=sum(sqm_vals)
            area_sqft=sum(sqft_vals)
    else:
        m=re.search(r"Accommodation\s+[^.]{0,140}?([\d,]+(?:\.\d+)?)\s*sq\.?ft",text,re.I)
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

    tenancy=_first([
        r"Tenancy Details\s+(.+?)(?=Rights of way|Auctioneer(?:'s|’s) Note|Pre-auction Offers|Viewings|DISCLAIMER|$)",
    ],text)
    if tenancy:
        start=_first([
            r"(?:let|lease)[^.;]{0,70}?from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
            r"(?:let|lease)[^.;]{0,70}?from\s+(\d{1,2}[./-]\d{1,2}[./-]20\d{2})",
        ],tenancy)
        if start:
            lot.lease_start=start

        expiry=_first([
            r"expir(?:es|ing|y)\s+(?:on\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
            r"expir(?:es|ing|y)\s+(?:on\s+)?(\d{1,2}[./-]\d{1,2}[./-]20\d{2})",
        ],tenancy)
        if expiry:
            lot.lease_expiry=expiry

        term=_first([
            r"(?:on|for)\s+(?:a\s+)?(?:term\s+of\s+)?(\d+(?:\.\d+)?\s*years?)\b",
        ],tenancy)
        if term:
            lot.lease_term=term
            if not lot.lease_expiry and start:
                years=re.search(r"\d+(?:\.\d+)?",term)
                derived=_derive_expiry(start,years.group(0) if years else None)
                if derived:
                    lot.lease_expiry=derived

        tenant=_first([
            r"(?:let|leased)\s+to\s+(.+?)(?=\s+(?:for|from|on|at a rental|at a rent|paying)|[.;])",
            r"Tenant\s*[:\-]\s*(.+?)(?=[.;])",
        ],tenancy)
        if tenant and len(tenant)<120:
            lot.tenant=tenant

        rent=_first([
            r"rental figure of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
            r"rent(?:al)?(?: figure)?(?: of| at)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)",
        ],tenancy)
        if rent:
            lot.annual_rent=_number(rent)

        review=_first([
            r"(subject to\s+\d+\s*year\s+reviews?)",
            r"(subject to\s+reviews?[^.;]{0,90})",
            r"(rent review[^.;]{0,140})",
            r"(index[- ]linked rent review[^.;]{0,120})",
        ],tenancy)
        if review:
            lot.rent_review=review

        lot.occupation="Tenanted"

    if re.search(r"vacant possession|commercial vacant",text,re.I) and not tenancy:
        lot.occupation="Vacant"

    if re.search(r"retail investment|retail unit|retail property",text,re.I):
        lot.property_type="Retail"
    elif re.search(r"industrial|warehouse|workshop",text,re.I):
        lot.property_type="Industrial"
    elif re.search(r"mixed use|mixed-use",text,re.I):
        lot.property_type="Mixed use"
    elif re.search(r"office",text,re.I):
        lot.property_type="Office"

    if re.search(r"highly sought[- ]after|popular location|prominent position|prominent location",text,re.I):
        phrase=_first([
            r"(highly sought[- ]after [^.]{0,90})",
            r"(prominent (?:position|location)[^.]{0,80})",
        ],text)
        lot.pitch=phrase or "Established/prominent location"

    if re.search(r"full repairing and insuring|\bFRI\b",text,re.I):
        lot.fri=True
    if not lot.rent_review:
        review=_first([r"(rent review[^.]{0,140})",r"(index[- ]linked rent review[^.]{0,120})"],text)
        if review:
            lot.rent_review=review
    brk=_first([r"((?:tenant|landlord)[^.;]{0,40}break[^.;]{0,120})",r"(break option[^.;]{0,120})"],text)
    if brk:
        lot.break_clause=brk

    lot.development_potential=True if re.search(r"development potential|development opportunity|subject to planning",text,re.I) else lot.development_potential
    lot.asset_management=True if re.search(r"asset management opportunity|asset management potential",text,re.I) else lot.asset_management

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
