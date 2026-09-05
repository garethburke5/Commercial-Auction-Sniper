import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/auction/property-search"
SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com"
PATTINSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "drinking establishment", "pub", "restaurant", "restaurants",
    "hot food takeaway", "takeaway", "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development", "land and development",
    "development land", "hospitality facility", "commercial land", "investment property",
)
RESIDENTIAL_LABELS = (
    "residential portfolio", "residential development", " hmo ", "house in ", "flat in ",
    "bungalow in ", "apartment in ", "retirement property", "bedroom house", "bed apartment",
    "terraced house", "semi-detached house", "detached house", "maisonette", "studio flat",
)
CLOSED_MARKERS = (
    " sold ", " sold stc ", " sold subject ", " auction ended ", " bidding ended ",
    " withdrawn ", " no longer available ", " under offer ",
)


def _is_current_auction(text):
    low = " " + norm(text).lower() + " "
    if any(x in low for x in CLOSED_MARKERS):
        return False
    return any(x in low for x in ("starting bid", "current bid", "reduced starting bid", "bid now", "online auction"))


def _is_commercial(text):
    low = " " + norm(text).lower() + " "
    if any(x in low for x in RESIDENTIAL_LABELS):
        return False
    return any(x in low for x in COMMERCIAL_LABELS)


def _auction_card(text):
    return _is_current_auction(text) and _is_commercial(text)


def _normalise_property_url(raw):
    raw = (raw or "").strip()
    if raw.startswith("/"):
        raw = urljoin(BASE, raw)
    raw = raw.replace("http://pattinson.co.uk/", "https://www.pattinson.co.uk/")
    raw = raw.replace("https://pattinson.co.uk/", "https://www.pattinson.co.uk/")
    u = raw.split("?")[0].split("#")[0].rstrip("/")
    return u if re.fullmatch(r"https://www\.pattinson\.co\.uk/property/\d+", u, re.I) else None


def _detail_url(a):
    return _normalise_property_url(urljoin(BASE, a.get("href") or ""))


