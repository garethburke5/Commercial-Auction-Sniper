from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
import historical_savills as hs
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
DIAGS = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
ARCHIVE_ROOT = savills.BASE + '/past-auctions/archive'
DATE_RE = re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b', re.I)
MONTHS = {m: i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def archive_url(page: int) -> str:
    return ARCHIVE_ROOT if page == 1 else f'{ARCHIVE_ROOT}/page-{page}'


def page_doc(url: str):
    try:
        return soup(url, use_browser=False), 'http'
    except Exception:
        return soup(url, use_browser=True), 'browser'


def dates_in_doc(doc):
    text = norm(doc.get_text(' ', strip=True))
    out = []
    for day, month, year in DATE_RE.findall(text):
        try:
            d = date(int(year), MONTHS[month.title()], int(day))
        except Exception:
            continue
        if d < date.today() and d not in out:
            out.append(d)
    return sorted(out)


def catalogue_auctions(doc, index_url):
    found = {}
    for a, href in hs._catalogue_anchors(doc):
        aid = hs._auction_id(href)
        card = savills.nearest_card(a, 3000) if hasattr(savills, 'nearest_card') else norm(a.get_text(' ', strip=True))
        start, end = savills._auction_dates(card, href)
        if not start:
            continue
        found[aid] = {
            'auction_id': aid,
            'catalogue': href,
            'start': start,
            'end': end or start,
            'label': card,
            'month': start.strftime('%Y-%m'),
            'source_index_url': index_url,
        }
    return list(found.values())


def diagnostic(page, url, dates, anchor_count, error=None):
    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    payload = {
        'source': SOURCE,
        'recorded_at': now_iso(),
        'stage': 'live-first-party-archive-ingestion',
        'archive_page': page,
        'archive_url': url,
        'dates_seen': [d.isoformat() for d in dates],
        'catalogue_anchor_count': anchor_count,
        'history_v2_events_added': 0,
        'counted_as_complete': False,
        'error': error,
        'blocker': 'Live Savills archive page contains dated auction summaries but exposes no resolvable lot catalogue anchors.' if dates and not anchor_count else None,
        'next_probe': 'Inspect latent first-party href/data attributes and surviving Savills legacy catalogue endpoints for these exact live archive dates before any third-party archival discovery.'
    }
    key = hashlib.sha1(url.encode()).hexdigest()[:8]
    path = DIAGS / f'savills_live_archive_page{page}_{key}_{stamp}.json'
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return str(path)


def main():
    progress = hs.load_progress()
    state = progress['sources'].setdefault(SOURCE, {})
    completed = {str(x) for x in (state.get('completed_auction_ids') or [])}

    pages = []
    linked = []
    unresolved = []
    browser_pages = 0
    scan_errors = []

    # Strict live-first order: inspect the oldest live page first and walk forward.
    for page in range(14, 0, -1):
        url = archive_url(page)
        try:
            doc, mode = page_doc(url)
            browser_pages += int(mode == 'browser')
            dates = dates_in_doc(doc)
            auctions = catalogue_auctions(doc, url)
            linked.extend(auctions)
            pages.append({'page': page, 'url': url, 'dates': [d.isoformat() for d in dates], 'catalogue_anchors': len(auctions), 'mode': mode})
            if dates and not auctions:
                unresolved.append({'page': page, 'url': url, 'dates': [d.isoformat() for d in dates]})
        except Exception as exc:
            scan_errors.append({'page': page, 'url': url, 'error': f'{type(exc).__name__}: {exc}'})

    all_dates = sorted({d for p in pages for d in p['dates']})
    state['live_archive_pages_scanned'] = len(pages)
    state['live_archive_browser_pages'] = browser_pages
    state['live_archive_scan_errors'] = scan_errors
    state['live_archive_oldest_date_seen'] = all_dates[0] if all_dates else None
    state['live_archive_latest_date_seen'] = all_dates[-1] if all_dates else None
    state['live_archive_unresolved'] = unresolved
    state['live_archive_discovery_exhausted'] = len(pages) == 14 and not scan_errors
    state['historically_complete'] = False

    # Ingest oldest linked, not-yet-completed live catalogue(s) first.
    candidates = sorted((a for a in linked if a['auction_id'] not in completed), key=lambda a: a['start'])
    rows_added = 0
    ingested = []
    failures = []
    for auction in candidates[:2]:
        try:
            rows, expected, feed = hs.fetch_auction(auction)
            db = update_history_database(rows, path=HISTORY)
            rows_added += len(rows)
            completed.add(auction['auction_id'])
            ingested.append({'auction_id': auction['auction_id'], 'date': auction['start'].isoformat(), 'catalogue_url': auction['catalogue'], 'rows': len(rows), 'expected': expected, 'feed': feed})
            state['last_history_event_count'] = len(db.get('auction_events') or [])
            state['last_success'] = now_iso()
            state['last_discovery_mode'] = 'savills-live-first-party-archive-oldest-first'
            month = auction['start'].strftime('%Y-%m')
            previous = state.get('earliest_month_reached')
            state['earliest_month_reached'] = min(previous, month) if previous else month
        except Exception as exc:
            failures.append({'auction_id': auction['auction_id'], 'catalogue_url': auction['catalogue'], 'error': f'{type(exc).__name__}: {exc}'})
            break

    state['completed_auction_ids'] = sorted(completed, key=lambda x: int(x) if x.isdigit() else x)
    state['auctions_completed'] = len(completed)
    state['auctions_discovered'] = max(int(state.get('auctions_discovered') or 0), len(completed) + len(candidates))
    state['lots_captured'] = int(state.get('lots_captured') or 0) + rows_added
    state['last_live_archive_rows'] = rows_added
    state['last_live_archive_ingested'] = ingested
    state['last_live_archive_failures'] = failures
    state['last_live_archive_run'] = now_iso()

    diag_path = None
    if rows_added:
        state['status'] = 'LIVE ARCHIVE INGESTING'
    elif failures:
        state['status'] = 'LIVE ARCHIVE DEGRADED'
        f = failures[0]
        diag_path = diagnostic(0, f['catalogue_url'], [], 1, f['error'])
    elif unresolved:
        # Oldest unresolved page is the concrete blocker for this run.
        target = sorted(unresolved, key=lambda x: min(x['dates']) if x['dates'] else '9999')[0]
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['live_archive_blocker_url'] = target['url']
        state['live_archive_blocker_dates'] = target['dates']
        diag_path = diagnostic(target['page'], target['url'], [date.fromisoformat(x) for x in target['dates']], 0)
    else:
        state['status'] = 'DISCOVERY EXPANSION'

    if diag_path:
        state['last_live_archive_diagnostic'] = diag_path
    hs.save_progress(progress)
    print(json.dumps({'rows_added': rows_added, 'ingested': ingested, 'unresolved_pages': len(unresolved), 'scan_errors': scan_errors, 'diagnostic': diag_path, 'state': state}, indent=2, default=str))


if __name__ == '__main__':
    main()
