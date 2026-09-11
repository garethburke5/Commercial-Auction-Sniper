from __future__ import annotations

"""Run the existing public-address recovery against the *oldest* unresolved
Savills live-archive date instead of its legacy 2019-only frontier helper.

This is intentionally a thin adapter: the evidence/persistence rules stay in
savills_public_address_frontier_recovery.py.  Only target selection changes.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import savills_public_address_frontier_recovery as recovery

DATA = Path("data")
MANIFEST = DATA / "source_diagnostics" / "savills_live_archive_manifest.json"
HISTORY = DATA / "property_history.json"
SOURCE = "Savills Auctions"


def _verified_dates() -> set[date]:
    if not HISTORY.exists():
        return set()
    db = json.loads(HISTORY.read_text(encoding="utf-8"))
    out: set[date] = set()
    for event in db.get("auction_events") or []:
        if event.get("source") != SOURCE:
            continue
        raw = event.get("auction_date")
        if not raw:
            continue
        try:
            out.add(date.fromisoformat(str(raw)[:10]))
        except ValueError:
            pass
    return out


def oldest_unresolved_manifest_dates(_state: dict) -> set[date]:
    """Return the oldest known live-archive auction date lacking lot events.

    We deliberately do not use a fixed year.  If the oldest year/date becomes
    covered, the next invocation advances automatically to the next unresolved
    date exposed by Savills' own live archive manifest.
    """
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    known: set[date] = set()
    for page in raw.get("pages") or []:
        for value in page.get("dates") or []:
            try:
                known.add(date.fromisoformat(str(value)))
            except ValueError:
                pass
    verified = _verified_dates()
    unresolved = sorted(d for d in known if d not in verified and d < date.today())
    return {unresolved[0]} if unresolved else set()


def run(max_source_pages: int = 120, max_clues: int = 160, max_live_checks: int = 220) -> int:
    recovery.frontier_dates = oldest_unresolved_manifest_dates
    return recovery.run(
        max_source_pages=max_source_pages,
        max_clues=max_clues,
        max_live_checks=max_live_checks,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-source-pages", type=int, default=120)
    ap.add_argument("--max-clues", type=int, default=160)
    ap.add_argument("--max-live-checks", type=int, default=220)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_source_pages, args.max_clues, args.max_live_checks) >= 0 else 1)
