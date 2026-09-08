from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from collectors.core import Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from collectors.utils import soup, legal_pack
from collectors import allsop
from history_database import update_history_database

BASE = "https://www.allsop.co.uk"
ALLSOP_RESULTS_INDEX = BASE + "/auctions/all-past-auction-results/"
DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"

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
                "results_url": href,
                "source_index_url": ALLSOP_RESULTS_INDEX,
            })
    dedup = {}
    for item in anchors:
        dedup[item["auction_id"]] = item
    return sorted(dedup.values(), key=lambda x: x.get("month") or "", reverse=True)


def _sold_price(text):
    text = norm(text)
    patterns = (
        r"\bSold(?:\s+Prior)?(?:\s+for|\s+at)?\s*£\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bSale Price\s*£\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bResult\s*£\s*([\d,]+(?:\.\d{1,2})?)",
    )
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _status_from_text(text):
    t = norm(text)
    if re.search(r"\bsold\s*prior\b", t, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bsold\b", t, re.I):
        return "SOLD"
    if re.search(r"\bwithdrawn(?:\s+prior)?\b", t, re.I):
        return "WITHDRAWN"
    if re.search(r"\bpostponed\b", t, re.I):
        return "POSTPONED"
    if re.search(r"\bunsold\b|\bnot sold\b", t, re.I):
        return "UNSOLD"
    return "ARCHIVED"


def _hydrate_allsop_historical(url, card, fallback_date=None, result_page_url=None):
    try:
        s = soup(url, use_browser=False)
    except Exception:
        try:
            s = soup(url, use_browser=True)
        except Exception:
            return None
    lot_number, address, main = allsop._main_identity(s)
    if not address:
        return None
    text = norm(main.get_text(" ", strip=True))
    combined = norm(card + " " + text)
    if not allsop._detail_is_target(combined):
        return None
    auction_date = allsop._exact_auction_date(text, fallback_date)
    if not auction_date and fallback_date:
        auction_date = fallback_date
    status = _status_from_text(combined)
    image = allsop._allsop_image(main, url)
    lp_url, lp_status = legal_pack(s, url)
    rent = parse_rent(combined)
    guide = parse_guide(combined)
    title = norm((main.find("h1") or s.find("h1")).get_text(" ", strip=True)) if (main.find("h1") or s.find("h1")) else None
    lot = Lot(
        source=allsop.SOURCE,
        url=url,
        address=address,
        lot_number=lot_number,
        auction_date=auction_date,
        image_url=image,
        guide_price=guide,
        annual_rent=rent,
        tenure=parse_tenure(combined),
        vat_status=parse_vat(combined),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        description=combined[:6500],
        property_type=title[:180] if title else None,
        status=status,
    ).finalise().to_dict()
    lot["sale_price"] = _sold_price(combined)
    lot["result_page_url"] = result_page_url
    lot["evidence_url"] = url
    return lot


def _discover_allsop_result_lots(results_url):
    """Discover lot links from a historical results page.

    Allsop's property-search results are JS-rendered. A normal HTTP response can
    therefore be a valid 200 page with zero lot cards. Try the cheap static path
    first, but require actual lot links; if none are present, render the page in
    Chromium and extract again.
    """
    found = {}
    static_error = None
    try:
        rs = soup(results_url, use_browser=False)
        allsop._extract_targets(rs, found, include_all_auction_lots=True)
    except Exception as exc:
        static_error = exc
    if found:
        return found, "static"

    browser_found = {}
    try:
        rs = soup(results_url, use_browser=True)
        allsop._extract_targets(rs, browser_found, include_all_auction_lots=True)
    except Exception as exc:
        detail = f"static={type(static_error).__name__}: {static_error}; " if static_error else ""
        raise RuntimeError(f"Allsop historical results could not be rendered ({detail}browser={type(exc).__name__}: {exc})") from exc
    if not browser_found:
        raise RuntimeError("Allsop historical results rendered but contained zero lot links")
    return browser_found, "browser"


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
            found, discovery_mode = _discover_allsop_result_lots(auction["results_url"])
            fallback = f"{auction['month']}-01" if auction.get("month") else None
            rows = []
            for href, meta in found.items():
                row = _hydrate_allsop_historical(
                    href, meta.get("card") or "", meta.get("auction_date") or fallback,
                    result_page_url=auction["results_url"],
                )
                if row:
                    rows.append(row)
            if not rows:
                raise RuntimeError(f"Allsop auction yielded zero historical rows from {len(found)} discovered lot links")

            update_history_database(rows, path=HISTORY_PATH)
            all_rows.extend(rows)
            completed.add(auction["auction_id"])
            state["completed_auction_ids"] = sorted(completed)
            state["auctions_completed"] = len(completed)
            state["lots_captured"] = int(state.get("lots_captured") or 0) + len(rows)
            state["last_success_rows"] = len(rows)
            state["last_discovery_mode"] = discovery_mode
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
    if args.source == "allsop":
        result = backfill_allsop(max_auctions=args.max_auctions, oldest_year=args.oldest_year)
    else:
        raise SystemExit("unsupported source")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["state"].get("last_run_auctions_selected") and result.get("rows", 0) == 0:
        raise SystemExit("Historical backfill selected auctions but captured zero rows; refusing false success")


if __name__ == "__main__":
    main()
