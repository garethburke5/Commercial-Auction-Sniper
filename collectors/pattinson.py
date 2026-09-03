import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"

COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "pub", "restaurant", "restaurants", "takeaway",
    "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development",
    "land and development", "development land",
)

AUCTION_MARKERS = (
    "being sold via secure sale",
    "auction property",
    "online auction notice",
    "starting bid",
    "current bid",
    "subject to unconditional reservation fee auction terms",
)


def _detail_url(href):
    u = urljoin(BASE, href or "")
    low = u.lower()
    if "pattinson.co.uk" in low and re.search(r"/property/\d+/?$", low):
        return u.split("?")[0].rstrip("/")
    return None


def _commercial(text):
    low = norm(text).lower()
    return any(x in low for x in COMMERCIAL_LABELS)


def _is_auction(text):
    low = norm(text).lower()
    return any(x in low for x in AUCTION_MARKERS)


def _extract_detail(url, seed=""):
    try:
        ds = soup(url, use_browser=False)
    except Exception:
        ds = soup(url, use_browser=True)

    h1 = ds.find("h1")
    title = ds.find("title")
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    title_text = norm(title.get_text(" ", strip=True)) if title else ""
    combined = norm(seed + " " + title_text + " " + text[:16000])

    # Pattinson's commercial results page mixes auction stock with ordinary
    # commercial sale listings. The detail page itself is the authoritative
    # auction test: it explicitly exposes Secure Sale / auction / bid language.
    if not _commercial(combined) or not _is_auction(combined):
        return None

    address = norm(h1.get_text(" ", strip=True)) if h1 else (title_text.split("|")[0] if title_text else url)
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

    ptype = next((label for label in (
        "Retail", "Hotel", "Offices", "Office", "Industrial", "Warehouse", "Workshop",
        "Leisure", "Restaurants", "Restaurant", "Mixed use", "Commercial Development",
        "Land & Development", "Commercial"
    ) if label.lower() in combined.lower()), None)

    lot_no = None
    m = re.search(r"\bLot\s*#?\s*(\d+[A-Za-z]?)\b", text, re.I)
    if m:
        lot_no = "Lot " + m.group(1)

    auction_date = None
    # Rolling timed auctions often expose the close date in card/detail copy.
    m = re.search(r"\((\d{1,2})\s+(Sep|September|Oct|October)\s+(?:20)?(\d{2})?\s*\d{1,2}:\d{2}\)", combined, re.I)
    if m:
        month = 9 if m.group(2).lower().startswith("sep") else 10
        year = 2000 + int(m.group(3)) if m.group(3) else 2026
        auction_date = f"{year:04d}-{month:02d}-{int(m.group(1)):02d}"

    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=lot_no,
        auction_date=auction_date,
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
        pages_seen = 0
        empty_pages = 0

        # Pattinson currently exposes ~20+ paginated commercial-sale pages.
        # Discovery deliberately accepts every property detail link from the
        # commercial feed and defers auction validation to each exact detail page.
        # This avoids fragile DOM-card assumptions that previously yielded zero.
        for n in range(1, 31):
            url = SEARCH + ("" if n == 1 else f"&p={n}")
            try:
                s = soup(url, use_browser=False)
            except Exception:
                try:
                    s = soup(url, use_browser=True)
                except Exception as e:
                    print("PATTINSON_SEARCH_FAIL", url, repr(e))
                    continue

            pages_seen += 1
            page_links = 0
            for a in s.find_all("a", href=True):
                href = _detail_url(a.get("href"))
                if not href:
                    continue
                page_links += 1
                seed = norm(a.get_text(" ", strip=True))
                targets.setdefault(href, seed)

            if page_links == 0:
                empty_pages += 1
            else:
                empty_pages = 0
            if n > 1 and empty_pages >= 2:
                break

        lots = []
        failures = 0
        rejected_non_auction = 0
        for href, seed in targets.items():
            try:
                lot = _extract_detail(href, seed)
                if lot:
                    lots.append(lot)
                else:
                    rejected_non_auction += 1
            except Exception as e:
                failures += 1
                print("PATTINSON_DETAIL_FAIL", href, repr(e))

        status = "LIVE" if lots else "FAILED"
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"Commercial-sale pages {pages_seen}; {len(targets)} exact property pages discovered; {len(lots)} auction-commercial published; {rejected_non_auction} non-auction/non-commercial rejected; {failures} detail failures",
            discovered_count=len(targets),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
