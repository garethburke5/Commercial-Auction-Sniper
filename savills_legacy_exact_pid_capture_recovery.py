from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    dates_in_text,
    frontier_dates,
    index_rows,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
    warc_html,
)
from savills_legacy_aid_capture_recovery_resilient import deterministic_collections

PID_RE = re.compile(
    r"https?://auctions\.savills\.co\.uk/Auctions/LotDetails\?pid=([0-9a-fA-F-]{36})",
    re.I,
)
AID_PID_RE = re.compile(
    r"https?://auctions\.savills\.co\.uk/Auctions/LotList\?aid=(\d+)&pid=([0-9a-fA-F-]{36})",
    re.I,
)


def all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from all_strings(k)
            yield from all_strings(v)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from all_strings(item)


def persisted_exact_pids(state: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return PID -> observed URLs and PID -> explicitly observed aid associations.

    This intentionally uses only strings already persisted in Savills progress/diagnostics.
    It does not enumerate or guess the PID namespace.
    """
    urls: dict[str, set[str]] = {}
    aids: dict[str, set[str]] = {}
    for text in all_strings(state):
        for m in PID_RE.finditer(text):
            pid = m.group(1).lower()
            urls.setdefault(pid, set()).add(m.group(0))
        for m in AID_PID_RE.finditer(text):
            aid, pid = m.group(1), m.group(2).lower()
            aids.setdefault(pid, set()).add(aid)
            urls.setdefault(pid, set()).add(
                f"http://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}"
            )
    return urls, aids


def known_aid_dates(state: dict) -> dict[str, date]:
    out: dict[str, date] = {}
    for key in (
        "legacy_aid_capture_last_run",
        "legacy_catalogue_capture_link_last_run",
        "legacy_exact_parallel_last_run",
    ):
        run = state.get(key) or {}
        for aid, raw in (run.get("aid_dates") or {}).items():
            try:
                out[str(aid)] = date.fromisoformat(str(raw))
            except ValueError:
                pass
    return out


def canonical_live_url(pid: str) -> str:
    return f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}"


def exact_rows(api: str, raw_url: str, timeout: int = 20) -> tuple[list[dict], str]:
    # Common Crawl's exact lookup is deterministic and bounded to a URL we already observed.
    query = api + "?" + urlencode({"url": raw_url, "matchType": "exact", "output": "json"})
    # Reuse the proven index parser; it also requires WARC coordinates and HTML status 200.
    rows, _ = index_rows(api, raw_url, "exact", timeout)
    return rows, query


def run(year: int = 2019, max_pids: int = 80, max_captures_per_pid: int = 4, max_live_checks: int = 120) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"

    targets = frontier_dates(state)
    pid_urls, pid_aids = persisted_exact_pids(state)
    aid_dates = known_aid_dates(state)
    collections = deterministic_collections(year)

    errors: list[str] = []
    capture_evidence: dict[str, list[dict]] = {}
    resolved_dates: dict[str, str] = {}
    date_sources: dict[str, str] = {}
    query_log: list[dict] = []

    # Only exact URLs already present in persisted evidence are queried. No broad/prefix scan.
    for pid in sorted(pid_urls)[:max_pids]:
        rows_for_pid: list[dict] = []
        observed_variants = set(pid_urls[pid])
        observed_variants.add(f"http://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}")
        observed_variants.add(f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}")
        for ident, api in collections:
            for raw_url in sorted(observed_variants):
                try:
                    rows, query = exact_rows(api, raw_url)
                    query_log.append({"collection": ident, "pid": pid, "url": raw_url, "rows": len(rows), "query": query})
                    rows_for_pid.extend(rows)
                except Exception as exc:
                    if len(errors) < 120:
                        errors.append(f"{ident} pid={pid} {raw_url} :: {type(exc).__name__}: {exc}")

        # De-duplicate captures, newest first, then fetch bodies individually.
        unique: dict[tuple, dict] = {}
        for row in rows_for_pid:
            key = (row.get("filename"), row.get("offset"), row.get("length"))
            unique[key] = row
        captures = sorted(unique.values(), key=lambda r: str(r.get("timestamp") or ""), reverse=True)
        for row in captures[:max_captures_per_pid]:
            try:
                html = warc_html(row)
                dates = dates_in_text(html)
                matched = dates & targets
                capture_evidence.setdefault(pid, []).append({
                    "archived_url": row.get("url"),
                    "capture_timestamp": row.get("timestamp"),
                    "warc_filename": row.get("filename"),
                    "frontier_dates_in_body": sorted(d.isoformat() for d in matched),
                })
                if len(matched) == 1:
                    d = next(iter(matched))
                    resolved_dates[pid] = d.isoformat()
                    date_sources[pid] = "archived LotDetails body"
                    break
            except Exception as exc:
                if len(errors) < 120:
                    errors.append(f"pid={pid} WARC body :: {type(exc).__name__}: {exc}")

        # If the archived body itself omitted the auction heading, an aid+pid pairing that was
        # already persisted is acceptable only when that aid has an independently recovered date.
        if pid not in resolved_dates:
            associated = {aid_dates[a] for a in pid_aids.get(pid, set()) if a in aid_dates}
            associated &= targets
            if len(associated) == 1:
                d = next(iter(associated))
                resolved_dates[pid] = d.isoformat()
                date_sources[pid] = "persisted exact aid+pid association plus independently recovered aid date"

    recovered: list[dict] = []
    rejected: list[dict] = []
    live_checks = 0
    for pid, raw_date in sorted(resolved_dates.items(), key=lambda kv: kv[1]):
        if live_checks >= max_live_checks:
            break
        live_checks += 1
        auction_day = date.fromisoformat(raw_date)
        archived_original = None
        evidence = capture_evidence.get(pid) or []
        if evidence:
            archived_original = str(evidence[0].get("archived_url") or "")
        if not archived_original:
            archived_original = next(iter(pid_urls.get(pid) or []), canonical_live_url(pid))
        row, reason = recover_candidate(canonical_live_url(pid), auction_day, archived_original)
        if row:
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({"pid": pid, "auction_date": raw_date, "url": canonical_live_url(pid), "reason": reason})

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        recovered_dates = [str(r.get("auction_date")) for r in recovered if r.get("auction_date")]
        if recovered_dates:
            earliest = min(recovered_dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(str(prev), earliest) if prev else earliest
            month = earliest[:7]
            prev_month = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(str(prev_month), month) if prev_month else month

    diagnostic = {
        "at": now_iso(),
        "year": year,
        "route": "commoncrawl-exact-persisted-pid-warc-to-live-savills",
        "frontier_dates": sorted(d.isoformat() for d in targets),
        "persisted_exact_pids": len(pid_urls),
        "pids_probed": min(len(pid_urls), max_pids),
        "query_hits": [q for q in query_log if q.get("rows")][:80],
        "pids_with_capture_evidence": len(capture_evidence),
        "resolved_pid_dates": resolved_dates,
        "resolved_date_sources": date_sources,
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "errors": errors,
        "next_safe_route": "If exact persisted PID WARC bodies do not resolve the remaining 2019 dates, query the already-persisted exact LotList?aid=<aid>&pid=<pid> URLs individually and fetch those WARC bodies; use only independently mapped aid dates and surviving first-party Savills lot pages for History V2 persistence.",
    }
    state["legacy_exact_pid_capture_last_run"] = diagnostic
    state["last_discovery_mode"] = diagnostic["route"]
    if added == 0:
        state["last_runtime_blocker"] = {
            "at": diagnostic["at"],
            "route": diagnostic["route"],
            "message": "Bounded aid-first LotDetails prefixes returned zero URLs. Exact PID-bearing Savills LotDetails URLs already persisted from Common Crawl evidence were therefore fetched individually; no validated older History V2 event was recovered in this pass.",
            "failing_live_legacy_routes": [canonical_live_url(pid) for pid in sorted(pid_urls)[:30]],
            "persisted_exact_pids": len(pid_urls),
            "pids_with_capture_evidence": len(capture_evidence),
            "resolved_pid_dates": resolved_dates,
            "repair": "savills_legacy_exact_pid_capture_recovery.py",
            "next_safe_route": diagnostic["next_safe_route"],
        }
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-pids", type=int, default=80)
    ap.add_argument("--max-captures-per-pid", type=int, default=4)
    ap.add_argument("--max-live-checks", type=int, default=120)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.max_pids, args.max_captures_per_pid, args.max_live_checks) >= 0 else 1)
