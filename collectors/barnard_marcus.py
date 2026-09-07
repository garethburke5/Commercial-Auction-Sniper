import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Barnard Marcus"
BASE = "https://www.barnardmarcusauctions.co.uk"
UPCOMING = BASE + "/auctions/upcoming/"
LOT_RE = re.compile(r"/auctions/(\d{1,2}-[a-z]+-20\d{2})/(\d+)/?", re.I)

# Barnard Marcus residential pages routinely mention nearby shops, bars,
# restaurants and commercial centres in the Location paragraph. Classification
# must therefore be based on the actual sale particulars before Location, not the
# whole page. These are explicit asset/use signals, not neighbourhood prose.
TARGET_SIGNALS = re.compile(
    r"\b(?:mixed[- ]use|commercial\s+(?:property|unit|premises|building|investment|element)|"
    r"ground[- ]floor\s+(?:shop|retail|commercial)|shop(?:\s+unit)?|retail\s+(?:unit|investment|premises)|"
    r"office(?:s|\s+unit|\s+building|\s+investment)?|warehouse|industrial(?:\s+unit|\s+property)?|"
    r"workshop|public house|pub\b|restaurant\s+(?:premises|unit|investment)|takeaway|"
    r"care home|hotel|commercial freehold|freehold commercial|ground rent investment)\b",
    re.I,
)
RESIDENTIAL_ONLY_SUMMARY = re.compile(
    r"\b(?:long leasehold|leasehold|freehold)?\s*(?:one|two|three|four|five|six|\d+)[- ]bed(?:room)?\s+"
    r"(?:flat|maisonette|house|bungalow)|\b(?:second|first|ground|third|fourth) floor flat\b|"
    r"\b(?:detached|semi-detached|terraced) house\b|\bresidential flat\b",
    re.I,
)


def _slug_date(slug):
    try:
        return datetime.strptime(slug, "%d-%B-%Y").date().isoformat()
    except ValueError:
        return None


def _sitemap_urls():
    urls = set()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 AuctionSniper/1.0"})
    queue = [BASE + "/sitemap.xml"]
    seen = set()
    while queue and len(seen) < 20:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            r = session.get(url, timeout=25)
            r.raise_for_status()
        except Exception:
            continue
        xml = BeautifulSoup(r.text, "xml")
        locs = [norm(x.get_text()) for x in xml.find_all("loc")]
        for loc in locs:
            if LOT_RE.search(urlparse(loc).path):
                urls.add(loc)
            elif loc.endswith(".xml") and BASE in loc:
                queue.append(loc)
    return urls


def _upcoming_dates():
    s = soup(UPCOMING, use_browser=False)
    dates = set()
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "")
        m = re.search(r"/auctions/(\d{1,2}-[a-z]+-20\d{2})/?$", urlparse(href).path, re.I)
        if m:
            iso = _slug_date(m.group(1))
            if iso and iso >= date.today().isoformat():
                dates.add(iso)
    text = norm(s.get_text(" ", strip=True))
    for m in re.finditer(r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})", text, re.I):
        try:
            iso = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date().isoformat()
            if iso >= date.today().isoformat():
                dates.add(iso)
        except ValueError:
            pass
    return dates


def _discover():
    future_dates = _upcoming_dates()
    urls = set()
    for url in _sitemap_urls():
        m = LOT_RE.search(urlparse(url).path)
        if not m:
            continue
        iso = _slug_date(m.group(1))
        if iso and iso in future_dates:
            urls.add(url)
    return urls, future_dates


def _sale_summary(text):
    """Return the listing's asset/tenancy summary, excluding neighbourhood prose."""
    value = norm(text)
    # The site consistently introduces locality prose with Location:. Anything
    # after that is unsafe for property-use classification because it mentions
    # shops/restaurants/retail transport nodes for ordinary flats and houses.
    m = re.search(r"\bLocation\s*:\s*", value, re.I)
    if m:
        value = value[:m.start()]
    # Ignore header/menu boilerplate before the substantive order/description.
    return value[-3500:]


