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


def load_old():
    p = DATA / "properties.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("properties", [])
    except Exception:
        return []


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


def run():
    old = load_old()
    today = datetime.now(timezone.utc).date()
    old_by_key = {_key(x): dict(x) for x in old if _key(x) != ("", "")}

    results = []
    current_by_key = {}
    source_status = {}

    for fn in COLLECTORS:
        r = fn()
        status = r.to_status_dict()
        results.append(status)
        source_status[r.source] = r.status

        if r.status == "LIVE":
            for lot in r.lots:
                item = lot.to_dict()
                current_by_key[_key(item)] = item

    # History is append-preserving: once a commercial auction lot has been captured,
    # it remains in the radar after the auction finishes or disappears from the
    # auctioneer's current catalogue. A freshly collected exact source/url always wins.
    merged_by_key = dict(old_by_key)
    merged_by_key.update(current_by_key)

    current_keys = set(current_by_key)
    for key, item in merged_by_key.items():
        if key in current_keys:
            continue

        if _auction_has_finished(item, today):
            # Keep all captured facts and the original URL; only lifecycle status changes.
            item["status"] = "ARCHIVED"
        elif source_status.get(item.get("source")) not in {None, "LIVE"}:
            # Future/current lot retained while its collector is temporarily unavailable.
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
    }
    (DATA / "properties.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at": snapshot["generated_at"],
        "property_count": len(merged),
        "archived_count": sum(1 for x in merged if x.get("status") == "ARCHIVED"),
        "sources": results,
    }, indent=2))


if __name__ == "__main__":
    run()
