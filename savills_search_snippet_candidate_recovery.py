from __future__ import annotations

import html as htmlmod
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote

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

SEARCH_ENDPOINTS = [
    ('brave', 'https://search.brave.com/search?q={q}'),
    ('duckduckgo-lite', 'https://lite.duckduckgo.com/lite/?q={q}'),
]

ADDRESS_HINT = re.compile(
    r'(?P<address>(?:\d+[A-Za-z]?[-–]?\d*\s+)?[A-Z][^|\n]{4,150}?\b(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b)',
    re.I,
)
SAVILLS_URL = re.compile(r'https?://(?:resize\.)?auctions\.savills\.co\.uk/[^\s"<>]+', re.I)
PA_URL = re.compile(r'https?://propertyauctions\.io/listings/[0-9a-f]{20,}', re.I)
ASSET_ID = re.compile(r'/assets/images/lots/(\d+)/(\d+)/', re.I)
LEGACY_SAVILLS_ID = re.compile(r'(?:[?&](?:aid|pid|id)=)(\d+)', re.I)


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


def frontier_dates(limit=12):
    m = load_json(MANIFEST, {})
    dates = []
    for page in m.get('pages') or []:
        if int(page.get('page') or 0) >= 10:
            dates.extend(page.get('dates') or [])
    return sorted({d for d in dates if d < '2019-12-16'})[:limit]


def previous_listing_urls():
    p = load_json(PROGRESS, {})
    s = (p.get('sources') or {}).get(SOURCE) or {}
    r = s.get('public_aggregator_candidate_last_run') or {}
    out = []
    for d, urls in (r.get('discovered_listing_urls_by_date') or {}).items():
        for u in urls or []:
            out.append((d, u))
    return out


