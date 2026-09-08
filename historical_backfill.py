from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen

from collectors.core import Lot, norm, parse_vat
from collectors.utils import soup
from collectors import allsop
from history_database import update_history_database

BASE = "https://www.allsop.co.uk"
ALLSOP_RESULTS_INDEX = BASE + "/auctions/all-past-auction-results/"
DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
API_PAGE_SIZE = 20

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_progress():
    if not PROGRESS_PATH.exists():
        return {"schema_version": 1, "updated_at": None, "sources": {}}
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        data.setdefault("schema_version", 1)
        data.setdefault("sources", {})
        return data
    except Exception:
        return {"schema_version": 1, "updated_at": None, "sources": {}}


def save_progress(progress):
    DATA.mkdir(exist_ok=True)
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


def _auction_month(label):
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", label or "", re.I)
    if not m:
        return None
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"


def _canonical_results_url(auction_id, page=1):
    # Allsop currently returns 404 for /property-search/?... but 200 for
    # /property-search?... . Construct the canonical route instead of trusting
    # historical href formatting from the archive index.
    return f"{BASE}/property-search?auction_id={auction_id}&page={int(page)}&view=list"


def discover_allsop_commercial_auctions():
    s = soup(ALLSOP_RESULTS_INDEX, use_browser=False)
    anchors = []
    in_commercial = False
    current_label = None
    for node in s.find_all(["h2", "h3", "h4", "h5", "h6", "li", "a", "div", "p"]):
        text = norm(node.get_text(" ", strip=True))
        if text == "Commercial Auctions":
            in_commercial = True
            continue
        if text == "Residential Auctions":
            in_commercial = False
            continue
        if not in_commercial:
            continue
        month = _auction_month(text)
        if month:
            current_label = text
        if node.name == "a" and node.get("href"):
            href = urljoin(BASE, node.get("href"))
            if "property-search" not in href or "auction_id=" not in href:
                continue
            qs = parse_qs(urlparse(href).query)
            auction_id = (qs.get("auction_id") or [None])[0]
            if not auction_id:
                continue
            label = current_label or text
            month_key = _auction_month(label)
            anchors.append({
                "auction_id": auction_id,
                "label": label,
                "month": month_key,
                "results_url": _canonical_results_url(auction_id),
                "source_index_url": ALLSOP_RESULTS_INDEX,
            })
    dedup = {}
    for item in anchors:
        dedup[item["auction_id"]] = item
    return sorted(dedup.values(), key=lambda x: x.get("month") or "", reverse=True)


def _api_json(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE + "/property-search",
    })
    with urlopen(req, timeout=35) as response:
        if response.status != 200:
            raise RuntimeError(f"Allsop API HTTP {response.status} for {url}")
        return json.loads(response.read().decode("utf-8"))


def _api_search_page(auction_id, page):
    url = f"{BASE}/api/search?auction_id={auction_id}&page={int(page)}&view=list&react"
    payload = _api_json(url)
    data = payload.get("data") or {}
    rows = data.get("results")
    total = data.get("total")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise RuntimeError(f"Unexpected Allsop search API contract on page {page}")
    return rows, total, url


def _float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _auction_date_from_api(value, fallback_month=None):
    try:
        # The API publishes auction_date as epoch milliseconds. UTC date matches
        # Allsop's visible catalogue date for midnight-local records.
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return f"{fallback_month}-01" if fallback_month else None


def _status_from_api(item):
    value = norm(str(item.get("lot_status") or item.get("lotStatus") or item.get("allsop_lotstatus") or ""))
    low = value.lower()
    if "sold prior" in low:
        return "SOLD PRIOR"
    if "sold" in low:
        return "SOLD"
    if "withdraw" in low:
        return "WITHDRAWN"
    if "postpon" in low:
        return "POSTPONED"
    if "unsold" in low or "not sold" in low:
        return "UNSOLD"
    return value.upper() if value else "ARCHIVED"


