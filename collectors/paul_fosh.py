import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Paul Fosh Auctions"
BASE = "https://auction.paulfosh.com"
UPCOMING = BASE + "/future-auctions"

COMMERCIAL_TERMS = (
    "commercial", "retail", "shop", "office", "industrial", "warehouse", "business",
    "investment", "mixed use", "mixed-use", "development", "former police", "former bank",
    "public house", "pub", "restaurant", "takeaway", "storage unit", "workshop", "garage",
)
RESIDENTIAL_ONLY = ("house for owner", "flat for owner", "bungalow", "cottage for owner")


def _commercial(text):
    low = norm(text).lower()
    if any(x in low for x in COMMERCIAL_TERMS):
        return True
    return False


def _detail(url, seed):
    s = soup(url, use_browser=False)
    text = norm(s.get_text(" ", strip=True))
    low = text.lower()
    if any(x in low for x in ("auction ended", "sold prior", "withdrawn", "postponed")):
        return None
    if not _commercial(seed + " " + text):
        return None

    address = None
    for tag in ("h1", "h2", "h3"):
        for h in s.find_all(tag):
            value = norm(h.get_text(" ", strip=True))
            if value and not re.match(r"^(lot\s*\d+|upcoming property auctions?)$", value, re.I):
                if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", value, re.I) or "," in value:
                    address = value
                    break
        if address:
            break
    if not address:
        return None

    ml = re.search(r"\bLot\s*[-:]?\s*(\d+[A-Z]?)\b", text, re.I)
    lot_number = "Lot " + ml.group(1).upper() if ml else None
    md = re.search(r"Bidding\s+(?:closes|ends)[^0-9]*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    auction_date = None
    if md:
        from datetime import datetime
        try: auction_date = datetime.strptime(" ".join(md.groups()), "%d %B %Y").date().isoformat()
        except ValueError: pass
    lp_url, lp_status = legal_pack(s, url)
    return Lot(
        source=SOURCE, url=url, address=address, lot_number=lot_number,
        auction_date=auction_date, image_url=image_from_soup(s, url),
        guide_price=parse_guide(text) or parse_guide(seed), annual_rent=parse_rent(text),
        tenure=parse_tenure(text), vat_status=parse_vat(text), legal_pack_url=lp_url,
        legal_pack_status=lp_status, status="Live", description=text[:4000],
        property_type="Commercial / Mixed Use",
    ).finalise()


def collect():
    try:
        s = soup(UPCOMING, use_browser=False)
        page_text = norm(s.get_text(" ", strip=True))
        scope_date = None
        md = re.search(r"Bidding\s+closes\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", page_text, re.I)
        if md:
            from datetime import datetime
            try: scope_date = datetime.strptime(" ".join(md.groups()), "%d %B %Y").date().isoformat()
            except ValueError: pass

        links = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "").split("?")[0]
            seed = norm(a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True))
            if href.startswith(BASE) and _commercial(seed) and href not in {UPCOMING, BASE + "/search", BASE + "/past-auctions"}:
                links[href] = seed

        lots = []
        failures = 0
        for href, seed in links.items():
            try:
                lot = _detail(href, seed)
                if lot: lots.append(lot)
            except Exception as exc:
                failures += 1
                print("PAUL_FOSH_DETAIL_FAIL", href, repr(exc))

        status = "LIVE" if lots and failures == 0 else ("DEGRADED" if lots else "FAILED")
        return SourceResult(
            SOURCE, status, lots,
            f"Paul Fosh upcoming auction: {len(links)} commercial/mixed candidates; {len(lots)} published; {failures} detail failures.",
            expected_count=None, discovered_count=len(links), authoritative_snapshot=False,
            scope_dates=(scope_date,) if scope_date else (),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Paul Fosh live discovery failed: {exc}")
