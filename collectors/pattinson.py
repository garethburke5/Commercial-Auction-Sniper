import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/auction/property-search"
PARTNER_BASE = "https://addisonbarton.pattinson.co.uk"
PARTNER_SEARCH = PARTNER_BASE + "/"
PATTINSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
SEARCH_PARAMS = {
    "IncludeCommercialProperties": "true",
    "OnlineOnly": "true",
    "PropertySort": "EndingSoonest",
    "PageSize": "100",
}
COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "drinking establishment", "pub", "restaurant", "restaurants",
    "hot food takeaway", "takeaway", "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development", "land and development",
    "development land", "hospitality facility", "commercial land", "investment property", "pair of flats",
    "block of apartments",
)
RESIDENTIAL_LABELS = (
    "residential portfolio", "residential development", " hmo ", "house in ", "flat in ",
    "bungalow in ", "apartment in ", "retirement property", "bedroom house", "bed apartment",
    "terraced house", "semi-detached house", "detached house", "maisonette", "studio flat",
)
MIXED_MARKERS = (
    "shop and flat", "shop with flat", "retail and residential", "commercial and residential",
    "commercial/residential", "mixed use", "mixed-use", "pair of flats", "block of apartments",
)
CLOSED_MARKERS = (
    " sold ", " sold stc ", " sold subject ", " auction ended ", " bidding ended ",
    " withdrawn ", " no longer available ", " under offer ",
)


def _is_current_auction(text):
    low = " " + norm(text).lower() + " "
    if any(x in low for x in CLOSED_MARKERS):
        return False
    return any(x in low for x in ("starting bid", "current bid", "reduced starting bid", "bid now", "online auction", "secure sale"))


def _is_commercial(text):
    low = " " + norm(text).lower() + " "
    if any(x in low for x in MIXED_MARKERS):
        return True
    if any(x in low for x in RESIDENTIAL_LABELS):
        return False
    return any(x in low for x in COMMERCIAL_LABELS)


def _auction_card(text):
    return _is_current_auction(text) and _is_commercial(text)


