from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from collectors.core import norm
from collectors.utils import soup
from history_database import _find_property, _property_id, postcode

DATA = Path("data")
HISTORY_PATH = DATA / "property_history.json"
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
SOURCE = "Savills Auctions"
BAD_ADDRESS = re.compile(r"login\s+to\s+see\s+times|book\s+a\s+viewing", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def title_address(url):
    doc = soup(url, use_browser=False)
    title = doc.find("title")
    text = norm(title.get_text(" ", strip=True)) if title else ""
    if "|" in text:
        text = norm(text.split("|", 1)[1])
    text = re.sub(r"^Savills\s+Property\s+Auctions\s*[-–:]\s*", "", text, flags=re.I)
    if not text or BAD_ADDRESS.search(text):
        raise RuntimeError(f"Could not recover Savills address from title: {url}")
    return text


def recompute_stats(db, added_properties_last_run=0):
    events = db.get("auction_events") or []
    db["generated_at"] = now_iso()
    db["stats"] = {
        "property_count": len(db.get("properties") or []),
        "auction_event_count": len(events),
        "sold_prior_count": sum(1 for e in events if str(e.get("status") or "").strip().upper() == "SOLD PRIOR"),
        "events_with_guide": sum(1 for e in events if e.get("guide_price") is not None),
        "events_with_source_url": sum(1 for e in events if (e.get("source_evidence") or {}).get("listing_url")),
        "added_properties_last_run": added_properties_last_run,
        "added_events_last_run": int((db.get("stats") or {}).get("added_events_last_run") or 0),
        "updated_events_last_run": int((db.get("stats") or {}).get("updated_events_last_run") or 0),
    }


def repair():
    if not HISTORY_PATH.exists():
        raise RuntimeError("property_history.json missing")
    db = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    events = db.get("auction_events") or []
    sav_events = [e for e in events if e.get("source") == SOURCE]
    targets = [e for e in sav_events if BAD_ADDRESS.search(str(e.get("address_as_published") or ""))]

    corrected = {}
    for event in targets:
        url = (event.get("source_evidence") or {}).get("listing_url")
        if not url:
            raise RuntimeError(f"Savills event {event.get('event_id')} lacks listing evidence")
        corrected[event.get("event_id")] = title_address(url)

    if corrected:
        corrected_ids = set(corrected)
        properties = []
        for prop in db.get("properties") or []:
            kept_ids = [eid for eid in (prop.get("auction_event_ids") or []) if eid not in corrected_ids]
            if not kept_ids:
                continue
            clean = dict(prop)
            clean["auction_event_ids"] = kept_ids
            properties.append(clean)

        existing_ids = {p.get("property_id") for p in properties}
        added_properties = 0
        observed_at = now_iso()
        for event in targets:
            eid = event.get("event_id")
            address = corrected[eid]
            prop, confidence = _find_property(properties, address)
            if prop is None:
                pid = _property_id(address)
                if pid in existing_ids:
                    salt = 1
                    base = pid
                    while pid in existing_ids:
                        pid = _property_id(f"{address} repair-{salt}")
                        salt += 1
                    if pid == base:
                        raise RuntimeError("Could not allocate unique Savills property id")
                prop = {
                    "property_id": pid,
                    "canonical_address": address,
                    "postcode": postcode(address),
                    "address_variants": [address],
                    "first_seen": event.get("first_seen") or observed_at,
                    "last_seen": event.get("last_seen") or observed_at,
                    "auction_event_ids": [],
                }
                properties.append(prop)
                existing_ids.add(pid)
                added_properties += 1
                confidence = 1.0
            else:
                variants = prop.setdefault("address_variants", [])
                if address not in variants:
                    variants.append(address)
                prop["last_seen"] = event.get("last_seen") or observed_at

            event["address_as_published"] = address
            event["property_id"] = prop["property_id"]
            event["match_confidence"] = confidence
            if eid not in prop["auction_event_ids"]:
                prop["auction_event_ids"].append(eid)

        db["properties"] = properties
        recompute_stats(db, added_properties_last_run=added_properties)
        HISTORY_PATH.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")

    remaining_bad = [
        e.get("event_id") for e in sav_events
        if BAD_ADDRESS.search(str(e.get("address_as_published") or ""))
    ]
    if remaining_bad:
        raise RuntimeError(f"Savills address repair left {len(remaining_bad)} bad events")

    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8")) if PROGRESS_PATH.exists() else {"sources": {}}
    state = (progress.setdefault("sources", {}).setdefault(SOURCE, {}))
    state["last_address_repairs"] = len(corrected)
    state["address_quality_checked"] = len(sav_events)
    state["last_quality_check"] = now_iso()
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "source": SOURCE,
        "events_checked": len(sav_events),
        "addresses_repaired": len(corrected),
        "remaining_bad": len(remaining_bad),
    }, indent=2))


if __name__ == "__main__":
    repair()
