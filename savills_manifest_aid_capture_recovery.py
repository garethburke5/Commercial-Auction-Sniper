from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import savills_legacy_aid_capture_recovery as legacy

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
MANIFEST = Path('data/source_diagnostics/savills_live_archive_manifest.json')
SOURCE = 'Savills Auctions'


def _add_date(found: set[date], raw) -> None:
    if not raw:
        return
    try:
        found.add(date.fromisoformat(str(raw)[:10]))
    except ValueError:
        pass


def manifest_dates(state: dict) -> set[date]:
    """Return every exact dated auction exposed by the surviving Savills archive.

    Prefer the persisted first-party manifest itself.  Progress has changed shape
    during the backfill and cannot be assumed to carry a complete flat date list.
    """
    found: set[date] = set()
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
            for page in manifest.get('pages') or []:
                for raw in page.get('dates') or []:
                    _add_date(found, raw)
        except Exception:
            pass
    if found:
        return found

    for raw in state.get('live_archive_dates_discovered') or []:
        _add_date(found, raw)
    if found:
        return found

    # Compatibility with older progress snapshots.  This is deliberately last
    # because page-level unresolved state can omit missing auctions on a partly
    # linked page.
    for page in state.get('live_archive_unresolved') or []:
        for raw in page.get('dates') or []:
            _add_date(found, raw)
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
        _add_date(found, event.get('auction_date'))
    return found


def unresolved_manifest_dates(state: dict) -> set[date]:
    """Every first-party manifest date absent from canonical lot-level history."""
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
        target_year = min(d.year for d in missing)
    else:
        print(json.dumps({
            'source': SOURCE,
            'events_added': 0,
            'reason': 'Every dated auction in the persisted Savills live manifest has at least one canonical History V2 event.',
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

    print(json.dumps({
        'source': SOURCE,
        'target_year': target_year,
        'target_dates': sorted(d.isoformat() for d in targets),
        'manifest_years': available_years,
    }, indent=2))

    original_frontier_dates = legacy.frontier_dates
    try:
        legacy.frontier_dates = lambda current_state: unresolved_dates_for_year(current_state, target_year)
        return legacy.run(target_year, args.max_live_checks)
    finally:
        legacy.frontier_dates = original_frontier_dates


if __name__ == '__main__':
    raise SystemExit(0 if main() >= 0 else 1)
