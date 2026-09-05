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
from collectors.clive_emson import collect as clive_emson
from collectors.pending import allsop

DATA = Path("data")
DATA.mkdir(exist_ok=True)

COLLECTORS = [ahl, savills, bond_wolfe, pugh, strettons, lsh, pattinson, mchugh, allsop, acuitus, clive_emson]
PUBLISHABLE = {"LIVE", "DEGRADED"}


def load_old_snapshot():
    p = DATA / "properties.json"
    if not p.exists():
        return {"properties": [], "archive": [], "source_health": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {
            "properties": data.get("properties", []),
            "archive": data.get("archive", []),
            "source_health": data.get("source_health", []),
        }
    except Exception:
        return {"properties": [], "archive": [], "source_health": []}


def _key(x):
    return (str(x.get("source") or "").strip(), str(x.get("url") or "").strip())


def _auction_date(x):
    raw = str(x.get("auction_date") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except Exception:
        return None


def _auction_has_finished(x, today):
    d = _auction_date(x)
    return bool(d and d < today)


def _complete_authoritative(r):
    """True only when a collector has proved a complete source-scoped catalogue."""
    return bool(
        getattr(r, "authoritative_snapshot", False)
        and r.status == "LIVE"
        and getattr(r, "expected_count", None)
        and len(r.lots) == r.expected_count
        and getattr(r, "scope_dates", ())
    )


def run():
    old_snapshot = load_old_snapshot()
    # Keep the full historical universe, but do not mix it into the current board.
    old = list(old_snapshot["properties"]) + list(old_snapshot["archive"])
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

    # Historical universe is append-preserving. Collector/site failures cannot erase it.
    merged_by_key = dict(old_by_key)
    merged_by_key.update(current_by_key)

    # Only a proved-complete authoritative scope can prune parser false positives
    # from that exact auction scope.
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

    # GLOBAL lifecycle rule for every auction house. A collector is not allowed to
    # keep a finished auction live merely because its scraper still points at the
    # old catalogue. Past auction dates are archived even when rediscovered today.
    for key, item in merged_by_key.items():
        if _auction_has_finished(item, today):
            item["status"] = "ARCHIVED"
            continue

        if key in current_keys:
            item["status"] = "CURRENT"
            continue

        # Previously captured future/undated rows not rediscovered this run are
        # kept for research but are not presented as current opportunities.
        if source_status.get(item.get("source")) is not None:
            item["status"] = "STALE SOURCE"

    history = list(merged_by_key.values())
    history.sort(key=lambda x: (
        str(x.get("auction_date") or ""),
        str(x.get("source") or ""),
        str(x.get("lot_number") or ""),
        str(x.get("address") or ""),
    ), reverse=True)

    # App-facing properties are ONLY positively rediscovered current/upcoming lots.
    # Finished and stale catalogues are preserved separately in the archive.
    active = [x for x in history if x.get("status") == "CURRENT"]
    archive = [x for x in history if x.get("status") != "CURRENT"]

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "properties": active,
        "archive": archive,
        "source_health": results,
        "integrity": {
            "active_property_count": len(active),
            "historical_property_count": len(archive),
            "authoritative_scopes_completed": len(authoritative_scopes),
            "stale_false_positive_rows_pruned": pruned,
        },
    }
    (DATA / "properties.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at": snapshot["generated_at"],
        "property_count": len(active),
        "historical_count": len(archive),
        "archived_count": sum(1 for x in archive if x.get("status") == "ARCHIVED"),
        "stale_source_count": sum(1 for x in archive if x.get("status") == "STALE SOURCE"),
        "authoritative_scopes_completed": len(authoritative_scopes),
        "stale_false_positive_rows_pruned": pruned,
        "sources": results,
    }, indent=2))


if __name__ == "__main__":
    run()
