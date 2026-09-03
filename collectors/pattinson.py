import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/auction/property-search"

COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "industrial", "warehouse", "workshop",
    "commercial", "public house", "pub", "restaurant", "takeaway", "care home",
    "nursery", "supermarket", "shop", "mixed use", "mixed-use", "business premises",
    "commercial development"
)

RESIDENTIAL_ONLY = (
    "apartment", "flat", "bungalow", "detached house", "semi-detached house",
    "terraced house", "end of terrace house", "maisonette", "cottage", "mobile home",
    "residential development"
)


def _auction_card(text):
    t = norm(text).lower()
    if "starting bid" not in t and "current bid" not in t:
        return False
    return any(x in t for x in COMMERCIAL_LABELS)


def _detail_url(href):
    u = urljoin(BASE, href or "")
    low = u.lower()
    if "pattinson.co.uk" not in low:
        return None
    if "/property/" in low and "property-search" not in low:
        return u.split("?")[0]
    return None


def _card_text(a):
    own = norm(a.get_text(" ", strip=True))
    if _auction_card(own):
        return own
    node = a
    best = own
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        txt = norm(node.get_text(" ", strip=True))
        if 20 <= len(txt) <= 2400:
            best = txt
            if _auction_card(txt):
                return txt
    return best


def _render_search_pages(page_count=10):
    """Render Pattinson search results in one browser session and wait for cards.

    Pattinson hydrates auction cards after DOMContentLoaded. The generic browser
    helper was returning valid HTML before those cards were consistently present,
    which produced a false zero-candidate result. This source-specific renderer
    waits for auction text and reuses one Chromium session for performance.
    """
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="Mozilla/5.0 (compatible; AuctionSniper/5.0)")
        page = ctx.new_page()
        for n in range(1, page_count + 1):
            url = SEARCH if n == 1 else SEARCH + f"?p={n}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                try:
                    page.get_by_text(re.compile(r"Starting Bid|Current Bid", re.I)).first.wait_for(timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1200)
                out.append((url, BeautifulSoup(page.content(), "lxml")))
            except Exception as e:
                print("PATTINSON_SEARCH_FAIL", url, repr(e))
        ctx.close()
        browser.close()
    return out


def _extract_detail(url, seed):
    try:
        ds = soup(url, use_browser=False)
    except Exception:
        ds = soup(url, use_browser=True)
    h1 = ds.find("h1")
    title = ds.find("title")
    address = norm(h1.get_text(" ", strip=True)) if h1 else (
        norm(title.get_text(" ", strip=True)).split("|")[0] if title else url
    )
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    combined = norm(seed + " " + text[:12000])
    low = combined.lower()

    if not any(x in low for x in COMMERCIAL_LABELS):
        return None

    guide = parse_guide(text) or parse_guide(seed)
    if not guide:
        m = re.search(r"(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", combined, re.I)
        if m:
            guide = float(m.group(1).replace(",", ""))

    rent = parse_rent(text)
    lp_url, lp_status = legal_pack(ds, url)

    occupation = None
    if re.search(r"vacant possession|\bvacant\b", text, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £", text, re.I):
        occupation = "Vacant"
        rent = None
    elif re.search(r"tenanted|tenant|let to|currently let|producing £", text, re.I):
        occupation = "Tenanted"

    ptype = None
    for label in ("Retail", "Hotel", "Office", "Industrial", "Warehouse", "Workshop", "Mixed use", "Commercial Development", "Commercial"):
        if label.lower() in low:
            ptype = label
            break

    lot_no = None
    m = re.search(r"\bLot\s*#?\s*(\d+[A-Za-z]?)\b", text, re.I)
    if m:
        lot_no = "Lot " + m.group(1)

    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=lot_no,
        auction_date=None,
        image_url=image_from_soup(ds, url),
        guide_price=guide,
        annual_rent=rent,
        tenure=parse_tenure(text + " " + seed),
        vat_status=parse_vat(text),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        description=text[:5000],
        property_type=ptype,
        occupation=occupation,
    ).finalise()


def collect():
    try:
        targets = {}
        pages = _render_search_pages(page_count=10)
        for _, s in pages:
            for a in s.find_all("a", href=True):
                href = _detail_url(a.get("href"))
                if not href:
                    continue
                card = _card_text(a)
                if not _auction_card(card):
                    continue
                low = card.lower()
                if any(x in low for x in RESIDENTIAL_ONLY) and not any(x in low for x in COMMERCIAL_LABELS):
                    continue
                targets.setdefault(href, card)

        lots = []
        failures = 0
        rejected = 0
        for href, seed in targets.items():
            try:
                lot = _extract_detail(href, seed)
                if lot:
                    lots.append(lot)
                else:
                    rejected += 1
            except Exception as e:
                failures += 1
                print("PATTINSON_DETAIL_FAIL", href, repr(e))

        status = "LIVE" if lots else "FAILED"
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"Auction search pages {len(pages)}; commercial candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures",
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
