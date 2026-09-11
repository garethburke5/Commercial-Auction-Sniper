from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import savills_legacy_aid_capture_recovery as legacy
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery_resilient import deterministic_collections

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))


def save_progress(progress: dict) -> None:
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


def known_aid_dates(state: dict) -> dict[str, date]:
    out: dict[str, date] = {}
    last = state.get("legacy_aid_capture_last_run") or {}
    for aid, raw in (last.get("aid_dates") or {}).items():
        try:
            out[str(aid)] = date.fromisoformat(str(raw))
        except ValueError:
            pass
    # The next unresolved Savills archive event after aid 1090 is 4 Nov 2019.
    # Do not assign an aid to it unless first-party/archive evidence does so.
    return out


def lot_links_from_catalogue_html(text: str, aid: str) -> list[str]:
    text = html_lib.unescape(text or "")
    found: list[str] = []
    seen: set[str] = set()
    patterns = [
        re.compile(r'''(?:href|url)\s*=\s*["']([^"']*LotDetails\?[^"']*pid=[^"'&#\s]+[^"']*)["']''', re.I),
        re.compile(r'''((?:https?://)?auctions\.savills\.co\.uk/Auctions/LotDetails\?[^\s"'<>]+pid=[^\s"'<>]+)''', re.I),
    ]
    for pat in patterns:
        for m in pat.finditer(text):
            raw = m.group(1).replace("&amp;", "&")
            candidate = urljoin("https://auctions.savills.co.uk/Auctions/", raw)
            q = parse_qs(urlparse(candidate).query)
            row_aid = (q.get("aid") or [None])[0]
            pid = (q.get("pid") or [None])[0]
            if row_aid and str(row_aid) != str(aid):
                continue
            if not pid:
                continue
            if candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    return found


def run(year: int = 2019, max_live_checks: int = 260) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"

    aid_dates = known_aid_dates(state)
    queries: list[str] = []
    capture_evidence: dict[str, list[dict]] = {}
    candidates: dict[str, list[str]] = {aid: [] for aid in aid_dates}
    errors: list[str] = []

    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        for ident, api in deterministic_collections(year):
            target = f"auctions.savills.co.uk/Auctions/LotList?aid={aid}"
            try:
                rows, query = legacy.index_rows(api, target, "exact", timeout=35)
                queries.append(query)
            except Exception as exc:
                if len(errors) < 80:
                    errors.append(f"{ident} aid={aid} index :: {type(exc).__name__}: {exc}")
                continue
            for row in rows[:6]:
                try:
                    body = legacy.warc_html(row, timeout=30)
                    links = lot_links_from_catalogue_html(body, aid)
                    if links:
                        capture_evidence.setdefault(aid, []).append({
                            "auction_date": auction_day.isoformat(),
                            "archived_catalogue_url": row.get("url"),
                            "capture_timestamp": row.get("timestamp"),
                            "warc_filename": row.get("filename"),
                            "lot_links_found": len(links),
                        })
                    for link in links:
                        if link not in candidates[aid]:
                            candidates[aid].append(link)
                except Exception as exc:
                    if len(errors) < 80:
                        errors.append(f"{ident} aid={aid} capture :: {type(exc).__name__}: {exc}")

    recovered_rows: list[dict] = []
    rejected: list[dict] = []
    live_checks = 0
    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        evidence_url = None
        evs = capture_evidence.get(aid) or []
        if evs:
            evidence_url = evs[0].get("archived_catalogue_url")
        for candidate in candidates.get(aid) or []:
            if live_checks >= max_live_checks:
                break
            live_checks += 1
            row, reason = legacy.recover_candidate(candidate, auction_day, evidence_url or candidate)
            if row:
                recovered_rows.append(row)
            elif len(rejected) < 100:
                rejected.append({"aid": aid, "url": candidate, "reason": reason})
        if live_checks >= max_live_checks:
            break

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered_rows:
        db = update_history_database(recovered_rows, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        dates = [str(r.get("auction_date")) for r in recovered_rows if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(str(prev), earliest) if prev else earliest
            month = earliest[:7]
            prev_month = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(str(prev_month), month) if prev_month else month

    diagnostic = {
        "at": now_iso(),
        "year": year,
        "route": "commoncrawl-warc-catalogue-html-lotdetails-links-to-live-savills",
        "aid_dates": {k: v.isoformat() for k, v in aid_dates.items()},
        "index_queries": queries[-40:],
        "capture_evidence": capture_evidence,
        "legacy_lot_links_found": sum(len(v) for v in candidates.values()),
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered_rows),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "errors": errors,
        "next_safe_route": "If archived catalogue bodies expose no LotDetails links, query exact legacy LotDetails URL prefixes by recovered aid across the deterministic 2019 Common Crawl indexes, then validate surviving first-party Savills pages before persistence.",
    }
    state["legacy_catalogue_capture_link_last_run"] = diagnostic
    if added:
        state["last_success"] = now_iso()
        state["last_discovery_mode"] = diagnostic["route"]
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=260)
    args = ap.parse_args()
    raise SystemExit(run(args.year, args.max_live_checks))
