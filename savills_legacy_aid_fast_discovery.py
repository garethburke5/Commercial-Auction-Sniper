from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import savills_legacy_aid_discovery as legacy
from history_database import update_history_database

SOURCE = legacy.SOURCE_KEY
PROGRESS_PATH = legacy.PROGRESS_PATH
HISTORY_PATH = legacy.HISTORY_PATH
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)',
    'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
    'Connection': 'close',
}


def source_count(db: dict) -> int:
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def probe(aid: int, timeout: float) -> dict | None:
    url = legacy.catalogue(aid)
    try:
        r = requests.get(url, headers=HEADERS, timeout=(4, timeout), allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code != 200 or len(r.text) < 1000:
        return None
    doc = BeautifulSoup(r.text, 'lxml')
    text = legacy.norm(doc.get_text(' ', strip=True))
    d = legacy.exact_date(text)
    links = legacy.detail_links(doc)
    if not d and not links:
        return None
    return {'aid': aid, 'url': url, 'date': d, 'links': links, 'text': text}


def run(probe_ids: int = 500, max_auctions: int = 12, floor_aid: int = 1, workers: int = 24, timeout: float = 7.0) -> int:
    progress = legacy.load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'

    cursor = int(state.get('legacy_aid_cursor') or legacy.SEED_AID)
    lower = max(floor_aid, cursor - probe_ids + 1)
    ids = list(range(cursor, lower - 1, -1))

    candidates: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(probe, aid, timeout): aid for aid in ids}
        for fut in as_completed(futures):
            try:
                info = fut.result()
            except Exception:
                info = None
            if info:
                candidates.append(info)

    state['legacy_aids_scanned'] = int(state.get('legacy_aids_scanned') or 0) + len(ids)
    state['legacy_aid_cursor'] = lower - 1
    candidates.sort(key=lambda x: x['aid'], reverse=True)

    processed = []
    total_added = 0
    recovered_auctions = 0
    earliest = None

    for info in candidates:
        d = info.get('date')
        entry = {
            'aid': info['aid'],
            'catalogue_url': info['url'],
            'auction_date': d.isoformat() if d else None,
            'lot_links': len(info.get('links') or {}),
        }
        processed.append(entry)
        if not d or d >= date.today() or not info.get('links'):
            continue

        rows, failures = legacy.recover(info)
        entry['commercial_rows_seen'] = len(rows)
        entry['failures'] = failures[:10]
        if failures:
            entry['persisted'] = False
            continue
        if not rows:
            entry['persisted'] = False
            continue

        before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
        before_n = source_count(before)
        db = update_history_database(rows, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        total_added += added
        recovered_auctions += 1
        entry['canonical_events_added'] = added
        entry['persisted'] = True
        state['lots_captured'] = after_n
        state['last_history_event_count'] = len(db.get('auction_events') or [])

        ds = [r.get('auction_date') for r in rows if r.get('auction_date')]
        if ds:
            e = min(ds)
            earliest = min(earliest, e) if earliest else e
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, e) if prev else e
            em = e[:7]
            prevm = state.get('earliest_month_reached')
            state['earliest_month_reached'] = min(prevm, em) if prevm else em
        if recovered_auctions >= max_auctions:
            break

    state['legacy_aid_last_run_at'] = legacy.now_iso()
    state['legacy_aid_last_processed'] = processed[-40:]
    state['legacy_aid_last_events_added'] = total_added
    state['legacy_aid_recovered_auctions'] = int(state.get('legacy_aid_recovered_auctions') or 0) + recovered_auctions
    state['legacy_aid_fast_last_probe'] = {
        'at': legacy.now_iso(),
        'cursor_start': cursor,
        'cursor_end': lower - 1,
        'ids_scanned': len(ids),
        'candidates_found': len(candidates),
        'events_added': total_added,
        'workers': workers,
        'timeout_seconds': timeout,
    }
    state['last_discovery_mode'] = 'savills-first-party-legacy-aid-concurrent'
    if earliest:
        state['legacy_aid_earliest_recovered_date'] = min(state.get('legacy_aid_earliest_recovered_date') or earliest, earliest)
    if state['legacy_aid_cursor'] < floor_aid:
        state['legacy_aid_discovery_exhausted'] = True
    if total_added == 0:
        state['legacy_aid_fast_last_blocker'] = {
            'at': legacy.now_iso(),
            'route': f'live-savills-LotList-aid-{cursor}-down-to-{lower}',
            'message': f'Concurrent first-party scan found {len(candidates)} candidate legacy auction IDs but added no canonical commercial events.',
            'next_safe_route': 'Use the persisted live archive manifest dates with Common Crawl WARC aid/pid captures, then validate any surviving Savills lot page before History V2 persistence.',
        }
    else:
        state.pop('legacy_aid_fast_last_blocker', None)

    legacy.save_progress(progress)
    print(json.dumps({
        'source': SOURCE,
        'cursor_start': cursor,
        'cursor_end': lower - 1,
        'ids_scanned': len(ids),
        'candidate_ids': [x['aid'] for x in candidates],
        'events_added': total_added,
        'recovered_auctions': recovered_auctions,
        'processed': processed,
    }, indent=2, default=str))
    return total_added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe-ids', type=int, default=500)
    ap.add_argument('--max-auctions', type=int, default=12)
    ap.add_argument('--floor-aid', type=int, default=1)
    ap.add_argument('--workers', type=int, default=24)
    ap.add_argument('--timeout', type=float, default=7.0)
    args = ap.parse_args()
    run(args.probe_ids, args.max_auctions, args.floor_aid, args.workers, args.timeout)
