#!/usr/bin/env python3
import html
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROGRESS = Path('data/historical_backfill_progress.json')
DIAG = Path('data/source_diagnostics/savills_year_gap_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}))\b', re.I)
LOT_RE = re.compile(r'\bLot\s*(?:No\.?\s*)?([A-Z]?\d+[A-Z]?)\b', re.I)
PRICE_RE = re.compile(r'(?:£|&pound;)\s?\d[\d,]*(?:\.\d{2})?', re.I)
COMMERCIAL_RE = re.compile(r'\b(?:retail|shop|office|industrial|warehouse|commercial|investment|public house|pub|restaurant|bank|garage|development|mixed[- ]?use|freehold ground rent|supermarket|medical|pharmacy)\b', re.I)
POSTBACK_RE = re.compile(r"__doPostBack\(['\"]([^'\"]+)['\"],['\"]([^'\"]*)['\"]\)", re.I)
ID_RE = re.compile(r'\b(?:PID|PropertyID|PropertyId|LotID|LotId|ListingID|ListingId)\s*[=:]\s*[\"\']?([A-Za-z0-9_-]+)', re.I)
QS_ID_RE = re.compile(r'[?&](?:PID|PropertyID|PropertyId|LotID|LotId|ListingID|ListingId)=([^&#\"\']+)', re.I)


def visible_text(soup):
    return ' '.join(soup.stripped_strings)


def hidden_fields(soup):
    out = {}
    for inp in soup.find_all('input', attrs={'type': 'hidden'}):
        name = inp.get('name')
        if name:
            out[name] = inp.get('value', '')
    return out


def page_postbacks(soup):
    found = []
    for tag in soup.find_all(True):
        for attr in ('href', 'onclick'):
            val = tag.get(attr)
            if not val:
                continue
            for target, arg in POSTBACK_RE.findall(html.unescape(val)):
                # Pagination only. This avoids mutating wishlist/search state while still
                # traversing the entire pager graph exposed by the catalogue.
                if arg.lower().startswith('page$'):
                    item = (target, arg)
                    if item not in found:
                        found.append(item)
    return found


def mine_surface(base_url, text, soup):
    urls = []
    ids = []
    rows = []
    for tag in soup.find_all(True):
        for attr in ('href', 'src', 'action', 'onclick', 'data-url', 'data-href', 'data-id', 'id'):
            val = tag.get(attr)
            if not val:
                continue
            if isinstance(val, list):
                val = ' '.join(val)
            val = html.unescape(str(val))
            for match in QS_ID_RE.findall(val):
                if match not in ids:
                    ids.append(match)
            if attr in ('href', 'src', 'action', 'data-url', 'data-href'):
                absolute = urljoin(base_url, val)
                if any(tok in absolute.lower() for tok in ('lot', 'property', 'auction', 'image', 'result')) and absolute not in urls:
                    urls.append(absolute)
    for match in ID_RE.findall(text):
        if match not in ids:
            ids.append(match)
    for tr in soup.find_all('tr'):
        row_text = ' '.join(tr.stripped_strings)
        if not row_text:
            continue
        lots = LOT_RE.findall(row_text)
        postcodes = POSTCODE_RE.findall(row_text)
        prices = PRICE_RE.findall(row_text)
        commercial = bool(COMMERCIAL_RE.search(row_text))
        if lots or postcodes or commercial:
            rows.append({
                'text': row_text[:1200],
                'lot_numbers': lots[:5],
                'postcodes': postcodes[:5],
                'prices': prices[:8],
                'commercial_signal': commercial,
                'strict_identity_signal': bool(lots and postcodes and commercial and prices),
            })
    return {'urls': urls[:500], 'ids': ids[:500], 'rows': rows[:500]}


