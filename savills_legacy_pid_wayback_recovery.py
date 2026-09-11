from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    dates_in_text,
    frontier_dates,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
)

UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def known_pid_urls(state: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    probe = state.get("commoncrawl_legacy_last_probe") or {}
    items = list(probe.get("raw_url_samples") or [])
    items += [x.get("url") for x in (probe.get("rejected_samples") or []) if isinstance(x, dict)]
    for raw in items:
        if not raw:
            continue
        q = parse_qs(urlparse(str(raw)).query)
        pid = (q.get("pid") or [None])[0]
        if not pid:
            continue
        aid = (q.get("aid") or [None])[0]
        rec = out.setdefault(str(pid), {"pid": str(pid), "aids": set(), "samples": []})
        if aid and str(aid).isdigit():
            rec["aids"].add(str(aid))
        if len(rec["samples"]) < 6:
            rec["samples"].append(str(raw))
    for rec in out.values():
        rec["aids"] = sorted(rec["aids"], key=lambda x: int(x))
    return out


def cdx_rows(target: str) -> tuple[list[dict], str]:
    # CDX is a distinct archival provider from Common Crawl. We ask only for exact known lot URLs.
    cdx = (
        "https://web.archive.org/cdx/search/cdx?"
        f"url={quote(target, safe='')}&output=json&filter=statuscode:200&filter=mimetype:text/html"
        "&fl=timestamp,original,digest&collapse=digest&from=2018&to=2020"
    )
    data = json.loads(fetch_text(cdx, timeout=25))
    if not isinstance(data, list) or len(data) < 2:
        return [], cdx
    header = data[0]
    rows = [dict(zip(header, row)) for row in data[1:] if isinstance(row, list)]
    return rows, cdx


def snapshot_text(timestamp: str, original: str) -> tuple[str, str]:
    snap = f"https://web.archive.org/web/{timestamp}id_/{original}"
    return fetch_text(snap, timeout=30), snap


def extract_aids(html: str) -> set[str]:
    return set(re.findall(r"(?:[?&](?:amp;)?aid=|aid%3d)(\d{2,8})\b", html or "", re.I))


def run(max_pids: int = 80, max_live_checks: int = 120) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"
    targets = frontier_dates(state)
    pid_map = known_pid_urls(state)

    errors: list[str] = []
    cdx_hits: list[dict] = []
    pid_dates: dict[str, date] = {}
    pid_date_evidence: dict[str, dict] = {}
    pid_aids: dict[str, set[str]] = {pid: set(rec.get("aids") or []) for pid, rec in pid_map.items()}

    # The earlier index recovery produced a bounded set of concrete legacy lot IDs. Work those
    # exact lots only; do not crawl Wayback or search unrelated Savills pages.
    for pid in list(sorted(pid_map))[:max_pids]:
        targets_for_pid = [
            f"http://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}",
            f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}",
        ]
        resolved = False
        for target in targets_for_pid:
            try:
                rows, cdx = cdx_rows(target)
            except Exception as exc:
                if len(errors) < 120:
                    errors.append(f"CDX {target} :: {type(exc).__name__}: {exc}")
                continue
            if rows:
                cdx_hits.append({"pid": pid, "target": target, "cdx": cdx, "captures": len(rows)})
            for row in sorted(rows, key=lambda r: str(r.get("timestamp") or ""), reverse=True)[:6]:
                ts = str(row.get("timestamp") or "")
                original = str(row.get("original") or target)
                try:
                    html, snapshot = snapshot_text(ts, original)
                except Exception as exc:
                    if len(errors) < 120:
                        errors.append(f"snapshot {pid} {ts} :: {type(exc).__name__}: {exc}")
                    continue
                pid_aids[pid].update(extract_aids(html))
                matched = dates_in_text(html) & targets
                if len(matched) == 1:
                    d = next(iter(matched))
                    pid_dates[pid] = d
                    pid_date_evidence[pid] = {
                        "auction_date": d.isoformat(),
                        "snapshot_url": snapshot,
                        "archived_original": original,
                        "timestamp": ts,
                        "aids": sorted(pid_aids[pid], key=lambda x: int(x)),
                    }
                    resolved = True
                    break
            if resolved:
                break

    recovered = []
    rejected = []
    live_checks = 0
    for pid, auction_day in sorted(pid_dates.items(), key=lambda kv: kv[1]):
        if live_checks >= max_live_checks:
            break
        live_checks += 1
        candidate = f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}"
        discovery = pid_date_evidence[pid].get("snapshot_url") or candidate
        row, reason = recover_candidate(candidate, auction_day, discovery)
        if row:
            # Keep the current Savills page as exact evidence; archival URL is discovery provenance only.
            row["archival_discovery_url"] = discovery
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({"pid": pid, "url": candidate, "reason": reason})

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        dates = [r.get("auction_date") for r in recovered if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
            em = earliest[:7]
            prevm = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(prevm, em) if prevm else em

    diagnostic = {
        "at": now_iso(),
        "route": "wayback-cdx-exact-legacy-pid-to-live-savills",
        "frontier_dates": sorted(d.isoformat() for d in targets),
        "known_pid_count": len(pid_map),
        "pids_checked": min(len(pid_map), max_pids),
        "cdx_hit_count": len(cdx_hits),
        "cdx_hit_samples": cdx_hits[:40],
        "pid_dates": {k: v.isoformat() for k, v in pid_dates.items()},
        "pid_date_evidence": pid_date_evidence,
        "pid_aids": {k: sorted(v, key=lambda x: int(x)) for k, v in pid_aids.items() if v},
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "errors": errors[:120],
    }
    state["legacy_pid_wayback_last_run"] = diagnostic
    state["last_discovery_mode"] = "wayback-cdx-exact-pid-to-live-savills-first-party"
    if added == 0:
        state["legacy_pid_wayback_last_blocker"] = {
            "at": diagnostic["at"],
            "message": "Common Crawl 2019 indexes were unavailable; exact known legacy Savills pid URLs were then queried through Wayback CDX but no older canonical Savills event was persistable.",
            "known_pid_count": diagnostic["known_pid_count"],
            "cdx_hit_count": diagnostic["cdx_hit_count"],
            "resolved_pid_dates": diagnostic["pid_dates"],
            "provider_error_samples": diagnostic["errors"][:25],
            "next_safe_route": "Use surviving Savills first-party archive dates plus public search-engine indexed snippets/PDF catalogue references to map legacy aid/pid IDs, then validate every recovered property against the surviving Savills first-party lot page before persistence.",
        }
    else:
        state.pop("legacy_pid_wayback_last_blocker", None)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pids", type=int, default=80)
    ap.add_argument("--max-live-checks", type=int, default=120)
    args = ap.parse_args()
    run(args.max_pids, args.max_live_checks)