def _property_id(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    parsed = urlparse(urljoin(BASE, raw))
    m = re.search(r"/property/(\d+)(?:/|$)", parsed.path, re.I)
    if m:
        return m.group(1)
    if parsed.path.rstrip("/").lower().endswith("/property"):
        pid = (parse_qs(parsed.query).get("id") or [None])[0]
        if pid and re.fullmatch(r"\d+", pid):
            return pid
    return None


def _canonical_property_url(raw):
    pid = _property_id(raw)
    return f"{BASE}/property/{pid}" if pid else None


def _partner_property_url(raw):
    pid = _property_id(raw)
    return f"{PARTNER_BASE}/property?id={pid}" if pid else None


def _detail_url(a):
    return _canonical_property_url(a.get("href") or "")


def _lot_from_card(card, url=None):
    text = norm(card)
    if not _auction_card(text):
        return None
    m = re.search(r"(?:Reduced\s+)?(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
    guide = float(m.group(1).replace(",", "")) if m else None
    address = text
    maddr = re.search(
        r"(?:Commercial Development|Land & Development|Hospitality Facility|Drinking Establishment|Hot Food Takeaway|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Commercial Land|Commercial|Investment Property|Pair of Flats|Block of Apartments)\s+in\s+(?:[A-Z]{1,2}\d[A-Z\d]?\s+)?(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|Gated|Rear|None|Residents)\s+parking|$)",
        text, re.I,
    )
    if maddr:
        address = norm(maddr.group(1))
    ptype = next((x for x in (
        "Commercial Development", "Land & Development", "Hospitality Facility", "Drinking Establishment",
        "Hot Food Takeaway", "Restaurant", "Retail", "Hotel", "Offices", "Industrial", "Warehouse",
        "Workshop", "Leisure", "Commercial Land", "Investment Property", "Pair of Flats",
        "Block of Apartments", "Commercial",
    ) if x.lower() in text.lower()), "Commercial")
    return Lot(
        source=SOURCE, url=url or SEARCH, address=address, auction_date=None,
        guide_price=guide, property_type=ptype, description=text[:5000],
    ).finalise()


def _html_soup(text):
    if not text or len(text) < 700 or "Just a moment..." in text or "cf-chl-" in text:
        return None
    return BeautifulSoup(text, "lxml")


def _direct_soup(url, timeout=15):
    try:
        r = requests.get(url, headers=PATTINSON_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return _html_soup(r.text)
        print("PATTINSON_DIRECT_STATUS", url, r.status_code, len(r.content))
    except Exception as exc:
        print("PATTINSON_DIRECT_FAIL", url, repr(exc))
    return None


def _parse_search_html(html):
    s = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html or "", "lxml")
    text = norm(s.get_text(" ", strip=True))
    m = re.search(r"\b(\d{1,6})\s+results\b", text, re.I)
    total = int(m.group(1)) if m else None
    found = {}
    all_property_ids = set()
    max_page = 1

    for a in s.find_all("a", href=True):
        href = a.get("href") or ""
        pid = _property_id(href)
        if pid:
            all_property_ids.add(pid)
            canonical = f"{BASE}/property/{pid}"
            card = norm(a.get_text(" ", strip=True))
            if not _auction_card(card):
                near = nearest_card(a, 4200)
                if _auction_card(near):
                    card = near
            if _auction_card(card):
                found[canonical] = card
        parsed = urlparse(urljoin(BASE, href))
        try:
            p = int((parse_qs(parsed.query).get("p") or ["1"])[0])
            max_page = max(max_page, p)
        except (TypeError, ValueError):
            pass

    return found, total, all_property_ids, max_page


def _page_url(page_number, search_base=SEARCH):
    params = dict(SEARCH_PARAMS)
    params["p"] = str(page_number)
    return search_base + ("&" if "?" in search_base else "?") + urlencode(params)


def _discover_with(fetcher, search_base=SEARCH, hard_cap=200):
    first = fetcher(_page_url(1, search_base))
    if first is None:
        return {}, None, 0
    first_found, total, first_ids, advertised_max = _parse_search_html(first)
    candidates = dict(first_found)
    pages_seen = 1
    page_size_seen = max(1, len(first_ids))
    estimated_pages = math.ceil(total / page_size_seen) if total else 1
    limit = min(hard_cap, max(1, advertised_max, estimated_pages))
    previous_ids = first_ids

    for n in range(2, limit + 1):
        page = fetcher(_page_url(n, search_base))
        if page is None:
            break
        page_found, _, page_ids, page_max = _parse_search_html(page)
        pages_seen += 1
        candidates.update(page_found)
        if page_max > limit:
            limit = min(hard_cap, page_max)
        if not page_ids:
            break
        if page_ids == previous_ids:
            break
        previous_ids = page_ids
    return candidates, total, pages_seen


def _discover_main():
    return _discover_with(lambda url: _direct_soup(url, timeout=15), SEARCH)


def _discover_partner():
    return _discover_with(lambda url: _direct_soup(url, timeout=15), PARTNER_SEARCH)


def _discover_browser(search_base=SEARCH):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent=PATTINSON_HEADERS["User-Agent"], locale="en-GB")
            page = context.new_page()

            def fetcher(url):
                response = page.goto(url, wait_until="domcontentloaded", timeout=35000)
                if not response or response.status != 200:
                    return None
                try:
                    page.wait_for_selector("a[href*='property']", timeout=7000)
                except Exception:
                    pass
                return BeautifulSoup(page.content(), "lxml")

            result = _discover_with(fetcher, search_base)
            context.close()
            browser.close()
            return result
    except Exception as exc:
        print("PATTINSON_BROWSER_FAIL", search_base, repr(exc))
        return {}, None, 0


def _discover_inventory():
    # Free/public routes only. The partner portal is first-party Pattinson data and
    # is intentionally preferred over any paid proxy dependency when main-site
    # Cloudflare rejects datacentre runners.
    for mode, fn in (
        ("auction-direct", _discover_main),
        ("partner-direct", _discover_partner),
        ("partner-browser", lambda: _discover_browser(PARTNER_SEARCH)),
        ("auction-browser", lambda: _discover_browser(SEARCH)),
    ):
        candidates, total, pages_seen = fn()
        if candidates:
            return candidates, total, pages_seen, mode
    return {}, None, 0, "unavailable"


def _detail_soup(url):
    # Canonical main page first, then the free Pattinson partner representation.
    ds = _direct_soup(url, timeout=10)
    if ds is not None:
        return ds, "main-detail"
    partner = _partner_property_url(url)
    if partner:
        ds = _direct_soup(partner, timeout=12)
        if ds is not None:
            return ds, "partner-detail"
    return None, None


def _apply_detail(lot, ds, seed, url):
    if ds is None:
        return lot
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    low = " " + text.lower() + " "
    if any(x in low for x in CLOSED_MARKERS):
        return None
    if not _is_current_auction(text + " " + seed):
        return None
    if not _is_commercial(text + " " + seed):
        return None

    h1 = ds.find("h1")
    if h1:
        title = norm(h1.get_text(" ", strip=True))
        if title and not re.search(r"pattinson|property search|properties at auction|just a moment", title, re.I):
            # Partner pages often put the generic property type in h1. Prefer the
            # address line immediately following it when present.
            postcode_address = None
            for node in h1.find_all_next(["h2", "h3", "p", "div"], limit=12):
                candidate = norm(node.get_text(" ", strip=True))
                if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", candidate, re.I) and len(candidate) < 240:
                    postcode_address = candidate
                    break
            lot.address = postcode_address or title
    elif ds.title:
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
    epc = re.search(r"\bEPC(?:\s+Rating)?\s*[:\-]?\s*([A-G])\b", text, re.I)
    if epc:
        lot.epc = epc.group(1).upper()
    if re.search(r"vacant possession|\bvacant\b", text, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", text, re.I):
        lot.occupation = "Vacant"
        lot.annual_rent = None
    elif re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", text, re.I):
        lot.occupation = "Tenanted"
    return lot.finalise()


def _enrich(url, seed):
    lot = _lot_from_card(seed, url)
    if not lot:
        return None, True, None
    ds, detail_mode = _detail_soup(url)
    if ds is None:
        return lot, False, None
    return _apply_detail(lot, ds, seed, url), True, detail_mode


def collect():
    try:
        candidates, total_results, pages_seen, mode = _discover_inventory()
        if not candidates:
            return SourceResult(
                SOURCE, "FAILED", [],
                "No parseable Pattinson commercial/mixed-use auction inventory from either the canonical site or the free first-party partner portal.",
                discovered_count=0,
            )

        lots = []
        detail_failures = 0
        rejected = 0
        detail_modes = {}
        with ThreadPoolExecutor(max_workers=14) as ex:
            futures = {ex.submit(_enrich, href, card): (href, card) for href, card in candidates.items()}
            for future in as_completed(futures):
                href, card = futures[future]
                try:
                    lot, enriched, detail_mode = future.result()
                    if lot:
                        lots.append(lot)
                        if not enriched:
                            detail_failures += 1
                        if detail_mode:
                            detail_modes[detail_mode] = detail_modes.get(detail_mode, 0) + 1
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
        detail_note = ", ".join(f"{k}={v}" for k, v in sorted(detail_modes.items())) or "detail-unavailable"
        return SourceResult(
            SOURCE, status, lots,
            f"Auction inventory {total_results if total_results is not None else 'unknown'} source results across {pages_seen} page(s) via {mode}; "
            f"{len(candidates)} current commercial/mixed-use auction cards; {len(lots)} published; {detail_failures} card-only/detail-limited; {rejected} rejected; {detail_note}",
            expected_count=len(candidates), discovered_count=len(candidates),
            authoritative_snapshot=(status == "LIVE"),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], str(exc))
