from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import (
    CC_COLLECTIONS,
    SAVILLS_HOST,
    SOURCE_KEY,
    _commoncrawl_collections,
    _normalise_candidate,
    recover_live,
    source_count,
)

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"
# Common Crawl's documented API examples query host/path values rather than scheme-qualified URLs.
CC_PATTERNS = (
    f"{SAVILLS_HOST}/*",
    f"{SAVILLS_HOST}/auctions/*",
    f"{SAVILLS_HOST}/Auctions/LotDetails*",
    f"{SAVILLS_HOST}/component/bidding/*",
    f"{SAVILLS_HOST}/index.php*",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_progress():
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "updated_at": None, "sources": {}}


def save_progress(progress):
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


def request_text(url, timeout=60):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def query_index(api, pattern, limit):
    # Keep the server query deliberately minimal for older indexes. Filtering happens locally.
    query = api + "?" + urlencode({"url": pattern, "output": "json"})
    out = []
    text = request_text(query)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("status") or row.get("statuscode") or "") != "200":
            continue
        mime = str(row.get("mime") or row.get("mimetype") or "").lower()
        if mime and "html" not in mime:
            continue
        u = str(row.get("url") or row.get("original") or "").strip()
        if u:
            out.append(u)
            if len(out) >= limit:
                break
    return out, query


def run(year: int, limit: int = 2000, max_live_checks: int = 300):
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"

    candidates = {}
    queries = []
    errors = []
    raw_count = 0
    samples = []

    collections = _commoncrawl_collections(year)
    if not collections:
        errors.append(f"No Common Crawl collection listed for {year} at {CC_COLLECTIONS}")

    for ident, api in collections:
        for pattern in CC_PATTERNS:
            try:
                originals, query = query_index(api, pattern, limit)
                queries.append({"collection": ident, "pattern": pattern, "url": query})
                raw_count += len(originals)
                if len(samples) < 20:
                    samples.extend(originals[: 20 - len(samples)])
                for original in originals:
                    candidate = _normalise_candidate(original)
                    if candidate:
                        candidates.setdefault(candidate, query)
            except Exception as exc:
                errors.append(f"{ident} {pattern} :: {type(exc).__name__}: {exc}")

    rows = []
    rejected = []
    for candidate, discovery_url in list(candidates.items())[:max_live_checks]:
        try:
            row, reason = recover_live(candidate, discovery_url)
            if row:
                rows.append(row)
            elif len(rejected) < 30:
                rejected.append({"url": candidate, "reason": reason})
        except Exception as exc:
            if len(rejected) < 30:
                rejected.append({"url": candidate, "reason": f"{type(exc).__name__}: {exc}"})

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if rows:
        db = update_history_database(rows, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        dates = [r.get("auction_date") for r in rows if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
            month = earliest[:7]
            prev_month = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(prev_month, month) if prev_month else month

    diagnostic = {
        "at": now_iso(),
        "snapshot_year": year,
        "query_mode": "commoncrawl-host-path-minimal-query-client-filter",
        "collections": [x[0] for x in collections],
        "raw_urls": raw_count,
        "normalised_candidate_urls": len(candidates),
        "live_checked": min(len(candidates), max_live_checks),
        "commercial_rows_seen": len(rows),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "queries": queries,
        "raw_url_samples": samples,
        "rejected_samples": rejected,
        "errors": errors[:40],
    }
    state["commoncrawl_legacy_last_probe"] = diagnostic
    state["commoncrawl_legacy_last_run_at"] = diagnostic["at"]
    state["commoncrawl_legacy_events_added"] = int(state.get("commoncrawl_legacy_events_added") or 0) + added
    state["last_discovery_mode"] = "commoncrawl-host-path-to-live-savills-first-party"
    if added == 0:
        state["commoncrawl_legacy_last_blocker"] = diagnostic
    else:
        state.pop("commoncrawl_legacy_last_blocker", None)
    save_progress(progress)

    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2012)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--max-live-checks", type=int, default=300)
    args = ap.parse_args()
    run(args.year, args.limit, args.max_live_checks)
