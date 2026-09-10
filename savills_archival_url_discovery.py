from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
SOURCE_KEY = "Savills Auctions"
SAVILLS_HOST = "auctions.savills.co.uk"
CDX = "https://web.archive.org/cdx/search/cdx"
CC_COLLECTIONS = "https://index.commoncrawl.org/collinfo.json"
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"
PATTERNS = (
    "https://auctions.savills.co.uk/auctions/*",
    "https://auctions.savills.co.uk/Auctions/LotDetails*",
    "https://auctions.savills.co.uk/component/bidding/*",
    "https://auctions.savills.co.uk/index.php?option=com_bidding*",
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


def source_count(db):
    return sum(1 for e in (db.get("auction_events") or []) if e.get("source") == SOURCE_KEY)


def _request_text(url, timeout=45):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _request_json(url, timeout=45):
    return json.loads(_request_text(url, timeout=timeout))


def _cdx_urls(pattern, snapshot_year, limit):
    params = {
        "url": pattern,
        "output": "json",
        "fl": "original,timestamp,statuscode,mimetype",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",
        "from": str(snapshot_year),
        "to": str(snapshot_year),
        "limit": str(limit),
    }
    url = CDX + "?" + urlencode(params, doseq=True)
    payload = _request_json(url)
    if not isinstance(payload, list) or len(payload) < 2:
        return [], url
    header = payload[0]
    try:
        oi = header.index("original")
    except ValueError:
        return [], url
    out = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) <= oi:
            continue
        original = str(row[oi]).strip()
        if original:
            out.append(original)
    return out, url


def _commoncrawl_collections(snapshot_year):
    """Return free Common Crawl indexes for the target year, newest first.

    This is URL discovery only.  A Common Crawl capture never becomes source evidence: every
    candidate must still resolve to a surviving live first-party Savills page before ingestion.
    """
    payload = _request_json(CC_COLLECTIONS)
    matches = []
    for row in payload if isinstance(payload, list) else []:
        ident = str(row.get("id") or "")
        api = str(row.get("cdx-api") or "")
        if str(snapshot_year) in ident and api.startswith("https://index.commoncrawl.org/"):
            matches.append((ident, api))
    return sorted(matches, reverse=True)


def _commoncrawl_urls(pattern, snapshot_year, limit):
    out = []
    query_urls = []
    errors = []
    for ident, api in _commoncrawl_collections(snapshot_year):
        params = {
            "url": pattern,
            "output": "json",
            "filter": ["status:200", "mime:text/html"],
            "collapse": "urlkey",
        }
        query_url = api + "?" + urlencode(params, doseq=True)
        query_urls.append(query_url)
        try:
            text = _request_text(query_url, timeout=45)
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                original = str(row.get("url") or "").strip()
                if original:
                    out.append(original)
                    if len(out) >= limit:
                        return out, query_urls, errors
        except Exception as exc:
            errors.append(f"{ident}: {type(exc).__name__}: {exc}")
    return out[:limit], query_urls, errors


def _normalise_candidate(url):
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.hostname or "").lower()
    if host != SAVILLS_HOST:
        return None
    path = p.path or "/"
    low = path.lower()
    if "/auctions/" in low:
        bits = [x for x in path.split("/") if x]
        if len(bits) < 3 or bits[0].lower() != "auctions" or not re.search(r"-\d{2,7}$", bits[-1]):
            return None
    elif "/component/bidding/" in low:
        bits = [x for x in path.split("/") if x]
        if len(bits) < 4 or not re.search(r"-\d{2,7}$", bits[-1]):
            return None
    elif "lotdetails" in low:
        if not (p.query and re.search(r"(?:^|&)(?:id|pid)=\d+", p.query, re.I)):
            return None
    elif low.endswith("/index.php"):
        q = dict(parse_qsl(p.query, keep_blank_values=True))
        joined = "&".join(f"{k}={v}" for k, v in q.items()).lower()
        if "com_bidding" not in joined or not any(k.lower() in {"id", "pid"} and str(v).isdigit() for k, v in q.items()):
            return None
    else:
        return None
    return urlunparse(p._replace(scheme="https", netloc=SAVILLS_HOST, fragment=""))


