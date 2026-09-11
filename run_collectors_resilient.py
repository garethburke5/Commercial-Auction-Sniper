"""Production entry point with lifecycle-safe and source-resilient auction collectors.

Keeps run_collectors.py as the canonical snapshot/quality pipeline while replacing
collectors that need durable production-specific resilience.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import run_collectors as pipeline
from collectors import auction_house_regions_resilient as regional
from collectors import auction_house_london_resilient as london
from collectors import clive_emson_resilient as clive
from collectors import symonds_sampson_resilient as symonds
from collectors import future_property_auctions_resilient as future_property
from collectors import bidx1 as bidx1_collector


_REPLACEMENTS = {
    "collect_east_anglia": regional.collect_east_anglia,
    "collect_west_yorkshire": regional.collect_west_yorkshire,
    "collect_sussex_hampshire": regional.collect_sussex_hampshire,
    "collect_south_west": regional.collect_south_west,
    "collect_wales": regional.collect_wales,
    "collect_cumbria": regional.collect_cumbria,
    "collect_north_east": regional.collect_north_east,
    "collect_north_west": regional.collect_north_west,
    "collect_lincolnshire": regional.collect_lincolnshire,
    "collect_manchester": regional.collect_manchester,
    "collect_chesterfield": regional.collect_chesterfield,
    "collect_coventry_warwickshire": regional.collect_coventry_warwickshire,
    "collect_scotland": regional.collect_scotland,
    "collect_hull_east_yorkshire": regional.collect_hull_east_yorkshire,
    "collect_birmingham_black_country": regional.collect_birmingham_black_country,
    "collect_northants_beds_bucks": regional.collect_northants_beds_bucks,
    "collect_beds_bucks": regional.collect_beds_bucks,
    "collect_leicestershire": regional.collect_leicestershire,
    "collect_tees_valley": regional.collect_tees_valley,
    "collect_national_online": regional.collect_national_online,
}

_PUBLISHED_TERMINAL = {"SOLD PRIOR", "WITHDRAWN", "WITHDRAWN PRIOR", "POSTPONED"}
_WORKFLOW_BOILERPLATE = re.compile(
    r"(?:login|log in|register to bid|cancel proxy bid|your bid|wishlist|connecting to auction|please wait)",
    re.I,
)
_RESERVE_RE = re.compile(r"\bReserve\s*£\s*([\d,]+(?:\.\d+)?)\b", re.I)
_GUIDE_RE = re.compile(r"\bGuide(?:\s+Price)?\s*£\s*[\d,]+(?:\.\d+)?\b", re.I)


def _normal_status(value):
    return str(value or "").strip().upper().replace("_", " ")


def _normal_token(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _apply_bidx1_reserve_proxy(result):
    """Use a published BidX1 reserve only when no guide is published.

    The reserve is explicitly labelled as a price/yield proxy in the description so
    downstream UI cannot mistake it for a true guide price.
    """
    if not result or str(getattr(result, "source", "")).strip().lower() != "bidx1":
        return result
    for lot in getattr(result, "lots", []) or []:
        if getattr(lot, "guide_price", None) is not None:
            continue
        text = str(getattr(lot, "description", "") or "")
        if _GUIDE_RE.search(text):
            continue
        match = _RESERVE_RE.search(text)
        if not match:
            continue
        reserve = float(match.group(1).replace(",", ""))
        lot.guide_price = reserve
        note = f"Reserve £{reserve:,.0f} used as price/yield proxy; no guide price published."
        if "price/yield proxy" not in text.lower():
            lot.description = (text.rstrip(" .") + ". " + note).strip()
        lot.finalise()
    return result


def _collect_bidx1_with_reserve_proxy():
    return _apply_bidx1_reserve_proxy(bidx1_collector.collect())


def _lot_identity(item):
    """Stable identity for one auction lot even when the auctioneer exposes URL variants."""
    source = _normal_token(item.get("source"))
    day = str(item.get("auction_date") or "")[:10]
    lot = _normal_token(item.get("lot_number"))
    address = _normal_token(item.get("address"))
    if source and day and lot and lot not in {"lot tbc", "tbc"} and address:
        return ("lot", source, day, lot, address)
    if source and day and address:
        return ("address", source, day, address)
    return ("url", source, str(item.get("url") or "").strip())


def _record_score(item):
    """Prefer the richer duplicate instead of whichever URL happened to be seen last."""
    fields = (
        "image_url", "guide_price", "annual_rent", "tenure", "vat_status", "property_type",
        "occupation", "area_sqft", "area_sqm", "epc", "tenant", "lease_term",
        "legal_pack_url", "legal_pack_status", "description",
    )
    score = sum(1 for f in fields if item.get(f) not in (None, "", "UNKNOWN", "NOT FOUND"))
    score += min(len(str(item.get("description") or "")) // 500, 8)
    if item.get("image_url"): score += 4
    if item.get("guide_price") is not None: score += 2
    if item.get("annual_rent") is not None: score += 2
    return score


def _clean_site_chrome(text):
    value = pipeline.clean_description(str(text or ""))
    match = _WORKFLOW_BOILERPLATE.search(value)
    if not match:
        return value
    if match.start() >= 120:
        value = value[: match.start()].strip(" :-|")
    else:
        value = _WORKFLOW_BOILERPLATE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip(" :-|")


def _auction_day(item):
    raw = str(item.get("auction_date") or "").strip()[:10]
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _finalize_published_snapshot(path=Path("data/properties.json"), today=None):
    today = today or date.today()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    properties = list(data.get("properties") or [])
    archive = list(data.get("archive") or [])

    for item in properties + archive:
        item["description"] = _clean_site_chrome(item.get("description"))

    moved = []
    retained_archive = []
    for item in archive:
        status = _normal_status(item.get("status"))
        auction_day = _auction_day(item)
        if status in _PUBLISHED_TERMINAL and auction_day and auction_day >= today:
            item["status"] = status
            moved.append(item)
        else:
            retained_archive.append(item)

    by_key = {}
    duplicate_count = 0
    for item in properties + moved:
        key = _lot_identity(item)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            continue
        duplicate_count += 1
        if _record_score(item) > _record_score(existing):
            by_key[key] = item

    properties = list(by_key.values())
    properties.sort(
        key=lambda x: (
            str(x.get("auction_date") or ""),
            str(x.get("source") or ""),
            str(x.get("lot_number") or ""),
            str(x.get("address") or ""),
        ),
        reverse=True,
    )

    data["properties"] = properties
    data["archive"] = retained_archive
    integrity = data.setdefault("integrity", {})
    integrity["published_property_count"] = len(properties)
    integrity["historical_property_count"] = len(retained_archive)
    integrity["published_lifecycle_counts"] = dict(Counter(_normal_status(x.get("status")) for x in properties))
    integrity["terminal_rows_restored_to_publication"] = len(moved)
    integrity["duplicate_lot_rows_removed"] = duplicate_count

    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(moved)


def _install_replacements():
    upgraded = []
    for collector in pipeline.COLLECTORS:
        module = getattr(collector, "__module__", "")
        name = getattr(collector, "__name__", "")
        if module == "collectors.auction_house_regions":
            upgraded.append(_REPLACEMENTS.get(name, collector))
        elif module == "collectors.auction_house_london_v2" and name == "collect":
            upgraded.append(london.collect)
        elif module == "collectors.clive_emson" and name == "collect":
            upgraded.append(clive.collect)
        elif module == "collectors.symonds_sampson" and name == "collect":
            upgraded.append(symonds.collect)
        elif module == "collectors.future_property_auctions" and name == "collect":
            upgraded.append(future_property.collect)
        elif module == "collectors.bidx1" and name == "collect":
            upgraded.append(_collect_bidx1_with_reserve_proxy)
        else:
            upgraded.append(collector)
    pipeline.COLLECTORS = upgraded


def run():
    _install_replacements()
    pipeline.run()
    moved = _finalize_published_snapshot()
    print(f"PUBLICATION FINALIZER restored {moved} sold-prior/withdrawn/postponed lot(s) to the published board")


if __name__ == "__main__":
    run()
