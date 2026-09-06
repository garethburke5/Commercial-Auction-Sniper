import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, nearest_card, image_from_soup, legal_pack

SOURCE = "Allsop Commercial"
BASE = "https://www.allsop.co.uk"
LANDING_PAGES = (
    BASE + "/auctions/commercial-auctions/",
    BASE + "/auctions/residential-auctions/",
)
SEARCHES = (
    BASE + "/property-search?future_auctions=on&page={page}&sortOrder=Max+Price&view=list",
    BASE + "/property-search?available_only=true&lot_type=both&page={page}&view=list",
)


def _lot_no(text):
    m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", text or "", re.I)
    return f"Lot {m.group(1)}" if m else "Lot TBC"


def _month_date(text):
    m = re.search(r"\b(?:Commercial|Residential)\s*-?\s*LOT(?:\s+\d+[A-Z]?)?\s*-?\s*([A-Za-z]{3,9})\s+(20\d{2})\b", text or "", re.I)
    if not m:
        return None
    month = m.group(1).lower()[:3]
    months = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06","jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
    return f"{m.group(2)}-{months.get(month, '01')}-01"


def _exact_auction_date(text, fallback=None):
    m = re.search(r"(?:offered on|auction(?:ed)?(?: on)?|auction date)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?", text or "", re.I)
    if not m:
        return fallback
    months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
    year = m.group(3) or (fallback[:4] if fallback else "2026")
    mm = months.get(m.group(2).lower())
    return f"{year}-{mm}-{int(m.group(1)):02d}" if mm else fallback


def _card_is_target(card):
    low = (card or "").lower()
    if "commercial lot" in low or "commercial - lot" in low:
        return True
    mixed_terms = ("mixed use", "mixed-use", "commercial & residential", "commercial and residential", "shop and residential", "retail and residential", "commercial unit")
    return any(x in low for x in mixed_terms) and is_commercial(card)


def _extract_targets(s, found):
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?", 1)[0]
        if "/lot-overview/" not in href:
            continue
        card = nearest_card(a, 5000) or norm(a.get_text(" ", strip=True))
        if not _card_is_target(card):
            continue
        found[href] = card


def _discover():
    found = {}
    # Canonical auction landing pages now expose early/current lots before the generic
    # property-search endpoint does. Always inspect them first so a published catalogue
    # cannot be incorrectly reported as pending.
    for url in LANDING_PAGES:
        try:
            _extract_targets(soup(url, use_browser=False), found)
        except Exception:
            try:
                _extract_targets(soup(url, use_browser=True), found)
            except Exception:
                pass

    for template in SEARCHES:
        repeated = None
        for page in range(1, 31):
            try:
                s = soup(template.format(page=page), use_browser=False)
            except Exception:
                continue
            before = len(found)
            page_found = {}
            _extract_targets(s, page_found)
            found.update(page_found)
            sig = tuple(sorted(page_found))
            if page > 1 and sig and sig == repeated:
                break
            if page > 1 and not sig:
                break
            if page > 1 and len(found) == before and not sig:
                break
            repeated = sig
    return found


def _hydrate(item):
    url, card = item
    s = soup(url, use_browser=False)
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True))
    low = text.lower()
    if "withdrawn" in low or "sold prior" in low:
        return None

    address = None
    postcode = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
    for tag in s.find_all(["h2", "h3", "h4", "h5", "div", "p"]):
        t = norm(tag.get_text(" ", strip=True))
        if postcode.search(t) and 8 <= len(t) <= 220:
            if not any(x in t.lower() for x in ("guide price", "lot overview", "register to bid")):
                address = t
                break
    if not address:
        pm = postcode.search(card)
        if pm:
            prefix = card[:pm.end()]
            parts = re.split(r"FEATURED LOT|Guide Price\*?|Yield\s+[\d.]+%", prefix, flags=re.I)
            address = norm(parts[-1])[-220:]
    if not address:
        return None

    title_tag = s.find("h1")
    opportunity_title = norm(title_tag.get_text(" ", strip=True)) if title_tag else ""
    combined = opportunity_title + " " + card + " " + text
    if not is_commercial(combined):
        return None

    lp_url, lp_status = legal_pack(s, url)
    rent = parse_rent(combined)
    guide = parse_guide(combined)
    tenure = parse_tenure(combined)
    auction_date = _exact_auction_date(text, _month_date(card))

    occupation = None
    if re.search(r"\bvacant\b|vacant possession", combined, re.I) and not rent:
        occupation = "Vacant / vacant possession"
    elif rent:
        occupation = "Tenanted"

    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=_lot_no(card),
        auction_date=auction_date,
        image_url=image_from_soup(s, url),
        guide_price=guide,
        annual_rent=rent,
        tenure=tenure,
        vat_status=parse_vat(combined),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        description=combined[:6500],
        occupation=occupation,
        property_type=opportunity_title[:180] if opportunity_title else None,
        development_potential=True if re.search(r"development|redevelopment|planning potential", combined, re.I) else None,
        asset_management=True if re.search(r"asset management", combined, re.I) else None,
        residential_conversion=True if re.search(r"conversion to residential|residential conversion", combined, re.I) else None,
        fri=True if re.search(r"\bFRI\b|full repairing and insuring", combined, re.I) else None,
    ).finalise()


def collect():
    try:
        targets = _discover()
        if not targets:
            return SourceResult(SOURCE, "CATALOGUE PENDING", [], "Allsop canonical auction pages and public search endpoints returned no commercial/mixed-use lots.", discovered_count=0)

        lots = []
        failures = 0
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_hydrate, item): item[0] for item in targets.items()}
            for f in as_completed(futs):
                try:
                    lot = f.result()
                    if lot:
                        lots.append(lot)
                except Exception:
                    failures += 1

        dedup = {x.url: x for x in lots}
        lots = list(dedup.values())
        status = "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"Allsop canonical+search collector: {len(targets)} commercial/mixed-use candidate pages discovered; {len(lots)} published; {failures} detail failures.",
            discovered_count=len(targets),
            authoritative_snapshot=False,
            scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Allsop collection failed: {exc}")
