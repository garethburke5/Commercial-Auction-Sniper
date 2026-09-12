from __future__ import annotations

"""Recover unresolved Savills lots by reading Common Crawl index files directly.

This deliberately bypasses index.commoncrawl.org.  It downloads the sparse
cluster index from data.commoncrawl.org, range-reads only the CDX gzip blocks
that cover the Savills auctions SURT hostname, extracts original Savills URLs,
opens their WARC captures, requires the exact unresolved Savills auction date,
and delegates final persistence to the existing strict first-party validator.
"""

import argparse
import bisect
import gzip
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    dates_in_text,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
    warc_html,
)
from savills_manifest_commoncrawl_frontier_recovery import (
    MANIFEST,
    STATIC_COLLECTIONS,
    canonical_live_candidate,
    oldest_unresolved_date,
)

DATA_HOST = "https://data.commoncrawl.org"
TARGET_SURT = "uk,co,savills,auctions)"
UA = "Commercial-Auction-Sniper/1.0 (+historical-research)"


def fetch_bytes(url: str, *, timeout: int = 45, start: int | None = None, length: int | None = None) -> bytes:
    headers = {"User-Agent": UA, "Accept-Encoding": "identity"}
    if start is not None and length is not None:
        headers["Range"] = f"bytes={start}-{start + length - 1}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cluster_entries(collection: str) -> list[tuple[str, str, int, int]]:
    url = f"{DATA_HOST}/cc-index/collections/{collection}/indexes/cluster.idx"
    raw = fetch_bytes(url, timeout=60)
    text = raw.decode("utf-8", errors="replace")
    out: list[tuple[str, str, int, int]] = []
    for line in text.splitlines():
        parts = line.split()
        file_i = next((i for i, p in enumerate(parts) if p.startswith("cdx-") and p.endswith(".gz")), None)
        if file_i is None or file_i + 2 >= len(parts):
            continue
        try:
            offset = int(parts[file_i + 1])
            length = int(parts[file_i + 2])
        except ValueError:
            continue
        # Everything before the cdx filename is the sparse CDX boundary key.
        key = " ".join(parts[:file_i])
        out.append((key, parts[file_i], offset, length))
    return out


def candidate_blocks(entries: list[tuple[str, str, int, int]], max_blocks: int) -> list[tuple[str, str, int, int]]:
    if not entries:
        return []
    keys = [e[0] for e in entries]
    # cluster.idx is ordered. Start at the block whose lower bound is immediately
    # before the Savills auctions SURT key, then inspect a bounded forward window.
    pos = max(0, bisect.bisect_right(keys, TARGET_SURT) - 1)
    picked = entries[max(0, pos - 2): min(len(entries), pos + max_blocks + 4)]
    return picked[: max_blocks + 6]


def decompress_member(blob: bytes) -> bytes:
    try:
        return gzip.decompress(blob)
    except Exception:
        # Range servers should return one gzip member. If a proxy returned extra
        # bytes, scan for the gzip magic and retry from there.
        idx = blob.find(b"\x1f\x8b")
        if idx >= 0:
            return gzip.decompress(blob[idx:])
        raise


def parse_cdx_block(blob: bytes) -> list[dict]:
    text = decompress_member(blob).decode("utf-8", errors="replace")
    rows: list[dict] = []
    for line in text.splitlines():
        if TARGET_SURT not in line:
            continue
        parts = line.split(" ", 2)
        if len(parts) != 3:
            continue
        surt, ts, payload = parts
        if not surt.startswith(TARGET_SURT):
            continue
        try:
            row = json.loads(payload)
        except json.JSONDecodeError:
            continue
        row.setdefault("timestamp", ts)
        url = str(row.get("url") or "")
        low = url.lower()
        if not (
            "auctions.savills.co.uk" in low
            and ("lotdetails" in low or "index.php" in low or "/auctions/" in low)
        ):
            continue
        rows.append(row)
    return rows


def collections_for_frontier(frontier: date) -> list[str]:
    out: list[str] = []
    for y in (frontier.year, frontier.year + 1, frontier.year - 1):
        for ident in STATIC_COLLECTIONS.get(y, []):
            if ident not in out:
                out.append(ident)
    return out


