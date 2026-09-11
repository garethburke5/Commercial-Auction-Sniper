from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, _commoncrawl_collections, source_count

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"
CC_DATA = "https://data.commoncrawl.org/"
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "updated_at": None, "sources": {}}


def save_progress(progress: dict) -> None:
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


def request_text(url: str, timeout: int = 45) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain;q=0.9,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def frontier_dates(state: dict) -> set[date]:
    current = state.get("earliest_date_reached") or "9999-12-31"
    out: set[date] = set()
    for page in state.get("live_archive_unresolved") or []:
        for raw in page.get("dates") or []:
            if str(raw).startswith("2019-") and str(raw) < str(current):
                try:
                    out.add(date.fromisoformat(str(raw)))
                except ValueError:
                    pass
    return out


def seed_aids(state: dict) -> set[str]:
    aids: set[str] = set()
    probe = state.get("commoncrawl_legacy_last_probe") or {}
    items = list(probe.get("raw_url_samples") or [])
    items += [x.get("url") for x in (probe.get("rejected_samples") or []) if isinstance(x, dict)]
    for raw in items:
        if not raw:
            continue
        q = parse_qs(urlparse(str(raw)).query)
        for aid in q.get("aid") or []:
            if str(aid).isdigit():
                aids.add(str(aid))
    return aids


def index_rows(api: str, target: str, match_type: str = "prefix", timeout: int = 45) -> tuple[list[dict], str]:
    query = api + "?" + urlencode({"url": target, "matchType": match_type, "output": "json"})
    text = request_text(query, timeout=timeout)
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(row.get("status") or row.get("statuscode") or "")
        mime = str(row.get("mime") or row.get("mimetype") or "").lower()
        if status and status != "200":
            continue
        if mime and "html" not in mime:
            continue
        if row.get("url") and row.get("filename") and row.get("offset") is not None and row.get("length") is not None:
            rows.append(row)
    return rows, query


