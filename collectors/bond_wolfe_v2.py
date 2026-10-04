"""Discover the advertised sale and reconcile every lot in its order of sale."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card, legal_pack
from .bond_wolfe import _rich_detail, _exact_property_image
from .publication_quality import commercial_decision, MIXED

SOURCE = "Bond Wolfe"
BASE = "https://www.bondwolfe.com"
URL = BASE + "/auctions/properties/"
ORDER_URL = BASE + "/order-of-sale/"
PROPERTY_URL = re.compile(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$", re.I)
TERMINAL = {"SOLD PRIOR", "SOLD", "WITHDRAWN", "POSTPONED"}


def _page_category(text):
    low = norm(text).lower()
    if "mixed use" in low or "mixed-use" in low: return "Mixed use"
    if "commercial" in low and "residential investment" in low: return "Mixed use"
    if "commercial investment" in low: return "Commercial investment"
    if "commercial vacant" in low: return "Commercial vacant"
    if "commercial" in low: return "Commercial"
    return None


def _date(text):
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", norm(text), re.I)
    if not m: return None
    try: return datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat()
    except ValueError: return None


def _sale_date(s):
    # Lot-specific auction heading; never a viewing/lease date or footer calendar.
    heading = s.select_one('.AuctionDetails-datetime')
    if heading: return _date(heading.get_text(' ', strip=True))
    for heading in s.select('h2, h3, h4'):
        if re.match(r'^Auction\s*:', heading.get_text(' ', strip=True), re.I):
            return _date(heading.get_text(' ', strip=True))
    return None


def _commercial_order_card(text):
    return _page_category(text) is not None


def _terminal_status(text):
    low = norm(text).lower()
    if 'sold prior' in low: return 'SOLD PRIOR'
    if 'withdrawn' in low or 'not being offered' in low: return 'WITHDRAWN'
    if 'postponed' in low: return 'POSTPONED'
    if re.search(r'\bsold(?:\s+for|\s+at|\s+£|$)', low): return 'SOLD'
    return None


def _listing_targets(s):
    targets = []; seen = set()
    for a in (s.find('main') or s).find_all('a', href=True):
        href = urljoin(BASE, a['href']).split('?', 1)[0].split('#', 1)[0]
        if not PROPERTY_URL.match(href): continue
        href = href.rstrip('/') + '/'
        if href in seen: continue
        seen.add(href)
        card = norm(a.get_text(' ', strip=True))
        if len(card) < 20: card = nearest_card(a, 2200)
        m = re.search(r'\bLot\s+(\d+[A-Z]?)\b', card, re.I)
        targets.append((href, card, f'Lot {m.group(1)}' if m else None, _terminal_status(card)))
    return targets


def _order_targets(s):
    # Compatibility helper; collect() deliberately inspects ALL catalogue lots.
    return [row for row in _listing_targets(s) if _commercial_order_card(row[1])]


def _particulars(s):
    """Isolate exact lot content from forms, navigation and related properties."""
    nodes = [s.select_one('.PropertyHeader-description'), s.select_one('.PropertyHeader-price'),
             s.select_one('.PropertyDetail-description')]
    if any(nodes):
        result = BeautifulSoup('<main></main>', 'lxml')
        for node in nodes:
            if node: result.main.append(BeautifulSoup(str(node), 'lxml'))
    else:
        result = BeautifulSoup(str(s.find('main') or s), 'lxml')
    for node in result.select('script, style, form, nav, footer, .PropertyHeader-navigation'):
        node.decompose()
    # All facts precede the auctioneer's repeated generic disclaimer.
    text = norm(result.get_text(' ', strip=True))
    return result, re.split(r'\bDISCLAIMER\b', text, flags=re.I)[0]


def _base_lot(href, card, lotno, ds, status='CURRENT', auction_date=None):
    h1 = ds.find('h1'); scoped, text = _particulars(ds)
    labels = ds.select_one('.PropertyDetail-attributes-types')
    category = _page_category(labels.get_text(' ', strip=True) if labels else card)
    lp_url, lp_status = legal_pack(ds, href)
    primary = ds.select_one('.Gallery-main .Gallery-slider img')
    primary_url = urljoin(href, primary.get('src') or primary.get('data-src') or '') if primary else None
    lot = Lot(source=SOURCE, url=href, address=norm(h1.get_text(' ', strip=True)) if h1 else href,
        lot_number=lotno, auction_date=auction_date, image_url=primary_url or _exact_property_image(ds, href),
        image_is_primary=bool(primary_url), image_source_url=href,
        guide_price=parse_guide(text), annual_rent=parse_rent(text), tenure=parse_tenure(text),
        vat_status=parse_vat(text), legal_pack_status=lp_status, legal_pack_url=lp_url,
        status=status, description=text[:12000], property_type=category,
        occupation='Vacant' if category == 'Commercial vacant' else None)
    lot = _rich_detail(lot, scoped)
    lot.description = text[:12000]
    lot.status = status
    return lot.finalise()


def _inspect(target, auction_date):
    href, card, lotno, card_terminal = target
    outcome = {'url': href, 'lot': lotno}
    try:
        ds = soup(href, use_browser=False)
        exact_date = _sale_date(ds)
        outcome['parsed'] = bool(ds.find('h1') and exact_date)
        if not outcome['parsed']:
            return None, {**outcome, 'outcome': 'detail_failure', 'reason': 'Missing exact lot title or auction date'}
        if exact_date != auction_date:
            return None, {**outcome, 'outcome': 'other_sale', 'auction_date': exact_date}
        scoped, text = _particulars(ds)
        number = ds.select_one('.PropertyDetail-attributes-lotnum')
        if number: lotno = norm(number.get_text(' ', strip=True))
        # Explicit statuses in the lot header/attributes take precedence. The
        # narrative may discuss a previously sold property and is not a status.
        lifecycle_text = ' '.join(norm(n.get_text(' ', strip=True)) for n in ds.select(
            '.PropertyHeader-price, .PropertyDetail-attributes, .PropertyHeader-status'))
        lifecycle = _terminal_status(lifecycle_text) or card_terminal or 'CURRENT'
        lot = _base_lot(href, card, lotno, ds, lifecycle, auction_date)
        labels = ds.select_one('.PropertyDetail-attributes-types')
        label_text = labels.get_text(' ', strip=True) if labels else card
        explicit_category = _page_category(label_text)
        asset = re.sub(r'\bLocation\s+.*?(?=\b(?:Accommodation|Energy Performance|Tenure|Planning)\b|$)', '', text, flags=re.S)
        decision = commercial_decision({**lot.to_dict(), 'description': asset, 'property_type': explicit_category})
        if not explicit_category and 'residential' in label_text.lower() and not MIXED.search(asset):
            # A flat above a shop does not include that shop; shared retirement
            # amenities do not make an individual flat a commercial investment.
            decision = False
        if decision is False or (not explicit_category and decision is not True):
            return None, {**outcome, 'outcome': 'classification_rejected', 'reason': 'No current commercial/mixed-use asset evidence'}
        if not lot.property_type: lot.property_type = 'Commercial'
        mixed = 'mixed' in lot.property_type.lower()
        return lot, {**outcome, 'outcome': 'mixed_use' if mixed else 'commercial', 'status': lifecycle}
    except Exception as exc:
        return None, {**outcome, 'parsed': False, 'outcome': 'detail_failure', 'reason': f'{type(exc).__name__}: {exc}'}


def collect():
    try:
        order = soup(ORDER_URL, use_browser=False)
        auction_date = _sale_date(order)
        if not auction_date:
            return SourceResult(SOURCE, 'FAILED', [], 'No authoritative auction date in order of sale; refused to guess from footer/calendar.')
        if auction_date < date.today().isoformat():
            return SourceResult(SOURCE, 'DEGRADED', [], f'Advertised order of sale is past ({auction_date}); no current catalogue established.',
                reconciliation={'current_catalogue_detected': False, 'catalogue_url': ORDER_URL})
        targets = _listing_targets(order)
        if not targets:
            return SourceResult(SOURCE, 'CATALOGUE PENDING', [], f'Sale {auction_date} announced; order of sale contains no lot links.',
                scope_dates=(auction_date,), reconciliation={'current_catalogue_detected': False, 'source_lot_count': 0, 'lots_discovered': 0,
                    'lots_parsed': 0, 'commercial_mixed_candidates': 0, 'commercial_candidates': 0, 'mixed_use_candidates': 0})
        # Low bounded concurrency; every lot is inspected, including residential
        # teasers and terminal cards which sometimes lose their type label.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda target: _inspect(target, auction_date), targets))
        lots = [lot for lot, _ in results if lot]
        outcomes = [outcome for _, outcome in results]
        counts = {name: sum(o['outcome'] == name for o in outcomes) for name in
                  ('detail_failure', 'other_sale', 'classification_rejected', 'commercial', 'mixed_use')}
        complete = not counts['detail_failure'] and not counts['other_sale']
        status = 'LIVE' if complete else ('DEGRADED' if lots else 'FAILED')
        return SourceResult(SOURCE, status, lots,
            f'{auction_date} complete order-of-sale traversal: {len(targets)} discovered; '
            f'{sum(o["parsed"] for o in outcomes)} parsed; {len(lots)} commercial/mixed-use; '
            f'{counts["classification_rejected"]} classification exclusions; '
            f'{counts["detail_failure"]} detail failures; {counts["other_sale"]} other-sale pages.',
            expected_count=len(lots) if complete else None, discovered_count=len(targets),
            authoritative_snapshot=complete, scope_dates=(auction_date,), reconciliation={
                'current_catalogue_detected': True, 'catalogue_url': ORDER_URL, 'auction_date': auction_date,
                'source_lot_count': len(targets), 'lots_discovered': len(targets),
                'lots_parsed': sum(o['parsed'] for o in outcomes), 'commercial_candidates': counts['commercial'],
                'mixed_use_candidates': counts['mixed_use'], 'commercial_mixed_candidates': len(lots),
                'classification_rejections': counts['classification_rejected'], 'detail_failures': counts['detail_failure'],
                'other_sale_rejections': counts['other_sale'], 'lot_outcomes': outcomes})
    except Exception as exc:
        return SourceResult(SOURCE, 'FAILED', [], f'{type(exc).__name__}: {exc}')
