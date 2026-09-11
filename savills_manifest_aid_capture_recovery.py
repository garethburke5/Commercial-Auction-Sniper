from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import savills_legacy_aid_capture_recovery as legacy

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
SOURCE = 'Savills Auctions'


def manifest_dates(state: dict) -> set[date]:
    """Return every exact dated auction exposed by the surviving Savills archive."""
    found: set[date] = set()
    for raw in state.get('live_archive_dates_discovered') or []:
        try:
            found.add(date.fromisoformat(str(raw)))
        except ValueError:
            pass
    if not found:
        # Older progress snapshots used the detailed first-party archive scan.
        for page in state.get('live_archive_unresolved') or []:
            for raw in page.get('dates') or []:
                try:
                    found.add(date.fromisoformat(str(raw)))
                except ValueError:
                    pass
    return found


def canonical_savills_dates() -> set[date]:
    if not HISTORY.exists():
        return set()
    try:
        db = json.loads(HISTORY.read_text(encoding='utf-8'))
    except Exception:
        return set()
    found: set[date] = set()
    for event in db.get('auction_events') or []:
        if event.get('source') != SOURCE:
            continue
        raw = event.get('auction_date')
        if not raw:
            continue
        try:
            found.add(date.fromisoformat(str(raw)[:10]))
        except ValueError:
            pass
    return found


def unresolved_manifest_dates(state: dict) -> set[date]:
    """Use canonical History V2 itself as the coverage test.

    A live archive page can contain some resolvable catalogue anchors and still have
    other auctions completely absent from canonical lot-level history.  Page-level
    'unresolved' flags therefore understate the real gap.  The authoritative target
    is every first-party manifest date for which History V2 has no Savills event.
    """
    return manifest_dates(state) - canonical_savills_dates()


def unresolved_dates_for_year(state: dict, year: int) -> set[date]:
    return {d for d in unresolved_manifest_dates(state) if d.year == year}


def years_from_manifest(state: dict) -> list[int]:
    return sorted({d.year for d in manifest_dates(state)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int)
    ap.add_argument('--max-live-checks', type=int, default=180)
    args = ap.parse_args()

    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = (progress.get('sources') or {}).get(SOURCE) or {}
    available_years = years_from_manifest(state)
    missing = unresolved_manifest_dates(state)

    if args.year is not None:
        target_year = args.year
    elif missing:
        # Oldest missing canonical auction first, regardless of whether another
        # auction on the same archive page happened to expose a catalogue anchor.
        target_year = min(d.year for d in missing)
    else:
        print(json.dumps({
            'source': SOURCE,
            'events_added': 0,
            'reason': 'Every dated auction in the current Savills live manifest has at least one canonical History V2 event.',
            'available_manifest_years': available_years,
        }, indent=2))
        return 0

    targets = unresolved_dates_for_year(state, target_year)
    if not targets:
        print(json.dumps({
            'source': SOURCE,
            'year': target_year,
            'events_added': 0,
            'reason': 'No canonical date gaps for this manifest year.',
            'available_manifest_years': available_years,
        }, indent=2))
        return 0

    original_frontier_dates = legacy.frontier_dates
    try:
        legacy.frontier_dates = lambda current_state: unresolved_dates_for_year(current_state, target_year)
        return legacy.run(target_year, args.max_live_checks)
    finally:
        legacy.frontier_dates = original_frontier_dates


if __name__ == '__main__':
    raise SystemExit(0 if main() >= 0 else 1)
