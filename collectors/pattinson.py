import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"
JINA_BASE = "https://r.jina.ai/http://www.pattinson.co.uk"
PATTINSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "no-cache",
}
JINA_HEADERS = {
    "Accept": "text/plain",
    "User-Agent": "Auction-Sniper/1.0 (+public-web-catalogue-monitor)",
    "X-No-Cache": "true",
}
COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "drinking establishment", "pub", "restaurant", "restaurants",
    "hot food takeaway", "takeaway", "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development",
    "land and development", "development land", "hospitality facility", "land",
)
RESIDENTIAL_LABELS = (
    "residential portfolio", "residential development", " hmo ", "house in ", "flat in ",
    "bungalow in ", "apartment in ", "retirement property", "bedroom house", "bed apartment",
)


def _auction_card(text):
    low = " " + norm(text).lower() + " "
    if not ("starting bid" in low or "current bid" in low or "reduced starting bid" in low):
        return False
    if any(x in low for x in RESIDENTIAL_LABELS):
        return False
    return any(x in low for x in COMMERCIAL_LABELS)


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
        r"(?:Commercial Development|Land & Development|Hospitality Facility|Drinking Establishment|Hot Food Takeaway|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Land|Commercial)\s+in\s+(?:[A-Z]{1,2}\d[A-Z\d]?\s+)?(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|Gated|Rear|None)\s+parking|$)",
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


def _jina_url(url):
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return JINA_BASE + path


def _jina_text(url, timeout=25):
    """Fetch Pattinson through Jina Reader when Pattinson blocks datacentre IPs.

    This is intentionally a source-specific fallback. The canonical URL remains
    Pattinson's exact property URL and every candidate is still positively
    classified as an auction-commercial listing before publication.
    """
    try:
        r = requests.get(_jina_url(url), headers=JINA_HEADERS, timeout=timeout)
        r.raise_for_status()
        text = r.text or ""
        if len(text) > 1000:
            return text
    except Exception as exc:
        print("PATTINSON_JINA_FAIL", url, repr(exc))
    return None


def _parse_search_html(html):
    s = BeautifulSoup(html or "", "lxml")
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


def _parse_search_markdown(markdown):
    text = markdown or ""
    m = re.search(r"\b(\d{1,5})\s+results\b", text, re.I)
    total = int(m.group(1)) if m else None
    found = {}

    # Jina preserves Pattinson result cards as Markdown links. Capture both
    # absolute and relative property URLs and classify on the visible card text.
    link_pat = re.compile(r"\[([^\]]{1,1200})\]\((https?://(?:www\.)?pattinson\.co\.uk/property/\d+|/property/\d+)(?:\?[^)]*)?\)", re.I | re.S)
    for match in link_pat.finditer(text):
        card = norm(match.group(1))
        href = _normalise_property_url(match.group(2))
        if href and _auction_card(card):
            found[href] = card

    # Some Reader renderings split the card text and URL over adjacent lines.
    # Recover those without inventing data by taking only a bounded preceding
    # window that itself contains an auction bid marker and commercial label.
    if not found:
        for match in re.finditer(r"https?://(?:www\.)?pattinson\.co\.uk/property/(\d+)", text, re.I):
            href = _normalise_property_url(match.group(0))
            start = max(0, match.start() - 1200)
            card = norm(re.sub(r"[\[\]()*_`#>|]", " ", text[start:match.start()]))
            if href and _auction_card(card):
                found[href] = card[-900:]
    return found, total


def _discover_via_jina():
    first_text = _jina_text(SEARCH, timeout=30)
    if not first_text:
        return {}, None, 0
    first_found, total = _parse_search_markdown(first_text)
    if not first_found:
        return {}, total, 1

    candidates = dict(first_found)
    pages_seen = 1
    limit = min(40, max(1, math.ceil((total or len(first_found)) / 20)))
    previous = set(first_found)
    for n in range(2, limit + 1):
        url = BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale"
        page_text = _jina_text(url, timeout=25)
        if not page_text:
            break
        page_found, _ = _parse_search_markdown(page_text)
        pages_seen += 1
        ids = set(page_found)
        if not ids or ids == previous:
            break
        candidates.update(page_found)
        previous = ids
    return candidates, total, pages_seen


