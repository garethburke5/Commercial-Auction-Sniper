import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/commercial/property-search?searchType=CommercialSale"

COMMERCIAL_LABELS = (
    "commercial development", "retail", "leisure", "hotel", "office", "industrial",
    "warehouse", "workshop", "commercial", "public house", "pub", "restaurant",
    "takeaway", "care home", "nursery", "supermarket", "shop", "land"
)


def _auction_card(text):
    t = norm(text).lower()
    return ("starting bid" in t or "current bid" in t) and any(x in t for x in COMMERCIAL_LABELS)


def _detail_url(href):
    u = urljoin(BASE, href or "")
    low = u.lower()
    if "pattinson.co.uk" not in low:
        return None
    # Pattinson property details live below /property/ or /commercial/ property routes.
    if "/property/" in low or "/commercial/" in low:
        if "property-search" not in low and "branch/" not in low:
            return u
    return None


def _extract_detail(url, seed):
    ds = soup(url, use_browser=False)
    h1 = ds.find("h1")
    title = ds.find("title")
    address = norm(h1.get_text(" ", strip=True)) if h1 else (
        norm(title.get_text(" ", strip=True)).split("|")[0] if title else url
    )
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    low = text.lower()

    if "sold" in low and "sold subject to contract" not in low and "starting bid" not in low and "current bid" not in low:
        return None
    if not any(x in (seed + " " + text[:5000]).lower() for x in COMMERCIAL_LABELS):
        return None

    guide = parse_guide(text) or parse_guide(seed)
    if not guide:
        m = re.search(r"(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text + " " + seed, re.I)
        if m:
            guide = float(m.group(1).replace(",", ""))

    rent = parse_rent(text)
    lp_url, lp_status = legal_pack(ds, url)

    occupation = None
    if re.search(r"vacant possession|\bvacant\b", text, re.I):
        occupation = "Vacant"
        rent = None
    elif re.search(r"tenanted|tenant|let to|currently let|producing £", text, re.I):
        occupation = "Tenanted"

    ptype = None
    for label in ("Commercial Development", "Retail", "Leisure", "Hotel", "Office", "Industrial", "Warehouse", "Workshop", "Land"):
        if label.lower() in (seed + " " + text[:2500]).lower():
            ptype = label
            break

    lot = Lot(
        source=SOURCE,
        url=url,
        address=address,
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
    )
    return lot.finalise()


def collect():
    try:
        targets = {}
        empty_pages = 0
        for page in range(1, 26):
            url = SEARCH + f"&p={page}"
            s = soup(url, use_browser=False)
            page_new = 0
            for a in s.find_all("a", href=True):
                card = norm((a.parent or a).get_text(" ", strip=True))
                if not _auction_card(card):
                    # climb a few levels to capture the whole result card
                    node = a
                    for _ in range(5):
                        node = getattr(node, "parent", None)
                        if node is None:
                            break
                        txt = norm(node.get_text(" ", strip=True))
                        if len(txt) <= 2200 and _auction_card(txt):
                            card = txt
                            break
                if not _auction_card(card):
                    continue
                href = _detail_url(a.get("href"))
                if not href or href in targets:
                    continue
                targets[href] = card
                page_new += 1
            if page_new == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0

        lots = []
        failures = 0
        for href, seed in targets.items():
            try:
                lot = _extract_detail(href, seed)
                if lot:
                    lots.append(lot)
            except Exception as e:
                failures += 1
                print("PATTINSON_DETAIL_FAIL", href, repr(e))

        status = "LIVE" if lots else "FAILED"
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"Commercial sale search auction candidates {len(targets)}; {len(lots)} published; {failures} detail failures",
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
