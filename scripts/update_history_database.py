import json
from pathlib import Path

from history_database import update_history_database

SNAPSHOT = Path("data/properties.json")
HISTORY = Path("data/property_history.json")


def main():
    if not SNAPSHOT.exists():
        raise SystemExit("data/properties.json not found")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = list(snapshot.get("properties") or []) + list(snapshot.get("archive") or [])
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
