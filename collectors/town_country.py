import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Town & Country Property Auctions"
REGIONS = (
    "https://www.townandcountrypropertyauctions.co.uk",
    "https://london.townandcountrypropertyauctions.co.uk",
    "https://homecounties.townandcountrypropertyauctions.co.uk",
    "https://south.townandcountrypropertyauctions.co.uk",
    "https://nwmwoc.townandcountrypropertyauctions.co.uk",
    "https://northeast.townandcountrypropertyauctions.co.uk",
    "https://southwales.townandcountrypropertyauctions.co.uk",
    "https://threeshires.townandcountrypropertyauctions.co.uk",
)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
DATE_RE = re.compile(r"(?:Auction Ends?|End Time)\s*[-:]?\s*(\d{1,2})/(\d{1,2})/(20\d{2})", re.I)
PAST_MARKERS = re.compile(r"auction ended|sold prior|withdrawn|result:\s*sold", re.I)
COMMERCIAL_EXTRA = (
    "commercial floor space", "commercial investment", "commercial property", "commercial premises",
    "mixed use", "mixed-use", "retail shop", "retail premises", "retail unit", "shop with",
    "office building", "occupational lease", "warehouse", "industrial", "business premises",
    "public house", "restaurant", "dental practice", "former bank", "former post office",
)


def _date(text):
    m = DATE_RE.search(text or "")
    if not m: return None
    try: return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
    except ValueError: return None


def _named_date(text):
    m=re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b",text or "",re.I)
    if not m: return None
    try: return datetime.strptime(" ".join(m.groups()),"%d %B %Y").date().isoformat()
    except ValueError: return None


def _canonical(url):
    p = urlparse(url)
    return p._replace(fragment="", query="").geturl().rstrip("/")


def _property_key(url):
    """Town & Country mirrors the same EIG lot across regional subdomains."""
    p=urlparse(_canonical(url))
    return p.path.rstrip("/").lower() or _canonical(url).lower()


def _is_target_text(text):
    low=" "+norm(text).lower()+" "
    if is_commercial(text): return True
    return any(x in low for x in COMMERCIAL_EXTRA)


def _nearest_lot_card(a):
    node=a; best=norm(a.get_text(" ",strip=True))
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None: break
        text=norm(node.get_text(" ",strip=True))
        if len(text)>len(best) and len(text)<=5000: best=text
        if DATE_RE.search(text) and POSTCODE_RE.search(text) and ("guide" in text.lower() or "minimum opening bid" in text.lower()):
            return text
        if len(text)>5000: break
    return best


def _discover_from_page(base, s, today=None):
    """Discover only current/future commercial or mixed-use catalogue cards."""
    today=today or datetime.now(timezone.utc).date().isoformat()
    found = {}
    for a in s.find_all("a", href=True):
        href = urljoin(base, a.get("href") or "")
        if "townandcountrypropertyauctions.co.uk" not in urlparse(href).netloc.lower(): continue
        low = urlparse(href).path.lower()
        if not any(token in low for token in ("/property/", "/lot/", "/lots/", "/auction-property/")): continue
        card=_nearest_lot_card(a)
        if not POSTCODE_RE.search(card): continue
        auction_date=_date(card)
        if auction_date and auction_date < today: continue
        if PAST_MARKERS.search(card): continue
        if not _is_target_text(card): continue
        found[_canonical(href)] = card
    return found


def _future_catalogue_links(base, s):
    today=datetime.now(timezone.utc).date().isoformat(); found=[]
    for a in s.find_all("a",href=True):
        href=urljoin(base,a.get("href") or "").split("?",1)[0]
        if "/future-auctions" not in href.lower(): continue
        node=a; text=norm(a.get_text(" ",strip=True))
        for _ in range(4):
            node=getattr(node,"parent",None)
            if node is None: break
            candidate=norm(node.get_text(" ",strip=True))
            if re.search(r"20\d{2}",candidate): text=candidate; break
        d=_named_date(text)
        if d and d < today: continue
        if href not in found: found.append(href)
    return found


def _discover_region(base):
    found={}; errors=[]
    try:
        diary=soup(base+"/auction",use_browser=False)
        catalogue_urls=_future_catalogue_links(base,diary)
        for url in catalogue_urls:
            try: found.update(_discover_from_page(base,soup(url,use_browser=False)))
            except Exception as exc: errors.append(f"{url}: {type(exc).__name__}")
        # Some EIG regions advertise the auction date/link in the diary but publish
        # the actual lot grid only at the generic future-auctions route. Try that
        # only when the advertised routes yielded no qualifying cards.
        generic=base+"/future-auctions/"
        if not found and generic not in catalogue_urls:
            try: found.update(_discover_from_page(base,soup(generic,use_browser=False)))
            except Exception as exc: errors.append(f"{generic}: {type(exc).__name__}")
        if found: return found
    except Exception as exc:
        errors.append(f"{base}/auction: {type(exc).__name__}")
    repeated = 0
    for page in range(1, 21):
        url = base + "/search" + (f"?page={page}" if page > 1 else "")
        try: s = soup(url, use_browser=False)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            if page == 1 and not found: raise RuntimeError("; ".join(errors)) from exc
            break
        page_found = _discover_from_page(base, s)
        new = set(page_found) - set(found); found.update(page_found)
        if page > 1 and not new:
            repeated += 1
            if repeated >= 2: break
        else: repeated = 0
    return found


