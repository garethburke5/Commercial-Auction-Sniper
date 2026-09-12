from __future__ import annotations

"""Recover exact Savills auction frontier from archived Savills newsroom article bodies.

Runs only after the surviving Savills newsroom sitemap route is exhausted. It queries
free Common Crawl indexes for historical Savills-owned newsroom URLs, opens bounded
first-party WARC bodies, and persists only explicit commercial/mixed-use lot facts tied
to the exact unresolved auction date. This is intentionally separate from archived
auction catalogue/LotList/LotDetails recovery.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, _commoncrawl_collections, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, save_progress, warc_html
from savills_manifest_commoncrawl_frontier_recovery import STATIC_COLLECTIONS, oldest_unresolved_date
from savills_newsroom_frontier_recovery import exact_auction_tie, rows_from_article

DATA = Path('data')
DIAGS = DATA / 'source_diagnostics'
CC_INDEX = 'https://index.commoncrawl.org/'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
PREFIXES = [
    'www.savills.com/insight-and-opinion/savills-news/',
    'savills.com/insight-and-opinion/savills-news/',
    'www.savills.co.uk/insight-and-opinion/savills-news/',
    'savills.co.uk/insight-and-opinion/savills-news/',
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def request_text(url: str, timeout: int = 35) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def collections(year: int, errors: list[str]):
    out = []
    for y in (year, year - 1, year + 1):
        try:
            out.extend(_commoncrawl_collections(y) or [])
        except Exception as exc:
            errors.append(f'collinfo {y} :: {type(exc).__name__}: {exc}')
        for ident in STATIC_COLLECTIONS.get(y, []):
            item = (ident, f'{CC_INDEX}{ident}-index')
            if item not in out:
                out.append(item)
    return out


def index_rows(api: str, prefix: str, timeout: int = 35):
    q = api + '?' + urlencode({'url': prefix, 'matchType': 'prefix', 'output': 'json', 'filter': 'status:200'})
    rows = []
    for line in request_text(q, timeout).splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        mime = str(row.get('mime') or row.get('mimetype') or '').lower()
        if mime and 'html' not in mime:
            continue
        if row.get('url') and row.get('filename') and row.get('offset') is not None and row.get('length') is not None:
            rows.append(row)
    return rows, q


def first_party(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return host == 'savills.com' or host.endswith('.savills.com') or host == 'savills.co.uk' or host.endswith('.savills.co.uk')


def run() -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    target = oldest_unresolved_date()
    if not target:
        return 0
    errors, queries, captures = [], [], []
    seen_keys = set()

    for ident, api in collections(target.year, errors):
        for prefix in PREFIXES:
            try:
                rows, query = index_rows(api, prefix)
                queries.append(query)
                for row in rows:
                    key = (row.get('url'), row.get('timestamp'))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        captures.append(row)
            except Exception as exc:
                if len(errors) < 80:
                    errors.append(f'{ident} {prefix} :: {type(exc).__name__}: {exc}')

    # Newest captures first within the target era, bounded to keep hourly runs finite.
    captures.sort(key=lambda r: str(r.get('timestamp') or ''), reverse=True)
    checked = 0
    matched = []
    recovered = []
    for row in captures[:320]:
        original = str(row.get('url') or '')
        if not first_party(original):
            continue
        try:
            html = warc_html(row)
            text = ' '.join(BeautifulSoup(html, 'lxml').stripped_strings)
        except Exception as exc:
            if len(errors) < 80:
                errors.append(f'{original} :: {type(exc).__name__}: {exc}')
            continue
        checked += 1
        if not exact_auction_tie(text, target):
            continue
        matched.append({'url': original, 'timestamp': row.get('timestamp')})
        for item in rows_from_article(original, text, target):
            item['discovery_index_url'] = next((q for q in queries if q), original)
            item['archived_capture_timestamp'] = row.get('timestamp')
            recovered.append(item)

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    added = 0
    after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            t = target.isoformat()
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or t, t)
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or t[:7], t[:7])
            state['status'] = 'ARCHIVED NEWSROOM INGESTED'

    diag = {
        'at': now_iso(), 'route': 'commoncrawl-first-party-savills-newsroom-warc',
        'frontier_date': target.isoformat(), 'index_queries': queries,
        'capture_rows': len(captures), 'warc_bodies_checked': checked,
        'matched_exact_date_articles': matched, 'commercial_rows_seen': len(recovered),
        'canonical_events_added': added, 'savills_events_before': before_n,
        'savills_events_after': after_n, 'errors': errors[:80],
        'evidence_rule': 'Original archived URL must be Savills-owned and article body must explicitly tie auction/target date to the lot facts.'
    }
    DIAGS.mkdir(parents=True, exist_ok=True)
    path = DIAGS / f'savills_archived_newsroom_frontier_{target.isoformat()}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json'
    path.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    state['archived_newsroom_frontier_last_run'] = diag
    state['archived_newsroom_frontier_last_diagnostic'] = str(path)
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    if not added:
        state['status'] = 'ARCHIVED NEWSROOM BLOCKED'
        state['archived_newsroom_frontier_last_blocker'] = {
            'frontier_date': target.isoformat(), 'route': diag['route'],
            'message': 'Archived Savills-owned newsroom WARC bodies yielded no canonical commercial lot event for the exact frontier date.',
            'next_safe_route': 'Use surviving 2013/2014 Savills newsroom article numeric IDs and archived URL inventories to probe bounded adjacent article-ID ranges, then parse only Savills-owned archived bodies with the exact frontier auction date.'
        }
    save_progress(progress)
    print(json.dumps(diag, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    raise SystemExit(0 if run() >= 0 else 1)
