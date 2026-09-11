from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

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
    warc_html,
)
from savills_legacy_aid_exact_recovery import api_for, request_text

COLLECTION_IDS = (
    "CC-MAIN-2019-51", "CC-MAIN-2019-47", "CC-MAIN-2019-43", "CC-MAIN-2019-39",
    "CC-MAIN-2019-35", "CC-MAIN-2019-30", "CC-MAIN-2019-26", "CC-MAIN-2019-22",
    "CC-MAIN-2019-18", "CC-MAIN-2019-13", "CC-MAIN-2019-09", "CC-MAIN-2019-04",
)
# These IDs were directly observed in the 2019 Common Crawl Savills Venue index during the
# preceding frontier run. Keep a few immediately earlier IDs because the historical boundary
# can straddle catalogue migrations, but prioritise 1124-1131.
AIDS = tuple(str(x) for x in list(range(1124, 1132)) + [1092, 1091, 1090, 1089, 1086])


def query_one(ident: str, aid: str, endpoint: str, scheme: str):
    target = f"{scheme}://auctions.savills.co.uk/Auctions/{endpoint}?aid={aid}"
    query = api_for(ident) + "?" + urlencode({"url": target, "matchType": "exact", "output": "json"})
    text = request_text(query, timeout=10)
    rows=[]
    for line in text.splitlines():
        try:
            row=json.loads(line)
        except Exception:
            continue
        status=str(row.get("status") or row.get("statuscode") or "")
        mime=str(row.get("mime") or row.get("mimetype") or "").lower()
        if status and status != "200":
            continue
        if mime and "html" not in mime:
            continue
        if row.get("filename") and row.get("offset") is not None and row.get("length") is not None:
            rows.append(row)
    return ident, aid, endpoint, query, rows


def pid_candidates(html: str, aid: str) -> list[str]:
    pids=[]
    seen=set()
    for m in re.finditer(r"(?:[?&](?:amp;)?pid=|pid%3d)([0-9a-fA-F-]{6,64}|\d{2,12})", html or "", re.I):
        pid=m.group(1)
        if pid.lower() in seen:
            continue
        seen.add(pid.lower())
        pids.append(pid)
    out=[]
    for pid in pids:
        out.append(f"https://auctions.savills.co.uk/Auctions/LotList?aid={aid}&pid={pid}")
        out.append(f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}")
    return out