def clean_text(s):
    s = htmlmod.unescape(s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def extract_search_evidence(raw, engine, query, target_date):
    soup = BeautifulSoup(raw, 'lxml')
    blocks = []
    # Search engines use different result containers; walk anchors and nearby text.
    for a in soup.find_all('a', href=True):
        href = htmlmod.unescape(a.get('href') or '')
        txt = clean_text(a.get_text(' ', strip=True))
        node = a
        near = txt
        for _ in range(4):
            node = getattr(node, 'parent', None)
            if node is None:
                break
            candidate = clean_text(node.get_text(' ', strip=True))
            if len(candidate) > len(near) and len(candidate) <= 1800:
                near = candidate
        combined = f'{href} {near}'
        if 'propertyauctions.io/listings/' not in combined.lower() and 'auctions.savills.co.uk' not in combined.lower():
            continue
        pa = sorted(set(PA_URL.findall(combined)))
        sv = sorted(set(SAVILLS_URL.findall(combined)))
        addresses = [m.group('address').strip(' -|,') for m in ADDRESS_HINT.finditer(near)]
        assets = []
        for u in sv:
            m = ASSET_ID.search(u)
            if m:
                assets.append({'auction_id': m.group(1), 'lot_id': m.group(2), 'url': u})
        blocks.append({
            'engine': engine,
            'query': query,
            'target_date': target_date,
            'anchor_href': href[:1000],
            'title': txt[:500],
            'snippet': near[:1800],
            'propertyauctions_urls': pa,
            'savills_urls': sv,
            'addresses': addresses[:10],
            'asset_ids': assets[:10],
        })
    return blocks


def search(query, target_date):
    results, errors = [], []
    for name, endpoint in SEARCH_ENDPOINTS:
        url = endpoint.format(q=quote_plus(query))
        try:
            raw = fetch(url, 20)
            blocks = extract_search_evidence(raw, name, query, target_date)
            results.extend(blocks)
            if blocks:
                break
        except Exception as exc:
            errors.append({'engine': name, 'query': query, 'url': url, 'error': f'{type(exc).__name__}: {exc}'})
        time.sleep(0.4)
    return results, errors


def queries_for_date(d, known_listing_urls):
    pretty = datetime.fromisoformat(d).strftime('%d %B %Y').lstrip('0')
    q = [
        f'site:propertyauctions.io/listings Savills "{pretty}" auction',
        f'site:propertyauctions.io/listings Savills "{pretty}" commercial',
        f'site:auctions.savills.co.uk "{pretty}" auction commercial',
        f'site:auctions.savills.co.uk "{pretty}" investment',
        f'site:resize.auctions.savills.co.uk/assets/images/lots "{pretty}" Savills',
    ]
    for _, u in known_listing_urls[:25]:
        q.append(f'"{u}"')
    return q


def search_first_party(address, d):
    if not address:
        return [], []
    pretty = datetime.fromisoformat(d).strftime('%d %B %Y').lstrip('0')
    qs = [
        f'site:auctions.savills.co.uk "{address}"',
        f'site:auctions.savills.co.uk "{address}" "{pretty}"',
        f'site:auctions.savills.co.uk "{address}" Savills auction',
    ]
    urls, diag = set(), []
    for q in qs:
        blocks, errs = search(q, d)
        diag.extend(errs)
        for b in blocks:
            urls.update(b.get('savills_urls') or [])
            href = b.get('anchor_href') or ''
            if 'auctions.savills.co.uk' in href.lower():
                m = SAVILLS_URL.search(unquote(href))
                if m:
                    urls.add(m.group(0))
    return sorted(urls), diag


def validate_first_party(url, d):
    # Never persist image CDN URLs; they are clues only.
    if 'resize.auctions.savills.co.uk' in url.lower() or '/assets/images/' in url.lower():
        return None, 'asset clue only'
    try:
        auction_day = datetime.fromisoformat(d).date()
        auction = {'start': auction_day, 'end': auction_day, 'catalogue': url, 'label': f'Search-index recovery {d}'}
        lot = savills._detail(url, auction, source_commercial=False)
        if not lot:
            return None, 'not classified commercial/mixed-use from Savills page'
        row = lot.finalise().to_dict()
        if row.get('auction_date') != d:
            return None, f'parsed auction date {row.get("auction_date")} != {d}'
        row['url'] = url
        row['evidence_url'] = url
        row['discovery_index_url'] = 'public-search-index-snippet'
        return row, None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def run():
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False

    dates = frontier_dates()
    known = previous_listing_urls()
    known_by_date = {}
    for d, u in known:
        known_by_date.setdefault(d, []).append((d, u))

    all_blocks, errors = [], []
    addresses_by_date = {}
    direct_savills_by_date = {}
    asset_clues = []

    for d in dates:
        for q in queries_for_date(d, known_by_date.get(d, [])):
            blocks, errs = search(q, d)
            all_blocks.extend(blocks)
            errors.extend(errs)
            for b in blocks:
                for addr in b.get('addresses') or []:
                    addresses_by_date.setdefault(d, set()).add(addr)
                for u in b.get('savills_urls') or []:
                    direct_savills_by_date.setdefault(d, set()).add(u)
                asset_clues.extend(b.get('asset_ids') or [])

    # Use snippets themselves as the bridge: address -> first-party indexed Savills URL.
    for d, addresses in list(addresses_by_date.items()):
        for addr in sorted(addresses)[:60]:
            urls, errs = search_first_party(addr, d)
            errors.extend(errs)
            direct_savills_by_date.setdefault(d, set()).update(urls)

    verified, rejected = [], []
    for d, urls in direct_savills_by_date.items():
        for u in sorted(urls):
            row, reason = validate_first_party(u, d)
            if row:
                verified.append(row)
            elif len(rejected) < 200:
                rejected.append({'date': d, 'url': u, 'reason': reason})

    before_db = load_json(HISTORY, {'auction_events': []})
    before = sum(1 for e in before_db.get('auction_events', []) if e.get('source') == SOURCE)
    after, added = before, 0
    if verified:
        db = update_history_database(verified, path=HISTORY)
        after = sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)
        added = max(0, after - before)
        state['lots_captured'] = after
        vd = sorted(r.get('auction_date') for r in verified if r.get('auction_date'))
        if vd:
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min([x for x in [prev, vd[0]] if x])

    serial_addresses = {k: sorted(v) for k, v in addresses_by_date.items()}
    serial_urls = {k: sorted(v) for k, v in direct_savills_by_date.items()}
    diagnostic = {
        'at': now_iso(),
        'route': 'search-index-snippet-address-to-first-party-savills',
        'target_dates': dates,
        'known_public_listing_urls_reused': len(known),
        'search_result_blocks': len(all_blocks),
        'addresses_by_date': serial_addresses,
        'direct_savills_urls_by_date': serial_urls,
        'asset_id_clues': asset_clues[:200],
        'verified_first_party_rows': len(verified),
        'canonical_events_added': added,
        'savills_events_before': before,
        'savills_events_after': after,
        'rejected_samples': rejected,
        'search_errors': errors[:250],
        'block_samples': all_blocks[:100],
    }
    diag_path = DATA / 'source_diagnostics' / f"savills_search_snippet_candidates_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    diag_path.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    state['search_snippet_candidate_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    state['status'] = 'DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if added:
        state.pop('search_snippet_candidate_last_blocker', None)
    else:
        state['search_snippet_candidate_last_blocker'] = {
            'at': diagnostic['at'],
            'message': 'Search-index snippets and known indexed listing URLs did not yield a first-party-validated older Savills event in this run.',
            'addresses_found': sum(len(v) for v in serial_addresses.values()),
            'savills_urls_found': sum(len(v) for v in serial_urls.values()),
            'asset_clues_found': len(asset_clues),
            'next_safe_route': 'Use any recovered address/asset ID clues as direct keys into Common Crawl CDX/WARC and archived Savills/PDF namespaces; if snippets expose no addresses, query Common Crawl for the 19 exact indexed PropertyAuctions listing URLs and parse archived copies without contacting the blocked live pages.',
        }
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    run()