def _is_target_particulars(text):
    summary = _sale_summary(text)
    if TARGET_SIGNALS.search(summary):
        return True
    # Never rescue a clearly residential-only summary from later locality words.
    if RESIDENTIAL_ONLY_SUMMARY.search(summary):
        return False
    return False


def _hydrate(url):
    s = soup(url, use_browser=False)
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True))
    if re.search(r"\bwithdrawn\b|sold prior", text, re.I):
        return None
    h1 = s.find("h1")
    address = norm(h1.get_text(" ", strip=True)) if h1 else None
    if not address or len(address) < 8 or not _is_target_particulars(text):
        return None
    m = LOT_RE.search(urlparse(url).path)
    auction_date = _slug_date(m.group(1)) if m else None
    lotm = re.search(r"\b(\d{1,3}[A-Z]?),?\s*Auction:", text, re.I)
    if not lotm:
        title = norm(s.title.get_text(" ", strip=True)) if s.title else ""
        lotm = re.search(r"^\s*(\d{1,3}[A-Z]?),\s*Auction", title, re.I)
    rent = parse_rent(text)
    lp_url, lp_status = legal_pack(s, url)
    summary = _sale_summary(text)
    property_type = None
    for label, pattern in (
        ("Mixed Use", r"mixed[- ]use"),
        ("Retail", r"\bshop\b|\bretail\b"),
        ("Office", r"\boffice(?:s)?\b"),
        ("Industrial", r"\bwarehouse\b|\bindustrial\b|\bworkshop\b"),
        ("Public House", r"\bpublic house\b|\bpub\b"),
        ("Commercial", r"\bcommercial\b"),
    ):
        if re.search(pattern, summary, re.I):
            property_type = label
            break
    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=f"Lot {lotm.group(1)}" if lotm else None,
        auction_date=auction_date,
        image_url=image_from_soup(s, url),
        guide_price=parse_guide(text),
        annual_rent=rent,
        tenure=parse_tenure(text),
        vat_status=parse_vat(text),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        description=text[:6500],
        occupation="Tenanted" if rent else ("Vacant / vacant possession" if re.search(r"full vacant possession|\bvacant\b", summary, re.I) else None),
        property_type=property_type or "Commercial",
        development_potential=True if re.search(r"development potential|redevelopment|subject to consents|stpp", summary, re.I) else None,
        residential_conversion=True if re.search(r"residential conversion|conversion to residential", summary, re.I) else None,
        fri=True if re.search(r"\bFRI\b|full repairing and insuring", text, re.I) else None,
    ).finalise()


def collect():
    try:
        targets, future_dates = _discover()
        if future_dates and not targets:
            return SourceResult(SOURCE, "FAILED", [], f"Barnard Marcus future auction(s) {sorted(future_dates)} are published but sitemap discovery found no lot detail pages.", discovered_count=0, scope_dates=tuple(sorted(future_dates)))
        if not targets:
            return SourceResult(SOURCE, "CATALOGUE PENDING", [], "No published future Barnard Marcus lot pages discovered.", discovered_count=0)
        lots = []
        failures = 0
        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = {ex.submit(_hydrate, url): url for url in targets}
            for future in as_completed(futures):
                try:
                    lot = future.result()
                    if lot:
                        lots.append(lot)
                except Exception:
                    failures += 1
        lots = list({x.url: x for x in lots}.values())
        status = "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Barnard Marcus collector: {len(targets)} future lot pages inspected from the first-party sitemap; {len(lots)} explicit commercial/mixed-use lots published after sale-particular classification; {failures} detail failures.",
            discovered_count=len(targets), authoritative_snapshot=False,
            scope_dates=tuple(sorted(future_dates)),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Barnard Marcus collection failed: {exc}")