def _address(s, text):
    for tag in s.find_all(["h1", "h2", "h3", "h4"]):
        value = norm(tag.get_text(" ", strip=True))
        if POSTCODE_RE.search(value) and 8 <= len(value) <= 260: return value
    m = re.search(r"([A-Za-z0-9][^\n|]{6,220}?\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b)", text or "", re.I)
    return norm(m.group(1)) if m else None


def _detail_status_near_title(s):
    h=s.find("h1")
    if not h: return None
    bits=[norm(h.get_text(" ",strip=True))]
    for node in h.find_all_next(limit=30):
        if getattr(node,"name",None) not in {"h2","h3","p","div","span","strong"}: continue
        text=norm(node.get_text(" ",strip=True))
        if not text: continue
        bits.append(text)
        if len(" ".join(bits))>1800: break
    probe=" ".join(bits)
    if re.search(r"\bsold\s*prior\b",probe,re.I): return "SOLD PRIOR"
    if re.search(r"\bwithdrawn\b",probe,re.I): return "WITHDRAWN"
    return None


def _hydrate(url, summary=""):
    if PAST_MARKERS.search(summary): return None
    auction_date = _date(summary)
    if auction_date and auction_date < datetime.now(timezone.utc).date().isoformat(): return None
    if not _is_target_text(summary): return None
    s = soup(url, use_browser=False)
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True)); combined = norm(summary + " " + text)
    terminal=_detail_status_near_title(s)
    if terminal: return None
    if not auction_date: auction_date=_date(text)
    address = _address(s, summary) or _address(s, text)
    if not address: return None
    rent = parse_rent(combined); lp_url, lp_status = legal_pack(s, url); lotm = re.search(r"\bLot\s*(\d+[A-Z]?)\b", summary, re.I)
    lot=Lot(source=SOURCE,url=_canonical(url),address=address,lot_number=f"Lot {lotm.group(1)}" if lotm else None,
        auction_date=auction_date,image_url=image_from_soup(s, url),guide_price=parse_guide(summary) or parse_guide(combined),annual_rent=rent,
        tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_status=lp_status,legal_pack_url=lp_url,
        description=combined[:6500],occupation="Tenanted" if rent else ("Vacant / vacant possession" if re.search(r"vacant possession|\bvacant\b", summary, re.I) else None),
        development_potential=True if re.search(r"development potential|development opportunity|redevelopment|subject to planning|stpp|conversion", combined, re.I) else None,
        residential_conversion=True if re.search(r"mixed[- ]use|retail.{0,120}(?:flat|residential)|commercial.{0,120}residential",combined,re.I) else None,
        property_type=("Mixed Use" if re.search(r"mixed[- ]use|retail.{0,100}(?:flat|residential)",summary,re.I) else
                       "Office" if re.search(r"office building|office premises",summary,re.I) else
                       "Industrial / Warehouse" if re.search(r"warehouse|industrial",summary,re.I) else
                       "Retail" if re.search(r"retail|shop",summary,re.I) else "Commercial"))
    return lot.finalise()


def collect():
    discovered_by_key={}; failed_regions=[]
    for base in REGIONS:
        try:
            for url,summary in _discover_region(base).items():
                key=_property_key(url)
                old=discovered_by_key.get(key)
                if old is None or len(summary)>len(old[1]): discovered_by_key[key]=(url,summary)
        except Exception as exc:
            failed_regions.append(f"{urlparse(base).netloc}: {type(exc).__name__}")
    discovered=dict(discovered_by_key.values()); lots=[]; failures=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_hydrate, url, summary): url for url, summary in discovered.items()}
        for future in as_completed(futures):
            try:
                lot = future.result()
                if lot: lots.append(lot)
            except Exception as exc:
                failures += 1; print("TOWN_COUNTRY_DETAIL_FAIL",futures[future],repr(exc))
    lots_by_key={}
    for x in lots: lots_by_key[_property_key(x.url)]=x
    lots=list(lots_by_key.values()); dates = tuple(sorted({x.auction_date for x in lots if x.auction_date}))
    if lots:
        status = "LIVE" if not failures and not failed_regions else "DEGRADED"
        msg = f"All-region Town & Country sweep: {len(discovered)} current/future commercial/mixed-use catalogue cards; {len(lots)} published; {failures} detail failures; {len(failed_regions)} regional discovery failures."
        return SourceResult(SOURCE, status, lots, msg, discovered_count=len(discovered), scope_dates=dates)
    if discovered:
        return SourceResult(SOURCE, "FAILED", [], f"Town & Country exposed {len(discovered)} current/future commercial/mixed-use catalogue cards but none hydrated successfully; {len(failed_regions)} regional discovery failures.", discovered_count=len(discovered))
    if failed_regions:
        return SourceResult(SOURCE, "FAILED", [], "Town & Country regional catalogues could not be reliably inspected: " + "; ".join(failed_regions), discovered_count=0)
    return SourceResult(SOURCE, "CATALOGUE PENDING", [], "Town & Country regional catalogues exposed no current/future commercial or mixed-use catalogue cards.", discovered_count=0)
