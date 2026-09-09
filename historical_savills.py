from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
ARCHIVE = savills.BASE + "/past-auctions/archive"
SOURCE_KEY = "Savills Auctions"


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


def _auction_id(href):
    m = re.search(r"/auctions/[^/]+-(\d+)$", (href or "").rstrip("/"), re.I)
    return m.group(1) if m else None


def _catalogue_anchors(doc):
    out = []
    for a in doc.find_all("a", href=True):
        href = urljoin(savills.BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if _auction_id(href):
            out.append((a, href))
    return out


def _archive_page(url):
    """Use cheap HTTP first; browser-render only when Savills returns an empty JS shell."""
    doc = soup(url, use_browser=False)
    anchors = _catalogue_anchors(doc)
    if anchors:
        return doc, anchors, "http"
    doc = soup(url, use_browser=True)
    return doc, _catalogue_anchors(doc), "browser"


def discover_past_auctions(max_pages=14):
    """Discover the complete currently-published Savills past-auction archive."""
    found = {}
    pages_scanned = 0
    browser_pages = 0
    empty_pages = 0
    for page in range(1, max_pages + 1):
        archive_url = ARCHIVE if page == 1 else f"{ARCHIVE}/page-{page}"
        doc, anchors, mode = _archive_page(archive_url)
        pages_scanned += 1
        browser_pages += int(mode == "browser")
        if not anchors:
            empty_pages += 1
            if page > 1:
                break
            continue
        for a, href in anchors:
            aid = _auction_id(href)
            card = savills.nearest_card(a, 2500) if hasattr(savills, "nearest_card") else norm(a.get_text(" ", strip=True))
            card = card or norm(a.get_text(" ", strip=True))
            start, end = savills._auction_dates(card, href)
            if not start:
                try:
                    cat = soup(href, use_browser=False)
                    title_node = cat.find("h1") or cat.find("title")
                    title = norm(title_node.get_text(" ", strip=True)) if title_node else ""
                    start, end = savills._auction_dates(title, href)
                    card = card or title
                except Exception:
                    pass
            if not start or not end or end >= date.today():
                continue
            found[aid] = {
                "auction_id": aid,
                "catalogue": href,
                "start": start,
                "end": end,
                "label": card,
                "month": start.strftime("%Y-%m"),
                "source_index_url": archive_url,
            }
    if not found:
        raise RuntimeError(
            f"Savills archive discovery returned zero dated past auctions after {pages_scanned} pages "
            f"({browser_pages} browser fallbacks); refusing false caught-up state"
        )
    auctions = sorted(found.values(), key=lambda x: (x["start"], int(x["auction_id"])), reverse=True)
    return auctions, {"pages_scanned": pages_scanned, "browser_pages": browser_pages, "empty_pages": empty_pages}


def _money(text):
    m = re.search(r"(?:Hammer\s*Price|Sold(?:\s+Prior|\s+Post)?(?:\s+for)?)\s*£\s*([\d,]+(?:\.\d+)?)", text or "", re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def _status(card, detail_text=""):
    text = norm(f"{card or ''} {detail_text or ''}")
    if re.search(r"\bwithdrawn(?:\s+prior)?\b", text, re.I):
        return "WITHDRAWN"
    if re.search(r"\bsold\s+prior\b", text, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bsold\s+post\b", text, re.I):
        return "SOLD POST"
    if re.search(r"\bunsold\b|\bnot sold\b", text, re.I):
        return "UNSOLD"
    if re.search(r"\bhammer\s*price\b|\bsold\b", text, re.I):
        return "SOLD"
    return "ARCHIVED"


def _canonical_evidence_url(href):
    """Keep the exact Savills listing path/query but normalize first-party HTTP links to HTTPS."""
    parsed = urlparse(href or "")
    host = (parsed.hostname or "").lower()
    if host != "savills.co.uk" and not host.endswith(".savills.co.uk"):
        raise RuntimeError(f"Refusing non-Savills historical evidence URL: {href}")
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"Refusing unsupported Savills evidence URL scheme: {href}")
    return urlunparse(parsed._replace(scheme="https", fragment=""))


def fetch_auction(auction):
    feed, targets = savills._discover_commercial_feed(auction)
    if not feed or not targets:
        raise RuntimeError("Savills commercial section could not be resolved from historical catalogue")
    rows = []
    failures = []
    for href, meta in targets.items():
        try:
            evidence_href = _canonical_evidence_url(href)
            lot = savills._detail(href, auction, source_commercial=True)
            if not lot:
                continue
            row = lot.finalise().to_dict()
            card = norm(str((meta or {}).get("card") or ""))
            row["status"] = _status(card, row.get("description"))
            row["sale_price"] = _money(card)
            row["source_id"] = urlparse(evidence_href).path.rstrip("/").split("-")[-1]
            row["url"] = evidence_href
            row["evidence_url"] = evidence_href
            row["result_page_url"] = _canonical_evidence_url(feed)
            rows.append(row)
        except Exception as exc:
            failures.append({"url": href, "error": f"{type(exc).__name__}: {exc}"})
    if failures:
        raise RuntimeError(f"{len(failures)} Savills detail pages failed; refusing partial auction persistence: {failures[:2]}")
    if not rows:
        raise RuntimeError(f"Savills commercial feed exposed {len(targets)} lots but zero rows were normalised")
    if len(rows) != len(targets):
        raise RuntimeError(f"Savills historical auction incomplete: discovered {len(targets)}, normalised {len(rows)}")
    return rows, len(targets), _canonical_evidence_url(feed)


def backfill(max_auctions=1, oldest_year=None):
    progress = load_progress()
    state = progress["sources"].setdefault(SOURCE_KEY, {
        "status": "NOT STARTED", "auctions_discovered": 0, "auctions_completed": 0,
        "lots_captured": 0, "earliest_month_reached": None, "completed_auction_ids": [], "failures": [],
    })
    auctions, discovery = discover_past_auctions()
    state["auctions_discovered"] = len(auctions)
    state["archive_pages_scanned"] = discovery["pages_scanned"]
    state["archive_browser_pages"] = discovery["browser_pages"]
    state["archive_empty_pages"] = discovery["empty_pages"]
    completed = set(str(x) for x in (state.get("completed_auction_ids") or []))
    selected = []
    for auction in auctions:
        if auction["auction_id"] in completed:
            continue
        if oldest_year and auction["start"].year < oldest_year:
            continue
        selected.append(auction)
        if len(selected) >= max_auctions:
            break
    state["status"] = "RUNNING" if selected else "CAUGHT UP"
    state["last_run_auctions_selected"] = len(selected)
    save_progress(progress)

    run_rows = 0
    run_failures = 0
    for auction in selected:
        state["last_attempt"] = {"auction_id": auction["auction_id"], "label": auction.get("label"), "catalogue_url": auction["catalogue"], "at": now_iso()}
        save_progress(progress)
        try:
            rows, expected, feed = fetch_auction(auction)
            db = update_history_database(rows, path=HISTORY_PATH)
            run_rows += len(rows)
            completed.add(auction["auction_id"])
            state["completed_auction_ids"] = sorted(completed, key=lambda x: int(x) if str(x).isdigit() else str(x))
            state["auctions_completed"] = len(completed)
            state["lots_captured"] = int(state.get("lots_captured") or 0) + len(rows)
            state["last_success_rows"] = len(rows)
            state["last_expected_lots"] = expected
            state["last_commercial_feed"] = feed
            state["last_history_event_count"] = len(db.get("auction_events") or [])
            state["last_discovery_mode"] = "savills-first-party-archive"
            month = auction.get("month")
            if month:
                previous = state.get("earliest_month_reached")
                state["earliest_month_reached"] = min(previous, month) if previous else month
            state["last_success"] = now_iso()
            state["status"] = "RUNNING"
            save_progress(progress)
        except Exception as exc:
            run_failures += 1
            failure = {"auction_id": auction["auction_id"], "catalogue_url": auction["catalogue"], "error": f"{type(exc).__name__}: {exc}", "at": now_iso()}
            state.setdefault("failures", []).append(failure)
            state["last_failure"] = failure
            state["status"] = "DEGRADED"
            save_progress(progress)

    remaining = [a for a in auctions if a["auction_id"] not in completed]
    if not remaining:
        state["status"] = "CAUGHT UP"
    elif run_failures:
        state["status"] = "DEGRADED"
    state["last_run_rows"] = run_rows
    state["last_run_failures"] = run_failures
    state["last_run"] = now_iso()
    save_progress(progress)
    return {"source": SOURCE_KEY, "rows": run_rows, "state": state}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-auctions", type=int, default=1)
    ap.add_argument("--oldest-year", type=int, default=None)
    args = ap.parse_args()
    result = backfill(max_auctions=args.max_auctions, oldest_year=args.oldest_year)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if result["state"].get("last_run_auctions_selected") and result.get("rows", 0) == 0:
        raise SystemExit("Savills backfill selected auctions but captured zero rows; refusing false success")
    if result["state"].get("last_run_failures"):
        raise SystemExit("Savills backfill had one or more auction failures; refusing partial success")


if __name__ == "__main__":
    main()
