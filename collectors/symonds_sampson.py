import re
from datetime import date
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, legal_pack, image_from_soup

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


def _event_card_text(anchor):
    own = norm(anchor.get_text(" ", strip=True))
    node = anchor
    best = own
    for _ in range(7):
        node = getattr(node, "parent", None)
        if node is None:
            break
        candidate = norm(node.get_text(" ", strip=True))
        if not candidate or len(candidate) > 2200:
            break
        event_links = [
            x for x in node.find_all("a", href=True)
            if "/event/property-auction-" in urljoin(BASE, x.get("href") or "").lower()
        ]
        if len(event_links) == 1:
            best = candidate
            if DATE_RE.search(candidate):
                return candidate
        elif len(event_links) > 1:
            break
    return best


def _event_links(s, today=None):
    today = today or date.today()
    found = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("#", 1)[0]
        if "/event/property-auction-" not in href.lower():
            continue
        block = _event_card_text(a)
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
    """Prefer the listing's actual hero/gallery image, including lazy/srcset/JSON-loaded images."""
    bad = ("logo", "icon", "staff", "office", "map", "floorplan", "epc", "avatar", "placeholder", "sprite")
    candidates = []

    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
        tag = s.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(urljoin(base, tag.get("content")))

    for img in s.find_all("img"):
        alt = norm(img.get("alt") or "").lower()
        for attr in ("data-src", "data-lazy-src", "data-original", "data-image", "data-url", "src"):
            raw = img.get(attr)
            if raw:
                candidates.append(urljoin(base, raw))
        for attr in ("srcset", "data-srcset"):
            raw = img.get(attr)
            if raw:
                for part in raw.split(","):
                    u = part.strip().split(" ")[0]
                    if u:
                        candidates.append(urljoin(base, u))
        if "property" in alt or "auction" in alt:
            for attr in ("src", "data-src", "data-lazy-src"):
                if img.get(attr):
                    candidates.insert(0, urljoin(base, img.get(attr)))

    raw_html = str(s).replace("\\/", "/")
    for u in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?', raw_html, re.I):
        candidates.append(u)

    seen = set()
    scored = []
    for u in candidates:
        if not u or u in seen:
            continue
        seen.add(u)
        low = u.lower()
        if any(x in low for x in bad):
            continue
        score = 0
        if "cdn.webdadi.net" in low: score += 6
        if re.search(r"[0-9a-f]{8}-[0-9a-f-]{20,}", low, re.I): score += 4
        if any(x in low for x in ("property", "images", "photos", "uploads", "media")): score += 2
        if low.endswith((".jpg", ".jpeg", ".webp")) or ".jpg?" in low or ".jpeg?" in low or ".webp?" in low: score += 2
        scored.append((score, u))
    if scored:
        scored.sort(reverse=True)
        if scored[0][0] > 0:
            return scored[0][1]

    generic = image_from_soup(s, base)
    if generic and not any(x in generic.lower() for x in bad):
        return generic
    return None


def _main_property_text(s):
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
        if len(" ".join(pieces)) > 9000:
            break
    return norm(" ".join(pieces))[:9000]


def _is_target(text):
    low = " " + norm(text).lower() + " "
    if is_commercial(text):
        return True
    if any(x in low for x in COMMERCIAL_EXTRA):
        return True
    if any(x in low for x in RESIDENTIAL_STRONG):
        return False
    return bool(re.search(r"\bdevelopment (?:site|land|plot)\b|\bbuilding plot\b", low))


def _address(s, url):
    h1 = s.find("h1")
    if h1:
        value = re.sub(r"^#?\s*", "", norm(h1.get_text(" ", strip=True)))
        if len(value) >= 6:
            return value
    title = s.find("title")
    if title:
        value = re.sub(r"\s*\|.*$", "", norm(title.get_text(" ", strip=True)))
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
            SOURCE, status, lots, message, discovered_count=len(lots),
            authoritative_snapshot=bool(status == "LIVE" and not event_failures and not detail_failures and published_event_dates),
            scope_dates=tuple(sorted(published_event_dates)),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Symonds & Sampson collection failed: {type(exc).__name__}: {exc}")
