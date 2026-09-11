from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, _commoncrawl_collections, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    dates_in_text,
    frontier_dates,
    index_rows,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
    seed_aids,
    warc_html,
)


def aid_from_url(raw: str) -> str | None:
    q = parse_qs(urlparse(raw or "").query)
    aid = (q.get("aid") or [None])[0]
    return str(aid) if aid and str(aid).isdigit() else None


def live_candidate(raw: str) -> str:
    p = urlparse(raw)
    return urlunparse(p._replace(scheme="https", netloc=(p.hostname or "auctions.savills.co.uk").lower(), fragment=""))


def run(year: int = 2019, max_live_checks: int = 180) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"
    targets = frontier_dates(state)
    aids = seed_aids(state)
    prior = state.get("legacy_aid_capture_last_run") or {}
    aids.update(str(x) for x in (prior.get("aids_seen") or []) if str(x).isdigit())

    queries = []
    errors = []
    venue_rows = []
    past_rows = []
    lot_rows = []
    collections = _commoncrawl_collections(year)

    for ident, api in collections:
        for target, bucket in (
            ("auctions.savills.co.uk/Auctions/Venue", venue_rows),
            ("auctions.savills.co.uk/Auctions/PastAuctions", past_rows),
            ("auctions.savills.co.uk/Auctions/LotList", lot_rows),
        ):
            try:
                rows, query = index_rows(api, target, "prefix", 45)
                queries.append({"collection": ident, "target": target, "url": query})
                bucket.extend(rows)
                for row in rows:
                    aid = aid_from_url(str(row.get("url") or ""))
                    if aid:
                        aids.add(aid)
            except Exception as exc:
                errors.append(f"{ident} {target} :: {type(exc).__name__}: {exc}")

    aid_dates = {}
    evidence = {}

    # Venue pages are the strongest legacy route because the auction ID is explicit in the URL.
    for row in sorted(venue_rows, key=lambda r: str(r.get("timestamp") or ""), reverse=True):
        aid = aid_from_url(str(row.get("url") or ""))
        if not aid or aid not in aids or aid in aid_dates:
            continue
        try:
            matched = dates_in_text(warc_html(row)) & targets
            if len(matched) == 1:
                d = next(iter(matched))
                aid_dates[aid] = d
                evidence[aid] = {"route": "Venue", "auction_date": d.isoformat(), "archived_url": row.get("url"), "capture_timestamp": row.get("timestamp"), "warc_filename": row.get("filename")}
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f"Venue aid {aid} :: {type(exc).__name__}: {exc}")

    # Old PastAuctions captures can carry aid links next to their dates. Resolve only when a
    # single known frontier date occurs in a tight source window around that exact aid token.
    for row in sorted(past_rows, key=lambda r: str(r.get("timestamp") or ""), reverse=True)[:20]:
        try:
            html = warc_html(row)
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f"PastAuctions capture :: {type(exc).__name__}: {exc}")
            continue
        low = html.lower()
        for aid in sorted(aids, key=lambda x: int(x)):
            if aid in aid_dates:
                continue
            for m in re.finditer(rf"aid(?:=|%3d){re.escape(aid)}\b", low, re.I):
                window = html[max(0, m.start() - 1800): min(len(html), m.end() + 1800)]
                matched = dates_in_text(window) & targets
                if len(matched) == 1:
                    d = next(iter(matched))
                    aid_dates[aid] = d
                    evidence[aid] = {"route": "PastAuctions-window", "auction_date": d.isoformat(), "archived_url": row.get("url"), "capture_timestamp": row.get("timestamp"), "warc_filename": row.get("filename")}
                    break
            if aid in aid_dates:
                continue

    lot_urls = {aid: {} for aid in aids}
    for row in lot_rows:
        raw = str(row.get("url") or "")
        aid = aid_from_url(raw)
        if not aid or aid not in lot_urls:
            continue
        q = parse_qs(urlparse(raw).query)
        if (q.get("pid") or [None])[0]:
            lot_urls[aid].setdefault(live_candidate(raw), raw)

    recovered = []
    rejected = []
    live_checks = 0
    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        for candidate, archived_original in lot_urls.get(aid, {}).items():
            if live_checks >= max_live_checks:
                break
            live_checks += 1
            row, reason = recover_candidate(candidate, auction_day, archived_original)
            if row:
                recovered.append(row)
            elif len(rejected) < 80:
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
        "year": year,
        "route": "commoncrawl-warc-venue-pastauctions-aid-date-to-live-savills",
        "frontier_dates": sorted(d.isoformat() for d in targets),
        "aids_seen": sorted(aids, key=lambda x: int(x)),
        "aid_dates": {k: v.isoformat() for k, v in aid_dates.items()},
        "aid_date_evidence": evidence,
        "venue_capture_rows": len(venue_rows),
        "past_auction_capture_rows": len(past_rows),
        "lot_capture_rows": len(lot_rows),
        "legacy_lot_urls": sum(len(x) for x in lot_urls.values()),
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "queries": queries,
        "errors": errors[:100],
    }
    state["legacy_venue_capture_last_run"] = diagnostic
    state["last_discovery_mode"] = "commoncrawl-warc-venue-pastauctions-date-to-live-savills"
    if added == 0:
        state["legacy_venue_capture_last_blocker"] = {
            "at": diagnostic["at"],
            "message": "Archived LotList aid/pid inventory plus archived Venue/PastAuctions date recovery produced no persistable older live Savills event.",
            "mapped_aids": diagnostic["aid_dates"],
            "unmapped_aids": sorted(set(aids) - set(aid_dates), key=lambda x: int(x)),
            "exact_routes": [q["url"] for q in queries[-12:]],
            "next_safe_route": "Query archived LotDetails captures for pid-specific address/title evidence and join pid captures back to aid through LotList captures before live first-party validation.",
        }
    else:
        state.pop("legacy_venue_capture_last_blocker", None)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=180)
    args = ap.parse_args()
    run(args.year, args.max_live_checks)