def run(max_blocks_per_collection: int = 12, max_rows: int = 500, max_warc_checks: int = 220, max_live_checks: int = 100) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    frontier = oldest_unresolved_date()
    at = now_iso()
    if not frontier:
        state["commoncrawl_direct_cdx_last_blocker"] = {
            "at": at,
            "route": "commoncrawl-direct-cluster-cdx-range-recovery",
            "message": "No unresolved date exists in the current Savills archive manifest.",
            "next_safe_route": "Rebuild the manifest from surviving Savills archive pages and continue from the earliest missing verified lot-level date.",
        }
        save_progress(progress)
        return 0

    errors: list[str] = []
    cluster_diag: list[dict] = []
    rows: list[dict] = []
    seen_capture: set[tuple] = set()
    collections = collections_for_frontier(frontier)

    for collection in collections:
        try:
            entries = cluster_entries(collection)
            blocks = candidate_blocks(entries, max_blocks_per_collection)
        except Exception as exc:
            errors.append(f"{collection} cluster.idx :: {type(exc).__name__}: {exc}")
            continue
        stat = {"collection": collection, "cluster_entries": len(entries), "blocks_attempted": 0, "rows_found": 0}
        for _key, filename, offset, length in blocks:
            if len(rows) >= max_rows:
                break
            stat["blocks_attempted"] += 1
            url = f"{DATA_HOST}/cc-index/collections/{collection}/indexes/{filename}"
            try:
                blob = fetch_bytes(url, timeout=45, start=offset, length=length)
                parsed = parse_cdx_block(blob)
            except Exception as exc:
                if len(errors) < 100:
                    errors.append(f"{collection} {filename}@{offset}+{length} :: {type(exc).__name__}: {exc}")
                continue
            stat["rows_found"] += len(parsed)
            for row in parsed:
                key = (row.get("url"), row.get("timestamp"), row.get("filename"), row.get("offset"))
                if key in seen_capture:
                    continue
                seen_capture.add(key)
                row["_cc_collection"] = collection
                rows.append(row)
                if len(rows) >= max_rows:
                    break
        cluster_diag.append(stat)
        if len(rows) >= max_rows:
            break

    def rank(row: dict):
        ts = str(row.get("timestamp") or "")
        y = int(ts[:4]) if len(ts) >= 4 and ts[:4].isdigit() else 9999
        return (abs(y - frontier.year), ts)

    rows.sort(key=rank)
    matching: list[dict] = []
    warc_checked = 0
    for row in rows:
        if warc_checked >= max_warc_checks:
            break
        warc_checked += 1
        try:
            body = warc_html(row, timeout=35)
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f"WARC {row.get('url')} :: {type(exc).__name__}: {exc}")
            continue
        if frontier not in dates_in_text(body):
            continue
        candidate = canonical_live_candidate(str(row.get("url") or ""))
        if candidate:
            matching.append({
                "candidate": candidate,
                "archived_url": row.get("url"),
                "timestamp": row.get("timestamp"),
                "collection": row.get("_cc_collection"),
            })

    unique: dict[str, dict] = {}
    for item in matching:
        unique.setdefault(item["candidate"], item)
    recovered, rejected = [], []
    live_checked = 0
    for candidate, item in unique.items():
        if live_checked >= max_live_checks:
            break
        live_checked += 1
        row, reason = recover_candidate(candidate, frontier, str(item.get("archived_url") or candidate))
        if row:
            row["archival_discovery_url"] = item.get("archived_url")
            row["commoncrawl_capture_timestamp"] = item.get("timestamp")
            row["commoncrawl_collection"] = item.get("collection")
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({"url": candidate, "archived_url": item.get("archived_url"), "reason": reason})

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        recovered_dates = [r.get("auction_date") for r in recovered if r.get("auction_date")]
        if recovered_dates:
            earliest = min(recovered_dates)
            state["earliest_date_reached"] = min(state.get("earliest_date_reached") or earliest, earliest)
            state["earliest_month_reached"] = min(state.get("earliest_month_reached") or earliest[:7], earliest[:7])

    diagnostic = {
        "at": at,
        "route": "commoncrawl-direct-cluster-cdx-range-recovery",
        "frontier_date": frontier.isoformat(),
        "collections_considered": collections,
        "cluster_diagnostics": cluster_diag,
        "cdx_rows_seen": len(rows),
        "warc_checked": warc_checked,
        "captures_with_exact_frontier_date": len(matching),
        "candidate_original_urls": len(unique),
        "live_checked": live_checked,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "matching_samples": matching[:30],
        "rejected_samples": rejected,
        "errors": errors[:100],
    }
    state["commoncrawl_direct_cdx_last_run"] = diagnostic
    state["last_discovery_mode"] = diagnostic["route"]
    if added:
        state.pop("commoncrawl_direct_cdx_last_blocker", None)
        state["status"] = "DISCOVERY EXPANSION"
    else:
        state["status"] = "LIVE ARCHIVE BLOCKED"
        state["commoncrawl_direct_cdx_last_blocker"] = {
            "at": at,
            "route": diagnostic["route"],
            "frontier_date": frontier.isoformat(),
            "message": "Direct Common Crawl cluster/CDX range recovery added no validated Savills event.",
            "cdx_rows_seen": len(rows),
            "warc_checked": warc_checked,
            "exact_date_captures": len(matching),
            "candidate_original_urls": len(unique),
            "next_safe_route": "If direct CDX exposed URLs but live pages no longer validate, persist archived Savills lot bodies as first-party evidence after extending the strict validator to accept immutable Common Crawl WARC evidence with exact lot URL and auction date. If no CDX rows were exposed, probe Savills-owned archived PDF/catalogue namespaces using the same direct index-file method.",
        }
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-blocks-per-collection", type=int, default=12)
    ap.add_argument("--max-rows", type=int, default=500)
    ap.add_argument("--max-warc-checks", type=int, default=220)
    ap.add_argument("--max-live-checks", type=int, default=100)
    args = ap.parse_args()
    run(args.max_blocks_per_collection, args.max_rows, args.max_warc_checks, args.max_live_checks)
