from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import recover_candidate
from savills_manifest_aid_capture_recovery import unresolved_manifest_dates
from savills_propertyauctions_clue_recovery import candidate_urls, parse_listing, search_urls

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAGNOSTICS = Path('data/source_diagnostics/savills_propertyauctions_chronology_recovery.json')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    return json.loads(PROGRESS.read_text(encoding='utf-8'))


def save_progress(progress: dict) -> None:
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')


def queries_for(target) -> list[str]:
    date_text = target.strftime('%d %B %Y')
    loose = target.strftime('%B %Y')
    return [
        f'site:propertyauctions.io/listings "Savills" "{date_text}"',
        f'site:propertyauctions.io/listings "Savills plc" "{date_text}"',
        f'site:propertyauctions.io/listings "Savills" "{loose}" auction',
    ]


def run(max_dates: int = 12, max_search_results: int = 35, max_live_checks: int = 260) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'

    unresolved = sorted(
        [d for d in unresolved_manifest_dates(state) if 2014 <= d.year <= 2019],
        reverse=True,
    )
    targets = unresolved[:max_dates]
    before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(before)

    date_runs = []
    recovered_by_key = {}
    total_live_checked = 0
    learned_ids: dict[str, list[str]] = {}

    for target in targets:
        discovered: list[str] = []
        errors: list[str] = []
        for query in queries_for(target):
            urls, errs = search_urls(query, max_results=max_search_results)
            errors.extend([f'{query} :: {e}' for e in errs])
            for url in urls:
                if url not in discovered:
                    discovered.append(url)
            if len(discovered) >= max_search_results:
                break

        matched = []
        for url in discovered[:max_search_results]:
            item, _reason = parse_listing(url, target)
            if item:
                matched.append(item)
                for clue in item.get('image_clues') or []:
                    aid = str(clue.get('auction_id') or '').strip()
                    if aid:
                        learned_ids.setdefault(target.isoformat(), [])
                        if aid not in learned_ids[target.isoformat()]:
                            learned_ids[target.isoformat()].append(aid)

        candidates: dict[str, str] = {}
        for item in matched:
            for candidate in candidate_urls(item, target):
                candidates.setdefault(candidate, item['discovery_url'])

        accepted = 0
        rejected = []
        for candidate, discovery in candidates.items():
            if total_live_checked >= max_live_checks:
                break
            total_live_checked += 1
            row, reason = recover_candidate(candidate, target, discovery)
            if row:
                row['archival_discovery_url'] = discovery
                key = (
                    str(row.get('auction_date') or ''),
                    str(row.get('lot_number') or ''),
                    str(row.get('source_url') or row.get('url') or ''),
                )
                recovered_by_key[key] = row
                accepted += 1
            elif len(rejected) < 15:
                rejected.append({'url': candidate, 'reason': reason})

        date_runs.append({
            'target_date': target.isoformat(),
            'indexed_listing_urls': len(discovered),
            'matched_target_pages': len(matched),
            'image_clues': sum(len(x.get('image_clues') or []) for x in matched),
            'candidate_first_party_urls': len(candidates),
            'accepted_first_party_rows': accepted,
            'learned_auction_ids': learned_ids.get(target.isoformat(), []),
            'errors': errors[:12],
            'rejected_candidate_samples': rejected,
        })
        if total_live_checked >= max_live_checks:
            break

    recovered = list(recovered_by_key.values())
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            all_dates = [str(r.get('auction_date')) for r in recovered if r.get('auction_date')]
            if all_dates:
                earliest = min(all_dates)
                state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
                state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'propertyauctions-unresolved-date-chronology-mapping-to-first-party-savills-validation',
        'dates_considered': len(targets),
        'dates_scanned': len(date_runs),
        'date_runs': date_runs,
        'learned_auction_ids_by_date': learned_ids,
        'live_checked': total_live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
    }
    state['propertyauctions_chronology_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['propertyauctions_chronology_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'message': 'Sweeping later unresolved 2014-2019 dates did not yet produce a lot-specific first-party Savills page valid for canonical persistence.',
            'learned_auction_ids_by_date': learned_ids,
            'next_safe_route': 'Bypass search engines entirely: crawl PropertyAuctions robots/sitemaps or listing pagination directly, extract Savills image auction/lot IDs at scale, build an auction-id/date chronology, then validate reconstructed lots only against first-party Savills pages.',
        }
    else:
        state.pop('propertyauctions_chronology_last_blocker', None)

    save_progress(progress)
    DIAGNOSTICS.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-dates', type=int, default=12)
    parser.add_argument('--max-search-results', type=int, default=35)
    parser.add_argument('--max-live-checks', type=int, default=260)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.max_dates, args.max_search_results, args.max_live_checks) >= 0 else 1)
