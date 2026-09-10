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

CC_HOSTS = (
    "auctions.savills.co.uk",
    "www.savills.co.uk",
    "savills.co.uk",
)

# Prefixes deliberately target legacy first-party auction applications.  Domain-wide
# queries against the 2013 indexes can return tens of thousands of Savills rows and
# time out at the index gateway before any auction URLs are returned.
CC_PREFIXES = (
    "/auctions/",
    "/auction/",
    "/property-auctions/",
    "/Auctions/",
    "/component/bidding/",
    "/index.php",
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
    if re.search(r"\.(?:jpg|jpeg|png|gif|svg|css|js|ico|pdf)(?:$|\?)", low):
        return False
    return True


def normalise_candidate(url: str):
    try:
        p = urlparse(url)
    except Exception:
        return None
    if not looks_like_auction_url(url):
        return None
    host = (p.hostname or "").lower()
    return urlunparse(p._replace(scheme="https", netloc=host, fragment=""))


def _parse_index_rows(text: str, limit: int):
    out = []
    raw_seen = 0
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
        if original and looks_like_auction_url(original):
            out.append(original)
            if len(out) >= limit:
                break
    return out, raw_seen


def query_index_prefix(api: str, host: str, prefix: str, limit: int):
    target = host + prefix
    query = api + "?" + urlencode({"url": target, "matchType": "prefix", "output": "json"})
    text = request_text(query, timeout=45)
    out, raw_seen = _parse_index_rows(text, limit)
    return out, raw_seen, query


def query_index_domain(api: str, host: str, limit: int):
    query = api + "?" + urlencode({"url": host, "matchType": "domain", "output": "json"})
    text = request_text(query, timeout=60)
    out, raw_seen = _parse_index_rows(text, limit)
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
        errors.append(f"collection discovery {CC_COLLECTIONS} :: {type(exc).__name__}: {exc}")

    if not collections:
        errors.append(f"No exact Common Crawl collection listed for {year} at {CC_COLLECTIONS}")

    for ident, api in collections:
        collection_hits = 0
        # First use compact prefix routes.  This is the primary repair for legacy 2013
        # domain queries which previously returned 504 before useful rows were emitted.
        for host in CC_HOSTS:
            for prefix in CC_PREFIXES:
                try:
                    originals, raw_seen, query = query_index_prefix(api, host, prefix, limit)
                    queries.append({"collection": ident, "host": host, "prefix": prefix, "match_type": "prefix", "url": query})
                    raw_count += raw_seen
                    filtered_count += len(originals)
                    collection_hits += len(originals)
                    if len(samples) < 30:
                        samples.extend(originals[: 30 - len(samples)])
                    for original in originals:
                        candidate = normalise_candidate(original)
                        if candidate:
                            candidates.setdefault(candidate, query)
                except Exception as exc:
                    errors.append(f"{ident} {host}{prefix} prefix :: {type(exc).__name__}: {exc}")

        # Only fall back to broad domain matching when every compact prefix was empty.
        # A failure here is diagnostic and cannot erase successful prefix results.
        if collection_hits == 0:
            for host in CC_HOSTS:
                try:
                    originals, raw_seen, query = query_index_domain(api, host, limit)
                    queries.append({"collection": ident, "host": host, "match_type": "domain-fallback", "url": query})
                    raw_count += raw_seen
                    filtered_count += len(originals)
                    if len(samples) < 30:
                        samples.extend(originals[: 30 - len(samples)])
                    for original in originals:
                        candidate = normalise_candidate(original)
                        if candidate:
                            candidates.setdefault(candidate, query)
                except Exception as exc:
                    errors.append(f"{ident} {host} domain fallback :: {type(exc).__name__}: {exc}")

    rows = []
    rejected = []
    for candidate, discovery_url in list(candidates.items())[:max_live_checks]:
        try:
            row, reason = recover_live(candidate, discovery_url)
            if row:
                rows.append(row)
            elif len(rejected) < 60:
                rejected.append({"url": candidate, "reason": reason})
        except Exception as exc:
            if len(rejected) < 60:
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
        "query_mode": "commoncrawl-exact-year-prefix-routes-with-domain-fallback",
        "collections": [x[0] for x in collections],
        "hosts_probed": list(CC_HOSTS),
        "prefixes_probed": list(CC_PREFIXES),
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
        "errors": errors[:100],
    }
    state["commoncrawl_legacy_last_probe"] = diagnostic
    state["commoncrawl_legacy_last_run_at"] = diagnostic["at"]
    state["commoncrawl_legacy_events_added"] = int(state.get("commoncrawl_legacy_events_added") or 0) + added
    state["commoncrawl_legacy_priority_year"] = year
    state["commoncrawl_legacy_exact_collections"] = [x[0] for x in collections]
    state["last_discovery_mode"] = "commoncrawl-exact-year-prefix-to-live-savills-first-party"
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
