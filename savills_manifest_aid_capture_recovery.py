from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import savills_legacy_aid_capture_recovery as legacy

PROGRESS = Path('data/historical_backfill_progress.json')
SOURCE = 'Savills Auctions'


def unresolved_dates_for_year(state: dict, year: int) -> set[date]:
    """Return exact live-Savills archive dates for a requested year.

    The older recovery module originally hard-coded 2019.  This wrapper deliberately
    derives its targets from the persisted first-party live archive manifest so the
    same WARC aid/pid recovery can descend through every visible archive year.
    """
    found: set[date] = set()
    for page in state.get('live_archive_unresolved') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
            except ValueError:
                continue
            if d.year == year:
                found.add(d)
    return found


def years_from_manifest(state: dict) -> list[int]:
    years: set[int] = set()
    for raw in state.get('live_archive_dates_discovered') or []:
        try:
            years.add(date.fromisoformat(str(raw)).year)
        except ValueError:
            pass
    if not years:
        for page in state.get('live_archive_unresolved') or []:
            for raw in page.get('dates') or []:
                try:
                    years.add(date.fromisoformat(str(raw)).year)
                except ValueError:
                    pass
    return sorted(years)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int)
    ap.add_argument('--max-live-checks', type=int, default=180)
    args = ap.parse_args()

    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = (progress.get('sources') or {}).get(SOURCE) or {}
    available_years = years_from_manifest(state)
    if args.year is not None:
        target_year = args.year
    else:
        # Oldest first: this follows the user's requirement to recover the deepest
        # practical Savills history rather than stopping at the current lot frontier.
        target_year = min(available_years) if available_years else 2019

    targets = unresolved_dates_for_year(state, target_year)
    if not targets:
        print(json.dumps({
            'source': SOURCE,
            'year': target_year,
            'events_added': 0,
            'reason': 'No unresolved first-party live archive dates for this year.',
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
