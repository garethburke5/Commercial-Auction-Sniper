from __future__ import annotations

"""Recover the oldest unresolved Savills live-manifest auction via Common Crawl.

This route is deliberately independent of public search-engine address clues. It
queries free Common Crawl indexes for historical Savills legacy lot URL families,
opens bounded WARC captures, requires the exact target auction date in archived
first-party content, reconstructs the original Savills URL, and then delegates to
strict surviving lot-page validation before History V2 persistence.
"""

import argparse
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, _commoncrawl_collections, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    dates_in_text,
    index_rows,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
    warc_html,
)

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'


def verified_dates() -> set[date]:
    if not HISTORY_PATH.exists():
        return set()
    db = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    out = set()
    for event in db.get('auction_events') or []:
        if event.get('source') != SOURCE_KEY or not event.get('auction_date'):
            continue
        try:
            out.add(date.fromisoformat(str(event['auction_date'])[:10]))
        except ValueError:
            pass
    return out


def oldest_unresolved_date() -> date | None:
    if not MANIFEST.exists():
        return None
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    known = set()
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                known.add(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                pass
    unresolved = sorted(d for d in known if d < date.today() and d not in verified_dates())
    return unresolved[0] if unresolved else None


def canonical_live_candidate(original: str) -> str | None:
    try:
        p = urlparse(original)
    except Exception:
        return None
    host = (p.hostname or '').lower()
    if host not in {'auctions.savills.co.uk', 'www.auctions.savills.co.uk'}:
        return None
    return urlunparse(p._replace(scheme='https', netloc='auctions.savills.co.uk', fragment=''))


def run(max_capture_rows: int = 360, max_warc_checks: int = 180, max_live_checks: int = 80) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    frontier = oldest_unresolved_date()
    if not frontier:
        state['manifest_commoncrawl_frontier_last_blocker'] = {
            'at': now_iso(),
            'route': 'commoncrawl-exact-date-legacy-lot-url-reconstruction',
            'message': 'No unresolved Savills live-manifest auction date remained.',
            'next_safe_route': 'Rebuild the live archive manifest and compare it with canonical lot-specific Savills event dates.'
        }
        save_progress(progress)
        return 0

    # Query multiple known historical Savills lot URL families. Search the target
    # year collections first, then adjacent-year collections because crawl capture
    # time can lag the auction date.
    collections = []
    seen_api = set()
    for y in (frontier.year, frontier.year + 1, frontier.year - 1):
        for ident, api in _commoncrawl_collections(y):
            if api not in seen_api:
                seen_api.add(api)
                collections.append((ident, api))

    prefixes = [
        'auctions.savills.co.uk/Auctions/LotDetails',
        'auctions.savills.co.uk/index.php',
        'auctions.savills.co.uk/auctions/',
    ]
    capture_rows = []
    queries = []
    errors = []
    seen_capture = set()
    for ident, api in collections:
        for prefix in prefixes:
            if len(capture_rows) >= max_capture_rows:
                break
            try:
                rows, query = index_rows(api, prefix, 'prefix', timeout=35)
                queries.append({'collection': ident, 'prefix': prefix, 'query': query, 'rows': len(rows)})
            except Exception as exc:
                errors.append(f'{ident} {prefix} :: {type(exc).__name__}: {exc}')
                continue
            for row in rows:
                key = (row.get('url'), row.get('timestamp'), row.get('filename'), row.get('offset'))
                if key in seen_capture:
                    continue
                seen_capture.add(key)
                capture_rows.append(row)
                if len(capture_rows) >= max_capture_rows:
                    break
        if len(capture_rows) >= max_capture_rows:
            break

    # Prefer captures whose crawl timestamp is closest to the auction year.
    def capture_rank(row: dict):
        ts = str(row.get('timestamp') or '')
        year = int(ts[:4]) if len(ts) >= 4 and ts[:4].isdigit() else 9999
        return (abs(year - frontier.year), ts)

    capture_rows.sort(key=capture_rank)
    matching = []
    warc_checked = 0
    for row in capture_rows:
        if warc_checked >= max_warc_checks:
            break
        warc_checked += 1
        try:
            body = warc_html(row, timeout=30)
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f'{row.get("url")} :: {type(exc).__name__}: {exc}')
            continue
        if frontier not in dates_in_text(body):
            continue
        candidate = canonical_live_candidate(str(row.get('url') or ''))
        if candidate:
            matching.append({'candidate': candidate, 'archived_url': row.get('url'), 'timestamp': row.get('timestamp')})

    # Deduplicate original URLs and validate only surviving exact Savills lot pages.
    unique = {}
    for item in matching:
        unique.setdefault(item['candidate'], item)
    recovered, rejected = [], []
    live_checked = 0
    for candidate, item in unique.items():
        if live_checked >= max_live_checks:
            break
        live_checked += 1
        row, reason = recover_candidate(candidate, frontier, str(item.get('archived_url') or candidate))
        if row:
            row['archival_discovery_url'] = item.get('archived_url')
            row['commoncrawl_capture_timestamp'] = item.get('timestamp')
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'url': candidate, 'archived_url': item.get('archived_url'), 'reason': reason})

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        dates = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates:
            earliest = min(dates)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'commoncrawl-exact-date-legacy-lot-url-reconstruction',
        'frontier_date': frontier.isoformat(),
        'collections_considered': [ident for ident, _ in collections],
        'index_queries': queries,
        'capture_rows_seen': len(capture_rows),
        'warc_checked': warc_checked,
        'captures_with_exact_frontier_date': len(matching),
        'candidate_original_urls': len(unique),
        'live_checked': live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'matching_samples': matching[:30],
        'rejected_samples': rejected,
        'errors': errors[:100],
    }
    state['manifest_commoncrawl_frontier_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added:
        state.pop('manifest_commoncrawl_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    else:
        state['manifest_commoncrawl_frontier_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'frontier_date': frontier.isoformat(),
            'message': 'Bounded Common Crawl exact-date reconstruction yielded no new surviving lot-specific first-party Savills commercial event.',
            'capture_rows_seen': len(capture_rows),
            'warc_checked': warc_checked,
            'exact_date_captures': len(matching),
            'candidate_original_urls': len(unique),
            'next_safe_route': 'Use archived Savills PastAuctions/Venue catalogue bodies for the exact frontier date to recover auction aid IDs, then enumerate pid/detail links from those catalogue captures before first-party validation.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-capture-rows', type=int, default=360)
    ap.add_argument('--max-warc-checks', type=int, default=180)
    ap.add_argument('--max-live-checks', type=int, default=80)
    args = ap.parse_args()
    run(args.max_capture_rows, args.max_warc_checks, args.max_live_checks)
