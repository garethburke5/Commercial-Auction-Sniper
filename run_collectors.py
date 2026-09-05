from pathlib import Path
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

from collectors.core import SourceResult
from collectors.auction_house_london_v2 import collect as ahl
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

BAD_ADDRESS = re.compile(
    r"(?:login|log in|sign in|register to bid|book a viewing|arrange a viewing|"
    r"viewing appointment|cancel proxy bid|your bid|remove from wishlist|add to wishlist|"
    r"connecting to auction|please wait|full details|legal pack available)", re.I
)


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
    return bool(
        getattr(r, "authoritative_snapshot", False)
        and r.status == "LIVE"
        and getattr(r, "expected_count", None)
        and len(r.lots) == r.expected_count
        and getattr(r, "scope_dates", ())
    )


def _address_from_url(item):
    """Recover a property-like label when a parser captured page chrome as h1."""
    url = str(item.get("url") or "")
    path = unquote(urlparse(url).path).strip("/")
    if not path:
        return None
    slug = path.split("/")[-1]
    slug = re.sub(r"-\d{4,7}$", "", slug)
    if slug.lower() in {"current-auction", "current-catalogue", "property-search", "auctions", "auction"}:
        return None
    label = re.sub(r"[-_]+", " ", slug).strip()
    if len(label) < 8 or not re.search(r"[A-Za-z]", label):
        return None
    return label.title()


def _sanitize_item(item):
    """Repair common extraction chrome; reject records that remain structurally unsafe."""
    item = dict(item)
    repairs = []
    address = str(item.get("address") or "").strip()
    if not address or len(address) < 6 or BAD_ADDRESS.search(address):
        recovered = _address_from_url(item)
        if recovered and not BAD_ADDRESS.search(recovered):
            item["address"] = recovered
            repairs.append("address_from_url")
        else:
            return None, repairs, "invalid_address"

    url = str(item.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None, repairs, "invalid_url"

    img = str(item.get("image_url") or "").strip()
    if img and re.search(r"(?:logo|favicon|sprite|placeholder|avatar|social|brandmark)", img, re.I):
        item["image_url"] = None
        repairs.append("generic_image_removed")

    occ = str(item.get("occupation") or "").strip().lower()
    if occ in {"vacant", "vacant possession"} and (item.get("annual_rent") is not None or item.get("gross_yield") is not None):
        item["annual_rent"] = None
        item["gross_yield"] = None
        repairs.append("vacant_rent_cleared")
    return item, repairs, None


def _collector_name(fn):
    module = getattr(fn, "__module__", "")
    leaf = module.rsplit(".", 1)[-1].replace("_v2", "").replace("_", " ").strip()
    return leaf.title() or getattr(fn, "__name__", "Unknown collector")


def _run_collector_safely(fn):
    """Never let one source exception abort all other sources or safe snapshot publication."""
    try:
        return fn()
    except Exception as exc:
        source = _collector_name(fn)
        return SourceResult(
            source=source,
            status="FAILED",
            lots=[],
            message=f"Collector raised {type(exc).__name__}: {exc}",
            discovered_count=0,
            authoritative_snapshot=False,
        )


def run():
    old_snapshot = load_old_snapshot()
    old = list(old_snapshot["properties"]) + list(old_snapshot["archive"])
    today = datetime.now(timezone.utc).date()
    old_by_key = {_key(x): dict(x) for x in old if _key(x) != ("", "")}

    results = []
    current_by_key = {}
    source_status = {}
    authoritative_scopes = []
    quality_repairs = 0
    quality_rejections = 0
    rejection_reasons = {}

    for fn in COLLECTORS:
        r = _run_collector_safely(fn)
        source_status[r.source] = r.status
        source_rejected = 0

        if r.status in PUBLISHABLE:
            for lot in r.lots:
                raw = lot.to_dict()
                item, repairs, reason = _sanitize_item(raw)
                quality_repairs += len(repairs)
                if item is None:
                    quality_rejections += 1
                    source_rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue
                current_by_key[_key(item)] = item

        status = r.to_status_dict()
        if source_rejected:
            status["status"] = "DEGRADED"
            status["message"] = f"{status.get('message','')} Quality gate rejected {source_rejected} unsafe record(s).".strip()
        results.append(status)

        if _complete_authoritative(r) and not source_rejected:
            authoritative_scopes.append((r.source, set(r.scope_dates)))

    merged_by_key = dict(old_by_key)
    merged_by_key.update(current_by_key)

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
        if _auction_has_finished(item, today):
            item["status"] = "ARCHIVED"
            continue
        if key in current_keys:
            item["status"] = "CURRENT"
            continue
        if source_status.get(item.get("source")) is not None:
            item["status"] = "STALE SOURCE"

    history = list(merged_by_key.values())
    history.sort(key=lambda x: (
        str(x.get("auction_date") or ""),
        str(x.get("source") or ""),
        str(x.get("lot_number") or ""),
        str(x.get("address") or ""),
    ), reverse=True)

    active = [x for x in history if x.get("status") == "CURRENT"]
    archive = [x for x in history if x.get("status") != "CURRENT"]

    bad_active = [x for x in active if _auction_has_finished(x, today) or BAD_ADDRESS.search(str(x.get("address") or ""))]
    if bad_active:
        raise RuntimeError(f"production quality gate failed: {len(bad_active)} unsafe active rows")

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
            "quality_repairs": quality_repairs,
            "quality_rejections": quality_rejections,
            "quality_rejection_reasons": rejection_reasons,
        },
    }
    (DATA / "properties.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at": snapshot["generated_at"],
        "property_count": len(active),
        "historical_count": len(archive),
        "archived_count": sum(1 for x in archive if x.get("status") == "ARCHIVED"),
        "stale_source_count": sum(1 for x in archive if x.get("status") == "STALE SOURCE"),
        "quality_repairs": quality_repairs,
        "quality_rejections": quality_rejections,
        "quality_rejection_reasons": rejection_reasons,
        "authoritative_scopes_completed": len(authoritative_scopes),
        "stale_false_positive_rows_pruned": pruned,
        "sources": results,
    }, indent=2))


if __name__ == "__main__":
    run()
