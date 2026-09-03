import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, nearest_card

SOURCE = "Savills Auctions"
BASE = "https://auctions.savills.co.uk"
CATALOGUE = BASE + "/auctions/15-september-2026-242"
AUCTION_DATE = "2026-09-15"

COMMERCIAL_POSITIVE = re.compile(
    r"commercial|retail|shop\b|office\b|industrial|warehouse|business centre|market\b|"
    r"mixed[- ]use|public house|\bpub\b|hotel\b|care (?:home|facility)|trade park|"
    r"investment let|commercial unit|commercial investment|retail investment|light industrial|"
    r"rail arches|development site|employment land|petrol station|veterinary|restaurant|cafe",
    re.I,
)
RESIDENTIAL_ONLY = re.compile(r"\b(flat|maisonette|house|bungalow|apartment|residential dwelling)\b", re.I)


def _money(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def _first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text or "", re.I)
        if m:
            return norm(m.group(1))
    return None


def _is_commercial(text):
    text = text or ""
    if not COMMERCIAL_POSITIVE.search(text):
        return False
    if re.search(r"mixed[- ]use|commercial|retail|shop\b|office\b|industrial|warehouse|market\b|pub\b|hotel\b|care (?:home|facility)|petrol station|veterinary", text, re.I):
        return True
    return not RESIDENTIAL_ONLY.search(text)


def _lot_no(card):
    m = re.search(r"\bLot\s*#?\s*(\d{1,3})[A-Za-z]?\b", card or "", re.I)
    return int(m.group(1)) if m else None


def _discover():
    """Discover the whole live Savills commercial section.

    Savills explicitly labels Lots 201-300 as its Commercial Section for the
    15/16 September sale. We therefore use the auctioneer's own lot-number
    classification rather than trying to infer commercial use from residential
    catalogue cards. All catalogue pages are scanned because the commercial
    section is paginated near the end of the sale catalogue.
    """
    urls = set()
    pages_checked = 0

    for page_no in range(1, 22):
        page = CATALOGUE if page_no == 1 else f"{CATALOGUE}/page-{page_no}"
        try:
            ds = soup(page, use_browser=False)
        except Exception:
            try:
                ds = soup(page, use_browser=True)
            except Exception:
                continue
        pages_checked += 1

        for a in ds.find_all("a", href=True):
            href = urljoin(BASE, a.get("href"))
            if "savills.co.uk/auctions/" not in href or "-242/" not in href:
                continue
            if href.rstrip("/") == CATALOGUE.rstrip("/"):
                continue
            if not re.search(r"-\d{4,6}/?$", href):
                continue

            card = nearest_card(a, 3500)
            lot_no = _lot_no(card)
            source_classified_commercial = lot_no is not None and 201 <= lot_no <= 300
            explicit_commercial = _is_commercial(card)
            if source_classified_commercial or explicit_commercial:
                urls.add(href.split("?")[0].rstrip("/"))

    return sorted(urls), pages_checked


def _detail(href):
    try:
        ds = soup(href, use_browser=False)
    except Exception:
        ds = soup(href, use_browser=True)
    main = ds.find("main") or ds
    text = norm(main.get_text(" ", strip=True))
    if not _is_commercial(text):
        return None

    h1 = ds.find("h1")
    address = norm(h1.get_text(" ", strip=True)) if h1 else href.rstrip("/").split("/")[-1].replace("-", " ").title()
    lot_number = _first([r"\bLot\s*#?\s*(\d+[A-Za-z]?)\b"], text)
    if lot_number:
        lot_number = "Lot " + lot_number

    guide = parse_guide(text)
    rent = parse_rent(text)
    tenure = parse_tenure(text)
    vat = parse_vat(text)

    area_sqft = area_sqm = None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft", text, re.I)
    if m:
        area_sqft = _money(m.group(1))
        area_sqm = round(area_sqft / 10.7639, 2) if area_sqft else None
    else:
        m = re.search(r"([\d,]+(?:\.\d+)?)\s*sq\.?\s*m", text, re.I)
        if m:
            area_sqm = _money(m.group(1))
            area_sqft = round(area_sqm * 10.7639, 2) if area_sqm else None

    tenant = _first([
        r"(?:property|unit) is let to\s+(.+?)\s+on\s+(?:a|an)\s+[^.]{0,140}?lease",
        r"Let to\s+(.+?)\s+on\s+(?:a|an)\s+[^.]{0,140}?lease",
    ], text)
    lease_term = _first([r"on\s+(?:a|an)\s+(\d+\s+year)\s+(?:FR&I\s+)?lease", r"(\d+\s+year)\s+lease"], text)
    lease_expiry = _first([r"(?:expiry|expiring|reversion)\s+(?:in\s+)?(20\d{2})", r"until\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})"], text)
    break_clause = _first([r"(break (?:option|clause)[^.]{0,120})", r"(mutual tenant and landlord break option[^.]{0,120})"], text)
    rent_review = _first([r"(rent review[^.]{0,140})"], text)
    fri = True if re.search(r"full repairing and insuring|\bFR&I\b|\bFRI\b", text, re.I) else None

    occupation = None
    if re.search(r"full vacant possession|\bvacant\b", text, re.I) and not rent:
        occupation = "Vacant"
    elif tenant or rent:
        occupation = "Tenanted"

    property_type = None
    for pat, label in [
        (r"mixed[- ]use", "Mixed use"), (r"industrial|warehouse|light industrial|rail arches", "Industrial"),
        (r"retail|shop\b|market\b", "Retail"), (r"office\b|business centre", "Office"),
        (r"hotel\b", "Hotel"), (r"public house|\bpub\b", "Pub"), (r"care (?:home|facility)", "Care facility"),
        (r"petrol station", "Petrol station"), (r"veterinary", "Veterinary")
    ]:
        if re.search(pat, text, re.I):
            property_type = label
            break

    return Lot(
        source=SOURCE, url=href, address=address, lot_number=lot_number,
        auction_date=AUCTION_DATE, image_url=image_from_soup(ds, href),
        guide_price=guide, annual_rent=rent, tenure=tenure, vat_status=vat,
        legal_pack_status="LOGIN REQUIRED", legal_pack_url=href,
        description=text[:5000], area_sqft=area_sqft, area_sqm=area_sqm,
        tenant=tenant, lease_term=lease_term, lease_expiry=lease_expiry,
        break_clause=break_clause, rent_review=rent_review, fri=fri,
        property_type=property_type, occupation=occupation,
        development_potential=True if re.search(r"development potential|conversion potential", text, re.I) else None,
        asset_management=True if re.search(r"asset management potential", text, re.I) else None,
        residential_conversion=True if re.search(r"residential conversion|conversion to residential", text, re.I) else None,
    ).finalise()


def collect():
    urls, pages_checked = _discover()
    lots = []
    rejected = failures = 0
    for href in urls:
        try:
            lot = _detail(href)
            if lot:
                lots.append(lot)
            else:
                rejected += 1
        except Exception:
            failures += 1
    status = "LIVE" if lots else "FAILED"
    return SourceResult(
        SOURCE, status, lots,
        f"15/16 Sep catalogue pages {pages_checked}; {len(urls)} source-classified/explicit commercial exact pages discovered; {len(lots)} published; {rejected} rejected; {failures} detail failures"
    )
