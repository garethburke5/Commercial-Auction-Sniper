import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, legal_pack

SOURCE = "BidX1"
BASE = "https://bidx1.com"
INDEX = BASE + "/en/united-kingdom"
MAX_PAGES = 40

COMMERCIAL_MARKERS = (
    "commercial auction", "mixed use", "mixed-use", "development site", "commercial",
    "retail", "industrial", "office", "warehouse", "leisure / hospitality",
)
RESIDENTIAL_ONLY_MARKERS = (
    "residential auction", "apartment", " flat ", "house", "bungalow", "maisonette",
)
MONTHS = {m.lower(): i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1
)}


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _property_id(url):
    m = re.search(r"/auction/property/(\d+)(?:[/?#]|$)", url or "", re.I)
    return m.group(1) if m else None


def _commercial_card(text):
    low = " " + norm(text).lower() + " "
    if "commercial auction" in low or "mixed use" in low or "mixed-use" in low:
        return True
    has_commercial = any(x in low for x in COMMERCIAL_MARKERS)
    has_residential = any(x in low for x in RESIDENTIAL_ONLY_MARKERS)
    return has_commercial and not has_residential


def _infer_year(month, day, today=None):
    today = today or date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today and (today - candidate).days > 14:
        candidate = date(today.year + 1, month, day)
    return candidate


def _date_from_card(text, today=None):
    text = norm(text)
    m = re.search(r"(?:Bidding|Registration) Opens\s+(\d{1,2})/(\d{1,2})\b", text, re.I)
    if m:
        d = _infer_year(int(m.group(2)), int(m.group(1)), today=today)
        return d.isoformat() if d else None
    m = re.search(r"Auction Date\s+(\d{1,2})\s+([A-Za-z]+)(?:\s+(20\d{2}))?", text, re.I)
    if m:
        month = MONTHS.get(m.group(2).lower())
        if not month:
            return None
        if m.group(3):
            try:
                return date(int(m.group(3)), month, int(m.group(1))).isoformat()
            except ValueError:
                return None
        d = _infer_year(month, int(m.group(1)), today=today)
        return d.isoformat() if d else None
    return None


def _discover(fetcher=_fetch, today=None):
    today = today or date.today()
    targets = {}
    dates = set()
    pages = 0
    complete = True
    previous_ids = None

    for page_num in range(1, MAX_PAGES + 1):
        url = INDEX if page_num == 1 else f"{INDEX}?page={page_num}"
        try:
            s = fetcher(url)
        except Exception:
            complete = False
            break
        pages += 1
        page_ids = set()
        links_seen = 0
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "").split("#", 1)[0]
            pid = _property_id(href)
            if not pid:
                continue
            links_seen += 1
            page_ids.add(pid)
            card = norm(a.get_text(" ", strip=True))
            if len(card) < 40:
                parent = a
                for _ in range(5):
                    parent = getattr(parent, "parent", None)
                    if parent is None:
                        break
                    candidate = norm(parent.get_text(" ", strip=True))
                    if 40 <= len(candidate) <= 1800:
                        card = candidate
                        break
            if not _commercial_card(card):
                continue
            auction_date = _date_from_card(card, today=today)
            if auction_date and auction_date < today.isoformat():
                continue
            canonical = f"{BASE}/en/en-gb/auction/property/{pid}"
            old = targets.get(canonical)
            if old is None or len(card) > len(old[0]):
                targets[canonical] = (card, auction_date)
            if auction_date:
                dates.add(auction_date)

        if not links_seen:
            break
        if previous_ids is not None and page_ids == previous_ids:
            break
        previous_ids = page_ids
    else:
        complete = False

    return targets, tuple(sorted(dates)), pages, complete


def _image_from_detail(s, base):
    """Recover a real BidX1 lot photo from static or hydrated gallery markup."""
    bad = ("support", "agent", "profile", "avatar", "team", "logo", "icon", "ber-", "user", "favourite", "flag", "spinner")
    candidates = []

    def add(raw, bonus=0):
        if not raw:
            return
        u = urljoin(base, str(raw).replace("\\/", "/").replace("\\u002F", "/").strip(' "\''))
        low = u.lower()
        if "images-prd.bidx1.com" not in low:
            return
        if any(x in low for x in bad):
            return
        score = bonus
        if any(x in low for x in ("property", "auction", "gallery", "photo", "image")): score += 6
        if any(x in low for x in ("large", "original", "1200", "1600", "1920")): score += 3
        if any(x in low for x in ("thumb", "thumbnail", "small", "100x", "150x")): score -= 3
        candidates.append((score, u))

    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}, {"property": "twitter:image"}, {"itemprop": "image"}):
        tag = s.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            add(tag.get("content"), 20)
    for link in s.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        if "image" in rel or "preload" in rel:
            add(link.get("href"), 10)
    for img in s.find_all("img"):
        alt = norm(img.get("alt") or "").lower()
        if any(x in alt for x in bad):
            continue
        bonus = 12 if any(x in alt for x in ("property", "lot", "building", "auction")) else 0
        for attr in ("data-src", "data-lazy-src", "data-original", "data-image", "data-url", "src"):
            add(img.get(attr), bonus)
        for attr in ("srcset", "data-srcset"):
            raw = img.get(attr)
            if raw:
                for part in raw.split(","):
                    add(part.strip().split(" ")[0], bonus)

    raw_html = str(s).replace("\\/", "/").replace("\\u002F", "/")
    for m in re.finditer(r'https?://images-prd\.bidx1\.com/[^"\'<>\s\\]+', raw_html, re.I):
        add(m.group(0), 8)
    for m in re.finditer(r'(?i)(?:image|photo|gallery|media)(?:Url|URL|Src|source)?["\']?\s*[:=]\s*["\']([^"\']+)', raw_html):
        add(m.group(1), 8)
    for m in re.finditer(r'url\(\s*["\']?(https?://images-prd\.bidx1\.com/[^"\')\s]+)["\']?\s*\)', raw_html, re.I):
        add(m.group(1), 10)

    if not candidates:
        return None
    best = {}
    for score, u in candidates:
        best[u] = max(score, best.get(u, -999))
    return max(best.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def _area(text):
    sqft = sqm = acres = None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b", text, re.I)
    if m: sqft = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\b", text, re.I)
    if m: sqm = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)\s*acres?\b", text, re.I)
    if m: acres = float(m.group(1))
    return sqft, sqm, acres