def fetch_initial(session, url):
    r = session.get(url, timeout=(8, 30), headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.8'})
    return r


def post_page(session, url, soup, target, arg):
    data = hidden_fields(soup)
    data['__EVENTTARGET'] = target
    data['__EVENTARGUMENT'] = arg
    form = soup.find('form')
    action = form.get('action') if form else ''
    post_url = urljoin(url, action or url)
    return session.post(post_url, data=data, timeout=(8, 30), headers={
        'User-Agent': UA,
        'Accept-Language': 'en-GB,en;q=0.8',
        'Referer': url,
    })


def run_catalogue(cat):
    url = cat['url']
    session = requests.Session()
    result = {
        'aid': cat.get('aid'), 'date': cat.get('date'), 'url': url,
        'initial_status': None, 'initial_error': None,
        'pages_replayed': 0, 'page_errors': [], 'postbacks_seen': [],
        'candidate_urls': [], 'candidate_ids': [], 'strict_identity_rows': [],
        'row_samples': [],
    }
    try:
        r = fetch_initial(session, url)
        result['initial_status'] = r.status_code
        r.raise_for_status()
    except Exception as exc:
        result['initial_error'] = f'{type(exc).__name__}: {exc}'
        return result

    soup = BeautifulSoup(r.text, 'html.parser')
    states = deque()
    seen = set()
    initial_postbacks = page_postbacks(soup)
    for pb in initial_postbacks:
        states.append((soup, pb[0], pb[1]))
    # Mine page 1 as part of the same traversal.
    surfaces = [mine_surface(url, r.text, soup)]

    while states:
        source_soup, target, arg = states.popleft()
        key = (target, arg)
        if key in seen:
            continue
        seen.add(key)
        result['postbacks_seen'].append({'target': target, 'argument': arg})
        try:
            rr = post_page(session, url, source_soup, target, arg)
            rr.raise_for_status()
            result['pages_replayed'] += 1
        except Exception as exc:
            result['page_errors'].append({'target': target, 'argument': arg, 'error': f'{type(exc).__name__}: {exc}'})
            continue
        page_soup = BeautifulSoup(rr.text, 'html.parser')
        surfaces.append(mine_surface(url, rr.text, page_soup))
        for nxt in page_postbacks(page_soup):
            if nxt not in seen:
                states.append((page_soup, nxt[0], nxt[1]))

    for surf in surfaces:
        for u in surf['urls']:
            if u not in result['candidate_urls']:
                result['candidate_urls'].append(u)
        for ident in surf['ids']:
            if ident not in result['candidate_ids']:
                result['candidate_ids'].append(ident)
        for row in surf['rows']:
            if len(result['row_samples']) < 50:
                result['row_samples'].append(row)
            if row['strict_identity_signal'] and row not in result['strict_identity_rows']:
                result['strict_identity_rows'].append(row)
    result['candidate_urls'] = result['candidate_urls'][:500]
    result['candidate_ids'] = result['candidate_ids'][:500]
    result['strict_identity_rows'] = result['strict_identity_rows'][:200]
    return result


def main():
    progress = json.loads(PROGRESS.read_text())
    source = progress['sources']['Savills Auctions']
    base = source.get('savills_year_gap_last_run') or {}
    catalogues = base.get('revalidated_propertyauctions_catalogues') or []
    # Traverse every revalidated catalogue for the target year; no page-number cutoff.
    target_year = int(base.get('target_year') or 2018)
    catalogues = [c for c in catalogues if str(c.get('date', '')).startswith(str(target_year))]
    runs = [run_catalogue(c) for c in catalogues]

    total_pages = sum(r['pages_replayed'] for r in runs)
    total_postbacks = sum(len(r['postbacks_seen']) for r in runs)
    total_ids = sum(len(r['candidate_ids']) for r in runs)
    total_urls = sum(len(r['candidate_urls']) for r in runs)
    strict_rows = sum(len(r['strict_identity_rows']) for r in runs)
    at = datetime.now(timezone.utc).isoformat()
    diag = {
        'at': at,
        'route': 'savills-2018-propertyauctions-live-aspnet-pagination-postback-enumeration',
        'target_year': target_year,
        'catalogues_attempted': len(runs),
        'initial_http_200': sum(1 for r in runs if r['initial_status'] == 200),
        'pagination_postbacks_discovered': total_postbacks,
        'pagination_pages_replayed': total_pages,
        'candidate_identifiers_mined': total_ids,
        'candidate_urls_mined': total_urls,
        'strict_identity_rows_found': strict_rows,
        'canonical_events_added': 0,
        'runs': runs,
    }
    source['savills_year_gap_postback_last_run'] = diag
    source['last_discovery_mode'] = diag['route']
    source['historically_complete'] = False
    source['discovery_exhausted'] = False
    source['status'] = 'YEAR GAP BLOCKED'
    first_url = runs[0]['url'] if runs else 'PropertyAuctions 2018 catalogue manifest'
    source['savills_year_gap_last_blocker'] = {
        'at': at,
        'route': diag['route'],
        'failing_url_or_route': first_url,
        'message': (
            f'Enumerated all pagination postbacks exposed by {len(runs)} revalidated 2018 Savills '
            f'PropertyAuctions catalogues: {total_postbacks} pager states, {total_pages} successful replay pages, '
            f'{total_ids} candidate property/lot identifiers and {total_urls} candidate detail/image URLs mined. '
            f'No canonical event was promoted because this route is identity-discovery only; {strict_rows} rows '
            f'contained lot+postcode+commercial+price signals and require deterministic reconciliation to the '
            f'first-party Savills auction evidence before History V2 insertion.'
        ),
        'next_safe_route': (
            'Resolve the mined PropertyAuctions property/lot identifiers and candidate detail/image URLs, then '
            'join any recovered full addresses deterministically to the matching Savills date+lot+type+result tuple; '
            'validate against surviving first-party Savills evidence before canonical insertion.'
        ),
    }
    progress['updated_at'] = at
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False))
    diagnostic = json.loads(DIAG.read_text()) if DIAG.exists() else {}
    diagnostic['postback_pagination_run'] = diag
    DIAG.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in diag.items() if k != 'runs'}, indent=2))


if __name__ == '__main__':
    main()
