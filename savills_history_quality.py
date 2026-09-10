from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from collectors.core import norm
from collectors.utils import soup
from history_database import _find_property, _property_id, postcode

SOURCE = "Savills Auctions"
BAD_ADDRESS_RE = re.compile(
    r"^(?:login\s+to\s+see\s+times\s+and\s+book\s+a\s+viewing|book\s+a\s+viewing|property\s+details?)$",
    re.I,
)
TITLE_PREFIX_RE = re.compile(r"^Savills\s+Property\s+Auctions\s*\|\s*", re.I)


def is_bad_address(value: object) -> bool:
    text = norm(str(value or ""))
    return not text or bool(BAD_ADDRESS_RE.match(text))


def _slug_fallback(url: str) -> str | None:
    slug = urlparse(url or "").path.rstrip("/").split("/")[-1]
    slug = re.sub(r"-\d{3,8}$", "", slug)
    if not slug:
        return None
    value = re.sub(r"-+", " ", slug).strip().title()
    # Restore normal UK postcode capitalisation when the slug carries one.
    value = re.sub(
        r"\b([A-Z]{1,2}\d[A-Z\d]?)\s+(\d[A-Z]{2})\b",
        lambda m: f"{m.group(1).upper()} {m.group(2).upper()}",
        value,
        flags=re.I,
    )
    return value or None


def address_from_listing_url(url: str) -> str | None:
    """Recover the published address from the surviving first-party Savills lot page.

    Legacy Savills pages can place a login modal in the first H1. The HTML title still
    carries the property address (for example, ``Savills Property Auctions | ...``).
    Only a first-party Savills URL is accepted; the URL slug is a last-resort fallback.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "savills.co.uk" or host.endswith(".savills.co.uk")):
        return None
    try:
        doc = soup(url, use_browser=False)
        title_node = doc.find("title")
        if title_node:
            title = norm(title_node.get_text(" ", strip=True))
            title = norm(TITLE_PREFIX_RE.sub("", title))
            if title and not is_bad_address(title) and title.lower() not in {"savills", "savills auctions"}:
                return title
    except Exception:
        pass
    return _slug_fallback(url)


def correct_rows(rows: list[dict]) -> tuple[list[dict], int]:
    corrected = 0
    for row in rows:
        if row.get("source") != SOURCE or not is_bad_address(row.get("address")):
            continue
        fixed = address_from_listing_url(str(row.get("evidence_url") or row.get("url") or ""))
        if fixed:
            row["address"] = fixed
            corrected += 1
    return rows, corrected


def repair_database(path: str | Path = "data/property_history.json") -> int:
    """Repair already-persisted Savills events whose address was modal boilerplate.

    Event identity is source/url/date/lot based, so the existing auction event is kept.
    Its property link is moved to the corrected address and orphan boilerplate property
    records are removed. No auction facts are invented or discarded.
    """
    p = Path(path)
    if not p.exists():
        return 0
    db = json.loads(p.read_text(encoding="utf-8"))
    properties = db.get("properties") or []
    events = db.get("auction_events") or []
    by_pid = {prop.get("property_id"): prop for prop in properties if prop.get("property_id")}
    repaired = 0
    now = datetime.now(timezone.utc).isoformat()

    for event in events:
        if event.get("source") != SOURCE or not is_bad_address(event.get("address_as_published")):
            continue
        listing_url = ((event.get("source_evidence") or {}).get("listing_url") or "").strip()
        fixed = address_from_listing_url(listing_url)
        if not fixed or is_bad_address(fixed):
            continue

        old_pid = event.get("property_id")
        target, confidence = _find_property(properties, fixed)
        if target is None:
            pid = _property_id(fixed)
            existing = {prop.get("property_id") for prop in properties}
            if pid in existing:
                # A duplicate ID should mean an equivalent address; reuse that record.
                target = next((prop for prop in properties if prop.get("property_id") == pid), None)
            if target is None:
                target = {
                    "property_id": pid,
                    "canonical_address": fixed,
                    "postcode": postcode(fixed),
                    "address_variants": [fixed],
                    "first_seen": event.get("first_seen") or now,
                    "last_seen": now,
                    "auction_event_ids": [],
                }
                properties.append(target)
                by_pid[pid] = target
            confidence = 1.0
        else:
            target["last_seen"] = now
            variants = target.setdefault("address_variants", [])
            if fixed not in variants:
                variants.append(fixed)

        eid = event.get("event_id")
        old_prop = by_pid.get(old_pid)
        if old_prop and old_prop is not target and eid in (old_prop.get("auction_event_ids") or []):
            old_prop["auction_event_ids"] = [x for x in old_prop.get("auction_event_ids") or [] if x != eid]

        ids = target.setdefault("auction_event_ids", [])
        if eid and eid not in ids:
            ids.append(eid)
        event["property_id"] = target["property_id"]
        event["match_confidence"] = confidence
        event["address_as_published"] = fixed
        event["last_seen"] = now
        repaired += 1

    if repaired:
        referenced = {e.get("property_id") for e in events if e.get("property_id")}
        properties[:] = [prop for prop in properties if prop.get("property_id") in referenced]
        db["properties"] = properties
        db["generated_at"] = now
        stats = db.setdefault("stats", {})
        stats["property_count"] = len(properties)
        stats["auction_event_count"] = len(events)
        stats["savills_addresses_repaired_last_run"] = repaired
        p.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    return repaired


if __name__ == "__main__":
    count = repair_database()
    print(json.dumps({"savills_addresses_repaired": count}))
