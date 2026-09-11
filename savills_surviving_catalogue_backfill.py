from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import historical_savills as hs
from history_database import update_history_database
from savills_history_quality import correct_rows, repair_database

DATA = Path('data')
HISTORY = DATA / 'property_history.json'
SOURCE = 'Savills Auctions'
# Bump when the shared Savills parser changes in a way that should force these
# known surviving catalogues back through production.
PARSER_REVISION = 2

# Surviving first-party catalogue routes independently verified on auctions.savills.co.uk.
# These bypass the obsolete /Auctions/LotList?aid= route and materially close the
# known 2014-2022 lot-level gap using canonical Savills evidence pages.
# Keep these oldest-first so each run attacks the historical boundary before newer gaps.
SEEDS = [
    {
        'auction_id': '3',
        'catalogue': 'https://auctions.savills.co.uk/auctions/december-2019-3',
        'start': date(2019, 12, 16),
        'end': date(2019, 12, 16),
        'label': 'December 2019: Monday 16 December 2019',
    },
    {
        'auction_id': '5',
        'catalogue': 'https://auctions.savills.co.uk/auctions/february-2020-5',
        'start': date(2020, 2, 12),
        'end': date(2020, 2, 12),
        'label': 'February 2020: Wednesday 12 February 2020',
    },
    {
        'auction_id': '6',
        'catalogue': 'https://auctions.savills.co.uk/auctions/march-2020-6',
        'start': date(2020, 3, 26),
        'end': date(2020, 3, 26),
        'label': 'March 2020: Thursday 26 March 2020',
    },
    {
        'auction_id': '7',
        'catalogue': 'https://auctions.savills.co.uk/auctions/may-2020-7',
        'start': date(2020, 5, 12),
        'end': date(2020, 5, 12),
        'label': 'May 2020: Tuesday 12 May 2020',
    },
    {
        'auction_id': '9',
        'catalogue': 'https://auctions.savills.co.uk/auctions/july-2020-9',
        'start': date(2020, 7, 29),
        'end': date(2020, 7, 29),
        'label': 'July 2020: Wednesday 29 July 2020',
    },
    {
        'auction_id': '10',
        'catalogue': 'https://auctions.savills.co.uk/auctions/september-2020-10',
        'start': date(2020, 9, 24),
        'end': date(2020, 9, 24),
        'label': 'September 2020: Thursday 24 September 2020',
    },
    {
        'auction_id': '11',
        'catalogue': 'https://auctions.savills.co.uk/auctions/november-2020-11',
        'start': date(2020, 11, 3),
        'end': date(2020, 11, 3),
        'label': 'November 2020: Tuesday 3 November 2020',
    },
    {
        'auction_id': '12',
        'catalogue': 'https://auctions.savills.co.uk/auctions/december-2020-12',
        'start': date(2020, 12, 16),
        'end': date(2020, 12, 16),
        'label': 'December 2020: Wednesday 16 December 2020',
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_count(db: dict) -> int:
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def main() -> None:
    progress = hs.load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False

    repaired = repair_database(HISTORY)
    state['legacy_address_repair_last_run_at'] = now_iso()
    state['legacy_addresses_repaired_last_run'] = repaired
    state['surviving_catalogue_parser_revision'] = PARSER_REVISION

    completed = {str(x) for x in (state.get('completed_auction_ids') or [])}
    attempts = []
    total_added = 0
    total_row_addresses_corrected = 0

    for seed in SEEDS:
        aid = seed['auction_id']
        if aid in completed:
            attempts.append({'auction_id': aid, 'catalogue_url': seed['catalogue'], 'status': 'already-complete'})
            continue
        auction = dict(seed)
        auction['month'] = seed['start'].strftime('%Y-%m')
        auction['source_index_url'] = seed['catalogue']
        attempt = {
            'auction_id': aid,
            'auction_date': seed['start'].isoformat(),
            'catalogue_url': seed['catalogue'],
            'status': 'started',
        }
        try:
            rows, expected, feed = hs.fetch_auction(auction)
            rows, corrected = correct_rows(rows)
            total_row_addresses_corrected += corrected
            bad = [r for r in rows if not str(r.get('address') or '').strip() or 'login to see times and book a viewing' in str(r.get('address') or '').lower()]
            if bad:
                raise RuntimeError(f'{len(bad)} Savills rows still have invalid legacy addresses after first-party title recovery')
            before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
            before_n = source_count(before)
            db = update_history_database(rows, path=HISTORY)
            after_n = source_count(db)
            added = max(0, after_n - before_n)
            total_added += added
            completed.add(aid)
            attempt.update({
                'status': 'persisted',
                'rows_normalised': len(rows),
                'row_addresses_corrected': corrected,
                'canonical_events_added': added,
                'expected': expected,
                'feed': feed,
            })
            state['lots_captured'] = after_n
            state['last_history_event_count'] = len(db.get('auction_events') or [])
            month = seed['start'].strftime('%Y-%m')
            prev_month = state.get('earliest_month_reached')
            state['earliest_month_reached'] = min(prev_month, month) if prev_month else month
            prev_date = state.get('earliest_date_reached')
            iso = seed['start'].isoformat()
            state['earliest_date_reached'] = min(prev_date, iso) if prev_date else iso
        except Exception as exc:
            attempt.update({'status': 'blocked', 'error': f'{type(exc).__name__}: {exc}'})
        attempts.append(attempt)

    state['completed_auction_ids'] = sorted(completed, key=lambda x: int(x) if x.isdigit() else x)
    state['auctions_completed'] = len(completed)
    state['auctions_discovered'] = max(int(state.get('auctions_discovered') or 0), len(completed))
    state['surviving_catalogue_last_run_at'] = now_iso()
    state['surviving_catalogue_last_attempts'] = attempts
    state['surviving_catalogue_last_events_added'] = total_added
    state['surviving_catalogue_row_addresses_corrected'] = total_row_addresses_corrected
    state['last_discovery_mode'] = 'savills-surviving-first-party-catalogue-seeds'
    if total_added:
        state['status'] = 'SURVIVING CATALOGUE INGESTING'
    elif repaired:
        state['status'] = 'DISCOVERY EXPANSION'
    else:
        state['status'] = 'SURVIVING CATALOGUE PROBE BLOCKED'
    hs.save_progress(progress)
    print(json.dumps({
        'events_added': total_added,
        'legacy_addresses_repaired': repaired,
        'row_addresses_corrected': total_row_addresses_corrected,
        'attempts': attempts,
        'state': state,
    }, indent=2, default=str))


if __name__ == '__main__':
    main()
