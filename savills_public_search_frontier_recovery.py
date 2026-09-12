from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs
from urllib.request import Request, urlopen

from collectors import savills
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
DIAGS = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

SEARCH_ENDPOINTS = (
    'https://html.duckduckgo.com/html/?q={q}',
    'https://www.google.com/search?q={q}&num=100&filter=0',
)

LOT_PATTERNS = (
    re.compile(r'https?://auctions\.savills\.co\.uk/Auctions/LotDetails\?[^\s"\'<>]+', re.I),
    re.compile(r'https?://auctions\.savills\.co\.uk/index\.php\?[^\s"\'<>]+', re.I),
    re.compile(r'https?://auctions\.savills\.co\.uk/auctions/[^\s"\'<>]+', re.I),
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_progress(progress):
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')


def get_text(url, timeout=25):
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.9'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def frontier_date(state):
    manifest_path = Path(state.get('live_archive_manifest') or 'data/source_diagnostics/savills_live_archive_manifest.json')
    manifest = load_json(manifest_path, {})
    dates = []
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            if raw:
                dates.append(str(raw))
    return min(dates) if dates else state.get('live_archive_oldest_date_seen')


def search_queries(frontier):
    y, m, d = frontier.split('-')
    month = datetime.strptime(m, '%m').strftime('%B')
    day = str(int(d))
    phrases = [
        f'"{day} {month} {y}" site:auctions.savills.co.uk',
        f'"{day}th {month} {y}" site:auctions.savills.co.uk',
        f'"{month} {y}" "LotDetails" "auctions.savills.co.uk"',
        f'"{month} {y}" "LotList?aid=" Savills Auctions',
        f'"{month} {y}" "view=commission" "auctions.savills.co.uk"',
    ]
    return phrases


def unwrap(raw):
    s = html.unescape(unquote(raw)).replace('&amp;', '&')
    if s.startswith('//'):
        s = 'https:' + s
    # Google redirect links: /url?q=https://...&sa=...
    if s.startswith('/url?'):
        q = parse_qs(urlparse(s).query)
        s = (q.get('q') or q.get('url') or [s])[0]
    # DuckDuckGo uddg redirect.
    q = parse_qs(urlparse(s).query)
    if q.get('uddg'):
        s = q['uddg'][0]
    return s


def candidate_urls(text):
    decoded = html.unescape(text or '').replace('\\u0026', '&').replace('\\/', '/')
    found = set()
    for pat in LOT_PATTERNS:
        for raw in pat.findall(decoded):
            u = unwrap(raw).rstrip('.,);]')
            p = urlparse(u)
            if (p.hostname or '').lower() == 'auctions.savills.co.uk':
                found.add(u)
    # Search result hrefs often contain escaped target URLs rather than raw URL text.
    for href in re.findall(r'href=["\']([^"\']+)["\']', decoded, re.I):
        u = unwrap(href)
        if 'auctions.savills.co.uk' not in u.lower():
            continue
        for pat in LOT_PATTERNS:
            m = pat.search(u)
            if m:
                found.add(unwrap(m.group(0)).rstrip('.,);]'))
    return sorted(found)


def is_lot_specific(url):
    p = urlparse(url)
    low = (p.path or '').lower()
    q = parse_qs(p.query)
    if 'lotdetails' in low and q.get('pid'):
        return True
    if 'index.php' in low and q.get('view') == ['commission'] and q.get('id'):
        return True
    return bool(re.search(r'/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$', p.path or '', re.I))


def validate_candidate(url, frontier):
    if not is_lot_specific(url):
        return None, 'not lot-specific'
    try:
        from collectors.utils import soup
        doc = soup(url, use_browser=False)
        main = doc.find('main') or doc
        text = ' '.join(main.stripped_strings)
        start, end = savills._auction_dates(text, url)
        auction_day = (end or start)
        if not auction_day or auction_day.isoformat() != frontier:
            return None, f'live listing date mismatch: {auction_day.isoformat() if auction_day else "missing"}'
        auction = {'start': auction_day, 'end': auction_day, 'catalogue': url, 'label': f'Savills public-index recovery {frontier}'}
        lot = savills._detail(url, auction, source_commercial=False)
        if not lot:
            return None, 'not commercial/mixed-use'
        row = lot.finalise().to_dict()
        row['url'] = url
        row['evidence_url'] = url
        row['result_page_url'] = url
        row['discovery_index_url'] = 'public-search-index'
        return row, None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def source_count(db):
    return sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)


def run(max_candidates=80):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    frontier = frontier_date(state)
    if not frontier:
        raise RuntimeError('No Savills archive frontier date available')

    query_log, candidates, errors = [], set(), []
    for query in search_queries(frontier):
        for template in SEARCH_ENDPOINTS:
            url = template.format(q=quote_plus(query))
            try:
                text = get_text(url)
                hits = candidate_urls(text)
                candidates.update(hits)
                query_log.append({'query': query, 'endpoint': url.split('?')[0], 'candidate_count': len(hits)})
            except Exception as exc:
                errors.append({'query': query, 'endpoint': url.split('?')[0], 'error': f'{type(exc).__name__}: {exc}'})

    accepted, rejected = [], []
    for candidate in sorted(candidates)[:max_candidates]:
        row, reason = validate_candidate(candidate, frontier)
        if row:
            accepted.append(row)
        else:
            rejected.append({'url': candidate, 'reason': reason})

    before = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before)
    added = 0
    after_n = before_n
    if accepted:
        db = update_history_database(accepted, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        ds = [r.get('auction_date') for r in accepted if r.get('auction_date')]
        if ds:
            earliest = min(ds)
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, earliest) if prev else earliest
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]

    result = {
        'at': now_iso(),
        'route': 'public-search-engine-index-to-live-savills-lot-validation',
        'frontier_date': frontier,
        'queries': query_log,
        'candidate_urls_seen': len(candidates),
        'live_candidates_checked': min(len(candidates), max_candidates),
        'commercial_rows_seen': len(accepted),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'accepted_evidence_urls': [r.get('evidence_url') for r in accepted],
        'rejected_samples': rejected[:80],
        'errors': errors[:40],
    }
    state['public_search_frontier_last_run'] = result
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    if not added:
        state['public_search_frontier_last_blocker'] = {
            'at': result['at'],
            'frontier_date': frontier,
            'route': result['route'],
            'message': 'Public search-engine indexes exposed no validated live Savills commercial lot page for the oldest known archive date.',
            'exact_failure': {'candidate_urls_seen': len(candidates), 'errors': errors[:12]},
            'next_safe_route': 'Query public web indexes for legacy Savills pid/aid URL mentions by adjacent dated-auction labels and known old endpoint signatures, then resolve candidate pid URLs directly against surviving Savills first-party pages.',
        }
    else:
        state.pop('public_search_frontier_last_blocker', None)
    save_progress(progress)

    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    diag = DIAGS / f'savills_public_search_frontier_{frontier}_{stamp}.json'
    diag.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-candidates', type=int, default=80)
    args = ap.parse_args()
    run(args.max_candidates)