def _description_from_api(item):
    bits = []
    for key in ("property_byline", "main_byline", "allsop_propertybyline"):
        value = norm(str(item.get(key) or ""))
        if value and value not in bits:
            bits.append(value)
    features = item.get("features") or []
    if isinstance(features, list):
        bits.extend(norm(str(x)) for x in features if norm(str(x)))
    for key in ("live_addendum", "rent_notes"):
        value = norm(str(item.get(key) or ""))
        if value:
            bits.append(value)
    return norm(" ".join(bits))[:6500]


def _row_from_api(item, auction, page):
    if item.get("is_commercial") is False and str(item.get("catalogue_type") or "").lower() != "commercial":
        return None
    address = norm(str(item.get("full_address") or item.get("allsop_address") or ""))
    if not address:
        raise RuntimeError(f"Allsop lot {item.get('allsop_lotid') or item.get('reference')} has no published address")
    lot_id = norm(str(item.get("allsop_lotid") or ""))
    if not lot_id:
        raise RuntimeError(f"Allsop lot {item.get('reference')} has no stable lot id")
    lot_number_raw = item.get("lot_number") if item.get("lot_number") is not None else item.get("allsop_lotnumber")
    lot_number = f"Lot {lot_number_raw}" if lot_number_raw not in (None, "") else None
    description = _description_from_api(item)
    result_url = _canonical_results_url(auction["auction_id"], page=page)
    image_id = norm(str(item.get("image_file_id") or item.get("featured_image_file_id") or ""))
    image_url = f"{BASE}/api/image/{image_id}/600/450" if image_id else None
    annual_rent = _float(item.get("income"))
    if annual_rent is None:
        annual_rent = _float(item.get("current_rent_per_annum"))
    guide = _float(item.get("guide_price_lower"))
    if guide is None:
        guide = _float(item.get("website_price_lower"))
    property_type = norm(str(item.get("property_byline") or item.get("main_byline") or item.get("allsop_propertybyline") or "")) or None
    occupation = norm(str(item.get("property_tenancy") or item.get("allsop_propertytenancy") or "")) or None
    tenant = None
    raw_tenant = item.get("tenant")
    if isinstance(raw_tenant, str) and raw_tenant.strip():
        try:
            tenant_data = json.loads(raw_tenant)
            names = [norm(str(r.get("lessee") or "")) for r in (tenant_data.get("rows") or []) if norm(str(r.get("lessee") or ""))]
            tenant = "; ".join(dict.fromkeys(names)) or None
        except Exception:
            tenant = None
    lot = Lot(
        source=allsop.SOURCE,
        url=result_url,
        address=address,
        lot_number=lot_number,
        auction_date=_auction_date_from_api(item.get("auction_date"), auction.get("month")),
        image_url=image_url,
        guide_price=guide,
        annual_rent=annual_rent,
        gross_yield=_float(item.get("net_yield")) or _float(item.get("yield")),
        tenure=norm(str(item.get("property_tenure") or item.get("allsop_propertytenure") or "")) or None,
        vat_status=parse_vat(description),
        legal_pack_status="AVAILABLE" if item.get("legal_pack_approved_by") else "UNKNOWN",
        description=description,
        property_type=property_type,
        occupation=occupation,
        tenant=tenant,
        status=_status_from_api(item),
    ).finalise().to_dict()
    lot["sale_price"] = _float(item.get("sale_price"))
    lot["source_id"] = lot_id
    lot["result_page_url"] = result_url
    lot["evidence_url"] = result_url
    return lot


