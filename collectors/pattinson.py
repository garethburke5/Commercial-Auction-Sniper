import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack, nearest_card

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"

COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "offices", "industrial", "warehouse", "workshop",
    "commercial", "public house", "pub", "restaurant", "restaurants", "takeaway",
    "care home", "nursery", "supermarket", "shop", "mixed use", "mixed-use",
    "business premises", "commercial development", "leisure", "land & development",
)


def _auction_card(text):
    t = norm(text).lower()
    return ("starting bid" in t or "current bid" in t) and any(x in t for x in COMMERCIAL_LABELS)


def _detail_url(href):
    u = urljoin(BASE, href or "")
    low = u.lower()
    if "pattinson.co.uk" in low and "/property/" in low and "property-search" not in low:
        return u.split("?")[0]
    return None


def _extract_detail(url, seed):
    try:
        ds = soup(url, use_browser=False)
    except Exception:
        ds = soup(url, use_browser=True)
    h1 = ds.find("h1")
    title = ds.find("title")
    address = norm(h1.get_text(" ", strip=True)) if h1 else (norm(title.get_text(" ", strip=True)).split("|")[0] if title else url)
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
    ptype = next((label for label in ("Retail", "Hotel", "Offices", "Office", "Industrial", "Warehouse", "Workshop", "Leisure", "Restaurants", "Restaurant", "Mixed use", "Commercial Development", "Commercial") if label.lower() in low), None)
    lot_no = None
    m = re.search(r"\bLot\s*#?\s*(\d+[A-Za-z]?)\b", text, re.I)
    if m:
        lot_no = "Lot " + m.group(1)
    return Lot(source=SOURCE, url=url, address=address, lot_number=lot_no, auction_date=None,
        image_url=image_from_soup(ds, url), guide_price=guide, annual_rent=rent,
        tenure=parse_tenure(text + " " + seed), vat_status=parse_vat(text),
        legal_pack_status=lp_status, legal_pack_url=lp_url, description=text[:5000],
        property_type=ptype, occupation=occupation).finalise()


def collect():
    try:
        targets = {}
        pages_seen = 0
        for n in range(1, 26):
            url = SEARCH + ("" if n == 1 else f"&p={n}")
            try:
                s = soup(url, use_browser=False)
                pages_seen += 1
            except Exception as e:
                print("PATTINSON_SEARCH_FAIL", url, repr(e))
                continue
            found_links = 0
            for a in s.find_all("a", href=True):
                href = _detail_url(a.get("href"))
                if not href:
                    continue
                found_links += 1
                card = nearest_card(a, 2600)
                if _auction_card(card):
                    targets.setdefault(href, card)
            if n > 1 and found_links == 0:
                break
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
        return SourceResult(SOURCE, status, lots,
            f"Commercial sale pages {pages_seen}; auction-commercial candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures")
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
