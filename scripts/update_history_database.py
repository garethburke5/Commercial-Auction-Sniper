import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_database import update_history_database

SNAPSHOT = Path("data/properties.json")
HISTORY = Path("data/property_history.json")


def snapshot_history_rows(snapshot):
    """Publication filters must not erase genuine non-commercial auction lots.

    Interface/search rows remain excluded. Prefer the most recent observation
    when a lot has moved between the commercial board and the retained bank.
    """
    excluded = [r for r in snapshot.get('excluded_properties', [])
                if str(r.get('publication_exclusion') or '').startswith(
                    ('Pure residential:', 'Unverified commercial use:'))]
    rows = {}
    for row in excluded + list(snapshot.get('archive') or []) + list(snapshot.get('properties') or []):
        if not row.get('source') or not row.get('url') or not row.get('address'):
            continue
        key = tuple(str(row.get(k) or '') for k in ('source', 'url', 'auction_date', 'lot_number'))
        old = rows.get(key)
        if old is None or str(row.get('collected_at') or '') >= str(old.get('collected_at') or ''):
            rows[key] = row
    return list(rows.values())


def main():
    if not SNAPSHOT.exists():
        raise SystemExit("data/properties.json not found")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = snapshot_history_rows(snapshot)
    db = update_history_database(rows, path=HISTORY)
    stats = db.get("stats") or {}
    print(
        "HISTORY",
        stats.get("property_count", 0), "properties;",
        stats.get("auction_event_count", 0), "auction events;",
        stats.get("sold_prior_count", 0), "sold prior;",
        stats.get("events_with_source_url", 0), "events with source URLs",
    )


if __name__ == "__main__":
    main()
