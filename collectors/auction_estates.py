import re
from datetime import date
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, legal_pack, image_from_soup

SOURCE = "Auction Estates"
BASE = "https://www.auctionestates.co.uk"
NEXT = BASE + "/next-auction"
LOTS = BASE + "/view-properties"
MONTHS = {name.lower(): i for i, name in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"), 1)}


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _auction_date(text):
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", norm(text), re.I)
    if not m or not MONTHS.get(m.group(2).lower()):
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
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
            if len(candidate) <= 3000 and len(candidate) > len(card):
                card = candidate
        if href not in found or len(card) > len(found[href]):
            found[href] = card
    return found


def _property_type(text):
    m = re.search(r"Property Type\s+([^|]{2,80}?)(?=\s+(?:Reception Rooms|Bedrooms|Bathrooms|Key Features|Part of the|Details|Tenure|EPC|Solicitors)\b)", norm(text), re.I)
    return norm(m.group(1)) if m else None


def _is_target(text):
    low = " " + norm(text).lower() + " "
    ptype = (_property_type(text) or "").lower()
    if ptype in {"commercial", "mixed use", "mixed-use", "telecoms"}:
        return True
    if ptype == "residential" and not any(x in low for x in ("shop", "retail", "commercial", "office", "workshop", "mixed use", "mixed-use")):
        return False
    if is_commercial(text):
        return True
    return any(x in low for x in ("commercial investment", "retail investment", "industrial investment", "office investment", "restaurant", "public house", "retail unit", "office building", "industrial warehouse", "commercial premises"))


def _image(s, base):
    bad = ("logo", "icon", "avatar", "staff", "map", "floorplan", "epc", "placeholder", "sprite", "social")
    candidates = []
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
        tag = s.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(urljoin(base, tag.get("content")))
    for img in s.find_all("img"):
        alt = norm(img.get("alt") or "").lower()
        for attr in ("data-src", "data-lazy-src", "data-original", "data-image", "data-url", "src"):
            if img.get(attr):
                candidates.append(urljoin(base, img.get(attr)))
        for attr in ("srcset", "data-srcset"):
            if img.get(attr):
                for part in img.get(attr).split(","):
                    u = part.strip().split(" ")[0]
                    if u:
                        candidates.append(urljoin(base, u))
        if "property" in alt or "lot" in alt:
            for attr in ("src", "data-src", "data-lazy-src"):
                if img.get(attr):
                    candidates.insert(0, urljoin(base, img.get(attr)))
    raw_html = str(s).replace("\\/", "/")
    candidates.extend(re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?', raw_html, re.I))
    seen, scored = set(), []
    for u in candidates:
        if not u or u in seen:
            continue
        seen.add(u)
        low = u.lower()
        if any(x in low for x in bad):
            continue
        score = (5 if "auctionestates" in low else 0) + (3 if any(x in low for x in ("property", "uploads", "images", "photos", "media")) else 0) + (2 if any(x in low for x in (".jpg", ".jpeg", ".webp")) else 0)
        scored.append((score, u))
    if scored:
        scored.sort(reverse=True)
        if scored[0][0] > 0:
            return scored[0][1]
    generic = image_from_soup(s, base)
    return generic if generic and not any(x in generic.lower() for x in bad) else None


def _description(s):
    h1 = s.find("h1")
    if not h1:
        return norm((s.find("main") or s).get_text(" ", strip=True))[:12000]
    pieces = []
    for node in [h1] + list(h1.find_all_next(limit=180)):
        if getattr(node, "name", None) in {"h1", "h2", "h3", "h4", "p", "li"}:
            value = norm(node.get_text(" ", strip=True))
            if value and value not in pieces:
                pieces.append(value)
        if len(" ".join(pieces)) > 12000:
            break
    return norm(" ".join(pieces))[:12000]


def _area(text):
    sqft = sqm = acres = None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square feet)\b", text, re.I)
    if m: sqft = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|square metres)\b", text, re.I)
    if m: sqm = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)\s*acres?\b", text, re.I)
    if m: acres = float(m.group(1))
    return sqft, sqm, acres


