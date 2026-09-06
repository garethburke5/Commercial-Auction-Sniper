import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
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
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
POSTCODE_DISTRICT = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\b", re.I)


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


def _header_auction_date(text):
    m = re.search(
        r"\b(?:Commercial|Residential)\s*-\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*&\s*\d{1,2}(?:st|nd|rd|th)?)?\s+([A-Za-z]{3,9})\s+(20\d{2})",
        text or "", re.I,
    )
    if not m:
        return None
    months = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06","jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
    mm = months.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{mm}-{int(m.group(1)):02d}" if mm else None


def _exact_auction_date(text, fallback=None):
    m = re.search(r"(?:offered on|auction(?:ed)?(?: on)?|auction date\.?)[^\d]{0,35}(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?", text or "", re.I)
    if not m:
        return fallback
    months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12",
              "jan":"01","feb":"02","mar":"03","apr":"04","jun":"06","jul":"07","aug":"08","sep":"09","sept":"09","oct":"10","nov":"11","dec":"12"}
    year = m.group(3) or (fallback[:4] if fallback else "2026")
    mm = months.get(m.group(2).lower())
    return f"{year}-{mm}-{int(m.group(1)):02d}" if mm else fallback


def _card_is_target(card):
    low = (card or "").lower()
    if "commercial lot" in low or "commercial - lot" in low:
        return True
    mixed_terms = ("mixed use", "mixed-use", "commercial & residential", "commercial and residential", "shop and residential", "retail and residential", "commercial unit")
    return any(x in low for x in mixed_terms) and is_commercial(card)


def _card_image(anchor):
    node = anchor
    for _ in range(7):
        if node is None:
            break
        try:
            img = image_from_soup(node, BASE)
        except Exception:
            img = None
        if img:
            low = img.lower()
            if not any(x in low for x in ("logo", "icon", "placeholder", "sprite", "social", "avatar")):
                return img
        node = getattr(node, "parent", None)
    return None


def _extract_targets(s, found):
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?", 1)[0]
        if "/lot-overview/" not in href:
            continue
        card = nearest_card(a, 5000) or norm(a.get_text(" ", strip=True))
        if not _card_is_target(card):
            continue
        found[href] = {"card": card, "image": _card_image(a)}


def _discover():
    found = {}
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


def _candidate_is_current_or_future(card, today=None):
    today = today or date.today()
    raw = _header_auction_date(card) or _month_date(card)
    if not raw:
        return True
    try:
        y, m, _ = (int(x) for x in raw.split("-", 2))
    except Exception:
        return True
    return (y, m) >= (today.year, today.month)


def _live_status_probe(s, card):
    bits = [card]
    for tag in s.find_all(["h1", "h2"], limit=4):
        bits.append(norm(tag.get_text(" ", strip=True)))
    return " ".join(bits)


def _address_from_soup(s, card):
    strings = [norm(x) for x in s.stripped_strings]
    for t in strings:
        if POSTCODE.search(t) and 8 <= len(t) <= 240:
            low = t.lower()
            if not any(x in low for x in ("guide price", "register to bid", "lot overview", "looking for finance")):
                return t

    pm = POSTCODE.search(card or "")
    if pm:
        prefix = (card or "")[:pm.end()]
        parts = re.split(r"FEATURED LOT|Guide Price\*?|Yield\s+[\d.]+%|(?:Commercial|Residential)\s*-.*?20\d{2}", prefix, flags=re.I)
        candidate = norm(parts[-1])[-240:]
        if POSTCODE.search(candidate):
            return candidate
    return None


def _teaser_address(card):
    text = norm(card)
    m = re.search(r"FEATURED LOT\s+(.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b)", text, re.I)
    if m:
        return norm(m.group(1))
    m = re.search(r"\b([A-Z][A-Za-z .'-]{2,60}\s+[A-Z]{1,2}\d[A-Z\d]?)\b", text)
    return norm(m.group(1)) if m else None


def _teaser_title(card):
    text = norm(card)
    m = re.search(r"FEATURED LOT\s+.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b\s+(.+?)(?:Guide Price|Yield|£|$)", text, re.I)
    return norm(m.group(1)) if m else None


def _teaser_lot(url, card, image_url=None):
    address = _teaser_address(card)
    if not address:
        return None
    title = _teaser_title(card)
    return Lot(
        source=SOURCE, url=url, address=address, lot_number=_lot_no(card),
        auction_date=_month_date(card), guide_price=parse_guide(card), image_url=image_url,
        property_type=title[:180] if title else "Commercial / mixed-use auction lot",
        description=card[:3500], status="CURRENT",
    ).finalise()


def _hydrate(item):
    url, meta = item
    if isinstance(meta, dict):
        card = meta.get("card") or ""
        teaser_image = meta.get("image")
    else:
        card = meta
        teaser_image = None
    try:
        s = soup(url, use_browser=False)
    except Exception:
        try:
            s = soup(url, use_browser=True)
        except Exception:
            return _teaser_lot(url, card, teaser_image)
    detail_image = image_from_soup(s, url) or teaser_image
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True))
    status_probe = _live_status_probe(s, card)
    if re.search(r"\b(?:withdrawn(?:\s+prior)?|sold\s+prior)\b", status_probe, re.I):
        return None

    address = _address_from_soup(s, card)
    if not address:
        return _teaser_lot(url, card, detail_image)

    title_tag = s.find("h1")
    opportunity_title = norm(title_tag.get_text(" ", strip=True)) if title_tag else ""
    combined = opportunity_title + " " + card + " " + text
    if not is_commercial(combined):
        return None

    lp_url, lp_status = legal_pack(s, url)
    rent = parse_rent(combined)
    guide = parse_guide(combined)
    tenure = parse_tenure(combined)
    fallback_date = _header_auction_date(combined) or _month_date(card)
    auction_date = _exact_auction_date(text, fallback_date)

    occupation = None
    if re.search(r"\bvacant\b|vacant possession", combined, re.I) and not rent:
        occupation = "Vacant / vacant possession"
    elif rent:
        occupation = "Tenanted"

    return Lot(
        source=SOURCE, url=url, address=address, lot_number=_lot_no(card + " " + text[:800]),
        auction_date=auction_date, image_url=detail_image, guide_price=guide,
        annual_rent=rent, tenure=tenure, vat_status=parse_vat(combined),
        legal_pack_status=lp_status, legal_pack_url=lp_url, description=combined[:6500],
        occupation=occupation, property_type=opportunity_title[:180] if opportunity_title else None,
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

        live_targets = {url: meta for url, meta in targets.items() if _candidate_is_current_or_future((meta.get("card") if isinstance(meta, dict) else meta) or "")}
        if not live_targets:
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                f"Allsop exposed {len(targets)} commercial/mixed-use history/featured lot pages, but no current/future commercial catalogue lots are published yet.",
                discovered_count=len(targets), authoritative_snapshot=True,
            )

        lots = []
        failures = 0
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_hydrate, item): item[0] for item in live_targets.items()}
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
            SOURCE, status, lots,
            f"Allsop canonical+search collector: {len(live_targets)} current/future commercial/mixed-use candidate pages from {len(targets)} total target tiles; {len(lots)} published; {failures} detail failures.",
            discovered_count=len(live_targets), authoritative_snapshot=False,
            scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Allsop collection failed: {exc}")
