import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, nearest_card

SOURCE = "Savills Auctions"
BASE = "https://auctions.savills.co.uk"
CATALOGUE = BASE + "/auctions/15-september-2026-242"
# Savills' commercial section is offered on Wednesday 16 September.
AUCTION_DATE = "2026-09-16"
# Savills' own commercial-property filter. quantity-100 keeps the complete
# current commercial section on one results page (83 lots at time of repair).
COMMERCIAL_FEED = BASE + "/auctions/15--16-september-2026-242/page-1/quantity-100/property_type-253/sort-by-0"

COMMERCIAL_POSITIVE = re.compile(
    r"commercial|retail|shop\b|office\b|industrial|warehouse|business centre|market\b|"
    r"mixed[- ]use|public house|\bpub\b|hotel\b|care (?:home|facility)|trade park|"
    r"investment let|commercial unit|commercial investment|retail investment|light industrial|"
    r"rail arches|development site|employment land|petrol station|veterinary|restaurant|cafe|"
    r"takeaway|betting office|trade counter|workshop|garage|showroom|leisure",
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
    if re.search(r"mixed[- ]use|commercial|retail|shop\b|office\b|industrial|warehouse|market\b|pub\b|hotel\b|care (?:home|facility)|petrol station|veterinary|takeaway|betting office|trade counter|workshop|garage|showroom|leisure", text, re.I):
        return True
    return not RESIDENTIAL_ONLY.search(text)


def _lot_no(card):
    m = re.search(r"\bLot\s*#?\s*(\d{1,3})[A-Za-z]?\b", card or "", re.I)
    return int(m.group(1)) if m else None


def _detail_href(a):
    href = urljoin(BASE, a.get("href") or "")
    if "savills.co.uk" not in href:
        return None
    # Current catalogue uses both SEO auction-detail URLs and legacy
    # index.php?id=...&view=commission exact detail pages.
    if re.search(r"/auctions/.+-\d{4,6}/?$", href, re.I):
        return href.split("?")[0].rstrip("/")
    if "index.php" in href and "id=" in href and "view=commission" in href:
        return href
    return None


def _discover():
    """Use Savills' own Commercial property filter as the source of truth.

    The previous collector stopped at catalogue page 21 and therefore missed
    later commercial lots after Savills expanded the sale to 262 properties.
    The source now exposes a dedicated property_type-253 commercial feed with
    quantity-100, so every lot on that feed is accepted as source-classified
    commercial. A full catalogue sweep remains as a resilience fallback.
    """
    urls = {}
    pages_checked = 0

    # Primary: auctioneer's dedicated commercial feed.
    try:
        ds = soup(COMMERCIAL_FEED, use_browser=False)
    except Exception:
        ds = soup(COMMERCIAL_FEED, use_browser=True)
    pages_checked += 1
    for a in ds.find_all("a", href=True):
        href = _detail_href(a)
        if not href:
            continue
        card = nearest_card(a, 4000)
        lot_no = _lot_no(card)
        # Avoid the synthetic Lot 0 commercial-section navigation card.
        if lot_no == 0:
            continue
        urls[href] = {"source_commercial": True, "card": card}

    # Fallback / cross-check: sweep all currently visible catalogue pages.
    # There are 25 pages today; use 35 headroom so catalogue growth cannot
    # silently truncate the collector again.
    for page_no in range(1, 36):
        page = CATALOGUE if page_no == 1 else f"{CATALOGUE}/page-{page_no}"
        try:
            cds = soup(page, use_browser=False)
        except Exception:
            try:
                cds = soup(page, use_browser=True)
            except Exception:
                continue
        pages_checked += 1
        text = norm(cds.get_text(" ", strip=True)).lower()
        # Once Savills returns an empty/non-catalogue page after the known
        # catalogue tail, stop instead of wasting requests.
        if page_no > 25 and "lot " not in text and "guide price" not in text:
            break
        for a in cds.find_all("a", href=True):
            href = _detail_href(a)
            if not href:
                continue
            card = nearest_card(a, 4000)
            lot_no = _lot_no(card)
            source_commercial = lot_no is not None and 201 <= lot_no <= 300
            if source_commercial or _is_commercial(card):
                urls.setdefault(href, {"source_commercial": source_commercial, "card": card})

    return urls, pages_checked


def _detail(href, source_commercial=False):
    try:
        ds = soup(href, use_browser=False)
    except Exception:
        ds = soup(href, use_browser=True)
    main = ds.find("main") or ds
    text = norm(main.get_text(" ", strip=True))
    # A lot selected by Savills' own Commercial filter is authoritative even
    # if its detail copy omits one of our keyword signals.
    if not source_commercial and not _is_commercial(text):
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
        (r"mixed[- ]use", "Mixed use"), (r"industrial|warehouse|light industrial|rail arches|workshop", "Industrial"),
        (r"retail|shop\b|market\b|betting office|showroom", "Retail"), (r"office\b|business centre", "Office"),
        (r"hotel\b", "Hotel"), (r"public house|\bpub\b", "Pub"), (r"care (?:home|facility)", "Care facility"),
        (r"petrol station", "Petrol station"), (r"veterinary", "Veterinary"), (r"leisure", "Leisure")
    ]:
        if re.search(pat, text, re.I):
            property_type = label
            break
    if source_commercial and not property_type:
        property_type = "Commercial"

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
    targets, pages_checked = _discover()
    lots = []
    rejected = failures = 0
    for href, meta in targets.items():
        try:
            lot = _detail(href, source_commercial=meta.get("source_commercial", False))
            if lot:
                lots.append(lot)
            else:
                rejected += 1
        except Exception as exc:
            failures += 1
            print("SAVILLS_DETAIL_FAIL", href, repr(exc))
    status = "LIVE" if lots else "FAILED"
    return SourceResult(
        SOURCE, status, lots,
        f"15/16 Sep dedicated commercial feed + {pages_checked - 1} catalogue pages; {len(targets)} source-classified/explicit commercial exact pages discovered; {len(lots)} published; {rejected} rejected; {failures} detail failures"
    )