def _fetch_allsop_auction_api(auction):
    first_rows, total, _ = _api_search_page(auction["auction_id"], 1)
    if total <= 0:
        raise RuntimeError("Allsop API reports zero historical lots")
    pages = max(1, math.ceil(total / API_PAGE_SIZE))
    raw_rows = list(first_rows)
    for page in range(2, pages + 1):
        page_rows, page_total, _ = _api_search_page(auction["auction_id"], page)
        if page_total != total:
            raise RuntimeError(f"Allsop API total changed during pagination: {total} -> {page_total}")
        raw_rows.extend(page_rows)
    by_id = {}
    for item in raw_rows:
        lot_id = norm(str(item.get("allsop_lotid") or ""))
        if lot_id:
            by_id[lot_id] = item
    if len(by_id) != total:
        raise RuntimeError(f"Allsop API pagination incomplete: expected {total} unique lots, got {len(by_id)}")

    rows = []
    for item in by_id.values():
        # Determine the page only for the human-verifiable evidence URL. The
        # stable Allsop lot id is also stored as source_id.
        idx = raw_rows.index(item)
        page = (idx // API_PAGE_SIZE) + 1
        row = _row_from_api(item, auction, page)
        if row:
            rows.append(row)
    if not rows:
        raise RuntimeError(f"Allsop API returned {total} lots but zero commercial historical rows")
    return rows, total, pages


def backfill_allsop(max_auctions=6, oldest_year=None):
    progress = load_progress()
    state = progress["sources"].setdefault("Allsop Commercial", {
        "status": "NOT STARTED", "auctions_discovered": 0, "auctions_completed": 0,
        "lots_captured": 0, "earliest_month_reached": None, "completed_auction_ids": [], "failures": [],
    })
    auctions = discover_allsop_commercial_auctions()
    state["auctions_discovered"] = len(auctions)
    completed = set(state.get("completed_auction_ids") or [])
    selected = []
    for a in auctions:
        if a["auction_id"] in completed:
            continue
        if oldest_year and a.get("month") and int(a["month"][:4]) < oldest_year:
            continue
        selected.append(a)
        if len(selected) >= max_auctions:
            break
    state["status"] = "RUNNING" if selected else "CAUGHT UP"
    state["last_run_auctions_selected"] = len(selected)
    save_progress(progress)

    all_rows = []
    failed_this_run = 0
    for auction in selected:
        state["last_attempt"] = {"auction_id": auction["auction_id"], "label": auction.get("label"), "at": now_iso()}
        save_progress(progress)
        try:
            rows, expected_lots, pages = _fetch_allsop_auction_api(auction)
            update_history_database(rows, path=HISTORY_PATH)
            all_rows.extend(rows)
            completed.add(auction["auction_id"])
            state["completed_auction_ids"] = sorted(completed)
            state["auctions_completed"] = len(completed)
            state["lots_captured"] = int(state.get("lots_captured") or 0) + len(rows)
            state["last_success_rows"] = len(rows)
            state["last_expected_lots"] = expected_lots
            state["last_api_pages"] = pages
            state["last_discovery_mode"] = "allsop-json-api"
            if auction.get("month"):
                earliest = state.get("earliest_month_reached")
                state["earliest_month_reached"] = min(filter(None, [earliest, auction["month"]])) if earliest else auction["month"]
            state["last_success"] = now_iso()
            state["status"] = "RUNNING"
            save_progress(progress)
        except Exception as exc:
            failed_this_run += 1
            failures = state.setdefault("failures", [])
            failure = {"auction_id": auction["auction_id"], "label": auction.get("label"), "error": f"{type(exc).__name__}: {exc}", "at": now_iso()}
            failures.append(failure)
            state["last_failure"] = failure
            state["status"] = "DEGRADED"
            save_progress(progress)

    remaining = [a for a in auctions if a["auction_id"] not in completed]
    if not remaining:
        state["status"] = "CAUGHT UP"
    elif failed_this_run:
        state["status"] = "DEGRADED"
    state["last_run_rows"] = len(all_rows)
    state["last_run_failures"] = failed_this_run
    state["last_run"] = now_iso()
    save_progress(progress)
    return {"source": "Allsop Commercial", "rows": len(all_rows), "state": state}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="allsop", choices=["allsop"])
    ap.add_argument("--max-auctions", type=int, default=6)
    ap.add_argument("--oldest-year", type=int, default=None)
    args = ap.parse_args()
    result = backfill_allsop(max_auctions=args.max_auctions, oldest_year=args.oldest_year)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["state"].get("last_run_auctions_selected") and result.get("rows", 0) == 0:
        raise SystemExit("Historical backfill selected auctions but captured zero rows; refusing false success")
    if result["state"].get("last_run_failures"):
        raise SystemExit("Historical backfill had one or more auction failures; refusing partial success")


if __name__ == "__main__":
    main()
