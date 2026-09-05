import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"
PATTINSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "no-cache",
}
COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "drinking establishment", "pub", "restaurant", "restaurants",
    "hot food takeaway", "takeaway", "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development",
    "land and development", "development land", "hospitality facility", "land",
)
RESIDENTIAL_LABELS = ("residential portfolio", "hmo", "house in ", "flat in ", "bungalow in ", "apartment in ")


def _auction_card(text):
    low = norm(text).lower()
    if not ("starting bid" in low or "current bid" in low or "reduced starting bid" in low):
        return False
    if any(x in low for x in RESIDENTIAL_LABELS):
        return False
    return any(x in low for x in COMMERCIAL_LABELS)


def _detail_url(a):
    u = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
    return u if re.fullmatch(r"https://www\.pattinson\.co\.uk/property/\d+", u, re.I) else None


def _lot_from_card(card, url=None):
    text = norm(card)
    if not _auction_card(text):
        return None
    m = re.search(r"(?:Reduced\s+)?(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
    guide = float(m.group(1).replace(",", "")) if m else None
    address = text
    maddr = re.search(
        r"(?:Commercial Development|Land & Development|Hospitality Facility|Drinking Establishment|Hot Food Takeaway|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Land|Commercial)\s+in\s+(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|Gated|Rear|None)\s+parking|$)",
        text, re.I)
    if maddr:
        address = norm(maddr.group(1))
    ptype = next((x for x in (
        "Commercial Development", "Land & Development", "Hospitality Facility", "Drinking Establishment",
        "Hot Food Takeaway", "Restaurant", "Retail", "Hotel", "Offices", "Industrial", "Warehouse", "Workshop", "Leisure", "Land", "Commercial"
    ) if x.lower() in text.lower()), "Commercial")
    return Lot(source=SOURCE, url=url or SEARCH, address=address, auction_date=None,
               guide_price=guide, property_type=ptype, description=text[:5000]).finalise()


def _direct_soup(url, timeout=10):
    try:
        r = requests.get(url, headers=PATTINSON_HEADERS, timeout=timeout)
        r.raise_for_status()
        if len(r.text) > 4000:
            return BeautifulSoup(r.text, "lxml")
    except Exception as exc:
        print("PATTINSON_DIRECT_FAIL", url, repr(exc))
    return None


def _search_soup(url):
    # Search inventory is essential, so allow one rendered fallback. Detail pages
    # never invoke Playwright: hundreds of per-lot browser launches previously made
    # the production scan run for more than an hour.
    s = _direct_soup(url, timeout=12)
    if s is not None:
        return s
    try:
        return soup(url, use_browser=True)
    except Exception:
        return None


def _enrich(url, seed):
    # Direct HTTP is fast and sufficient for Pattinson detail pages. If a detail
    # request fails transiently, retain the source card as a valid inventory row;
    # a later run can enrich it instead of losing the property entirely.
    ds = _direct_soup(url, timeout=9)
    base_lot = _lot_from_card(seed, url)
    if ds is None:
        return base_lot, False

    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    detail_is_auction = bool(re.search(r"starting bid|current bid|secure sale online bidding|online auction", text, re.I))
    detail_is_commercial = any(x in text.lower() for x in COMMERCIAL_LABELS) and not any(x in text.lower() for x in RESIDENTIAL_LABELS)
    lot = base_lot
    if not lot and detail_is_auction and detail_is_commercial:
        title_text = norm(ds.title.get_text(" ", strip=True)) if ds.title else ""
        address = title_text.split(" | Auction Property", 1)[0] if " | Auction Property" in title_text else ""
        h1 = ds.find("h1")
        ptype = norm(h1.get_text(" ", strip=True)) if h1 else "Commercial"
        lot = Lot(source=SOURCE, url=url, address=address or ptype, auction_date=None,
                  guide_price=parse_guide(text), property_type=ptype, description=text[:5000]).finalise()
    if not lot:
        return None, True

    if ds.title:
        tt = norm(ds.title.get_text(" ", strip=True))
        if " | Auction Property" in tt:
            lot.address = tt.split(" | Auction Property", 1)[0]
    h1 = ds.find("h1")
    if (not lot.address or " in " in lot.address.lower()) and h1:
        parent_text = norm((h1.parent or h1).get_text(" ", strip=True))
        h1_text = norm(h1.get_text(" ", strip=True))
        tail = parent_text[len(h1_text):].strip() if parent_text.startswith(h1_text) else ""
        if tail:
            lot.address = tail.split("Tenure", 1)[0].split("Connecting to auction", 1)[0].strip()

    lot.image_url = image_from_soup(ds, url)
    lot.guide_price = parse_guide(text) or lot.guide_price
    lot.annual_rent = parse_rent(text)
    lot.tenure = parse_tenure(text + " " + seed)
    lot.vat_status = parse_vat(text)
    lp_url, lp_status = legal_pack(ds, url)
    lot.legal_pack_url, lot.legal_pack_status = lp_url, lp_status
    lot.description = text[:5000]
    if re.search(r"vacant possession|\bvacant\b", text, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", text, re.I):
        lot.occupation = "Vacant"
        lot.annual_rent = None
    elif re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", text, re.I):
        lot.occupation = "Tenanted"
    return lot.finalise(), True


def _discover_page(url):
    s = _search_soup(url)
    if s is None:
        return {}, None
    text = norm(s.get_text(" ", strip=True))
    m = re.search(r"\b(\d{1,5})\s+results\b", text, re.I)
    total = int(m.group(1)) if m else None
    found = {}
    for a in s.find_all("a", href=True):
        href = _detail_url(a)
        if not href:
            continue
        card = norm(a.get_text(" ", strip=True))
        if not _auction_card(card):
            near = nearest_card(a, 2600)
            if _auction_card(near):
                card = near
        if _auction_card(card):
            found[href] = card
    return found, total


def collect():
    try:
        candidates = {}
        pages_seen = 0
        first, total_results = _discover_page(SEARCH)
        pages_seen += 1
        candidates.update(first)
        if not first:
            return SourceResult(SOURCE, "FAILED", [], "Pattinson commercial search returned no parseable auction cards on page 1.", discovered_count=0)

        # Source currently renders 20 cards per page. Derive the limit from the
        # advertised result total and keep a hard ceiling as runaway protection.
        page_limit = min(40, max(1, math.ceil((total_results or 20) / 20)))
        previous_ids = set(first)
        for n in range(2, page_limit + 1):
            url = BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale"
            found, _ = _discover_page(url)
            pages_seen += 1
            ids = set(found)
            if not ids or ids == previous_ids:
                break
            candidates.update(found)
            previous_ids = ids

        lots = []
        detail_failures = 0
        rejected = 0
        with ThreadPoolExecutor(max_workers=28) as ex:
            futs = {ex.submit(_enrich, href, card): (href, card) for href, card in candidates.items()}
            for f in as_completed(futs):
                href, card = futs[f]
                try:
                    lot, enriched = f.result()
                    if lot:
                        lots.append(lot)
                        if not enriched:
                            detail_failures += 1
                    else:
                        rejected += 1
                except Exception as exc:
                    detail_failures += 1
                    fallback = _lot_from_card(card, href)
                    if fallback:
                        lots.append(fallback)
                    print("PATTINSON_DETAIL_FAIL", href, repr(exc))

        dedup = {lot.url or (norm(lot.address).lower(), lot.guide_price): lot for lot in lots}
        lots = list(dedup.values())
        status = "LIVE" if lots and detail_failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Commercial inventory {total_results if total_results is not None else 'unknown'} source results across {pages_seen} page(s); {len(candidates)} commercial auction cards; {len(lots)} published; {detail_failures} awaiting detail enrichment; {rejected} detail rejections",
            discovered_count=len(candidates),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
