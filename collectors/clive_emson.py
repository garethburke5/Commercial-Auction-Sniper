import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Clive Emson"
BASE = "https://www.cliveemson.co.uk"
CURRENT = BASE + "/properties/"
COMMERCIAL = BASE + "/properties/commerical-property-auctions/"


def _money_value(raw):
    m = re.search(r"£\s*([\d,]+(?:\.\d{1,2})?)", raw or "")
    return float(m.group(1).replace(",", "")) if m else None


def _parse_passing_rent(text, guide_price=None):
    """Extract Clive Emson's passing rent without confusing price/fee boilerplate for rent.

    Prefer an explicit total current-rent statement. If that is absent, aggregate clearly
    labelled monthly tenancy rents. Only then fall back to the shared parser, rejecting an
    exact guide-price collision because that is almost always page-chrome contamination.
    """
    value = norm(text)

    explicit_patterns = [
        r"\bCurrently\s+let\s+at\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"\bCurrent(?:ly)?\s+(?:gross\s+)?(?:rent|rental income|income)\s*(?:is|of|at|:)\s*"
        r"(£\s*[\d,]+(?:\.\d{1,2})?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"\bTotal\s+(?:current\s+)?(?:rent|rental income|income)\s*(?:is|of|at|:)\s*"
        r"(£\s*[\d,]+(?:\.\d{1,2})?)\s*(?:per annum|p\.?a\.?|pa)\b",
    ]
    for pat in explicit_patterns:
        m = re.search(pat, value, re.I)
        if m:
            rent = _money_value(m.group(1))
            if rent and 500 <= rent <= 5_000_000:
                return rent

    monthly = []
    monthly_patterns = [
        r"\bLet\b[^.]{0,180}?\bat\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s+per calendar month\b",
        r"\bcurrent rental of\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s+per calendar month\b",
        r"\blicen[cs]e agreement\s+at\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s+per calendar month\b",
    ]
    seen_spans = set()
    for pat in monthly_patterns:
        for m in re.finditer(pat, value, re.I):
            # Avoid counting the same sentence twice when two patterns overlap.
            sentence_start = value.rfind(".", 0, m.start()) + 1
            sentence_end = value.find(".", m.end())
            if sentence_end < 0:
                sentence_end = len(value)
            key = norm(value[sentence_start:sentence_end]).lower()
            if key in seen_spans:
                continue
            seen_spans.add(key)
            amount = _money_value(m.group(1))
            if amount and 40 <= amount <= 100_000:
                monthly.append(amount)
    if monthly:
        return round(sum(monthly) * 12, 2)

    fallback = parse_rent(value)
    if fallback and guide_price and abs(fallback - guide_price) < 0.01:
        return None
    return fallback


def _parse_occupation(text):
    value = norm(text).lower()
    has_let = bool(re.search(
        r"\bcurrently let\b|\bseparately let\b|\blet on (?:a|the)\b|\blet to\b|"
        r"\blicen[cs]e agreement at\b|\bcurrent rental of\b",
        value,
        re.I,
    ))
    has_vacant = bool(re.search(r"\bvacant(?: possession)?\b", value, re.I))
    if "part vacant possession" in value or (has_let and has_vacant):
        return "Part Vacant / Part Let"
    if has_let:
        return "Let"
    if has_vacant or "category vacant commercial" in value:
        return "Vacant"
    return None


def _discover_current_auction():
    s = soup(CURRENT, use_browser=False)
    text = norm(s.get_text(" ", strip=True))
    mdate = re.search(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    auction_date = None
    if mdate:
        auction_date = datetime.strptime(" ".join(mdate.groups()), "%d %B %Y").date().isoformat()

    ids = []
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "")
        m = re.search(r"/properties/(\d+)/(\d+)/?", href)
        if m:
            ids.append(m.group(1))
    if not ids:
        raise RuntimeError("current catalogue exposed no property links")
    # The current catalogue page is one sale; use the most common auction id rather than
    # relying on a hard-coded catalogue number.
    auction_id = max(set(ids), key=ids.count)
    return auction_id, auction_date


def _candidate_links(auction_id):
    s = soup(COMMERCIAL, use_browser=False)
    out = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0]
        m = re.search(rf"/properties/{re.escape(auction_id)}/(\d+)/?", href)
        if not m:
            continue
        text = norm(a.get_text(" ", strip=True))
        out[href] = text
    return out


def _parse_detail(url, seed, auction_date):
    s = soup(url, use_browser=False)
    text = norm(s.get_text(" ", strip=True))
    low = text.lower()
    if "sold prior" in low or "withdrawn" in low or "postponed" in low:
        return None

    mcat = re.search(r"\bCategory\s+([^#]+?)(?:\s+Tenure\b|\s+Bedrooms\b|\s+Bathrooms\b|\s+Key Features\b)", text, re.I)
    category = norm(mcat.group(1)) if mcat else ""
    cat_low = category.lower()
    if category and not any(x in cat_low for x in ("commercial", "mixed", "industrial", "retail", "office", "leisure", "business")):
        return None

    mh1 = s.find("h1")
    lot_number = None
    if mh1:
        ml = re.search(r"Lot\s+(\d+[A-Z]?)", norm(mh1.get_text(" ", strip=True)), re.I)
        if ml:
            lot_number = "Lot " + ml.group(1)
    if not lot_number:
        ml = re.search(r"LOT\s+(\d+[A-Z]?)", seed, re.I)
        lot_number = "Lot " + ml.group(1) if ml else None

    address = None
    h2 = s.find("h2")
    if h2:
        address = norm(h2.get_text(" ", strip=True))
    if not address:
        address = seed or url

    mdate = re.search(r"Auction (?:Date|Ends):\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if mdate:
        auction_date = datetime.strptime(" ".join(mdate.groups()), "%d %B %Y").date().isoformat()

    guide_price = parse_guide(text) or parse_guide(seed)
    annual_rent = _parse_passing_rent(text, guide_price=guide_price)
    occupation = _parse_occupation(text)

    lp_url, lp_status = legal_pack(s, url)
    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=lot_number,
        auction_date=auction_date,
        image_url=image_from_soup(s, url),
        guide_price=guide_price,
        annual_rent=annual_rent,
        tenure=parse_tenure(text),
        vat_status=parse_vat(text),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        status="Live",
        description=text[:4000],
        property_type=category or "Commercial / Mixed Use",
        occupation=occupation,
    ).finalise()


def collect():
    try:
        auction_id, auction_date = _discover_current_auction()
        links = _candidate_links(auction_id)
        if not links:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Current auction {auction_id} discovered but commercial feed exposed no matching lots.",
                expected_count=None, discovered_count=0, authoritative_snapshot=False,
                scope_dates=(auction_date,) if auction_date else (),
            )

        lots = []
        failures = 0
        for href, seed in links.items():
            try:
                lot = _parse_detail(href, seed, auction_date)
            except Exception as exc:
                failures += 1
                print("CLIVE_EMSON_DETAIL_FAIL", href, repr(exc))
                continue
            if lot:
                lots.append(lot)

        # Every link on Clive Emson's dedicated commercial page for the discovered current
        # auction is expected to publish. If a detail fails, do not declare completeness.
        expected = len(links)
        status = "LIVE" if len(lots) == expected and failures == 0 else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic auction {auction_id}: {expected} commercial links discovered; {len(lots)} published; {failures} detail failures.",
            expected_count=expected,
            discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"),
            scope_dates=(auction_date,) if auction_date else (),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Clive Emson discovery failed: {exc}")