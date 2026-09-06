import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, legal_pack

SOURCE = "Symonds & Sampson"
BASE = "https://auctions.symondsandsampson.co.uk"
EVENTS = BASE + "/events/property-auction/symonds-and-sampson-property-auctions?eventdate=upcoming"

DATE_RE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b", re.I)
MONTHS = {name.lower(): i for i, name in enumerate((
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
), 1)}

COMMERCIAL_EXTRA = (
    "public house", "pub", "commercial", "mixed use", "mixed-use", "retail", "shop", "office",
    "industrial", "warehouse", "workshop", "business park", "business premises", "restaurant",
    "hotel", "leisure", "investment property", "commercial premises", "commercial building",
    "garages", "garage block", "redevelopment potential", "development opportunity",
)
RESIDENTIAL_STRONG = (
    "detached house", "semi-detached house", "terraced house", "bungalow", "residential flat",
    "bedroom flat", "family home", "residential property",
)


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _parse_date(text):
    m = DATE_RE.search(norm(text))
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    except ValueError:
        return None


def _event_links(s, today=None):
    today = today or date.today()
    found = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("#", 1)[0]
        if "/event/property-auction-" not in href.lower():
            continue
        node = a
        block = norm(a.get_text(" ", strip=True))
        for _ in range(5):
            node = getattr(node, "parent", None)
            if node is None:
                break
            candidate = norm(node.get_text(" ", strip=True))
            if len(candidate) <= 1800 and len(candidate) > len(block):
                block = candidate
        event_date = _parse_date(block)
        if event_date and event_date >= today.isoformat():
            found[href] = event_date
    return found


def _property_links(event_s, event_date):
    found = {}
    for a in event_s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("#", 1)[0]
        if "/property/" not in href.lower():
            continue
        if href in found:
            continue
        text = norm(a.get_text(" ", strip=True))
        if not text:
            continue
        found[href] = (text, event_date)
    return found


def _image(s, base):
    candidates = []
    for img in s.find_all("img"):
        raw = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
        if not raw:
            continue
        u = urljoin(base, raw)
        low = u.lower()
        alt = norm(img.get("alt") or "").lower()
        if "cdn.webdadi.net" not in low:
            continue
        if any(x in low for x in ("logo", "icon", "staff", "office", "map", "floorplan", "epc")):
            continue
        if "property image" in alt or re.search(r"[0-9a-f]{8}-[0-9a-f-]{20,}", low, re.I):
            candidates.append(u)
    return candidates[0] if candidates else None


def _main_property_text(s):
    # Bound text to the actual listing and avoid cookie/nav/footer chrome.
    h1 = s.find("h1") or s.find("h2")
    if not h1:
        return norm((s.find("main") or s).get_text(" ", strip=True))[:9000]
    pieces = []
    for node in [h1] + list(h1.find_all_next(limit=90)):
        if getattr(node, "name", None) in {"script", "style", "nav", "footer"}:
            continue
        if getattr(node, "name", None) in {"h1", "h2", "h3", "h4", "p", "li"}:
            value = norm(node.get_text(" ", strip=True))
            if value and value not in pieces:
                pieces.append(value)
        joined = " ".join(pieces)
        if len(joined) > 9000:
            break
    return norm(" ".join(pieces))[:9000]


def _is_target(text):
    low = " " + norm(text).lower() + " "
    if is_commercial(text):
        return True
    if any(x in low for x in COMMERCIAL_EXTRA):
        return True
    # Do not treat generic "potential" on a house as commercial/development stock.
    if any(x in low for x in RESIDENTIAL_STRONG):
        return False
    if re.search(r"\bdevelopment (?:site|land|plot)\b|\bbuilding plot\b", low):
        return True
    return False


def _address(s, url):
    h1 = s.find("h1")
    if h1:
        value = norm(h1.get_text(" ", strip=True))
        value = re.sub(r"^#?\s*", "", value)
        if len(value) >= 6:
            return value
    title = s.find("title")
    if title:
        value = norm(title.get_text(" ", strip=True))
        value = re.sub(r"\s*\|.*$", "", value)
        if len(value) >= 6:
            return value
    return url


def _area(text):
    sqft = sqm = acres = None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b", text, re.I)
    if m: sqft = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\b", text, re.I)
    if m: sqm = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)\s*acres?\b", text, re.I)
    if m: acres = float(m.group(1))
    return sqft, sqm, acres


