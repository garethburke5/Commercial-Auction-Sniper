"""Traverse the complete public Paul Fosh catalogue before classifying details."""
from __future__ import annotations

import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, enrich_common_fields

SOURCE = "Paul Fosh Auctions"
BASE = "https://auction.paulfosh.com"
UPCOMING = BASE + "/future-auctions"
EVENTS = "https://www.paulfosh.com/auctions/upcoming/"
LOT_PATH = re.compile(r"^/lot/details/[a-z0-9-]+/?$", re.I)
TERMINAL = {"SOLD PRIOR", "WITHDRAWN", "POSTPONED"}


def _fetch(url):
    return soup(url, use_browser=False)


def _date(text):
    matches = re.findall(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text or "", re.I)
    for day, month, year in reversed(matches):
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(f"{day} {month} {year}", fmt).date().isoformat()
            except ValueError:
                pass
    return None


def _closing_date(text):
    text = norm(text)
    m = re.search(r"Bidding\s+(?:closes|ends)\s+(.{8,65})", text, re.I)
    if m:
        found = _date(m.group(1))
        if found:
            return found
    m = re.search(r"ONLINE AUCTION\s+from\s+(.{8,95}?20\d{2})", text, re.I)
    return _date(m.group(1)) if m else None


def _page_url(raw, base):
    p = urlsplit(urljoin(base, raw))
    allowed = p.netloc.lower() == "auction.paulfosh.com" and (
        re.fullmatch(r"/future-auctions(?:/\d+)?/?", p.path, re.I)
        or re.fullmatch(r"/auction/(?:online|catalogue)/\d+/?", p.path, re.I)
    )
    if not allowed:
        return None
    # Keep pagination and closed-lot state, discard view/sort variants only.
    query = [(k,v) for k,v in parse_qsl(p.query) if k.lower() not in {"viewtype","order"} and not k.lower().startswith("utm_")]
    return urlunsplit(("https", p.netloc.lower(), p.path.rstrip("/"), urlencode(sorted(query)), ""))


def _card(a):
    best = a
    for parent in a.parents:
        links = {urlsplit(x.get("href", "")).path.lower() for x in parent.select('a[href]') if LOT_PATH.match(urlsplit(x.get('href','')).path)}
        if len(links) > 1:
            break
        if len(norm(parent.get_text(" ", strip=True))) > 6000:
            break
        best = parent
    return norm(best.get_text(" ", strip=True))


def _discover(fetcher=None):
    fetcher = fetcher or _fetch
    queue = deque([UPCOMING, EVENTS])
    visited = set()
    lots = {}
    scopes = set()
    totals = []
    failures = []
    while queue and len(visited) < 60:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            page = fetcher(url)
        except Exception as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        text = norm(page.get_text(" ", strip=True))
        closing = _closing_date(text)
        if closing:
            scopes.add(closing)
        total = re.search(r"Showing\s+results\s+[\d,]+\s*[-–]\s*[\d,]+\s+of\s+([\d,]+)", text, re.I)
        if total:
            totals.append(int(total.group(1).replace(",", "")))
        for a in page.select('a[href]'):
            target = urljoin(url, a['href'])
            parsed = urlsplit(target)
            if parsed.netloc.lower() == "auction.paulfosh.com" and LOT_PATH.match(parsed.path):
                canonical = urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip('/').lower(), "", ""))
                seed = _card(a)
                previous = lots.get(canonical, {})
                if len(seed) >= len(previous.get("seed", "")):
                    lots[canonical] = {"seed": seed, "auction_date": closing or previous.get("auction_date"), "catalogue_url": url}
            else:
                candidate = _page_url(target, url)
                if candidate and candidate not in visited and candidate not in queue:
                    queue.append(candidate)
    if queue:
        failures.append({"url": queue[0], "error": "Catalogue traversal safety limit reached"})
    expected = max(totals) if totals else None
    return lots, sorted(scopes), expected, failures, sorted(visited)


def _particulars(s):
    sections = []
    for heading in s.select('h3.lot-data-heading'):
        label = norm(heading.get_text(" ", strip=True)).lower()
        if any(x in label for x in ("fees", "additional costs", "viewing", "office contact", "finance")):
            continue
        sections.append(norm(heading.parent.get_text(" ", strip=True)))
    if sections:
        return norm(" ".join(sections))
    # Older EIG templates use a lot-description container instead.
    box = s.select_one('.lot-description, #lot-description, [itemprop="description"]')
    return norm(box.get_text(" ", strip=True)) if box else ""


def _commercial(text):
    """Require property particulars, never 'investment' or the site's navigation."""
    return bool(re.search(
        r"\bmixed[ -]use\b|\bcommercial\s+(?:premises|property|building|unit|accommodation|use)\b|"
        r"\bretail\s+(?:unit|premises|shop|investment|property)\b|\bshop\s+(?:and|with|premises|unit)\b|"
        r"\b(?:office accommodation|office building|office premises|industrial|warehouse|workshop|"
        r"public house|restaurant|takeaway|supermarket|commercial yard|compound/yard)\b", text, re.I))