def _lease_details(text):
    low = norm(text)
    expiry = None
    m = re.search(r"(?:lease\s+(?:until|till|to)|expires?\s+)([A-Za-z]+\s+20\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2})", low, re.I)
    if m:
        expiry = norm(m.group(1))
    holding_over = bool(re.search(r"holding over", low, re.I))
    return expiry, holding_over


def _tenancy_details(text):
    """Extract explicit current tenant and lease facts from Auction Estates prose."""
    value = norm(text)
    tenant = None
    for pat in (
        r"(?:investment property|commercial property|retail investment property|property|unit|premises)\s+let\s+to\s+([^.;]{2,100}?)(?=\s+(?:located|in the|on a|at a|for a|with a|current rent|rent reserved)|[.;])",
        r"\blet\s+to\s+([^.;]{2,100}?)(?=\s+(?:on a|at a|for a|current rent|rent reserved)|[.;])",
    ):
        m = re.search(pat, value, re.I)
        if m:
            candidate = norm(m.group(1)).strip(" ,:-")
            if candidate and not re.search(r"nearby occupiers|former tenant|previous tenant", candidate, re.I):
                tenant = candidate[:100]
                break

    term = start = None
    m = re.search(r"\blet\s+on\s+a\s+(\d+(?:\.\d+)?)\s+year\s+lease\s+from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})", value, re.I)
    if not m:
        m = re.search(r"\blease\s+(?:for|of)\s+(\d+(?:\.\d+)?)\s+years?\s+from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})", value, re.I)
    if m:
        years = float(m.group(1))
        term = f"{years:g} years"
        start = norm(re.sub(r"(\d{1,2})(?:st|nd|rd|th)", r"\1", m.group(2), flags=re.I))

    fri = True if re.search(r"\bFRI\b|full repairing and insuring", value, re.I) else None
    no_break = bool(re.search(r"\bno break\b|without (?:a )?break|no break clause", value, re.I))
    break_clause = "No break" if no_break else None
    return tenant, term, start, fri, break_clause


def _terminal_status_near_title(s):
    """Read the current lot's availability status without scanning unrelated cards.

    Auction Estates prints SoldPrior near the title, while Postponed can replace the
    guide-price value. Keep the probe bounded to the header/summary area and stop at
    Key Features/auction particulars so statuses on recommended lots cannot leak in.
    """
    h1 = s.find("h1")
    if not h1:
        return None
    parts = [norm(h1.get_text(" ", strip=True))]
    for node in h1.find_all_next(limit=40):
        name = getattr(node, "name", None)
        if name not in {"div", "span", "p", "strong", "h2", "h3", "dt", "dd"}:
            continue
        text = norm(node.get_text(" ", strip=True))
        if not text:
            continue
        if re.search(r"\bKey\s*Features\b|\bPart of the\b|\bDetails\b", text, re.I):
            break
        parts.append(text)
        if len(" ".join(parts)) > 1800:
            break
    probe = norm(" ".join(parts))
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", probe, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bWithdrawn\b", probe, re.I):
        return "WITHDRAWN"
    if re.search(r"\bPostponed\b", probe, re.I):
        return "POSTPONED"
    return None