def _live_url(candidate, timeout=20):
    req = Request(candidate, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        final = r.geturl()
        if getattr(r, "status", 200) >= 400:
            return None
    p = urlparse(final)
    if (p.hostname or "").lower() != SAVILLS_HOST:
        return None
    return urlunparse(p._replace(scheme="https", fragment=""))


def _sale_price(text):
    pats = [
        r"Hammer\s*Price\s*£\s*([\d,]+(?:\.\d+)?)",
        r"Sold(?:\s+Prior|\s+Post)?(?:\s+for)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ]
    for pat in pats:
        m = re.search(pat, text or "", re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return None


def _status(text):
    t = text or ""
    if re.search(r"\bwithdrawn(?:\s+prior)?\b", t, re.I):
        return "WITHDRAWN"
    if re.search(r"\bsold\s+prior\b", t, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bsold\s+post\b", t, re.I):
        return "SOLD POST"
    if re.search(r"\bunsold\b|\bnot sold\b", t, re.I):
        return "UNSOLD"
    if re.search(r"\bhammer\s*price\b|\bsold\b", t, re.I):
        return "SOLD"
    return "ARCHIVED"


def recover_live(candidate, discovery_url):
    live = _live_url(candidate)
    if not live:
        return None, "no surviving Savills page"
    doc = soup(live, use_browser=False)
    main = doc.find("main") or doc
    text = norm(main.get_text(" ", strip=True))
    start, end = savills._auction_dates(text, live)
    auction_day = end or start
    if not auction_day or auction_day >= date.today():
        return None, "exact historical auction date unresolved from live Savills page"
    auction = {"start": auction_day, "end": auction_day, "catalogue": live, "label": f"Savills archival URL recovery {auction_day.isoformat()}"}
    lot = savills._detail(live, auction, source_commercial=False)
    if not lot:
        return None, "live page is not classified commercial/mixed-use"
    row = lot.finalise().to_dict()
    row["url"] = live
    row["evidence_url"] = live
    row["result_page_url"] = live
    row["discovery_index_url"] = discovery_url
    row["sale_price"] = _sale_price(text)
    row["status"] = _status(text)
    return row, None


def run(snapshot_years=1, start_year=2020, floor_year=2008, cdx_limit=1200, max_live_checks=240):
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"
    year = int(state.get("archival_url_snapshot_year_cursor") or start_year)
    years_done = []
    total_added = 0
    total_live = 0
    total_candidates = 0
    run_errors = []

    for _ in range(snapshot_years):
        if year < floor_year:
            state["archival_url_discovery_exhausted"] = True
            break
        discovered = {}
        query_urls = []
        year_errors = []
        route_counts = {"wayback": 0, "commoncrawl": 0}
        for pattern in PATTERNS:
            wayback_ok = False
            try:
                originals, query_url = _cdx_urls(pattern, year, cdx_limit)
                query_urls.append({"route": "wayback_cdx", "url": query_url})
                wayback_ok = True
                route_counts["wayback"] += len(originals)
                for original in originals:
                    candidate = _normalise_candidate(original)
                    if candidate:
                        discovered[candidate] = query_url
            except Exception as exc:
                year_errors.append(f"Wayback {pattern} :: {type(exc).__name__}: {exc}")

            # Common Crawl is an independent, free URL-index fallback.  Run it whenever Wayback
            # failed OR returned no URLs, which avoids a single archival provider becoming the
            # historical boundary.
            if (not wayback_ok) or route_counts["wayback"] == 0:
                try:
                    originals, cc_queries, cc_errors = _commoncrawl_urls(pattern, year, cdx_limit)
                    query_urls.extend({"route": "commoncrawl_index", "url": u} for u in cc_queries)
                    route_counts["commoncrawl"] += len(originals)
                    year_errors.extend(f"CommonCrawl {e}" for e in cc_errors)
                    discovery_url = cc_queries[0] if cc_queries else CC_COLLECTIONS
                    for original in originals:
                        candidate = _normalise_candidate(original)
                        if candidate:
                            discovered.setdefault(candidate, discovery_url)
                except Exception as exc:
                    year_errors.append(f"CommonCrawl {pattern} :: {type(exc).__name__}: {exc}")

        total_candidates += len(discovered)
        rows = []
        live_checked = 0
        rejected = 0
        for candidate, discovery_url in list(discovered.items())[:max_live_checks]:
            live_checked += 1
            try:
                row, reason = recover_live(candidate, discovery_url)
                if row:
                    rows.append(row)
                    total_live += 1
                else:
                    rejected += 1
            except Exception as exc:
                rejected += 1
                if len(year_errors) < 30:
                    year_errors.append(f"{candidate} :: {type(exc).__name__}: {exc}")
        added = 0
        if rows:
            before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
            before_n = source_count(before)
            db = update_history_database(rows, path=HISTORY_PATH)
            after_n = source_count(db)
            added = max(0, after_n - before_n)
            total_added += added
            state["lots_captured"] = after_n
            state["last_history_event_count"] = len(db.get("auction_events") or [])
            dates = [r.get("auction_date") for r in rows if r.get("auction_date")]
            if dates:
                earliest = min(dates)
                prev = state.get("earliest_date_reached")
                state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
                em = earliest[:7]
                prevm = state.get("earliest_month_reached")
                state["earliest_month_reached"] = min(prevm, em) if prevm else em
        years_done.append({
            "snapshot_year": year,
            "candidate_urls": len(discovered),
            "route_raw_url_counts": route_counts,
            "live_checked": live_checked,
            "commercial_rows_seen": len(rows),
            "canonical_events_added": added,
            "rejected_or_dead": rejected,
            "discovery_queries": query_urls,
            "errors": year_errors[:30],
        })
        run_errors.extend(year_errors)
        year -= 1
        state["archival_url_snapshot_year_cursor"] = year
        save_progress(progress)

    state["archival_url_last_run_at"] = now_iso()
    state["archival_url_years_scanned"] = int(state.get("archival_url_years_scanned") or 0) + len(years_done)
    state["archival_url_candidates_seen"] = int(state.get("archival_url_candidates_seen") or 0) + total_candidates
    state["archival_url_surviving_commercial_seen"] = int(state.get("archival_url_surviving_commercial_seen") or 0) + total_live
    state["archival_url_events_added"] = int(state.get("archival_url_events_added") or 0) + total_added
    state["archival_url_last_events_added"] = total_added
    state["archival_url_last_processed"] = years_done
    state["archival_url_last_error_count"] = len(run_errors)
    state["archival_url_routes"] = ["wayback_cdx", "commoncrawl_index", "live_savills_validation"]
    state["last_discovery_mode"] = "savills-multi-archive-index-to-live-first-party"
    if not total_candidates and years_done:
        state["archival_url_last_blocker"] = {
            "at": now_iso(),
            "snapshot_year": years_done[-1]["snapshot_year"],
            "message": "No candidate Savills lot URLs returned by either free archival index for this snapshot year; live first-party evidence requirement remains enforced.",
            "routes": years_done[-1]["discovery_queries"],
            "errors": years_done[-1]["errors"],
        }
    else:
        state.pop("archival_url_last_blocker", None)
    save_progress(progress)
    print(json.dumps({"source": SOURCE_KEY, "events_added": total_added, "years": years_done, "state": state}, indent=2, ensure_ascii=False))
    return total_added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-years", type=int, default=1)
    ap.add_argument("--start-year", type=int, default=2020)
    ap.add_argument("--floor-year", type=int, default=2008)
    ap.add_argument("--cdx-limit", type=int, default=1200)
    ap.add_argument("--max-live-checks", type=int, default=240)
    args = ap.parse_args()
    run(args.snapshot_years, args.start_year, args.floor_year, args.cdx_limit, args.max_live_checks)