def _property_type(text):
    low = text.lower()
    for label, markers in (
        ("Mixed Use", ("mixed use", "mixed-use")),
        ("Public House", ("public house", "grade ii listed pub", " pub ")),
        ("Retail", ("retail", "shop")),
        ("Office", ("office",)),
        ("Industrial", ("industrial", "warehouse", "workshop", "business park")),
        ("Development", ("development site", "development land", "building plot", "redevelopment potential")),
        ("Garages", ("garages", "garage block")),
        ("Commercial", ("commercial",)),
    ):
        if any(x in low for x in markers):
            return label
    return "Commercial / Development"


def _detail(url, seed, event_date, fetcher=_fetch):
    s = fetcher(url)
    text = _main_property_text(s)
    combined = norm(seed + " " + text)
    if not _is_target(combined):
        return None

    guide = parse_guide(combined)
    if guide is None:
        m = re.search(r"Guide(?: Price)?\s*£+\s*([\d,]+(?:\.\d+)?)", combined, re.I)
        if m: guide = float(m.group(1).replace(",", ""))
    rent = parse_rent(combined)
    lp_url, lp_status = legal_pack(s, url)
    lot = Lot(
        source=SOURCE, url=url, address=_address(s, url), auction_date=event_date,
        image_url=_image(s, url), guide_price=guide, annual_rent=rent,
        tenure=parse_tenure(combined), vat_status=parse_vat(combined),
        legal_pack_status=lp_status, legal_pack_url=lp_url,
        property_type=_property_type(combined), description=text,
    )
    lot.area_sqft, lot.area_sqm, lot.site_area_acres = _area(combined)
    if re.search(r"\bvacant possession\b|\bvacant\b", combined, re.I) and not re.search(r"\blet to\b|\btenant\b|\btenanted\b|\bproducing\s+£", combined, re.I):
        lot.occupation = "Vacant"
    elif re.search(r"\blet to\b|\btenant\b|\btenanted\b|\bproducing\s+£|\brental income\b", combined, re.I):
        lot.occupation = "Tenanted"
    if re.search(r"redevelopment potential|development potential|development opportunity|subject to planning|planning permission|building plot", combined, re.I):
        lot.development_potential = True
    if re.search(r"in need of (?:some )?renovation|refurbish|refurbishment", combined, re.I):
        lot.refurbishment = True
    if re.search(r"residential conversion|living accommodation|residential accommodation|flat above|accommodation above", combined, re.I):
        lot.residential_conversion = True
    if re.search(r"Grade\s+II\*?\s+Listed", combined, re.I):
        lot.listed_status = "Grade II Listed"
    pm = re.search(r"(?:large|customer|private|rear)?\s*car park|parking for\s+(\d+)\s+(?:cars|vehicles)", combined, re.I)
    if pm:
        lot.parking = f"Parking for {pm.group(1)} vehicles" if pm.group(1) else "Car park / parking mentioned"
    return lot.finalise()


def collect():
    try:
        index = _fetch(EVENTS)
        events = _event_links(index)
        if not events:
            return SourceResult(SOURCE, "FAILED", [], "No future Symonds & Sampson property-auction events could be parsed.")

        candidates = {}
        published_event_dates = set()
        pending_event_dates = set()
        event_failures = 0
        for event_url, event_date in events.items():
            try:
                es = _fetch(event_url)
                links = _property_links(es, event_date)
                if links:
                    published_event_dates.add(event_date)
                    candidates.update(links)
                else:
                    pending_event_dates.add(event_date)
            except Exception as exc:
                event_failures += 1
                print("SYMONDS_EVENT_FAIL", event_url, repr(exc))

        lots = []
        detail_failures = 0
        for href, (seed, event_date) in candidates.items():
            try:
                lot = _detail(href, seed, event_date)
                if lot:
                    lots.append(lot)
            except Exception as exc:
                detail_failures += 1
                print("SYMONDS_DETAIL_FAIL", href, repr(exc))

        if event_failures:
            status = "DEGRADED" if lots else "FAILED"
        else:
            status = "LIVE" if lots or published_event_dates else "CATALOGUE PENDING"
        message = (
            f"All-future Symonds & Sampson sweep: {len(events)} future event(s); "
            f"{len(published_event_dates)} published catalogue(s), {len(pending_event_dates)} pending; "
            f"{len(candidates)} property pages inspected; {len(lots)} commercial/mixed-use/development lots published; "
            f"{detail_failures} detail failures; {event_failures} event failures."
        )
        return SourceResult(
            SOURCE, status, lots, message,
            discovered_count=len(lots),
            authoritative_snapshot=bool(status == "LIVE" and not event_failures and not detail_failures and published_event_dates),
            scope_dates=tuple(sorted(published_event_dates)),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Symonds & Sampson collection failed: {type(exc).__name__}: {exc}")
