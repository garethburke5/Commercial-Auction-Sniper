import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, nearest_card

SOURCE = "Savills Auctions"
BASE = "https://auctions.savills.co.uk"
UPCOMING = BASE + "/upcoming-auctions"

COMMERCIAL_POSITIVE = re.compile(
    r"commercial|retail|shop\b|office\b|industrial|warehouse|business centre|market\b|"
    r"mixed[- ]use|public house|\bpub\b|hotel\b|care (?:home|facility)|trade park|"
    r"investment let|commercial unit|commercial investment|retail investment|light industrial|"
    r"rail arches|development site|employment land|petrol station|veterinary|restaurant|cafe|"
    r"takeaway|betting office|trade counter|workshop|garage|showroom|leisure",
    re.I,
)
RESIDENTIAL_ONLY = re.compile(r"\b(flat|maisonette|house|bungalow|apartment|residential dwelling)\b", re.I)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


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
    if re.search(r"/auctions/.+-\d{4,6}/?$", href, re.I):
        return href.split("?")[0].rstrip("/")
    if "index.php" in href and "id=" in href and "view=commission" in href:
        return href
    return None


def _card_block(a):
    node = a
    fallback = norm(a.get_text(" ", strip=True))
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = norm(node.get_text(" ", strip=True))
        if not (20 <= len(text) <= 2200):
            continue
        fallback = text
        if _lot_no(text) is not None and re.search(r"guide price|available at|sold prior|withdrawn|lot\s*\d+", text, re.I):
            return text
    return fallback


def _auction_dates(text, href=""):
    """Return (start_date, end_date) for a Savills sale card/title."""
    text = norm(text)
    m = re.search(r"\b(\d{1,2})\s*&\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b", text, re.I)
    if m and m.group(3).lower() in MONTHS:
        y, mo = int(m.group(4)), MONTHS[m.group(3).lower()]
        return date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        return d, d
    # URL fallback: /auctions/29-september-2026-243
    m = re.search(r"/auctions/(\d{1,2})-([a-z]+)-(20\d{2})-\d+", href or "", re.I)
    if m and m.group(2).lower() in MONTHS:
        d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        return d, d
    return None, None


def _discover_next_auction():
    """
    Discover the active/next Savills auction from Savills' own auction calendar.
    No catalogue date or auction id is hard-coded. The earliest sale whose end date
    is today or later wins, so the collector rolls forward automatically after a sale.
    """
    try:
        us = soup(UPCOMING, use_browser=False)
    except Exception:
        us = soup(UPCOMING, use_browser=True)

    candidates = {}
    today = date.today()
    for a in us.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"/auctions/[^/]+-\d+$", href, re.I):
            continue
        card = nearest_card(a, 2500) or norm(a.get_text(" ", strip=True))
        start, end = _auction_dates(card, href)
        if not start:
            # Fetch the catalogue title only when the calendar card omitted its date.
            try:
                cs = soup(href, use_browser=False)
                title = norm((cs.find("h1") or cs.find("title")).get_text(" ", strip=True))
                start, end = _auction_dates(title, href)
            except Exception:
                pass
        if not start or not end or end < today:
            continue
        candidates[href] = (start, end, card)

    if not candidates:
        return None
    href, (start, end, card) = min(candidates.items(), key=lambda item: (item[1][0], item[0]))
    return {"catalogue": href, "start": start, "end": end, "label": card}


def _discover_commercial_feed(auction):
    """Resolve the commercial-only feed from the selected auction itself."""
    catalogue = auction["catalogue"]
    try:
        cs = soup(catalogue, use_browser=False)
    except Exception:
        cs = soup(catalogue, use_browser=True)

    feed_candidates = []
    for a in cs.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "")
        label = norm(a.get_text(" ", strip=True)).lower()
        if "property_type-253" in href or "commercial section" in label:
            feed_candidates.append(href)

    # Generic filtered route works on Savills catalogues when the explicit
    # Commercial Section link is not exposed in static markup.
    feed_candidates.append(catalogue + "/page-1/quantity-100/property_type-253/sort-by-0")

    seen = set()
    for feed in feed_candidates:
        feed = feed.split("?")[0] if "property_type-253" not in feed else feed
        if feed in seen:
            continue
        seen.add(feed)
        try:
            ds = soup(feed, use_browser=False)
        except Exception:
            try:
                ds = soup(feed, use_browser=True)
            except Exception:
                continue
        targets = {}
        for a in ds.find_all("a", href=True):
            href = _detail_href(a)
            if not href:
                continue
            card = _card_block(a)
            lot_no = _lot_no(card)
            if lot_no in {None, 0}:
                continue
            targets[href] = {"source_commercial": True, "card": card, "lot_no": lot_no}
        if targets:
            return feed, targets
    return None, {}


def _offered_date(text, auction):
    """Prefer the actual day stated on the lot page, else sale end date."""
    m = re.search(r"To be offered on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*(\d{1,2})\s+([A-Za-z]+)", text or "", re.I)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(auction["start"].year, MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except Exception:
            pass
    return auction["end"].isoformat()


def _detail(href, auction, source_commercial=False):
    try:
        ds = soup(href, use_browser=False)
    except Exception:
        ds = soup(href, use_browser=True)
    main = ds.find("main") or ds
    text = norm(main.get_text(" ", strip=True))
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
        auction_date=_offered_date(text, auction), image_url=image_from_soup(ds, href),
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
    auction = _discover_next_auction()
    if not auction:
        return SourceResult(SOURCE, "FAILED", [], "Could not discover the next Savills auction from the auction calendar")

    feed, targets = _discover_commercial_feed(auction)
    if not targets:
        scope = tuple(d.isoformat() for d in ({auction['start'], auction['end']}))
        return SourceResult(
            SOURCE, "CATALOGUE PENDING", [],
            f"Next auction discovered automatically: {auction['start'].isoformat()} to {auction['end'].isoformat()}; commercial section not published yet",
            authoritative_snapshot=False, scope_dates=scope,
        )

    expected = len(targets)
    lots = []
    rejected = failures = 0
    for href, meta in targets.items():
        try:
            lot = _detail(href, auction, source_commercial=True)
            if lot:
                lots.append(lot)
            else:
                rejected += 1
        except Exception as exc:
            failures += 1
            print("SAVILLS_DETAIL_FAIL", href, repr(exc))

    status = "LIVE" if lots and len(lots) == expected else "DEGRADED" if lots else "FAILED"
    scope = tuple(sorted({auction["start"].isoformat(), auction["end"].isoformat()}))
    return SourceResult(
        SOURCE, status, lots,
        f"Auto-selected next Savills auction {auction['start'].isoformat()} to {auction['end'].isoformat()}; commercial feed {feed}; {len(targets)} discovered; {len(lots)} published; {rejected} rejected; {failures} detail failures",
        expected_count=expected,
        discovered_count=len(targets),
        authoritative_snapshot=(status == "LIVE"),
        scope_dates=scope,
    )