def _discover_inventory():
    """Discover all current Pattinson auction-commercial inventory.

    Retrieval order is direct HTML, one reusable Chromium session, then Jina
    Reader. Pattinson currently blocks GitHub-hosted runners with HTTP 403, so
    the proxy path prevents one anti-bot edge from becoming a catalogue outage.
    """
    first = _direct_soup(SEARCH, timeout=12)
    if first is not None:
        found, total = _parse_search_html(str(first))
        if found:
            pages = {1: found}
            limit = min(40, max(1, math.ceil((total or len(found)) / 20)))
            for n in range(2, limit + 1):
                s = _direct_soup(BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale", timeout=10)
                if s is None:
                    break
                page_found, _ = _parse_search_html(str(s))
                if not page_found:
                    break
                pages[n] = page_found
            merged = {}
            for p in pages.values():
                merged.update(p)
            return merged, total, len(pages), "direct"

    try:
        from playwright.sync_api import sync_playwright
        candidates = {}
        total = None
        pages_seen = 0
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            context = browser.new_context(
                user_agent=PATTINSON_HEADERS["User-Agent"],
                locale="en-GB",
                extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
                viewport={"width": 1440, "height": 1200},
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.goto(SEARCH, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector("a[href*='/property/']", timeout=10000)
            except Exception:
                pass
            first_found, total = _parse_search_html(page.content())
            pages_seen = 1
            candidates.update(first_found)
            if first_found:
                limit = min(40, max(1, math.ceil((total or len(first_found)) / 20)))
                previous = set(first_found)
                for n in range(2, limit + 1):
                    page.goto(BASE + f"/commercial/property-search?p={n}&searchType=CommercialSale", wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_selector("a[href*='/property/']", timeout=8000)
                    except Exception:
                        pass
                    page_found, _ = _parse_search_html(page.content())
                    pages_seen += 1
                    ids = set(page_found)
                    if not ids or ids == previous:
                        break
                    candidates.update(page_found)
                    previous = ids
            context.close()
            browser.close()
        if candidates:
            return candidates, total, pages_seen, "browser"
    except Exception as exc:
        print("PATTINSON_BROWSER_FAIL", repr(exc))

    candidates, total, pages_seen = _discover_via_jina()
    return candidates, total, pages_seen, "reader-proxy"


def _enrich_from_markdown(url, seed, text):
    lot = _lot_from_card(seed, url)
    if not lot or not text:
        return lot
    cleaned = norm(re.sub(r"[\[\]()*_`#>|]", " ", text))

    # Property page title normally contains the address. Do not overwrite a
    # valid card-derived address with generic site/navigation copy.
    mt = re.search(r"^Title:\s*(.+?)(?:\s+URL Source:|$)", text, re.I | re.M)
    if mt:
        title = norm(mt.group(1))
        title = re.sub(r"\s*\|\s*(?:Auction Property|Pattinson Estate Agents).*$", "", title, flags=re.I)
        if title and not re.search(r"pattinson|property search|commercial properties", title, re.I):
            lot.address = title

    lot.guide_price = parse_guide(cleaned) or lot.guide_price
    lot.annual_rent = parse_rent(cleaned)
    lot.tenure = parse_tenure(cleaned + " " + seed)
    lot.vat_status = parse_vat(cleaned)
    lot.description = cleaned[:5000]

    # Reader preserves image URLs. Reject logos/icons and use the first likely
    # property photograph only.
    for im in re.finditer(r"!\[[^\]]*\]\((https?://[^)]+)\)", text, re.I):
        image = im.group(1)
        low = image.lower()
        if not any(x in low for x in ("logo", "icon", "avatar", "badge", "favicon")):
            lot.image_url = image
            break

    if re.search(r"vacant possession|\bvacant\b", cleaned, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", cleaned, re.I):
        lot.occupation = "Vacant"
        lot.annual_rent = None
    elif re.search(r"tenant|tenanted|let to|currently let|producing £|currently rented", cleaned, re.I):
        lot.occupation = "Tenanted"
    return lot.finalise()


def _enrich(url, seed):
    ds = _direct_soup(url, timeout=8)
    base_lot = _lot_from_card(seed, url)
    if ds is None:
        reader = _jina_text(url, timeout=20)
        if reader:
            return _enrich_from_markdown(url, seed, reader), True
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


def collect():
    try:
        candidates, total_results, pages_seen, mode = _discover_inventory()
        if not candidates:
            return SourceResult(
                SOURCE, "FAILED", [],
                "Pattinson commercial search returned no parseable auction-commercial cards after direct, browser and reader-proxy discovery.",
                discovered_count=0,
            )

        lots = []
        detail_failures = 0
        rejected = 0
        # Keep fallback traffic courteous and avoid proxy/rate-limit bursts.
        workers = 8 if mode == "reader-proxy" else 16
        with ThreadPoolExecutor(max_workers=workers) as ex:
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
        status = "LIVE" if lots and detail_failures == 0 and rejected == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Commercial inventory {total_results if total_results is not None else 'unknown'} source results across {pages_seen} page(s) via {mode}; {len(candidates)} auction-commercial cards; {len(lots)} published; {detail_failures} awaiting detail enrichment; {rejected} detail rejections",
            expected_count=len(candidates),
            discovered_count=len(candidates),
            authoritative_snapshot=(status == "LIVE"),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
