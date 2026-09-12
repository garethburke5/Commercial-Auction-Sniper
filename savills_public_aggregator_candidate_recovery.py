from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from collectors import savills
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
SOURCE = 'Savills Auctions'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

PUBLIC_INDEX = 'https://propertyauctions.io'
SEARCH_ENDPOINTS = [
    ('brave', 'https://search.brave.com/search?q={q}'),
    ('yahoo', 'https://search.yahoo.com/search?p={q}'),
    ('duckduckgo-lite', 'https://lite.duckduckgo.com/lite/?q={q}'),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def fetch(url, timeout=20):
    r = requests.get(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.9'}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def frontier_dates():
    m = load_json(MANIFEST, {})
    dates = []
    for page in m.get('pages') or []:
        if int(page.get('page') or 0) >= 10:
            dates.extend(page.get('dates') or [])
    # Work oldest first, but include the whole unresolved pre-current-canonical frontier.
    return sorted({d for d in dates if d < '2019-12-16'})


def extract_listing_urls(html):
    soup = BeautifulSoup(html, 'lxml')
    out = set()
    for a in soup.find_all('a', href=True):
        href = urljoin(PUBLIC_INDEX, a['href'])
        m = re.search(r'https://propertyauctions\.io/listings/[0-9a-f]{20,}', href, re.I)
        if m:
            out.add(m.group(0).split('?', 1)[0])
    for m in re.finditer(r'https://propertyauctions\.io/listings/[0-9a-f]{20,}', html, re.I):
        out.add(m.group(0))
    return out


def search_public_index(target_date):
    pretty = datetime.fromisoformat(target_date).strftime('%d %B %Y').lstrip('0')
    queries = [
        f'site:propertyauctions.io/listings Savills "{pretty}" Commercial',
        f'site:propertyauctions.io/listings Savills "{pretty}" "Mixed Use"',
        f'site:propertyauctions.io/listings Savills "{pretty}" auction',
    ]
    hits = set()
    diagnostics = []
    for query in queries:
        for name, endpoint in SEARCH_ENDPOINTS:
            url = endpoint.format(q=quote_plus(query))
            try:
                html = fetch(url, 18)
                found = extract_listing_urls(html)
                hits.update(found)
                diagnostics.append({'engine': name, 'query': query, 'url': url, 'hits': len(found), 'ok': True})
                if found:
                    break
            except Exception as exc:
                diagnostics.append({'engine': name, 'query': query, 'url': url, 'hits': 0, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'})
            time.sleep(0.3)
    return sorted(hits), diagnostics


def parse_public_candidate(url, target_dates):
    html = fetch(url, 20)
    soup = BeautifulSoup(html, 'lxml')
    text = ' '.join(soup.stripped_strings)
    if not re.search(r'\bSavills(?: plc)?\b', text, re.I):
        return None
    if not re.search(r'\bCommercial\b|\bMixed Use\b|\bMixed-Use\b', text, re.I):
        return None
    h1 = soup.find('h1')
    address = ' '.join(h1.stripped_strings) if h1 else None
    matched = []
    for d in target_dates:
        pretty1 = datetime.fromisoformat(d).strftime('%d %b %Y').lstrip('0')
        pretty2 = datetime.fromisoformat(d).strftime('%d %B %Y').lstrip('0')
        if pretty1.lower() in text.lower() or pretty2.lower() in text.lower():
            matched.append(d)
    savills_assets = sorted(set(re.findall(r'https?://[^\s"\']*auctions\.savills\.co\.uk[^\s"\']+', html, re.I)))
    return {'url': url, 'address': address, 'matched_dates': matched, 'savills_assets': savills_assets[:20]}


def search_first_party(address, auction_date):
    if not address:
        return [], []
    pretty = datetime.fromisoformat(auction_date).strftime('%d %B %Y').lstrip('0')
    query = f'site:auctions.savills.co.uk "{address}" "{pretty}"'
    hits, diag = set(), []
    for name, endpoint in SEARCH_ENDPOINTS:
        url = endpoint.format(q=quote_plus(query))
        try:
            html = fetch(url, 18)
            soup = BeautifulSoup(html, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'auctions.savills.co.uk' in href.lower():
                    m = re.search(r'https?://[^&\s"<>]*auctions\.savills\.co\.uk[^&\s"<>]*', href, re.I)
                    if m:
                        hits.add(m.group(0))
            diag.append({'engine': name, 'query': query, 'hits': len(hits), 'ok': True})
            if hits:
                break
        except Exception as exc:
            diag.append({'engine': name, 'query': query, 'hits': 0, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'})
    return sorted(hits), diag


def validate_first_party(url, auction_date):
    try:
        auction_day = datetime.fromisoformat(auction_date).date()
        auction = {'start': auction_day, 'end': auction_day, 'catalogue': url, 'label': f'Public-index candidate recovery {auction_date}'}
        lot = savills._detail(url, auction, source_commercial=False)
        if not lot:
            return None, 'not commercial/mixed-use by Savills first-party parser'
        row = lot.finalise().to_dict()
        if row.get('auction_date') != auction_date:
            return None, f'first-party page resolved to auction date {row.get("auction_date")}'
        row['url'] = url
        row['evidence_url'] = url
        row['discovery_index_url'] = PUBLIC_INDEX + '/auctioneers/savills'
        return row, None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def run(max_dates=8, max_candidates=80):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    dates = frontier_dates()[:max_dates]
    discovered = {}
    search_diag = []
    candidate_rows = []
    verified = []
    rejected = []

    for d in dates:
        urls, diag = search_public_index(d)
        search_diag.extend(diag)
        discovered[d] = urls
        for u in urls:
            if len(candidate_rows) >= max_candidates:
                break
            try:
                c = parse_public_candidate(u, dates)
                if c and c.get('matched_dates'):
                    candidate_rows.append(c)
            except Exception as exc:
                rejected.append({'url': u, 'reason': f'candidate fetch: {type(exc).__name__}: {exc}'})

    for c in candidate_rows:
        for d in c.get('matched_dates') or []:
            hits, diag = search_first_party(c.get('address'), d)
            search_diag.extend(diag)
            for url in hits:
                row, reason = validate_first_party(url, d)
                if row:
                    verified.append(row)
                elif len(rejected) < 120:
                    rejected.append({'candidate': c['url'], 'savills_url': url, 'reason': reason})

    before_db = load_json(HISTORY, {'auction_events': []})
    before = sum(1 for e in before_db.get('auction_events', []) if e.get('source') == SOURCE)
    after = before
    added = 0
    if verified:
        db = update_history_database(verified, path=HISTORY)
        after = sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)
        added = max(0, after - before)
        state['lots_captured'] = after
        older = sorted(r.get('auction_date') for r in verified if r.get('auction_date'))
        if older:
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min([x for x in [prev, older[0]] if x])

    diagnostic = {
        'at': now_iso(),
        'route': 'public-propertyauctions-index-to-first-party-savills-validation',
        'public_index': PUBLIC_INDEX + '/auctioneers/savills',
        'public_index_reported_past_lots': 21587,
        'public_index_reported_total_lots': 23563,
        'target_dates': dates,
        'discovered_listing_urls_by_date': discovered,
        'candidate_rows': candidate_rows[:100],
        'verified_first_party_rows': len(verified),
        'canonical_events_added': added,
        'savills_events_before': before,
        'savills_events_after': after,
        'rejected_samples': rejected[:120],
        'search_diagnostics': search_diag[:200],
    }
    diag_path = DATA / 'source_diagnostics' / f"savills_public_aggregator_candidates_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    diag_path.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    state['public_aggregator_candidate_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    state['status'] = 'DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    state['public_aggregator_candidate_last_blocker'] = None if added else {
        'at': diagnostic['at'],
        'message': 'Public Savills aggregator/index route produced no first-party-validated older canonical event in this run.',
        'public_index': diagnostic['public_index'],
        'candidate_count': len(candidate_rows),
        'next_safe_route': 'Use discovered public candidate addresses/postcodes to query archived Savills PDFs, cached search documents, and Common Crawl captures address-by-address rather than by dead legacy numeric namespaces.',
    }
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    run()
