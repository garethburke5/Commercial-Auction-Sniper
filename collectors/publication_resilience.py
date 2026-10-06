"""Keep a healthy production board publishable when an auctioneer is temporarily unreachable.

The canonical collector already retains previous rows and marks them STALE SOURCE when a
collector fails. This publication step promotes still-future retained rows back onto the
public board and records the source as DEGRADED, never LIVE. It does not fabricate fresh
coverage or prune inventory from an unavailable source.

A failed collector with no previously published inventory is also represented as DEGRADED
rather than FAILED. There is nothing to preserve in that case, so treating the outage as a
publication-blocking inventory loss would deadlock the whole national refresh. The source
remains explicitly non-authoritative and its outage is recorded in source health.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from source_manifest import manifest_coverage

DATA = Path("data/properties.json")
TERMINAL = {"SOLD PRIOR", "WITHDRAWN", "WITHDRAWN PRIOR", "POSTPONED", "AUCTION ENDED", "COMPLETED", "ARCHIVED"}


def _day(row):
    try:
        return date.fromisoformat(str(row.get("auction_date") or "")[:10])
    except Exception:
        return None


def _status(row):
    return str(row.get("status") or "").strip().upper().replace("_", " ")


def _current_enough(row, today, now):
    day=_day(row)
    if day is not None:return day>=today
    # Rolling online catalogues can advertise live lots without a fixed date.
    # Retain recent evidence briefly during an outage, never indefinitely.
    try:captured=datetime.fromisoformat(str(row.get('collected_at') or '').replace('Z','+00:00'))
    except ValueError:return False
    if captured.tzinfo is None:captured=captured.replace(tzinfo=timezone.utc)
    return timedelta(0)<=now-captured<=timedelta(hours=48)


def apply(path=DATA, today=None, now=None):
    now=now or datetime.now(timezone.utc)
    today = today or now.date()
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    properties = list(data.get("properties") or [])
    archive = list(data.get("archive") or [])
    health = list(data.get("source_health") or [])

    failed_sources = {
        str(h.get("source") or "") for h in health
        if str(h.get("status") or "").upper() == "FAILED"
        or (str(h.get("status") or "").upper() == "DEGRADED"
            and h.get("authoritative_snapshot") is False
            and (h.get("reconciliation") or {}).get("discovery_failures"))
    }
    preserved = Counter()
    kept_archive = []
    existing = {(str(x.get("source") or ""), str(x.get("url") or "")) for x in properties}

    for row in archive:
        source = str(row.get("source") or "")
        day = _day(row)
        key = (source, str(row.get("url") or ""))
        if source in failed_sources and _status(row) == "STALE SOURCE" and _current_enough(row,today,now) and key not in existing:
            row["status"] = "CURRENT"
            properties.append(row)
            existing.add(key)
            preserved[source] += 1
        else:
            kept_archive.append(row)

    zero_inventory_outages = []
    for h in health:
        source = str(h.get("source") or "")
        if source not in failed_sources:
            continue
        retained_total = sum(1 for x in properties + kept_archive if str(x.get("source") or "") == source)
        original = str(h.get("message") or "").strip()
        h["status"] = "DEGRADED"
        h["authoritative_snapshot"] = False
        if retained_total:
            h["message"] = (original + " " if original else "") + f"Temporary collector outage: retained {retained_total} last-known-good row(s); {preserved[source]} eligible current row(s) restored on the public board. Undated rows expire after 48 hours without fresh evidence."
        else:
            h["zero_inventory_outage"] = True
            zero_inventory_outages.append(source)
            h["message"] = (original + " " if original else "") + "Temporary collector outage with no last-known-good inventory to preserve; source is unavailable and non-authoritative, but no published inventory was lost."

    data["properties"] = properties
    data["archive"] = kept_archive
    data["source_health"] = health
    coverage = manifest_coverage(health)
    integrity = data.setdefault("integrity", {})
    integrity["target_coverage"] = coverage
    integrity["acceptance_ready"] = coverage.get("acceptance_ready", False)
    integrity["temporary_outage_sources_preserved"] = dict(preserved)
    integrity["zero_inventory_outage_sources"] = sorted(zero_inventory_outages)
    integrity["published_property_count"] = len(properties)
    integrity["historical_property_count"] = len(kept_archive)
    from run_collectors import refresh_quality_telemetry
    from .publication_quality import prepare_publication
    prepare_publication(data)
    refresh_quality_telemetry(data)
    # Reconcile the rows customers actually receive, after outage restoration.
    from source_reconciliation import attach
    attach(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("SOURCE RESILIENCE", json.dumps({"failed_sources": sorted(failed_sources), "preserved_future_rows": dict(preserved), "zero_inventory_outages": sorted(zero_inventory_outages), "acceptance_ready": coverage.get("acceptance_ready")}, sort_keys=True))
    return data


if __name__ == "__main__":
    apply()
