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

# Pattinson treats the repository-wide AuctionSniper UA differently from a normal
# browser on its search pages. Keep this identity local to this collector so a
# source-specific anti-bot workaround cannot destabilise the other auction houses.
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
    if not ("starting bid" in low or "current bid" in low):
        return False
    if any(x in low for x in RESIDENTIAL_LABELS):
        return False
    return any(x in low for x in COMMERCIAL_LABELS)


def _detail_url(a):
    u = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
    if re.fullmatch(r"https://www\.pattinson\.co\.uk/property/\d+", u, re.I):
        return u
    return None


def _lot_from_card(card, url=None):
    text = norm(card)
    if not _auction_card(text):
        return None
    m = re.search(r"(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
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


def _source_soup(url):
    """Fetch Pattinson search/detail HTML with a normal browser identity first."""
    try:
        r = requests.get(url, headers=PATTINSON_HEADERS, timeout=25)
        r.raise_for_status()
        if len(r.text) > 5000:
            return BeautifulSoup(r.text, "lxml")
    except Exception as exc:
        print("PATTINSON_DIRECT_FAIL", url, repr(exc))
    for use_browser in (False, True):
        try:
            s = soup(url, use_browser=use_browser)
            if s:
                return s
        except Exception:
            pass
    return None


def _enrich(url, seed):
    ds = _source_soup(url)
    if ds is None:
        return None
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))

    # Detail pages are authoritative. This also allows recovery when the search
    # card text is embedded in JS rather than attached to the result anchor.
    detail_is_auction = bool(re.search(r"starting bid|current bid|secure sale online bidding|online auction", text, re.I))
    detail_is_commercial = any(x in text.lower() for x in COMMERCIAL_LABELS) and not any(x in text.lower() for x in RESIDENTIAL_LABELS)
    lot = _lot_from_card(seed, url)
    if not lot and detail_is_auction and detail_is_commercial:
        title_text = ""
        title = ds.find("title")
        if title:
            title_text = norm(title.get_text(" ", strip=True))
        address = title_text.split(" | Auction Property", 1)[0] if " | Auction Property" in title_text else ""
        h1 = ds.find("h1")
        ptype = norm(h1.get_text(" ", strip=True)) if h1 else "Commercial"
        lot = Lot(source=SOURCE, url=url, address=address or ptype, auction_date=None,
                  guide_price=parse_guide(text), property_type=ptype, description=text[:5000]).finalise()
    if not lot:
        return None

    title = ds.find("title")
    if title:
        tt = norm(title.get_text(" ", strip=True))
        if " | Auction Property" in tt:
            lot.address = tt.split(" | Auction Property", 1)[0]
    if not lot.address or lot.address == seed or " in " in lot.address.lower():
        h1 = ds.find("h1")
        if h1:
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
    return lot.finalise()


def _discover_page(url):
    s = _source_soup(url)
    if s is None:
        return {}
    found = {}
    raw_property_urls = set()
    for a in s.find_all("a", href=True):
        href = _detail_url(a)
        if not href:
            continue
        raw_property_urls.add(href)
        card = norm(a.get_text(" ", strip=True))
        if not _auction_card(card):
            near = nearest_card(a, 3200)
            if _auction_card(near):
                card = near
        if _auction_card(card):
            found[href] = card

    # Some responses contain property links but render result text separately.
    # Preserve those URLs as detail-validation candidates instead of returning a
    # catastrophic false zero; _enrich will require auction + commercial evidence.
    if not found and raw_property_urls:
        found.update({href: "" for href in raw_property_urls})
    return found


def collect():
    try:
        candidates = {}
        pages_seen = 0
        previous_page_ids = None
        consecutive_empty = 0
        for n in range(1, 31):
            url = SEARCH if n == 1 else BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale"
            found = _discover_page(url)
            pages_seen += 1
            page_ids = {href.rsplit("/", 1)[-1] for href in found}
            candidates.update(found)
            if page_ids:
                consecutive_empty = 0
            else:
                consecutive_empty += 1
            if n > 1 and page_ids and page_ids == previous_page_ids:
                break
            if consecutive_empty >= 2 and candidates:
                break
            previous_page_ids = page_ids or previous_page_ids

        lots = []
        failures = 0
        with ThreadPoolExecutor(max_workers=12) as ex:
            futs = {ex.submit(_enrich, href, card): href for href, card in candidates.items()}
            for f in as_completed(futs):
                try:
                    lot = f.result()
                    if lot:
                        lots.append(lot)
                except Exception as exc:
                    failures += 1
                    print("PATTINSON_DETAIL_FAIL", futs[f], repr(exc))

        dedup = {}
        for lot in lots:
            key = lot.url or (norm(lot.address).lower(), lot.guide_price)
            dedup[key] = lot
        lots = list(dedup.values())
        status = "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Commercial inventory pages {pages_seen}; {len(candidates)} property candidates; {len(lots)} verified auction-commercial lots published; {failures} enrichment failures",
            discovered_count=len(candidates),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