def _lot_from_card(card, url=None):
    text = norm(card)
    if not _auction_card(text):
        return None
    m = re.search(r"(?:Reduced\s+)?(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
    guide = float(m.group(1).replace(",", "")) if m else None
    address = text
    maddr = re.search(
        r"(?:Commercial Development|Land & Development|Hospitality Facility|Drinking Establishment|Hot Food Takeaway|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Commercial Land|Commercial|Investment Property)\s+in\s+(?:[A-Z]{1,2}\d[A-Z\d]?\s+)?(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|Gated|Rear|None|Residents)\s+parking|$)",
        text, re.I,
    )
    if maddr:
        address = norm(maddr.group(1))
    ptype = next((x for x in (
        "Commercial Development", "Land & Development", "Hospitality Facility", "Drinking Establishment",
        "Hot Food Takeaway", "Restaurant", "Retail", "Hotel", "Offices", "Industrial", "Warehouse",
        "Workshop", "Leisure", "Commercial Land", "Investment Property", "Commercial",
    ) if x.lower() in text.lower()), "Commercial")
    return Lot(
        source=SOURCE, url=url or SEARCH, address=address, auction_date=None,
        guide_price=guide, property_type=ptype, description=text[:5000],
    ).finalise()


def _html_soup(text):
    if not text or len(text) < 1000 or "Just a moment..." in text:
        return None
    return BeautifulSoup(text, "lxml")


def _direct_soup(url, timeout=10):
    try:
        r = requests.get(url, headers=PATTINSON_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return _html_soup(r.text)
        print("PATTINSON_DIRECT_STATUS", url, r.status_code)
    except Exception as exc:
        print("PATTINSON_DIRECT_FAIL", url, repr(exc))
    return None


def _scraperapi_soup(url, *, render=False, timeout=75):
    key = os.getenv("SCRAPERAPI_KEY", "").strip()
    if not key:
        return None
    params = {
        "api_key": key,
        "url": url,
        "country_code": "uk",
        "premium": "true",
    }
    if render:
        params["render"] = "true"
    try:
        r = requests.get(SCRAPERAPI_ENDPOINT, params=params, timeout=timeout)
        if r.status_code == 200:
            parsed = _html_soup(r.text)
            if parsed is not None:
                return parsed
        print("PATTINSON_SCRAPERAPI_STATUS", url, r.status_code, len(r.content))
    except Exception as exc:
        print("PATTINSON_SCRAPERAPI_FAIL", url, repr(exc))
    return None


def _parse_search_html(html):
    s = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html or "", "lxml")
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
            near = nearest_card(a, 3200)
            if _auction_card(near):
                card = near
        if _auction_card(card):
            found[href] = card
    return found, total


def _page_url(page_number):
    return SEARCH if page_number == 1 else SEARCH + f"?p={page_number}"


def _discover_with(fetcher):
    first = fetcher(_page_url(1))
    if first is None:
        return {}, None, 0
    first_found, total = _parse_search_html(first)
    candidates = dict(first_found)
    pages_seen = 1
    if total is None:
        limit = 100
    else:
        limit = min(100, max(1, math.ceil(total / 20)))
    previous = set(first_found)
    for n in range(2, limit + 1):
        page = fetcher(_page_url(n))
        if page is None:
            break
        page_found, _ = _parse_search_html(page)
        pages_seen += 1
        ids = set(page_found)
        if ids == previous and ids:
            break
        candidates.update(page_found)
        previous = ids
        # If the final page has no property links at all, stop. A page with only
        # residential cards is valid and must not terminate an auction-wide sweep.
        if not page.find("a", href=re.compile(r"/property/\d+")):
            break
    return candidates, total, pages_seen


def _discover_direct():
    return _discover_with(lambda url: _direct_soup(url, timeout=12))


def _discover_scraperapi():
    return _discover_with(lambda url: _scraperapi_soup(url, render=True, timeout=75))


def _discover_browser():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
            context = browser.new_context(user_agent=PATTINSON_HEADERS["User-Agent"], locale="en-GB")
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            def fetcher(url):
                response = page.goto(url, wait_until="domcontentloaded", timeout=35000)
                if not response or response.status != 200:
                    return None
                try:
                    page.wait_for_selector("a[href*='/property/']", timeout=8000)
                except Exception:
                    pass
                return BeautifulSoup(page.content(), "lxml")

            result = _discover_with(fetcher)
            context.close(); browser.close()
            return result
    except Exception as exc:
        print("PATTINSON_BROWSER_FAIL", repr(exc))
        return {}, None, 0


def _discover_inventory():
    candidates, total, pages_seen = _discover_direct()
    if candidates:
        return candidates, total, pages_seen, "auction-direct"
    candidates, total, pages_seen = _discover_browser()
    if candidates:
        return candidates, total, pages_seen, "auction-browser"
    candidates, total, pages_seen = _discover_scraperapi()
    return candidates, total, pages_seen, "auction-scraperapi"


def _apply_detail(lot, ds, seed, url):
    if ds is None:
        return lot
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    low = " " + text.lower() + " "
    if any(x in low for x in CLOSED_MARKERS):
        return None
    if not _is_current_auction(text):
        return None
    if not _is_commercial(text + " " + seed):
        return None

    if ds.title:
        tt = norm(ds.title.get_text(" ", strip=True))
        tt = re.sub(r"\s*\|\s*(?:Auction Property|Pattinson Estate Agents).*$", "", tt, flags=re.I)
        if tt and not re.search(r"pattinson|property search|commercial properties|just a moment", tt, re.I):
            lot.address = tt

    lot.image_url = image_from_soup(ds, url)
    lot.guide_price = parse_guide(text) or lot.guide_price
    if not lot.guide_price:
        m = re.search(r"(?:Reduced\s+)?(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
        if m:
            lot.guide_price = float(m.group(1).replace(",", ""))
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


def _enrich(url, seed, use_proxy=False):
    lot = _lot_from_card(seed, url)
    if not lot:
        return None, True
    ds = _direct_soup(url, timeout=8)
    if ds is None and use_proxy:
        ds = _scraperapi_soup(url, render=False, timeout=50)
    if ds is None:
        return lot, False
    return _apply_detail(lot, ds, seed, url), True


def collect():
    try:
        candidates, total_results, pages_seen, mode = _discover_inventory()
        if not candidates:
            key_present = bool(os.getenv("SCRAPERAPI_KEY", "").strip())
            message = (
                "Pattinson auction search is protected by a Cloudflare managed challenge on GitHub/Azure egress. "
                + ("Configured residential proxy also returned no parseable current commercial auction cards."
                   if key_present else "Set SCRAPERAPI_KEY to enable the residential-proxy fallback for the auction inventory.")
            )
            return SourceResult(SOURCE, "FAILED", [], message, discovered_count=0)

        lots = []
        detail_failures = 0
        rejected = 0
        use_proxy = mode == "auction-scraperapi"
        workers = 6 if use_proxy else 16
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_enrich, href, card, use_proxy): (href, card) for href, card in candidates.items()}
            for future in as_completed(futures):
                href, card = futures[future]
                try:
                    lot, enriched = future.result()
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
        status = "LIVE" if lots and len(lots) == len(candidates) and rejected == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Auction inventory {total_results if total_results is not None else 'unknown'} source results across {pages_seen} page(s) via {mode}; "
            f"{len(candidates)} current commercial/mixed-use auction cards; {len(lots)} published; {detail_failures} card-only/detail-limited; {rejected} rejected",
            expected_count=len(candidates), discovered_count=len(candidates),
            authoritative_snapshot=(status == "LIVE"),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], str(exc))
