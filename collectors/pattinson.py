import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Pattinson Auction"
BASE = "https://www.pattinson.co.uk"
SEARCH = BASE + "/auction/property-search"

COMMERCIAL_LABELS = (
    "retail", "hotel", "office", "industrial", "warehouse", "workshop",
    "commercial", "public house", "pub", "restaurant", "takeaway", "care home",
    "nursery", "supermarket", "shop", "mixed use", "mixed-use", "business premises"
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
    if any(x in t for x in COMMERCIAL_LABELS):
        return True
    return False


def _detail_url(href):
    u = urljoin(BASE, href or "")
    low = u.lower()
    if "pattinson.co.uk" not in low:
        return None
    if "/property/" in low and "property-search" not in low:
        return u
    return None


def _card_text(a):
    # Pattinson's entire result is often the anchor itself; if not, climb just
    # enough to capture the listing without swallowing neighbouring cards.
    own = norm(a.get_text(" ", strip=True))
    if _auction_card(own):
        return own
    node = a
    best = own
    for _ in range(5):
        node = getattr(node, "parent", None)
        if node is None:
            break
        txt = norm(node.get_text(" ", strip=True))
        if 20 <= len(txt) <= 1800:
            best = txt
            if _auction_card(txt):
                return txt
    return best


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
    combined = norm(seed + " " + text[:8000])
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
    if re.search(r"vacant possession|\bvacant\b", text, re.I):
        occupation = "Vacant"
        rent = None
    elif re.search(r"tenanted|tenant|let to|currently let|producing £", text, re.I):
        occupation = "Tenanted"

    ptype = None
    for label in ("Retail", "Hotel", "Office", "Industrial", "Warehouse", "Workshop", "Mixed use", "Commercial"):
        if label.lower() in low:
            ptype = label
            break

    return Lot(
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
    ).finalise()


def collect():
    try:
        targets = {}
        pages_scanned = 0
        for page in range(1, 31):
            url = SEARCH if page == 1 else SEARCH + f"?p={page}"
            s = soup(url, use_browser=False)
            pages_scanned += 1
            page_new = 0
            for a in s.find_all("a", href=True):
                href = _detail_url(a.get("href"))
                if not href:
                    continue
                card = _card_text(a)
                if not _auction_card(card):
                    continue
                # Exclude clearly residential cards unless there is an explicit
                # commercial label on the same listing.
                low = card.lower()
                if any(x in low for x in RESIDENTIAL_ONLY) and not any(x in low for x in COMMERCIAL_LABELS):
                    continue
                if href not in targets:
                    targets[href] = card
                    page_new += 1
            # Do not stop after one quiet page: Pattinson mixes residential and
            # commercial stock, so commercial cards can be sparse across pages.
            if page >= 10 and page_new == 0 and len(targets) >= 8:
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
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"Auction search pages {pages_scanned}; commercial candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures",
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