def _detail(url, card, auction_date, fetcher=_fetch):
    s = fetcher(url)
    text = _description(s)
    combined = norm(card + " " + text)
    terminal_status = _terminal_status_near_title(s)
    if not _is_target(combined):
        return None

    h1 = s.find("h1")
    address = norm(h1.get_text(" ", strip=True)) if h1 else url
    guide = parse_guide(combined)
    if guide is None:
        m = re.search(r"Guide price\s*£\s*([\d,]+(?:\.\d+)?)", combined, re.I)
        if m: guide = float(m.group(1).replace(",", ""))
    rent = parse_rent(combined)
    if rent is None:
        m = re.search(r"(?:total\s+)?current\s+rent\s+reserved\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|pa|p\.a\.)", combined, re.I)
        if m: rent = float(m.group(1).replace(",", ""))

    lp_url, lp_status = legal_pack(s, url)
    lot = Lot(source=SOURCE, url=url, address=address, auction_date=auction_date,
              image_url=_image(s, url), guide_price=guide, annual_rent=rent,
              tenure=parse_tenure(combined), vat_status=parse_vat(combined),
              legal_pack_status=lp_status, legal_pack_url=lp_url,
              property_type=_property_type(combined) or "Commercial", description=text,
              status=terminal_status or "CURRENT")
    lot.area_sqft, lot.area_sqm, lot.site_area_acres = _area(combined)

    tenant, lease_term, lease_start, fri, break_clause = _tenancy_details(combined)
    if tenant: lot.tenant = tenant
    if lease_term: lot.lease_term = lease_term
    if lease_start: lot.lease_start = lease_start
    if fri is not None: lot.fri = fri
    if break_clause: lot.break_clause = break_clause

    has_vacant = bool(re.search(r"\bvacant possession\b|\bvacant\b", combined, re.I))
    has_let = bool(re.search(r"\blet on a lease\b|\blet to\b|\btenant\b|\btenanted\b|\bcurrent rent\b|\brent reserved\b", combined, re.I))
    if has_vacant and has_let: lot.occupation = "Part Vacant / Part Let"
    elif has_vacant: lot.occupation = "Vacant"
    elif has_let: lot.occupation = "Tenanted"

    expiry, holding_over = _lease_details(combined)
    if expiry: lot.lease_expiry = expiry
    if holding_over:
        lot.lease_term = "Holding over" if not lot.lease_term else lot.lease_term + " · holding over"
        lot.break_status = "Holding over"

    if re.search(r"scope for conversion of (?:the )?uppers? to residential|conversion of upper floors? to residential|residential conversion|subject to planning|\bSTP\b", combined, re.I):
        lot.residential_conversion = True
        lot.development_potential = True
    elif re.search(r"development potential|redevelopment|scope for .*development|potential for future development|future development|full planning permission", combined, re.I):
        lot.development_potential = True
    if re.search(r"refurbish|refurbishment|requires restoration|in need of renovation", combined, re.I):
        lot.refurbishment = True
    if re.search(r"self[- ]contained access", combined, re.I):
        lot.asset_management = True
    if re.search(r"prominent position|heart of .*town centre|heart of .*city centre|pedestrianised|prominent location", combined, re.I):
        lot.pitch = "Prominent/central commercial location"
    if re.search(r"secure car park", combined, re.I):
        lot.parking = "Secure car park"
    else:
        pm = re.search(r"\b(\d+)\s+(?:allocated\s+)?(?:car\s+)?parking spaces?\b|\b(\d+)\s+space car park\b", combined, re.I)
        if pm:
            lot.parking = f"{pm.group(1) or pm.group(2)} parking spaces"
        elif re.search(r"\bcar park\b|\bparking\b", combined, re.I):
            lot.parking = "Parking mentioned"
    near = re.search(r"(?:Adjacent to|Nearby occupiers?:?)\s+(.+?)(?:\.|Close to|$)", combined, re.I)
    if near: lot.nearby_occupiers = norm(near.group(1))[:300]
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
        lots, failures, terminal = [], 0, 0
        terminal_statuses = {"SOLD PRIOR", "WITHDRAWN", "POSTPONED"}
        for href, card in all_links.items():
            try:
                lot = _detail(href, card, auction_date)
                if lot:
                    lots.append(lot)
                    if lot.status in terminal_statuses:
                        terminal += 1
            except Exception as exc:
                failures += 1
                print("AUCTION_ESTATES_DETAIL_FAIL", href, repr(exc))
        status = "LIVE" if failures == 0 else "DEGRADED"
        live_count = sum(1 for x in lots if x.status not in terminal_statuses)
        return SourceResult(SOURCE, status, lots,
            f"Current Auction Estates {auction_date} catalogue: {len(all_links)} total lot pages inspected; {live_count} live commercial/mixed-use lots; {terminal} sold-prior/withdrawn/postponed lots preserved for archive; {failures} detail failures.",
            discovered_count=len(lots), authoritative_snapshot=bool(status == "LIVE"), scope_dates=(auction_date,))
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Auction Estates collection failed: {type(exc).__name__}: {exc}")
