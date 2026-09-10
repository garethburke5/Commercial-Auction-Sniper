from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import (
    CC_COLLECTIONS,
    SOURCE_KEY,
    _commoncrawl_collections,
    recover_live,
    source_count,
)

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"

# Historical Savills pages were not necessarily hosted on today's dedicated auction
# subdomain.  Query first-party Savills UK host families as domains, then apply strict
# auction-path filtering locally.  Common Crawl remains discovery evidence only: a
# candidate must still resolve to a live Savills first-party page before ingestion.
CC_HOSTS = (
    "auctions.savills.co.uk",
    "www.savills.co.uk",
    "savills.co.uk",
)
AUCTION_PATH_HINTS = (
    "/auctions/",
    "/auction/",
    "/property-auctions/",
    "/Auctions/LotDetails",
    "/component/bidding/",
    "/index.php",
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


def is_savills_uk_host(host: str) -> bool:
    host = (host or "").lower().split(":", 1)[0]
    return host == "savills.co.uk" or host.endswith(".savills.co.uk")


def looks_like_auction_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    if not is_savills_uk_host(p.hostname or ""):
        return False
    joined = (p.path or "") + ("?" + p.query if p.query else "")
    low = joined.lower()
    if not any(h.lower() in low for h in AUCTION_PATH_HINTS):
        return False
    # Reject obvious static assets and search/filter chrome.
    if re.search(r"\.(?:jpg|jpeg|png|gif|svg|css|js|ico|pdf)(?:$|\?)", low):
        return False
    return True


def normalise_candidate(url: str):
    """Preserve the discovered Savills UK host/path but canonicalise scheme/fragment."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    if not looks_like_auction_url(url):
        return None
    host = (p.hostname or "").lower()
    return urlunparse(p._replace(scheme="https", netloc=host, fragment=""))


def query_index_domain(api: str, host: str, limit: int):
    # Domain matching avoids relying on wildcard semantics that differ across old CDX
    # indexes.  Filtering to auction paths/status/mime happens client-side.
    query = api + "?" + urlencode({"url": host, "matchType": "domain", "output": "json"})
    out = []
    raw_seen = 0
    text = request_text(query)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_seen += 1
        status = str(row.get("status") or row.get("statuscode") or "")
        if status and status != "200":
            continue
        mime = str(row.get("mime") or row.get("mimetype") or "").lower()
        if mime and "html" not in mime:
            continue
        original = str(row.get("url") or row.get("original") or "").strip()
        if not original or not looks_like_auction_url(original):
            continue
        out.append(original)
        if len(out) >= limit:
            break
    return out, raw_seen, query


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
    filtered_count = 0
    samples = []

    try:
        collections = _commoncrawl_collections(year)
    except Exception as exc:
        collections = []
        errors.append(
            f"collection discovery {CC_COLLECTIONS} :: {type(exc).__name__}: {exc}"
        )

    if not collections:
        errors.append(f"No usable Common Crawl collection listed for {year} at {CC_COLLECTIONS}")

    for ident, api in collections:
        for host in CC_HOSTS:
            try:
                originals, raw_seen, query = query_index_domain(api, host, limit)
                queries.append({"collection": ident, "host": host, "url": query})
                raw_count += raw_seen
                filtered_count += len(originals)
                if len(samples) < 30:
                    samples.extend(originals[: 30 - len(samples)])
                for original in originals:
                    candidate = normalise_candidate(original)
                    if candidate:
                        candidates.setdefault(candidate, query)
            except Exception as exc:
                # A legacy index/host failure is diagnostic data, not a reason to discard
                # successful probes from other collections/hosts or abort publication.
                errors.append(f"{ident} {host} :: {type(exc).__name__}: {exc}")

    rows = []
    rejected = []
    for candidate, discovery_url in list(candidates.items())[:max_live_checks]:
        try:
            row, reason = recover_live(candidate, discovery_url)
            if row:
                rows.append(row)
            elif len(rejected) < 40:
                rejected.append({"url": candidate, "reason": reason})
        except Exception as exc:
            if len(rejected) < 40:
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
        "query_mode": "commoncrawl-domain-match-legacy-savills-hosts-client-filter",
        "collections": [x[0] for x in collections],
        "hosts_probed": list(CC_HOSTS),
        "raw_index_rows_seen": raw_count,
        "auction_path_urls_seen": filtered_count,
        "normalised_candidate_urls": len(candidates),
        "live_checked": min(len(candidates), max_live_checks),
        "commercial_rows_seen": len(rows),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "queries": queries,
        "raw_url_samples": samples,
        "rejected_samples": rejected,
        "errors": errors[:60],
    }
    state["commoncrawl_legacy_last_probe"] = diagnostic
    state["commoncrawl_legacy_last_run_at"] = diagnostic["at"]
    state["commoncrawl_legacy_events_added"] = int(state.get("commoncrawl_legacy_events_added") or 0) + added
    state["last_discovery_mode"] = "commoncrawl-domain-match-legacy-hosts-to-live-savills-first-party"
    if added == 0:
        state["commoncrawl_legacy_last_blocker"] = diagnostic
    else:
        state.pop("commoncrawl_legacy_last_blocker", None)
    save_progress(progress)

    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2013)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--max-live-checks", type=int, default=300)
    args = ap.parse_args()
    run(args.year, args.limit, args.max_live_checks)
