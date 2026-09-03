from pathlib import Path
import json
from datetime import datetime, timezone

from collectors.auction_house_london import collect as ahl
from collectors.savills import collect as savills
from collectors.bond_wolfe_v2 import collect as bond_wolfe
from collectors.pugh import collect as pugh
from collectors.strettons import collect as strettons
from collectors.lsh import collect as lsh
from collectors.acuitus import collect as acuitus
from collectors.pattinson import collect as pattinson
from collectors.mchugh import collect as mchugh
from collectors.pending import allsop, clive_emson

DATA = Path("data")
DATA.mkdir(exist_ok=True)

COLLECTORS = [ahl, savills, bond_wolfe, pugh, strettons, lsh, pattinson, mchugh, allsop, acuitus, clive_emson]
PUBLISHABLE = {"LIVE", "DEGRADED"}


def load_old_snapshot():
    p = DATA / "properties.json"
    if not p.exists():
        return {"properties": [], "source_health": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {
            "properties": data.get("properties", []),
            "source_health": data.get("source_health", []),
        }
    except Exception:
        return {"properties": [], "source_health": []}


def _key(x):
    return (str(x.get("source") or "").strip(), str(x.get("url") or "").strip())


def _auction_has_finished(x, today):
    raw = str(x.get("auction_date") or "").strip()
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw[:10]).date() < today
    except Exception:
        return False


def _complete_authoritative(r):
    """True only when a collector has proved a complete source-scoped catalogue.

    Partial/degraded collectors may publish useful fresh rows, but they are never
    allowed to delete previously captured rows. Pruning is permitted only when a
    source explicitly declares an authoritative scope and its published count
    exactly matches the source-advertised expected count.
    """
    return bool(
        getattr(r, "authoritative_snapshot", False)
        and r.status == "LIVE"
        and getattr(r, "expected_count", None)
        and len(r.lots) == r.expected_count
        and getattr(r, "scope_dates", ())
    )


def run():
    old_snapshot = load_old_snapshot()
    old = old_snapshot["properties"]
    today = datetime.now(timezone.utc).date()
    old_by_key = {_key(x): dict(x) for x in old if _key(x) != ("", "")}

    results = []
    current_by_key = {}
    source_status = {}
    authoritative_scopes = []

    for fn in COLLECTORS:
        r = fn()
        status = r.to_status_dict()
        results.append(status)
        source_status[r.source] = r.status

        if r.status in PUBLISHABLE:
            for lot in r.lots:
                item = lot.to_dict()
                current_by_key[_key(item)] = item

        if _complete_authoritative(r):
            authoritative_scopes.append((r.source, set(r.scope_dates)))

    # Append-preserving by default: a partial scrape, site outage, pagination
    # change or parser regression cannot erase catalogue history.
    merged_by_key = dict(old_by_key)
    merged_by_key.update(current_by_key)

    # Exception: when a collector proves it has the COMPLETE authoritative source
    # scope (published == source-advertised count), stale rows from that same sale
    # can be removed. This is what cleans parser-created false positives without
    # risking data loss during an incomplete run.
    current_keys = set(current_by_key)
    pruned = 0
    for source, scope_dates in authoritative_scopes:
        stale_keys = [
            key for key, item in merged_by_key.items()
            if key not in current_keys
            and item.get("source") == source
            and str(item.get("auction_date") or "")[:10] in scope_dates
        ]
        for key in stale_keys:
            merged_by_key.pop(key, None)
            pruned += 1

    for key, item in merged_by_key.items():
        if key in current_keys:
            continue

        if _auction_has_finished(item, today):
            item["status"] = "ARCHIVED"
        elif source_status.get(item.get("source")) not in {None, "LIVE"}:
            item["status"] = "STALE SOURCE"

    merged = list(merged_by_key.values())
    merged.sort(key=lambda x: (
        str(x.get("auction_date") or ""),
        str(x.get("source") or ""),
        str(x.get("lot_number") or ""),
        str(x.get("address") or ""),
    ), reverse=True)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "properties": merged,
        "source_health": results,
        "integrity": {
            "authoritative_scopes_completed": len(authoritative_scopes),
            "stale_false_positive_rows_pruned": pruned,
        },
    }
    (DATA / "properties.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at": snapshot["generated_at"],
        "property_count": len(merged),
        "archived_count": sum(1 for x in merged if x.get("status") == "ARCHIVED"),
        "authoritative_scopes_completed": len(authoritative_scopes),
        "stale_false_positive_rows_pruned": pruned,
        "sources": results,
    }, indent=2))


if __name__ == "__main__":
    run()
