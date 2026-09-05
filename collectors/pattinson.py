import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"

COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "drinking establishment", "pub", "restaurant", "restaurants",
    "takeaway", "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development",
    "land and development", "development land", "hospitality facility", "land",
)
RESIDENTIAL_LABELS = ("residential portfolio", "hmo", "house in ", "flat in ", "bungalow in ", "apartment in ")


def _auction_card(text):
    low = norm(text).lower()
    # Pattinson mixes sale, letting and auction inventory on the commercial search.
    # A bid marker is the reliable discriminator for a currently auction-listed lot.
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
        r"(?:Commercial Development|Land & Development|Hospitality Facility|Drinking Establishment|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Land|Commercial)\s+in\s+(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|Gated|None)\s+parking|$)",
        text, re.I)
    if maddr:
        address = norm(maddr.group(1))
    ptype = next((x for x in (
        "Commercial Development", "Land & Development", "Hospitality Facility", "Drinking Establishment",
        "Restaurant", "Retail", "Hotel", "Offices", "Industrial", "Warehouse", "Workshop", "Leisure", "Land", "Commercial"
    ) if x.lower() in text.lower()), "Commercial")
    return Lot(source=SOURCE, url=url or SEARCH, address=address, auction_date=None,
               guide_price=guide, property_type=ptype, description=text[:5000]).finalise()


def _enrich(url, seed):
    ds = None
    for use_browser in (False, True):
        try:
            ds = soup(url, use_browser=use_browser)
            if ds:
                break
        except Exception:
            pass
    if ds is None:
        return None
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    lot = _lot_from_card(seed, url)
    if not lot:
        return None

    # Detail h1 is usually a property type; the line immediately following it is
    # the true address. Prefer the page title (which contains the address) first.
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
    if re.search(r"vacant possession|\bvacant\b", text, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £", text, re.I):
        lot.occupation = "Vacant"
        lot.annual_rent = None
    elif re.search(r"tenant|tenanted|let to|currently let|producing £", text, re.I):
        lot.occupation = "Tenanted"
    return lot.finalise()


def _discover_page(url):
    """Return candidate auction cards, retrying the JS-rendered page when needed."""
    best = {}
    for use_browser in (False, True):
        try:
            s = soup(url, use_browser=use_browser)
        except Exception as exc:
            print("PATTINSON_SEARCH_FAIL", url, use_browser, repr(exc))
            continue
        found = {}
        for a in s.find_all("a", href=True):
            href = _detail_url(a)
            if not href:
                continue
            card = norm(a.get_text(" ", strip=True))
            if not _auction_card(card):
                near = nearest_card(a, 2400)
                if _auction_card(near):
                    card = near
            if _auction_card(card):
                found[href] = card
        if len(found) > len(best):
            best = found
        # One useful rendered page is enough; do not pay browser cost twice.
        if found and use_browser:
            break
        if found and not use_browser:
            break
    return best


def collect():
    try:
        candidates = {}
        pages_seen = 0
        previous_page_ids = None
        for n in range(1, 31):
            url = SEARCH if n == 1 else BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale"
            found = _discover_page(url)
            pages_seen += 1
            page_ids = {href.rsplit("/", 1)[-1] for href in found}
            candidates.update(found)

            # Search currently advertises about 20+ pages. Stop only after a real
            # pagination terminator/repeat, never because static HTML produced a false zero.
            if n > 1 and page_ids and page_ids == previous_page_ids:
                break
            if n > 1 and not page_ids:
                # one empty page after a populated previous page is the natural end
                if previous_page_ids:
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
            f"Commercial-sale pages {pages_seen}; {len(candidates)} auction-commercial cards discovered; {len(lots)} published; {failures} enrichment failures",
            discovered_count=len(candidates),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
