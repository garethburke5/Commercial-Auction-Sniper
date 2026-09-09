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
UNIT_RE = re.compile(r"\b(?:unit|flat|suite|shop)\s*([0-9]+[a-z]?)\b", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def unit_id(address):
    m = UNIT_RE.search(str(address or ""))
    return m.group(1).lower() if m else None


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


def unit_collision_event_ids(sav_events):
    grouped = {}
    for event in sav_events:
        grouped.setdefault(event.get("property_id"), []).append(event)
    out = set()
    for group in grouped.values():
        units = {unit_id(e.get("address_as_published")) for e in group}
        units.discard(None)
        if len(units) > 1:
            out.update(e.get("event_id") for e in group)
    return out


def safe_find_property(properties, address):
    prop, confidence = _find_property(properties, address)
    if prop is None:
        return None, confidence
    wanted_unit = unit_id(address)
    if wanted_unit:
        existing_units = {
            unit_id(v)
            for v in (prop.get("address_variants") or [prop.get("canonical_address")])
            if v
        }
        existing_units.discard(None)
        if existing_units and wanted_unit not in existing_units:
            return None, confidence
    return prop, confidence


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
    collision_ids = unit_collision_event_ids(sav_events)
    targets = [
        e for e in sav_events
        if BAD_ADDRESS.search(str(e.get("address_as_published") or "")) or e.get("event_id") in collision_ids
    ]

    corrected = {}
    address_repairs = 0
    unit_splits = 0
    for event in targets:
        eid = event.get("event_id")
        current = norm(str(event.get("address_as_published") or ""))
        if BAD_ADDRESS.search(current):
            url = (event.get("source_evidence") or {}).get("listing_url")
            if not url:
                raise RuntimeError(f"Savills event {eid} lacks listing evidence")
            corrected[eid] = title_address(url)
            address_repairs += 1
        else:
            corrected[eid] = current
            unit_splits += 1

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
            prop, confidence = safe_find_property(properties, address)
            if prop is None:
                pid = _property_id(address)
                if pid in existing_ids:
                    salt = 1
                    while pid in existing_ids:
                        pid = _property_id(f"{address} repair-{salt}")
                        salt += 1
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

    remaining_collisions = unit_collision_event_ids(sav_events)
    if remaining_collisions:
        raise RuntimeError(f"Savills repair left {len(remaining_collisions)} events in cross-unit property merges")

    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8")) if PROGRESS_PATH.exists() else {"sources": {}}
    state = progress.setdefault("sources", {}).setdefault(SOURCE, {})
    state["last_address_repairs"] = address_repairs
    state["last_unit_split_repairs"] = unit_splits
    state["address_quality_checked"] = len(sav_events)
    state["last_quality_check"] = now_iso()
    # `historical_savills` counts every raw row it successfully normalises. A Savills
    # listing can legitimately resolve to an already-known canonical event, so that
    # raw cumulative count can exceed History V2's persisted source-event count.
    # Completeness telemetry must describe what actually persisted, not attempted rows.
    state["lots_captured"] = len(sav_events)
    state["last_history_event_count"] = len(events)
    state["last_canonical_source_event_count"] = len(sav_events)
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "source": SOURCE,
        "events_checked": len(sav_events),
        "addresses_repaired": address_repairs,
        "unit_split_repairs": unit_splits,
        "remaining_bad": len(remaining_bad),
        "remaining_unit_collisions": len(remaining_collisions),
    }, indent=2))


if __name__ == "__main__":
    repair()
