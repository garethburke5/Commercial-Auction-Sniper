from __future__ import annotations

import argparse
import json
from datetime import date
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
)
from savills_legacy_aid_capture_recovery_resilient import deterministic_collections
from savills_legacy_aid_exact_recovery import request_text


def known_aid_dates(state: dict) -> dict[str, date]:
    out: dict[str, date] = {}
    for key in ("legacy_aid_capture_last_run", "legacy_catalogue_capture_link_last_run"):
        run = state.get(key) or {}
        for aid, raw in (run.get("aid_dates") or {}).items():
            try:
                out[str(aid)] = date.fromisoformat(str(raw))
            except ValueError:
                pass
    return out


def rows_for(api: str, target: str, timeout: int = 20) -> tuple[list[dict], str]:
    query = api + "?" + urlencode({"url": target, "matchType": "prefix", "output": "json"})
    text = request_text(query, timeout=timeout)
    rows: list[dict] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        status = str(row.get("status") or row.get("statuscode") or "")
        mime = str(row.get("mime") or row.get("mimetype") or "").lower()
        if status and status != "200":
            continue
        if mime and "html" not in mime:
            continue
        if row.get("url"):
            rows.append(row)
    return rows, query


def live_candidate(raw: str) -> str:
    p = urlparse(raw)
    return urlunparse(p._replace(scheme="https", netloc="auctions.savills.co.uk", fragment=""))


def run(year: int = 2019, max_live_checks: int = 260) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"

    aid_dates = known_aid_dates(state)
    candidates: dict[str, dict[str, str]] = {aid: {} for aid in aid_dates}
    query_log: list[dict] = []
    errors: list[str] = []

    # This route is intentionally different from the failed LotList-body parser: query the
    # Common Crawl URL index directly for the bounded legacy LotDetails namespace for each
    # already-date-mapped aid. It avoids a broad /Auctions/ scan and never guesses a PID.
    for aid in sorted(aid_dates, key=int):
        prefixes = []
        for scheme in ("http", "https"):
            for path in ("Auctions/LotDetails", "auctions/LotDetails", "Auctions/lotdetails"):
                prefixes.extend([
                    f"{scheme}://auctions.savills.co.uk/{path}?aid={aid}",
                    f"{scheme}://auctions.savills.co.uk/{path}?aid={aid}&pid=",
                ])
        for ident, api in deterministic_collections(year):
            for target in prefixes:
                try:
                    rows, query = rows_for(api, target)
                    query_log.append({"collection": ident, "aid": aid, "target": target, "rows": len(rows), "query": query})
                except Exception as exc:
                    if len(errors) < 120:
                        errors.append(f"{ident} aid={aid} {target} :: {type(exc).__name__}: {exc}")
                    continue
                for row in rows:
                    raw = str(row.get("url") or "")
                    parsed = urlparse(raw)
                    qs = parse_qs(parsed.query)
                    row_aid = (qs.get("aid") or [None])[0]
                    pid = (qs.get("pid") or [None])[0]
                    if row_aid and str(row_aid) != aid:
                        continue
                    if not pid:
                        continue
                    candidates[aid].setdefault(live_candidate(raw), raw)

    recovered: list[dict] = []
    rejected: list[dict] = []
    live_checks = 0
    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        for candidate, archived_original in candidates.get(aid, {}).items():
            if live_checks >= max_live_checks:
                break
            live_checks += 1
            row, reason = recover_candidate(candidate, auction_day, archived_original)
            if row:
                recovered.append(row)
            elif len(rejected) < 100:
                rejected.append({"aid": aid, "url": candidate, "reason": reason})
        if live_checks >= max_live_checks:
            break

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
        "route": "commoncrawl-bounded-lotdetails-aid-prefix-to-live-savills",
        "aid_dates": {k: v.isoformat() for k, v in aid_dates.items()},
        "query_count": len(query_log),
        "query_hits": [q for q in query_log if q.get("rows")][:80],
        "legacy_lotdetails_urls_by_aid": {k: len(v) for k, v in candidates.items()},
        "legacy_lotdetails_urls": sum(len(v) for v in candidates.values()),
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "errors": errors,
        "next_safe_route": "If aid-first LotDetails prefixes are empty, enumerate only exact PID-bearing LotDetails URLs already observed in persisted Common Crawl samples/captures and fetch their archived bodies individually; do not return to broad catalogue scans.",
    }
    state["legacy_lotdetails_prefix_last_run"] = diagnostic
    state["last_discovery_mode"] = diagnostic["route"]
    if added == 0:
        state["last_runtime_blocker"] = {
            "at": diagnostic["at"],
            "route": diagnostic["route"],
            "message": "Archived LotList WARC bodies exposed zero PID links; bounded direct LotDetails prefixes were therefore attacked by already-mapped legacy aid without guessing property facts.",
            "failing_live_legacy_routes": [f"https://auctions.savills.co.uk/Auctions/LotList?aid={aid}" for aid in sorted(aid_dates, key=int)],
            "direct_lotdetails_urls_found": diagnostic["legacy_lotdetails_urls"],
            "repair": "savills_legacy_lotdetails_prefix_recovery.py",
            "next_safe_route": diagnostic["next_safe_route"],
        }
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=260)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.max_live_checks) >= 0 else 1)
