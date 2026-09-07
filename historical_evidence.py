from __future__ import annotations

import json
from pathlib import Path

from history_database import _event_id


def merge_result_evidence(rows, path="data/property_history.json"):
    p = Path(path)
    if not p.exists():
        return 0
    db = json.loads(p.read_text(encoding="utf-8"))
    by_id = {e.get("event_id"): e for e in db.get("auction_events", []) if e.get("event_id")}
    updated = 0
    for row in rows:
        event = by_id.get(_event_id(row))
        if not event:
            continue
        changed = False
        sale_price = row.get("sale_price")
        if sale_price is not None and event.get("sale_price") != sale_price:
            event["sale_price"] = sale_price
            changed = True
        evidence = event.setdefault("source_evidence", {})
        for src_key, dest_key in (
            ("result_page_url", "result_page_url"),
            ("evidence_url", "evidence_url"),
            ("url", "listing_url"),
            ("legal_pack_url", "legal_pack_url"),
        ):
            value = row.get(src_key)
            if value and evidence.get(dest_key) != value:
                evidence[dest_key] = value
                changed = True
        if changed:
            updated += 1
    stats = db.setdefault("stats", {})
    events = db.get("auction_events", [])
    stats["events_with_sale_price"] = sum(1 for e in events if e.get("sale_price") is not None)
    stats["events_with_result_page"] = sum(1 for e in events if (e.get("source_evidence") or {}).get("result_page_url"))
    p.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    return updated
