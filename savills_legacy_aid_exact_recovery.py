from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
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
    seed_aids,
    warc_html,
)

COLLECTION_IDS = (
    "CC-MAIN-2019-51", "CC-MAIN-2019-47", "CC-MAIN-2019-43", "CC-MAIN-2019-39",
    "CC-MAIN-2019-35", "CC-MAIN-2019-30", "CC-MAIN-2019-26", "CC-MAIN-2019-22",
    "CC-MAIN-2019-18", "CC-MAIN-2019-13", "CC-MAIN-2019-09", "CC-MAIN-2019-04",
)
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"


def api_for(ident: str) -> str:
    return f"https://index.commoncrawl.org/{ident}-index"


def request_text(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def exact_rows(api: str, target: str, match_type: str = "exact") -> tuple[list[dict], str]:
    q = api + "?" + urlencode({"url": target, "matchType": match_type, "output": "json"})
    text = request_text(q)
    rows = []
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
        if row.get("url") and row.get("filename") and row.get("offset") is not None and row.get("length") is not None:
            rows.append(row)
    return rows, q


def variants(path_query: str) -> list[str]:
    return [
        f"http://auctions.savills.co.uk/{path_query}",
        f"https://auctions.savills.co.uk/{path_query}",
        f"auctions.savills.co.uk/{path_query}",
    ]


def live_candidate(raw: str) -> str:
    p = urlparse(raw)
    return urlunparse(p._replace(scheme="https", netloc=(p.hostname or "auctions.savills.co.uk").lower(), fragment=""))


def run(year: int = 2019, max_live_checks: int = 200) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"
    targets = frontier_dates(state)
    aids = seed_aids(state)
    for key in ("legacy_aid_capture_last_run", "legacy_venue_capture_last_run"):
        prior = state.get(key) or {}
        aids.update(str(x) for x in (prior.get("aids_seen") or []) if str(x).isdigit())
    # IDs already observed in the 2019 Common Crawl URL index during the preceding frontier run.
    aids.update({"1071","1072","1086","1089","1090","1091","1092","1124","1125","1126","1127","1128","1129","1130","1131"})

    errors = []
    queries = []
    capture_by_aid: dict[str, list[dict]] = {a: [] for a in aids}
    lot_by_aid: dict[str, dict[str, str]] = {a: {} for a in aids}

    # Exact aid queries are deliberately tiny. They avoid the broad LotList prefix scans that
    # returned 503/504 from every 2019 index in the prior production run.
    for ident in COLLECTION_IDS:
        api = api_for(ident)
        for aid in sorted(aids, key=int):
            if aid in capture_by_aid and len(capture_by_aid[aid]) >= 3 and lot_by_aid[aid]:
                continue
            for endpoint in (f"Auctions/Venue?aid={aid}", f"Auctions/LotList?aid={aid}"):
                for target in variants(endpoint):
                    try:
                        rows, query = exact_rows(api, target, "exact")
                        queries.append({"collection": ident, "aid": aid, "endpoint": endpoint.split("?")[0], "url": query, "rows": len(rows)})
                        capture_by_aid[aid].extend(rows)
                    except Exception as exc:
                        if len(errors) < 120:
                            errors.append(f"{ident} {target} exact :: {type(exc).__name__}: {exc}")
            # A query-prefix restricted to this single aid is still small enough to recover pid inventory.
            for target in variants(f"Auctions/LotList?aid={aid}&pid="):
                try:
                    rows, query = exact_rows(api, target, "prefix")
                    queries.append({"collection": ident, "aid": aid, "endpoint": "LotList aid+pid prefix", "url": query, "rows": len(rows)})
                    for row in rows:
                        raw = str(row.get("url") or "")
                        q = parse_qs(urlparse(raw).query)
                        if (q.get("pid") or [None])[0]:
                            lot_by_aid[aid].setdefault(live_candidate(raw), raw)
                except Exception as exc:
                    if len(errors) < 120:
                        errors.append(f"{ident} aid {aid} pid-prefix :: {type(exc).__name__}: {exc}")

    aid_dates = {}
    evidence = {}
    for aid in sorted(aids, key=int):
        for row in sorted(capture_by_aid.get(aid) or [], key=lambda r: str(r.get("timestamp") or ""), reverse=True)[:12]:
            try:
                matched = dates_in_text(warc_html(row)) & targets
                if len(matched) == 1:
                    d = next(iter(matched))
                    aid_dates[aid] = d
                    evidence[aid] = {
                        "auction_date": d.isoformat(),
                        "archived_url": row.get("url"),
                        "capture_timestamp": row.get("timestamp"),
                        "warc_filename": row.get("filename"),
                    }
                    break
            except Exception as exc:
                if len(errors) < 120:
                    errors.append(f"aid {aid} WARC :: {type(exc).__name__}: {exc}")

    # Retain any pid-bearing URLs previously seen even if exact-index pid prefix is temporarily unavailable.
    prior_probe = state.get("commoncrawl_legacy_last_probe") or {}
    prior_urls = list(prior_probe.get("raw_url_samples") or []) + [x.get("url") for x in (prior_probe.get("rejected_samples") or []) if isinstance(x, dict)]
    for raw in prior_urls:
        if not raw:
            continue
        q = parse_qs(urlparse(str(raw)).query)
        aid = (q.get("aid") or [None])[0]
        pid = (q.get("pid") or [None])[0]
        if aid and pid and str(aid) in lot_by_aid:
            lot_by_aid[str(aid)].setdefault(live_candidate(str(raw)), str(raw))

    recovered = []
    rejected = []
    live_checks = 0
    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        for candidate, archived_original in lot_by_aid.get(aid, {}).items():
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
        "route": "commoncrawl-fixed-collection-exact-aid-warc-to-live-savills",
        "frontier_dates": sorted(d.isoformat() for d in targets),
        "aids_seen": sorted(aids, key=int),
        "aid_dates": {k:v.isoformat() for k,v in aid_dates.items()},
        "aid_date_evidence": evidence,
        "capture_rows": sum(len(v) for v in capture_by_aid.values()),
        "legacy_lot_urls": sum(len(v) for v in lot_by_aid.values()),
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "query_count": len(queries),
        "successful_query_samples": [q for q in queries if q.get("rows")][:40],
        "rejected_samples": rejected,
        "errors": errors[:120],
    }
    state["legacy_aid_exact_last_run"] = diagnostic
    state["last_discovery_mode"] = "commoncrawl-fixed-2019-exact-aid-to-live-savills"
    if added == 0:
        state["legacy_aid_exact_last_blocker"] = {
            "at": diagnostic["at"],
            "message": "Broad Common Crawl prefix routes were unavailable (503/504); fixed-collection exact aid recovery also produced no persistable older event.",
            "mapped_aids": diagnostic["aid_dates"],
            "unmapped_aids": sorted(set(aids)-set(aid_dates), key=int),
            "capture_rows": diagnostic["capture_rows"],
            "legacy_lot_urls": diagnostic["legacy_lot_urls"],
            "provider_errors": diagnostic["errors"][:20],
            "next_safe_route": "Use exact Common Crawl LotDetails pid queries from the already-persisted legacy URL samples, recover archived title/address/date context, and join pid evidence back to aid without any broad index scan.",
        }
    else:
        state.pop("legacy_aid_exact_last_blocker", None)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=200)
    args=ap.parse_args()
    run(args.year, args.max_live_checks)