def warc_html(row: dict, timeout: int = 35) -> str:
    filename = str(row["filename"])
    offset = int(row["offset"])
    length = int(row["length"])
    req = Request(
        CC_DATA + filename,
        headers={
            "User-Agent": UA,
            "Range": f"bytes={offset}-{offset + length - 1}",
            "Accept-Encoding": "identity",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    text = raw.decode("utf-8", "replace")
    pos = text.lower().find("<!doctype")
    if pos < 0:
        pos = text.lower().find("<html")
    return text[pos:] if pos >= 0 else text


def dates_in_text(text: str) -> set[date]:
    clean = norm(re.sub(r"<[^>]+>", " ", text or ""))
    found: set[date] = set()
    pats = [
        re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", re.I),
        re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", re.I),
    ]
    for idx, pat in enumerate(pats):
        for m in pat.finditer(clean):
            try:
                if idx == 0:
                    d, mon, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
                else:
                    mon, d, y = m.group(1).lower(), int(m.group(2)), int(m.group(3))
                found.add(date(y, MONTHS[mon], d))
            except Exception:
                pass
    for m in re.finditer(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", clean):
        try:
            found.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    return found


def live_first_party(candidate: str, timeout: int = 20) -> str | None:
    req = Request(candidate, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as r:
            final = r.geturl()
            if getattr(r, "status", 200) >= 400:
                return None
    except Exception:
        return None
    p = urlparse(final)
    host = (p.hostname or "").lower()
    if host != "savills.co.uk" and not host.endswith(".savills.co.uk"):
        return None
    return urlunparse(p._replace(scheme="https", fragment=""))


def is_lot_specific_savills_url(url: str) -> bool:
    """Require an exact Savills auction lot route before historical persistence.

    Discovery providers may return generic Savills corporate/property pages. Those
    pages must never inherit the target auction date merely because their prose
    contains commercial-property words. Both surviving legacy PID routes and the
    current auction-slug/lot-id routes are accepted.
    """
    if not url:
        return False
    p = urlparse(str(url))
    if (p.hostname or "").lower() != "auctions.savills.co.uk":
        return False
    path = p.path or ""
    low = path.lower()
    q = parse_qs(p.query)
    if ("lotdetails" in low or "index.php" in low) and (
        q.get("pid") or (q.get("view") == ["commission"] and q.get("id"))
    ):
        return True
    if re.search(r"/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$", path, re.I):
        return True
    return False


def sale_price(text: str):
    for pat in (r"Hammer\s*Price\s*£\s*([\d,]+(?:\.\d+)?)", r"Sold(?:\s+Prior|\s+Post)?(?:\s+for)?\s*£\s*([\d,]+(?:\.\d+)?)"):
        m = re.search(pat, text or "", re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return None


def status_from_text(text: str) -> str:
    if re.search(r"\bwithdrawn(?:\s+prior)?\b", text or "", re.I):
        return "WITHDRAWN"
    if re.search(r"\bsold\s+prior\b", text or "", re.I):
        return "SOLD PRIOR"
    if re.search(r"\bsold\s+post\b", text or "", re.I):
        return "SOLD POST"
    if re.search(r"\bunsold\b|\bnot sold\b", text or "", re.I):
        return "UNSOLD"
    if re.search(r"\bhammer\s*price\b|\bsold\b", text or "", re.I):
        return "SOLD"
    return "ARCHIVED"


def recover_candidate(candidate: str, auction_day: date, discovery_url: str):
    live = live_first_party(candidate)
    if not live:
        return None, "no surviving Savills first-party page"
    if not is_lot_specific_savills_url(live):
        return None, "surviving Savills page is not lot-specific auction evidence"
    try:
        doc = soup(live, use_browser=False)
        main = doc.find("main") or doc
        text = norm(main.get_text(" ", strip=True))
        live_start, live_end = savills._auction_dates(text, live)
        live_day = live_end or live_start
        if live_day and live_day != auction_day:
            return None, f"live page date {live_day.isoformat()} conflicts with archived catalogue date {auction_day.isoformat()}"
        auction = {
            "start": auction_day,
            "end": auction_day,
            "catalogue": live,
            "label": f"Savills archived aid recovery {auction_day.isoformat()}",
        }
        lot = savills._detail(live, auction, source_commercial=False)
        if not lot:
            return None, "surviving live page is not classified commercial/mixed-use"
        row = lot.finalise().to_dict()
        row["url"] = live
        row["evidence_url"] = live
        row["result_page_url"] = live
        row["discovery_index_url"] = discovery_url
        row["sale_price"] = sale_price(text)
        row["status"] = status_from_text(text)
        return row, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run(year: int = 2019, max_live_checks: int = 180) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    state["status"] = "DISCOVERY EXPANSION"
    targets = frontier_dates(state)
    aids = seed_aids(state)
    errors: list[str] = []
    query_urls: list[str] = []
    capture_rows: list[dict] = []

    collections = _commoncrawl_collections(year)
    for ident, api in collections:
        try:
            rows, query = index_rows(api, "auctions.savills.co.uk/Auctions/LotList", "prefix", 45)
            query_urls.append(query)
            capture_rows.extend(rows)
            for row in rows:
                q = parse_qs(urlparse(str(row.get("url") or "")).query)
                for aid in q.get("aid") or []:
                    if str(aid).isdigit():
                        aids.add(str(aid))
        except Exception as exc:
            errors.append(f"{ident} LotList prefix :: {type(exc).__name__}: {exc}")

    rows_by_aid: dict[str, list[dict]] = {aid: [] for aid in aids}
    lot_urls_by_aid: dict[str, dict[str, str]] = {aid: {} for aid in aids}
    for row in capture_rows:
        original = str(row.get("url") or "")
        q = parse_qs(urlparse(original).query)
        aid = (q.get("aid") or [None])[0]
        if not aid or str(aid) not in rows_by_aid:
            continue
        aid = str(aid)
        rows_by_aid[aid].append(row)
        pid = (q.get("pid") or [None])[0]
        if pid:
            p = urlparse(original)
            live_candidate = urlunparse(p._replace(scheme="https", netloc=(p.hostname or "auctions.savills.co.uk").lower(), fragment=""))
            lot_urls_by_aid[aid].setdefault(live_candidate, str(row.get("url") or ""))

    aid_dates: dict[str, date] = {}
    aid_date_evidence: dict[str, dict] = {}
    for aid in sorted(aids, key=lambda x: int(x)):
        candidates = sorted(rows_by_aid.get(aid) or [], key=lambda r: str(r.get("timestamp") or ""), reverse=True)
        catalogue_only = [r for r in candidates if not parse_qs(urlparse(str(r.get("url") or "")).query).get("pid")]
        for row in (catalogue_only + candidates)[:8]:
            try:
                html = warc_html(row)
                matched = dates_in_text(html) & targets
                if len(matched) == 1:
                    d = next(iter(matched))
                    aid_dates[aid] = d
                    aid_date_evidence[aid] = {
                        "auction_date": d.isoformat(),
                        "archived_url": row.get("url"),
                        "capture_timestamp": row.get("timestamp"),
                        "warc_filename": row.get("filename"),
                    }
                    break
            except Exception as exc:
                if len(errors) < 80:
                    errors.append(f"aid {aid} capture :: {type(exc).__name__}: {exc}")

    recovered_rows = []
    rejected = []
    live_checks = 0
    for aid, auction_day in sorted(aid_dates.items(), key=lambda kv: kv[1]):
        for candidate, archived_original in lot_urls_by_aid.get(aid, {}).items():
            if live_checks >= max_live_checks:
                break
            live_checks += 1
            discovery = next((q for q in query_urls if q), archived_original)
            row, reason = recover_candidate(candidate, auction_day, discovery)
            if row:
                recovered_rows.append(row)
            elif len(rejected) < 80:
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
        dates = [r.get("auction_date") for r in recovered_rows if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
            month = earliest[:7]
            prev_month = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(prev_month, month) if prev_month else month

    diagnostic = {
        "at": now_iso(),
        "year": year,
        "route": "commoncrawl-warc-aid-to-date-to-live-savills",
        "frontier_dates": sorted(d.isoformat() for d in targets),
        "aids_seen": sorted(aids, key=lambda x: int(x)),
        "aid_dates": {k: v.isoformat() for k, v in aid_dates.items()},
        "aid_date_evidence": aid_date_evidence,
        "archive_capture_rows": len(capture_rows),
        "legacy_lot_urls": sum(len(x) for x in lot_urls_by_aid.values()),
        "live_checked": live_checks,
        "commercial_rows_seen": len(recovered_rows),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
        "query_urls": query_urls,
        "errors": errors[:80],
    }
    state["legacy_aid_capture_last_run"] = diagnostic
    state["last_discovery_mode"] = "commoncrawl-warc-aid-date-to-live-savills-first-party"
    if added == 0:
        state["legacy_aid_capture_last_blocker"] = {
            "at": diagnostic["at"],
            "message": "Legacy Savills aid/pid URLs are now recovered, but no older canonical event was persistable from this route.",
            "unmapped_aids": sorted(set(aids) - set(aid_dates), key=lambda x: int(x)),
            "mapped_aids": diagnostic["aid_dates"],
            "next_safe_route": "Use archived PastAuctions/Venue capture bodies to map any remaining aid IDs to exact first-party auction dates, then reuse the recovered pid inventory against live Savills pages.",
        }
    else:
        state.pop("legacy_aid_capture_last_blocker", None)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=180)
    args = ap.parse_args()
    run(args.year, args.max_live_checks)
