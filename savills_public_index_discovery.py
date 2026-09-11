from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
SOURCE = 'Savills Auctions'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_progress(p):
    p['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')


def source_count(db):
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def target_dates(year=None):
    m = load_json(MANIFEST, {})
    dates = []
    for page in m.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
            except ValueError:
                continue
            if year is None or d.year == year:
                dates.append(d)
    return sorted(set(dates))


def fetch_text(url, timeout=20):
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.9'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def search_urls(q):
    endpoints = [
        'https://www.google.com/search?num=100&q=' + quote_plus(q),
        'https://www.bing.com/search?count=50&q=' + quote_plus(q),
        'https://html.duckduckgo.com/html/?q=' + quote_plus(q),
    ]
    out, errors = set(), []
    for endpoint in endpoints:
        try:
            text = html.unescape(fetch_text(endpoint))
        except Exception as exc:
            errors.append({'endpoint': endpoint.split('?', 1)[0], 'error': f'{type(exc).__name__}: {exc}'})
            continue
        text = text.replace('\\u0026', '&').replace('\\/', '/')
        for raw in re.findall(r'https?://[^\"\'<>\s]+', text):
            raw = unquote(raw).rstrip(').,;\"\'')
            if 'auctions.savills.co.uk' in raw.lower():
                out.add(raw)
        for raw in re.findall(r'(?:url|q)=([^&\"\']+)', text):
            raw = unquote(raw)
            if raw.startswith('http') and 'auctions.savills.co.uk' in raw.lower():
                out.add(raw)
    return sorted(out), errors


def canonical_candidate(u):
    p = urlparse(u)
    if not p.hostname or not p.hostname.lower().endswith('savills.co.uk'):
        return None
    if 'auctions.savills.co.uk' not in p.hostname.lower():
        return None
    return p._replace(scheme='https', query='', fragment='').geturl().rstrip('/')


def validate(candidate, target):
    try:
        doc = soup(candidate, use_browser=False)
    except Exception:
        try:
            doc = soup(candidate, use_browser=True)
        except Exception as exc:
            return None, f'fetch: {type(exc).__name__}: {exc}'
    text = norm((doc.find('main') or doc).get_text(' ', strip=True))
    start, end = savills._auction_dates(text, candidate)
    seen = end or start
    if seen and seen != target:
        return None, f'date mismatch {seen.isoformat()}'
    auction = {'start': target, 'end': target, 'catalogue': candidate, 'label': f'Public-index recovery {target.isoformat()}'}
    try:
        lot = savills._detail(candidate, auction, source_commercial=False)
    except Exception as exc:
        return None, f'detail: {type(exc).__name__}: {exc}'
    if not lot:
        return None, 'not commercial/mixed-use'
    row = lot.finalise().to_dict()
    row['url'] = candidate
    row['evidence_url'] = candidate
    row['discovery_index_url'] = 'public-search-index'
    return row, None


def run(year=None, max_dates=4, max_candidates=120):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    dates = target_dates(year)
    if not dates:
        state['public_index_last_blocker'] = {'at': now_iso(), 'message': 'No manifest dates available for requested year.', 'year': year}
        save_progress(progress)
        return 0

    before_db = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before_db)
    recovered, evidence, errors, rejected = [], [], [], []
    checked = set()
    for target in dates[:max_dates]:
        terms = [
            f'\"{target.strftime("%d %B %Y")}\" \"Savills Auctions\"',
            f'\"{target.strftime("%-d %B %Y")}\" site:auctions.savills.co.uk/auctions Savills',
            f'\"Savills auction\" \"{target.strftime("%B %Y")}\" lot',
        ]
        candidates = set()
        for term in terms:
            urls, errs = search_urls(term)
            errors.extend(errs)
            candidates.update(filter(None, (canonical_candidate(u) for u in urls)))
        for candidate in sorted(candidates):
            if candidate in checked or len(checked) >= max_candidates:
                continue
            checked.add(candidate)
            row, reason = validate(candidate, target)
            if row:
                recovered.append(row)
                evidence.append({'auction_date': target.isoformat(), 'url': candidate})
            elif len(rejected) < 80:
                rejected.append({'auction_date': target.isoformat(), 'url': candidate, 'reason': reason})
        if len(checked) >= max_candidates:
            break

    added = 0
    after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        ds = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if ds:
            earliest = min(ds)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            em = earliest[:7]
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or em, em)

    diag = {
        'at': now_iso(), 'route': 'public-search-index-to-surviving-savills-first-party', 'year': year,
        'target_dates': [d.isoformat() for d in dates[:max_dates]], 'candidate_urls_checked': len(checked),
        'verified_first_party_commercial_rows': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'evidence': evidence[:80], 'rejected_samples': rejected, 'search_errors': errors[:80],
    }
    state['public_index_last_run'] = diag
    state['last_discovery_mode'] = 'public-index-date-to-live-savills-first-party'
    if added == 0:
        state['public_index_last_blocker'] = {
            'at': diag['at'], 'route': diag['route'],
            'message': 'Public search indexes yielded no new persistable Savills commercial lot for the oldest manifest dates.',
            'next_safe_route': 'Mine indexed historical Savills auction PDFs/catalogue extracts and reputable auction-result pages for exact addresses/lot numbers, then resolve those exact addresses back into the surviving Savills auction namespace before persistence.'
        }
    else:
        state.pop('public_index_last_blocker', None)
    save_progress(progress)
    print(json.dumps(diag, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int)
    ap.add_argument('--max-dates', type=int, default=4)
    ap.add_argument('--max-candidates', type=int, default=120)
    args = ap.parse_args()
    run(args.year, args.max_dates, args.max_candidates)
