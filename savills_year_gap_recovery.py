from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import recover_candidate
from savills_manifest_aid_capture_recovery import manifest_dates
from savills_propertyauctions_clue_recovery import candidate_urls, parse_listing, search_urls
from savills_propertyauctions_cursor_recovery import (
    get as fetch_catalogue,
    rows as catalogue_rows,
    valid_heading_date,
)

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAGNOSTIC = Path('data/source_diagnostics/savills_year_gap_recovery.json')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_day(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:
        return None


def canonical_dates(db: dict) -> set[date]:
    out: set[date] = set()
    for event in db.get('auction_events') or []:
        if event.get('source') != SOURCE_KEY:
            continue
        d = iso_day(event.get('auction_date'))
        if d:
            out.add(d)
    return out


def recovered_catalogues_from_state(state: dict, year: int) -> list[dict]:
    """Recover dated PropertyAuctions AID catalogue evidence already persisted anywhere in Savills state.

    Earlier cursor/postback runs persisted detailed AID evidence in nested diagnostics but did not always
    carry forward the flattened validated catalogue manifest.  Mine that evidence instead of assuming an
    in-memory manifest survived the conflict-safe publisher.
    """
    found: dict[tuple[int, str], dict] = {}

    def walk(node):
        if isinstance(node, dict):
            aid = node.get('aid')
            raw_date = node.get('date') or node.get('auction_date')
            url = node.get('url') or node.get('catalogue_url') or node.get('evidence_url')
            d = iso_day(raw_date)
            if (
                d and d.year == year and aid is not None and str(aid).isdigit()
                and url and 'propertyauctions.com' in str(url).lower() and 'aid=' in str(url).lower()
            ):
                key = (int(aid), d.isoformat())
                found[key] = {
                    'aid': int(aid),
                    'date': d.isoformat(),
                    'url': str(url),
                    'title': str(node.get('title') or ''),
                    'validation': 'recovered from persisted Savills PropertyAuctions diagnostic state; live dated Savills heading must be revalidated',
                }
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(state)
    return sorted(found.values(), key=lambda x: (x['date'], x['aid']))


def queries_for_clue(clue: dict) -> list[str]:
    location = str(clue.get('location') or '').strip()
    ptype = str(clue.get('property_type') or '').strip()
    lot = str(clue.get('lot_number') or '').strip()
    auction_date = str(clue.get('auction_date') or '')
    day = iso_day(auction_date)
    date_text = day.strftime('%d %B %Y') if day else auction_date
    queries = [
        f'site:propertyauctions.io/listings "Savills" "{location}" "{date_text}"',
        f'site:propertyauctions.io/listings "Savills" "{location}" "{ptype}"',
        f'site:propertyauctions.io/listings "Savills" "{location}" "Lot {lot}"',
    ]
    out = []
    for q in queries:
        if '""' in q or q in out:
            continue
        out.append(q)
    return out


def run(year: int, max_clues: int = 180, max_search_results: int = 12, max_live_checks: int = 320) -> int:
    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'YEAR GAP RECOVERY'

    db_before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(db_before)
    existing_dates = canonical_dates(db_before)
    master_dates = sorted(d for d in manifest_dates(state) if d.year == year)

    validated = state.get('propertyauctions_validated_catalogue_manifest') or []
    catalogue_manifest = []
    for item in validated:
        d = iso_day(item.get('date'))
        if d and d.year == year and item.get('aid') is not None and item.get('url'):
            catalogue_manifest.append(item)
    manifest_source = 'flattened-validated-manifest'
    if not catalogue_manifest:
        catalogue_manifest = recovered_catalogues_from_state(state, year)
        manifest_source = 'nested-persisted-diagnostic-state'

    by_aid = {}
    for item in catalogue_manifest:
        by_aid[int(item['aid'])] = item
    catalogue_manifest = sorted(by_aid.values(), key=lambda x: str(x.get('date') or ''))

    catalogue_runs = []
    clues: list[dict] = []
    revalidated_catalogues = []
    for item in catalogue_manifest:
        aid = int(item['aid'])
        returned_aid, url, status, text, error = fetch_catalogue(aid)
        run_rec = {
            'aid': returned_aid,
            'persisted_date': item.get('date'),
            'url': url,
            'status': status,
            'error': error,
            'observed_savills_date': None,
            'commercial_mixed_clues': 0,
        }
        if status == 200 and text:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, 'html.parser')
                plain = ' '.join(soup.stripped_strings)
                observed = valid_heading_date(plain)
                run_rec['observed_savills_date'] = observed
                if observed and str(observed).startswith(f'{year}-'):
                    parsed = catalogue_rows(soup, aid, observed, url)
                    run_rec['commercial_mixed_clues'] = len(parsed)
                    clues.extend(parsed)
                    revalidated_catalogues.append({
                        'aid': aid,
                        'date': observed,
                        'url': url,
                        'validation': 'live PropertyAuctions page has explicit dated SAVILLS heading',
                        'strict_commercial_mixed_lots_on_initial_grid': len(parsed),
                    })
                else:
                    run_rec['validation_failure'] = 'live page lacks explicit dated Savills heading for target year'
            except Exception as exc:
                run_rec['parse_error'] = f'{type(exc).__name__}: {exc}'
        catalogue_runs.append(run_rec)

    deduped = {}
    for clue in clues:
        key = (str(clue.get('auction_date')), str(clue.get('aid')), str(clue.get('lot_number')))
        deduped[key] = clue
    clues = list(deduped.values())[:max_clues]

    recovered = {}
    clue_runs = []
    live_checks = 0
    for clue in clues:
        target = iso_day(clue.get('auction_date'))
        if not target:
            continue
        discovered: list[str] = []
        search_errors: list[str] = []
        for query in queries_for_clue(clue):
            urls, errs = search_urls(query, max_results=max_search_results)
            search_errors.extend(f'{query} :: {e}' for e in errs)
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

        first_party = {}
        for item in matched:
            for candidate in candidate_urls(item, target):
                first_party.setdefault(candidate, item['discovery_url'])

        accepted = 0
        rejected = []
        for candidate, discovery in first_party.items():
            if live_checks >= max_live_checks:
                break
            live_checks += 1
            row, reason = recover_candidate(candidate, target, discovery)
            if row:
                row['legacy_catalogue_url'] = clue.get('evidence_url')
                row['legacy_catalogue_aid'] = clue.get('aid')
                row['legacy_catalogue_lot_number'] = clue.get('lot_number')
                key = (str(row.get('auction_date')), str(row.get('lot_number')), str(row.get('source_url') or row.get('url')))
                recovered[key] = row
                accepted += 1
            elif len(rejected) < 8:
                rejected.append({'url': candidate, 'reason': reason})

        clue_runs.append({
            'aid': clue.get('aid'),
            'auction_date': clue.get('auction_date'),
            'lot_number': clue.get('lot_number'),
            'property_type': clue.get('property_type'),
            'location': clue.get('location'),
            'result': clue.get('result'),
            'catalogue_url': clue.get('evidence_url'),
            'indexed_listing_urls': len(discovered),
            'matched_listing_pages': len(matched),
            'candidate_first_party_urls': len(first_party),
            'accepted_first_party_rows': accepted,
            'search_errors': search_errors[:6],
            'rejected_samples': rejected,
        })
        if live_checks >= max_live_checks:
            break

    rows = list(recovered.values())
    after_n = before_n
    added = 0
    if rows:
        db_after = update_history_database(rows, path=HISTORY)
        after_n = source_count(db_after)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        state['last_history_event_count'] = after_n
        recovered_dates = [str(r.get('auction_date')) for r in rows if r.get('auction_date')]
        if recovered_dates:
            earliest = min(recovered_dates)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    if revalidated_catalogues:
        merged = {str(x.get('aid')): x for x in (state.get('propertyauctions_validated_catalogue_manifest') or []) if x.get('aid') is not None}
        for item in revalidated_catalogues:
            merged[str(item['aid'])] = item
        state['propertyauctions_validated_catalogue_manifest'] = sorted(merged.values(), key=lambda x: int(x['aid']), reverse=True)

    missing_master_dates = [d.isoformat() for d in master_dates if d not in existing_dates]
    diag = {
        'at': now_iso(),
        'route': 'savills-year-gap-persisted-aid-evidence-to-live-catalogue-to-lot-tuple-to-first-party-validation',
        'target_year': year,
        'master_manifest_dates': [d.isoformat() for d in master_dates],
        'master_dates_without_preexisting_canonical_event': missing_master_dates,
        'catalogue_manifest_source': manifest_source,
        'catalogue_candidates_recovered': catalogue_manifest,
        'revalidated_propertyauctions_catalogues': revalidated_catalogues,
        'catalogue_runs': catalogue_runs,
        'commercial_mixed_clues': len(clues),
        'clues_processed': len(clue_runs),
        'live_first_party_checks': live_checks,
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'clue_runs': clue_runs,
    }
    state['savills_year_gap_last_run'] = diag
    state['last_discovery_mode'] = diag['route']
    state['savills_year_gap_focus'] = {
        'year': year,
        'master_dates': len(master_dates),
        'revalidated_legacy_catalogues': len(revalidated_catalogues),
        'commercial_mixed_clues': len(clues),
        'canonical_events_added': added,
    }

    if added == 0:
        failing = catalogue_runs[0]['url'] if catalogue_runs else f'Savills master-manifest year {year}'
        state['status'] = 'YEAR GAP BLOCKED'
        state['savills_year_gap_last_blocker'] = {
            'at': diag['at'],
            'route': diag['route'],
            'failing_url_or_route': failing,
            'message': (
                f'Year {year} reconciliation recovered {len(catalogue_manifest)} persisted AID catalogue candidate(s), '
                f'revalidated {len(revalidated_catalogues)} as explicit dated Savills catalogue(s), and extracted '
                f'{len(clues)} strict commercial/mixed-use lot clue(s), but no clue completed the indexed-detail plus '
                'first-party Savills validation chain required for a new canonical History V2 event.'
            ),
            'next_safe_route': (
                'Use the exact revalidated AID/lot/type/location/result tuples from this diagnostic to enumerate '
                'PropertyAuctions listing pagination/sitemaps and image asset IDs directly (no date-only search), then '
                'reconcile any full-address hit back to the catalogue tuple and first-party Savills evidence.'
            ),
            'catalogue_urls': [x['url'] for x in catalogue_runs],
        }
    else:
        state.pop('savills_year_gap_last_blocker', None)
        state['status'] = 'YEAR GAP RECOVERY ACTIVE'

    progress['updated_at'] = diag['at']
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in diag.items() if k != 'clue_runs'}, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--max-clues', type=int, default=180)
    parser.add_argument('--max-search-results', type=int, default=12)
    parser.add_argument('--max-live-checks', type=int, default=320)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.year, args.max_clues, args.max_search_results, args.max_live_checks) >= 0 else 1)