def run(max_live_checks: int = 220) -> int:
    progress=load_progress()
    state=progress.setdefault("sources",{}).setdefault(SOURCE_KEY,{})
    state["historically_complete"]=False
    state["discovery_exhausted"]=False
    state["status"]="DISCOVERY EXPANSION"
    targets=frontier_dates(state)

    jobs=[]
    for ident in COLLECTION_IDS:
        for aid in AIDS:
            for endpoint in ("Venue","LotList"):
                for scheme in ("http","https"):
                    jobs.append((ident,aid,endpoint,scheme))

    captures={aid:{"Venue":[],"LotList":[]} for aid in AIDS}
    errors=[]
    query_hits=[]
    with ThreadPoolExecutor(max_workers=24) as pool:
        future_map={pool.submit(query_one,*j):j for j in jobs}
        for fut in as_completed(future_map):
            ident,aid,endpoint,scheme=future_map[fut]
            try:
                _,_,_,query,rows=fut.result()
                if rows:
                    captures[aid][endpoint].extend(rows)
                    query_hits.append({"collection":ident,"aid":aid,"endpoint":endpoint,"scheme":scheme,"rows":len(rows),"query":query})
            except Exception as exc:
                if len(errors)<160:
                    errors.append(f"{ident} aid={aid} {endpoint} {scheme} :: {type(exc).__name__}: {exc}")

    aid_dates={}
    aid_evidence={}
    lot_candidates={aid:[] for aid in AIDS}
    capture_parse_errors=[]
    for aid in AIDS:
        rows=(captures[aid]["Venue"]+captures[aid]["LotList"])
        # Newest capture first, but cap duplicate WARC downloads.
        rows=sorted(rows,key=lambda r:str(r.get("timestamp") or ""),reverse=True)
        seen_capture=set()
        for row in rows:
            key=(row.get("filename"),row.get("offset"),row.get("length"))
            if key in seen_capture:
                continue
            seen_capture.add(key)
            if len(seen_capture)>10:
                break
            try:
                html=warc_html(row)
                matched=dates_in_text(html)&targets
                if aid not in aid_dates and len(matched)==1:
                    d=next(iter(matched))
                    aid_dates[aid]=d
                    aid_evidence[aid]={"auction_date":d.isoformat(),"archived_url":row.get("url"),"capture_timestamp":row.get("timestamp"),"warc_filename":row.get("filename")}
                if "lotlist" in str(row.get("url") or "").lower():
                    lot_candidates[aid].extend(pid_candidates(html,aid))
            except Exception as exc:
                if len(capture_parse_errors)<100:
                    capture_parse_errors.append(f"aid={aid} {row.get('url')} :: {type(exc).__name__}: {exc}")

    # Deduplicate while preserving order.
    for aid,urls in lot_candidates.items():
        lot_candidates[aid]=list(dict.fromkeys(urls))

    recovered=[]
    rejected=[]
    live_checks=0
    for aid,auction_day in sorted(aid_dates.items(),key=lambda kv:kv[1]):
        for candidate in lot_candidates.get(aid) or []:
            if live_checks>=max_live_checks:
                break
            live_checks+=1
            row,reason=recover_candidate(candidate,auction_day,aid_evidence[aid].get("archived_url") or candidate)
            if row:
                recovered.append(row)
            elif len(rejected)<100:
                rejected.append({"aid":aid,"url":candidate,"reason":reason})
        if live_checks>=max_live_checks:
            break

    before=json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events":[]}
    before_n=source_count(before)
    after_n=before_n
    added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY_PATH)
        after_n=source_count(db)
        added=max(0,after_n-before_n)
        state["lots_captured"]=after_n
        dates=[r.get("auction_date") for r in recovered if r.get("auction_date")]
        if dates:
            earliest=min(dates)
            prev=state.get("earliest_date_reached")
            state["earliest_date_reached"]=min(prev,earliest) if prev else earliest
            em=earliest[:7]
            prevm=state.get("earliest_month_reached")
            state["earliest_month_reached"]=min(prevm,em) if prevm else em

    diagnostic={
        "at":now_iso(),
        "route":"commoncrawl-fixed-collection-parallel-exact-venue-lotlist-warc",
        "frontier_dates":sorted(d.isoformat() for d in targets),
        "aids_probed":list(AIDS),
        "query_jobs":len(jobs),
        "query_hits":query_hits[:80],
        "aid_dates":{k:v.isoformat() for k,v in aid_dates.items()},
        "aid_date_evidence":aid_evidence,
        "lot_candidates_by_aid":{k:len(v) for k,v in lot_candidates.items()},
        "live_checked":live_checks,
        "commercial_rows_seen":len(recovered),
        "canonical_events_added":added,
        "savills_events_before":before_n,
        "savills_events_after":after_n,
        "query_errors":errors[:160],
        "capture_errors":capture_parse_errors[:100],
        "rejected_samples":rejected,
    }
    state["legacy_exact_parallel_last_run"]=diagnostic
    state["last_discovery_mode"]="commoncrawl-fixed-collection-parallel-exact-aid-warc-to-live-savills"
    if added==0:
        state["legacy_exact_parallel_last_blocker"]={
            "at":diagnostic["at"],
            "message":"Common Crawl broad 2019 prefixes returned 503/504. Fixed-collection exact Venue/LotList queries were executed against the known legacy Savills aid IDs but produced no persistable older canonical event.",
            "mapped_aids":diagnostic["aid_dates"],
            "lot_candidates_by_aid":diagnostic["lot_candidates_by_aid"],
            "query_hit_count":len(query_hits),
            "provider_error_samples":diagnostic["query_errors"][:25],
            "next_safe_route":"Query exact archived LotDetails captures for the already-known pid GUIDs, use archived body metadata to recover property/date context, then validate the surviving live Savills property page without any catalogue-prefix query.",
        }
    else:
        state.pop("legacy_exact_parallel_last_blocker",None)
    save_progress(progress)
    print(json.dumps(diagnostic,indent=2,ensure_ascii=False))
    return added


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--max-live-checks",type=int,default=220)
    args=ap.parse_args()
    run(args.max_live_checks)