def _property_type(text):
    for label in ("Mixed Use", "Development Site", "Retail", "Industrial", "Office", "Warehouse", "Leisure / Hospitality", "Commercial"):
        if re.search(rf"\b{re.escape(label)}\b", text, re.I): return label
    return "Commercial"


def _detail(url, seed, auction_date, fetcher=_fetch):
    s = fetcher(url)
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True))
    h1 = s.find("h1")
    address = norm(h1.get_text(" ", strip=True)) if h1 else None
    if not address or len(address) < 6:
        title = s.find("title")
        address = norm(title.get_text(" ", strip=True)).split("|")[0] if title else url
    detail_date = _date_from_card(text)
    auction_date = detail_date or auction_date
    if auction_date and auction_date < date.today().isoformat(): return None
    guide = parse_guide(text) or parse_guide(seed)
    rent = parse_rent(text)
    image = _image_from_detail(s, url)
    if not image:
        # Static HTML is often only the shell; request the browser-hydrated DOM before
        # declaring the lot photo unavailable.
        try:
            hydrated = soup(url, use_browser=True)
            image = _image_from_detail(hydrated, url)
        except Exception:
            pass
    lp_url, lp_status = legal_pack(s, url)
    if lp_status == "NOT FOUND" and re.search(r"\bView Legal Pack\b|\bLegal Document Download\b", text, re.I): lp_status = "AVAILABLE - LOGIN REQUIRED"
    lot = Lot(source=SOURCE, url=url, address=address, auction_date=auction_date,
        image_url=image, guide_price=guide, annual_rent=rent,
        tenure=parse_tenure(text), vat_status=parse_vat(text), legal_pack_status=lp_status,
        legal_pack_url=lp_url, property_type=_property_type(text), description=text[:9000])
    lot.area_sqft, lot.area_sqm, lot.site_area_acres = _area(text)
    if re.search(r"\bvacant possession\b", text, re.I) and not re.search(r"\blet to\b|\btenanted\b|\bproducing\s+£", text, re.I): lot.occupation = "Vacant"
    elif re.search(r"\blet to\b|\btenanted\b|\bproducing\s+£|\brent(?:al)? income\b", text, re.I): lot.occupation = "Tenanted"
    if re.search(r"development potential|development opportunity|planning permission|subject to (?:the )?necessary consents|subject to planning", text, re.I): lot.development_potential = True
    if re.search(r"asset management|reconfiguration|repositioning|scope to increase", text, re.I): lot.asset_management = True
    if re.search(r"conversion to residential|residential conversion|planning permission for .*residential", text, re.I): lot.residential_conversion = True
    epc = re.search(r"Energy Performance Indicator\s+([A-G])\b|\bEPC(?: Rating)?\s*[:\-]?\s*([A-G])\b", text, re.I)
    if epc: lot.epc = (epc.group(1) or epc.group(2)).upper()
    return lot.finalise()


def collect():
    try:
        targets, scope_dates, pages, complete = _discover()
        lots = []; failures = 0
        for href, (card, auction_date) in targets.items():
            try:
                lot = _detail(href, card, auction_date)
                if lot: lots.append(lot)
            except Exception as exc:
                failures += 1; print("BIDX1_DETAIL_FAIL", href, repr(exc))
        if targets and not lots:
            return SourceResult(SOURCE, "FAILED", [], f"BidX1 exposed {len(targets)} current/future commercial auction candidates across {pages} pages but none could be parsed.", expected_count=len(targets) if complete else None, discovered_count=len(targets), authoritative_snapshot=False, scope_dates=scope_dates)
        if lots:
            status = "LIVE" if complete and failures == 0 and len(lots) == len(targets) else "DEGRADED"
            return SourceResult(SOURCE, status, lots, f"All-current/future BidX1 UK sweep: {pages} list pages; {len(targets)} commercial candidates; {len(lots)} published; {failures} detail failures.", expected_count=len(targets) if complete else None, discovered_count=len(targets), authoritative_snapshot=bool(complete and failures == 0 and scope_dates), scope_dates=scope_dates)
        return SourceResult(SOURCE, "CATALOGUE PENDING", [], f"BidX1 UK inventory inspected across {pages} pages; no current/future commercial or mixed-use auction lots identified.", expected_count=0 if complete else None, discovered_count=0, authoritative_snapshot=False, scope_dates=scope_dates)
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"BidX1 collection failed: {type(exc).__name__}: {exc}")