def _lifecycle(text):
    if re.search(r"\bsold\s*prior\b", text, re.I): return "SOLD PRIOR"
    if re.search(r"\bwithdrawn\b", text, re.I): return "WITHDRAWN"
    if re.search(r"\bpostponed\b", text, re.I): return "POSTPONED"
    if re.search(r"\bauction ended\b", text, re.I): return "AUCTION ENDED"
    return "CURRENT"


def _primary_image(s, url):
    for img in s.select('.swiper-slide img, img[alt^="Image 1 of"]'):
        context = " ".join(str(img.get(k, "")) for k in ('alt','title','src','data-src'))
        if re.search(r'floor[ -]?plan|site[ -]?plan|map|epc|logo', context, re.I):
            continue
        raw = img.get('data-src') or img.get('src')
        if raw and not raw.startswith('data:'):
            return urljoin(url, raw)
    return None


def _detail(url, seed, auction_date=None, fetcher=None):
    s = (fetcher or _fetch)(url)
    heading = s.find('h1')
    if not heading:
        raise ValueError("Lot page has no address heading")
    title = norm(heading.get_text(" ", strip=True))
    particulars = _particulars(s)
    if not particulars:
        raise ValueError("Lot page has no readable particulars")
    # The footer advertises commercial auctions on every residential lot.
    # Scope classification to the actual asset description and facts.
    if not _commercial(particulars):
        return None
    address = re.sub(r'^Lot\s+\d+[A-Z]?\s*[-–:]\s*', '', title, flags=re.I)
    lm = re.search(r'\bLot\s+(\d+[A-Z]?)\b', title, re.I)
    price_heading = next((h for h in s.find_all(['h2','h3','h4']) if re.search(r'Guide\s*Price', h.get_text(), re.I)), None)
    price_text = norm(price_heading.get_text(' ', strip=True)) if price_heading else ''
    lifecycle = _lifecycle(seed)
    # A closed lot may carry an early closing timestamp; its published catalogue
    # date remains the date of the sale in the lot's own auction particulars.
    closing = _closing_date(particulars) or auction_date
    if not closing:
        raise ValueError("Lot page has no identifiable auction date")
    legal = next((a for a in s.select('a[href]') if '/lot/legals/' in a['href']), None)
    text = norm(title + ' ' + price_text + ' ' + particulars)
    mixed = bool(re.search(r'mixed[ -]use|shop (?:and|with) (?:a )?flat|commercial and residential', particulars, re.I))
    lot = Lot(source=SOURCE, url=url, address=address, lot_number='Lot '+lm.group(1).upper() if lm else None,
              auction_date=closing, image_url=_primary_image(s,url), image_is_primary=True, image_source_url=url, guide_price=parse_guide(price_text) or parse_guide(seed),
              annual_rent=parse_rent(particulars), tenure=parse_tenure(particulars), vat_status=parse_vat(particulars),
              legal_pack_url=urljoin(url,legal['href']) if legal else None,
              legal_pack_status='LOGIN REQUIRED' if legal else 'UNKNOWN', status=lifecycle,
              description=text, property_type='Mixed Use' if mixed else None)
    return enrich_common_fields(lot,particulars).finalise()


def collect():
    try:
        targets, scopes, expected, errors, pages = _discover()
        if not targets:
            return SourceResult(SOURCE, 'FAILED' if errors else 'CATALOGUE PENDING', [],
                                f'No lot detail pages found; {len(pages)} catalogue/event pages inspected; {len(errors)} page failures.',
                                scope_dates=tuple(scopes))
        lots = []
        excluded = 0
        detail_failures = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_detail,u,m['seed'],m.get('auction_date')):u for u,m in targets.items()}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    lot = future.result()
                    if lot is None: excluded += 1
                    else: lots.append(lot)
                except Exception as exc:
                    detail_failures.append({'url':url,'error':f'{type(exc).__name__}: {exc}'})
        complete = not errors and not detail_failures and (expected is None or len(targets) >= expected)
        reconciliation = {
            'catalogue_expected_lots':expected, 'detail_pages_discovered':len(targets),
            'detail_pages_inspected':len(targets)-len(detail_failures), 'commercial_mixed_lots':len(lots),
            'noncommercial_excluded':excluded, 'catalogue_pages':pages,
            'detail_failures':detail_failures, 'discovery_failures':errors, 'complete':complete,
            'lot_urls':sorted(targets), 'retained_statuses':dict(Counter(x.status for x in lots)),
        }
        return SourceResult(SOURCE,'LIVE' if complete else 'DEGRADED',lots,
            f'Paul Fosh: {len(targets)}/{expected if expected is not None else "unknown"} public lots discovered; '
            f'{len(targets)-len(detail_failures)} details inspected; {len(lots)} commercial/mixed-use retained; '
            f'{excluded} noncommercial excluded; {len(detail_failures)} detail and {len(errors)} discovery failures.',
            expected_count=len(lots) if complete else None, discovered_count=len(targets),
            authoritative_snapshot=complete, scope_dates=tuple(sorted(set(scopes)|{x.auction_date for x in lots})),
            reconciliation=reconciliation)
    except Exception as exc:
        return SourceResult(SOURCE,'FAILED',[],f'Paul Fosh inventory traversal failed: {type(exc).__name__}: {exc}')
