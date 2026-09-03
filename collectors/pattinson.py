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
    "land and development", "development land", "hospitality facility", "land",
)


def _auction_card(text):
    low = norm(text).lower()
    return ("starting bid" in low or "current bid" in low) and any(x in low for x in COMMERCIAL_LABELS)


def _detail_url(a):
    u = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
    low = u.lower()
    if "pattinson.co.uk" not in low or "property-search" in low:
        return None
    # Pattinson has changed detail URL shapes over time; do not require /property/<id>.
    if any(x in low for x in ("/commercial/", "/property/", "/properties/")):
        return u
    return None


def _lot_from_card(card, url=None):
    text = norm(card)
    if not _auction_card(text):
        return None
    m = re.search(r"(?:Starting Bid|Current Bid)\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
    guide = float(m.group(1).replace(",", "")) if m else None
    # Card wording is consistently '<type> in <postcode/address>'. Keep it usable even
    # if Pattinson changes the detail-link route again.
    address = text
    maddr = re.search(r"(?:Commercial Development|Land & Development|Hospitality Facility|Restaurants?|Retail|Hotels?|Offices?|Industrial|Warehouse|Workshop|Leisure|Land|Commercial)\s+in\s+(.+?)(?:\s+(?:Garage|Double Garage|Allocated|On Street|Off Street|Driveway|Private|None)\s+parking|$)", text, re.I)
    if maddr:
        address = norm(maddr.group(1))
    ptype = next((x for x in ("Commercial Development","Land & Development","Hospitality Facility","Restaurant","Retail","Hotel","Offices","Industrial","Warehouse","Workshop","Leisure","Land","Commercial") if x.lower() in text.lower()), "Commercial")
    auction_date = None
    md = re.search(r"\((\d{1,2})\s+(Sep|September|Oct|October)\s+(?:20)?(\d{2})?\s*\d{1,2}:\d{2}\)", text, re.I)
    if md:
        month = 9 if md.group(2).lower().startswith("sep") else 10
        year = 2000 + int(md.group(3)) if md.group(3) else 2026
        auction_date = f"{year:04d}-{month:02d}-{int(md.group(1)):02d}"
    return Lot(source=SOURCE, url=url or SEARCH, address=address, auction_date=auction_date,
               guide_price=guide, property_type=ptype, description=text[:5000]).finalise()


def _enrich(url, seed):
    try:
        ds = soup(url, use_browser=False)
    except Exception:
        ds = soup(url, use_browser=True)
    main = ds.find("main") or ds.find("article") or ds
    text = norm(main.get_text(" ", strip=True))
    lot = _lot_from_card(seed, url)
    if not lot:
        return None
    h1 = ds.find("h1")
    if h1:
        lot.address = norm(h1.get_text(" ", strip=True))
    lot.image_url = image_from_soup(ds, url)
    lot.guide_price = parse_guide(text) or lot.guide_price
    lot.annual_rent = parse_rent(text)
    lot.tenure = parse_tenure(text + " " + seed)
    lot.vat_status = parse_vat(text)
    lp_url, lp_status = legal_pack(ds, url)
    lot.legal_pack_url, lot.legal_pack_status = lp_url, lp_status
    lot.description = text[:5000]
    if re.search(r"vacant possession|\bvacant\b", text, re.I) and not re.search(r"tenant|tenanted|let to|currently let|producing £", text, re.I):
        lot.occupation = "Vacant"; lot.annual_rent = None
    elif re.search(r"tenant|tenanted|let to|currently let|producing £", text, re.I):
        lot.occupation = "Tenanted"
    return lot.finalise()


def collect():
    try:
        candidates = {}
        pages_seen = 0
        for n in range(1, 31):
            url = SEARCH + ("" if n == 1 else f"&p={n}")
            try:
                s = soup(url, use_browser=False)
            except Exception:
                try: s = soup(url, use_browser=True)
                except Exception as exc:
                    print("PATTINSON_SEARCH_FAIL", url, repr(exc)); continue
            pages_seen += 1
            page_hits = 0
            for a in s.find_all("a", href=True):
                card = nearest_card(a, 1800)
                if not _auction_card(card):
                    continue
                page_hits += 1
                href = _detail_url(a)
                key = href or norm(card)[:500]
                candidates.setdefault(key, (href, card))
            # If anchors do not carry usable links, parse auction cards from visible page text.
            if page_hits == 0:
                text = norm(s.get_text(" ", strip=True))
                chunks = re.split(r"(?=(?:Current Bid\s*)?Starting Bid\s*£)", text, flags=re.I)
                for chunk in chunks:
                    chunk = norm(chunk[:1200])
                    if _auction_card(chunk):
                        candidates.setdefault(chunk[:500], (None, chunk))
            if n > 1 and page_hits == 0 and "Starting Bid" not in norm(s.get_text(" ", strip=True)):
                break

        lots=[]; failures=0
        for _, (href, card) in candidates.items():
            try:
                lot = _enrich(href, card) if href else _lot_from_card(card)
                if lot: lots.append(lot)
            except Exception as exc:
                failures += 1; print("PATTINSON_DETAIL_FAIL", href, repr(exc))
        # Deduplicate fallback cards by address/guide/date while preserving richer URL records.
        dedup={}
        for lot in lots:
            key=(norm(lot.address).lower(), lot.guide_price, lot.auction_date)
            if key not in dedup or (lot.url != SEARCH and dedup[key].url == SEARCH): dedup[key]=lot
        lots=list(dedup.values())
        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,
            f"Commercial-sale pages {pages_seen}; {len(candidates)} auction-commercial cards discovered; {len(lots)} published; {failures} enrichment failures",
            discovered_count=len(candidates))
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
