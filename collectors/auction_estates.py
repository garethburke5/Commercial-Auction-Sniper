import re
from datetime import date
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, legal_pack, image_from_soup

SOURCE = "Auction Estates"
BASE = "https://www.auctionestates.co.uk"
NEXT = BASE + "/next-auction"
LOTS = BASE + "/view-properties"

MONTHS = {name.lower(): i for i, name in enumerate((
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
), 1)}


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _auction_date(text):
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", norm(text), re.I)
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    except ValueError:
        return None


def _lot_links(s):
    found = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("#", 1)[0]
        if not re.search(r"/property/[^/?#]+-\d+/?$", href, re.I):
            continue
        node = a
        card = norm(a.get_text(" ", strip=True))
        for _ in range(5):
            node = getattr(node, "parent", None)
            if node is None:
                break
            candidate = norm(node.get_text(" ", strip=True))
            if len(candidate) <= 2400 and len(candidate) > len(card):
                card = candidate
        if href not in found or len(card) > len(found[href]):
            found[href] = card
    return found


def _property_type(text):
    m = re.search(r"Property Type\s+([^|]{2,60}?)(?=\s+(?:Reception Rooms|Bedrooms|Bathrooms|Key Features|Part of the|Details|Tenure|EPC|Solicitors)\b)", norm(text), re.I)
    return norm(m.group(1)) if m else None


def _is_target(text):
    low = " " + norm(text).lower() + " "
    ptype = (_property_type(text) or "").lower()
    if ptype in {"commercial", "mixed use", "mixed-use"}:
        return True
    if ptype == "residential":
        return False
    if is_commercial(text):
        return True
    if "commercial investment" in low or "retail investment" in low or "industrial investment" in low or "office investment" in low:
        return True
    if any(x in low for x in ("restaurant", "public house", "retail unit", "office building", "industrial warehouse", "commercial premises")):
        return True
    return False


def _image(s, base):
    """Extract the real lot photo from hero/gallery/lazy-loaded markup."""
    bad = ("logo", "icon", "avatar", "staff", "map", "floorplan", "epc", "placeholder", "sprite", "social")
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
        if "property" in alt or "lot" in alt:
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
        if "auctionestates" in low: score += 5
        if any(x in low for x in ("property", "uploads", "images", "photos", "media")): score += 3
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


def _description(s):
    h1 = s.find("h1")
    if not h1:
        return norm((s.find("main") or s).get_text(" ", strip=True))[:8000]
    pieces = []
    for node in [h1] + list(h1.find_all_next(limit=100)):
        if getattr(node, "name", None) in {"h1", "h2", "h3", "h4", "p", "li"}:
            value = norm(node.get_text(" ", strip=True))
            if value and value not in pieces:
                pieces.append(value)
        if len(" ".join(pieces)) > 8000:
            break
    return norm(" ".join(pieces))[:8000]


def _area(text):
    sqft = sqm = acres = None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square feet)\b", text, re.I)
    if m: sqft = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|square metres)\b", text, re.I)
    if m: sqm = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)\s*acres?\b", text, re.I)
    if m: acres = float(m.group(1))
    return sqft, sqm, acres


def _detail(url, card, auction_date, fetcher=_fetch):
    s = fetcher(url)
    text = _description(s)
    combined = norm(card + " " + text)
    if not _is_target(combined):
        return None
    h1 = s.find("h1")
    address = norm(h1.get_text(" ", strip=True)) if h1 else url
    guide = parse_guide(combined)
    if guide is None:
        m = re.search(r"Guide price\s*£\s*([\d,]+(?:\.\d+)?)", combined, re.I)
        if m: guide = float(m.group(1).replace(",", ""))
    rent = parse_rent(combined)
    lp_url, lp_status = legal_pack(s, url)
    lot = Lot(
        source=SOURCE, url=url, address=address, auction_date=auction_date,
        image_url=_image(s, url), guide_price=guide, annual_rent=rent,
        tenure=parse_tenure(combined), vat_status=parse_vat(combined),
        legal_pack_status=lp_status, legal_pack_url=lp_url,
        property_type=_property_type(combined) or "Commercial", description=text,
    )
    lot.area_sqft, lot.area_sqm, lot.site_area_acres = _area(combined)
    if re.search(r"\bvacant possession\b|\bvacant\b", combined, re.I) and not re.search(r"\blet to\b|\btenant\b|\btenanted\b|\bcurrent rent\b", combined, re.I):
        lot.occupation = "Vacant"
    elif re.search(r"\blet to\b|\btenant\b|\btenanted\b|\bcurrent rent\b|\brent reserved\b", combined, re.I):
        lot.occupation = "Tenanted"
    if re.search(r"development potential|redevelopment|scope for .*development|subject to planning", combined, re.I):
        lot.development_potential = True
    if re.search(r"refurbish|refurbishment|requires restoration|in need of renovation", combined, re.I):
        lot.refurbishment = True
    near = re.search(r"Nearby occupiers:?\s*(.+?)(?:\.|Close to|$)", combined, re.I)
    if near: lot.nearby_occupiers = norm(near.group(1))[:300]
    if re.search(r"prominent position|heart of .*town centre|heart of .*city centre|pedestrianised", combined, re.I):
        lot.pitch = "Prominent/central commercial location"
    return lot.finalise()


def collect():
    try:
        ns = _fetch(NEXT)
        auction_date = _auction_date(norm(ns.get_text(" ", strip=True)))
        if not auction_date:
            return SourceResult(SOURCE, "FAILED", [], "Could not parse Auction Estates next-auction date.")
        if auction_date < date.today().isoformat():
            return SourceResult(SOURCE, "FAILED", [], f"Auction Estates advertised next auction {auction_date} is already past.")

        ls = _fetch(LOTS)
        all_links = _lot_links(ls)
        if not all_links:
            return SourceResult(SOURCE, "CATALOGUE PENDING", [], f"Next auction {auction_date} is published but currently has no lot pages.", scope_dates=(auction_date,))

        lots = []
        failures = 0
        for href, card in all_links.items():
            try:
                lot = _detail(href, card, auction_date)
                if lot:
                    lots.append(lot)
            except Exception as exc:
                failures += 1
                print("AUCTION_ESTATES_DETAIL_FAIL", href, repr(exc))
        status = "LIVE" if failures == 0 else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Current Auction Estates {auction_date} catalogue: {len(all_links)} total lot pages inspected; {len(lots)} commercial/mixed-use lots published; {failures} detail failures.",
            discovered_count=len(lots), authoritative_snapshot=bool(status == "LIVE"), scope_dates=(auction_date,),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Auction Estates collection failed: {type(exc).__name__}: {exc}")
