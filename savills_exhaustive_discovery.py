from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
SOURCE_KEY = "Savills Auctions"
INDEX_BASE = "https://auctionradar.co.uk"
SAVILLS_HOST = "auctions.savills.co.uk"
ARCHIVE = f"https://{SAVILLS_HOST}/past-auctions/archive"
SITEMAP = f"https://{SAVILLS_HOST}/sitemap.xml"
UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"


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


def _source_event_count(db):
    return sum(1 for e in (db.get("auction_events") or []) if e.get("source") == SOURCE_KEY)


def _read_url(url, timeout=30):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def _first_party(url):
    host = (urlparse(url or "").hostname or "").lower()
    return host == SAVILLS_HOST or host.endswith("." + SAVILLS_HOST)


def month_sequence(start="2021-12", floor_year=2002):
    y, m = [int(x) for x in start.split("-")]
    while y >= floor_year:
        yield f"{y:04d}-{m:02d}"
        m -= 1
        if m == 0:
            y -= 1
            m = 12


def previous_month(value):
    y, m = [int(x) for x in value.split("-")]
    m -= 1
    if m == 0:
        y -= 1
        m = 12
    return f"{y:04d}-{m:02d}"


def _date_from_text(text):
    months = "January February March April May June July August September October November December"
    pat = rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({months.replace(' ', '|')})\s+(20\d{{2}})\b"
    out = []
    for m in re.finditer(pat, text or "", re.I):
        try:
            out.append(date(int(m.group(3)), savills.MONTHS[m.group(2).lower()], int(m.group(1))))
        except Exception:
            pass
    return min(out) if out else None


def scan_first_party_archive(max_pages=30):
    """Enumerate every surviving Savills archive page independent of catalogue links.

    Old archive cards can retain auction dates and results after their catalogue hrefs have
    disappeared.  This records a truthful first-party discovery boundary without pretending
    that the underlying lots have been recovered.
    """
    pages = []
    dates = []
    consecutive_empty = 0
    for page in range(1, max_pages + 1):
        url = ARCHIVE if page == 1 else f"{ARCHIVE}/page-{page}"
        try:
            doc = soup(url, use_browser=False)
            text = norm(doc.get_text(" ", strip=True))
        except Exception as exc:
            pages.append({"page": page, "url": url, "error": f"{type(exc).__name__}: {exc}"})
            consecutive_empty += 1
            if consecutive_empty >= 2 and page > 14:
                break
            continue
        page_dates = []
        months = "January|February|March|April|May|June|July|August|September|October|November|December"
        for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({months})\s+(20\d{{2}})\b", text, re.I):
            try:
                d = date(int(m.group(3)), savills.MONTHS[m.group(2).lower()], int(m.group(1)))
                if d < date.today():
                    page_dates.append(d)
            except Exception:
                pass
        # Month-labelled auctions sometimes expose the precise date elsewhere; this deliberately
        # stores only exact dates parsed from the first-party page.
        if page_dates:
            dates.extend(page_dates)
            consecutive_empty = 0
            pages.append({"page": page, "url": url, "auction_dates_found": len(set(page_dates)), "earliest": min(page_dates).isoformat(), "latest": max(page_dates).isoformat()})
        else:
            consecutive_empty += 1
            pages.append({"page": page, "url": url, "auction_dates_found": 0})
            if page >= 14 and consecutive_empty >= 2:
                break
    return pages, (min(dates) if dates else None), (max(dates) if dates else None)


def _xml_locs(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    return [n.text.strip() for n in root.iter() if n.tag.lower().endswith("loc") and n.text and n.text.strip()]


def discover_sitemap_urls(max_sitemaps=50):
    """Read Savills' public first-party sitemap/index recursively and return historical lot URLs."""
    queue = [SITEMAP]
    seen_maps = set()
    urls = set()
    failures = []
    while queue and len(seen_maps) < max_sitemaps:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        try:
            locs = _xml_locs(_read_url(sm))
        except Exception as exc:
            failures.append({"url": sm, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for loc in locs:
            if not _first_party(loc):
                continue
            low = loc.lower()
            if low.endswith(".xml") or "sitemap" in low:
                if loc not in seen_maps:
                    queue.append(loc)
                continue
            if "/auctions/" in low or "/component/bidding/" in low or ("index.php" in low and "option=com_bidding" in low):
                urls.add(loc.split("#")[0])
    return sorted(urls), {"sitemaps_scanned": len(seen_maps), "failures": failures}


def _auction_key(url):
    path = urlparse(url or "").path.rstrip("/")
    m = re.search(r"/(?:auctions|component/bidding)/([^/]+-\d+)(?:/|$)", path, re.I)
    return m.group(1).lower() if m else None


def recover_first_party_sitemap(max_urls=500, before_year=2023):
    """Recover surviving historical first-party lots directly from Savills' own sitemap.

    Sitemap URLs are evidence, not inferred facts: exact auction date still has to resolve from
    the surviving lot page.  Detail parsing/classification remains in the production Savills parser.
    """
    urls, meta = discover_sitemap_urls()
    candidates = []
    for u in urls:
        key = _auction_key(u)
        if not key:
            continue
        ym = re.search(r"\b(20\d{2})\b", key)
        if ym and int(ym.group(1)) >= before_year:
            continue
        # A catalogue root is useful discovery but not a property event.
        tail = urlparse(u).path.rstrip("/").split("/")[-1]
        if tail == key or re.match(r"^(?:page|quantity|sort-by|property_type)-", tail, re.I):
            continue
        candidates.append(u)
    candidates = candidates[:max_urls]
    rows = []
    failures = []
    exact_dates = []
    for href in candidates:
        try:
            doc = soup(href, use_browser=False)
            text = norm(doc.get_text(" ", strip=True))
            start, end = savills._auction_dates(text, href)
            auction_day = end or start or _date_from_text(text)
            if not auction_day or auction_day.year >= before_year:
                continue
            auction = {"start": auction_day, "end": auction_day, "catalogue": href, "label": f"Savills first-party sitemap recovery {auction_day.isoformat()}"}
            lot = savills._detail(href, auction, source_commercial=False)
            if not lot:
                continue
            row = lot.finalise().to_dict()
            row["url"] = href
            row["evidence_url"] = href
            row["result_page_url"] = href
            row["discovery_index_url"] = SITEMAP
            rows.append(row)
            exact_dates.append(auction_day)
        except Exception as exc:
            failures.append({"url": href, "error": f"{type(exc).__name__}: {exc}"})
    meta.update({"urls_discovered": len(urls), "historical_lot_candidates": len(candidates), "lot_failures": failures, "earliest_recovered_date": min(exact_dates).isoformat() if exact_dates else None})
    return rows, meta


def _auction_date(text, month):
    patterns = [
        r"Auction\s*Date\s*:?\s*(\d{1,2})\s+([A-Za-z]+)[, ]+(20\d{2})",
        r"(\d{1,2})\s+([A-Za-z]+)[, ]+(20\d{2})\s+Auction date",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", re.I)
        if not m:
            continue
        name = m.group(2).lower()
        if name in savills.MONTHS:
            try:
                return date(int(m.group(3)), savills.MONTHS[name], int(m.group(1)))
            except ValueError:
                pass
    return None


def _lot_no(text):
    m = re.search(r"\bLot\s+(\d{1,4}[A-Za-z]?)\b", text or "", re.I)
    return m.group(1) if m else None


def _first_party_link(doc):
    choices = []
    for a in doc.find_all("a", href=True):
        href = urljoin(INDEX_BASE, a.get("href") or "")
        if _first_party(href) and ("/auctions/" in href or "/component/bidding/" in href or ("index.php" in href and "id=" in href)):
            choices.append(href.split("#")[0])
    return choices[0] if choices else None


def discover_month(month, max_lot_pages=300):
    index_url = f"{INDEX_BASE}/results/{month}"
    doc = soup(index_url, use_browser=False)
    lot_urls = []
    seen = set()
    for a in doc.find_all("a", href=True):
        href = urljoin(INDEX_BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"auctionradar\.co\.uk/lot/\d+$", href, re.I) or href in seen:
            continue
        card = norm(a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True))
        if "savills" in card.lower():
            seen.add(href)
            lot_urls.append(href)
    if not lot_urls:
        for a in doc.find_all("a", href=True):
            href = urljoin(INDEX_BASE, a.get("href") or "").split("?")[0].rstrip("/")
            if re.search(r"auctionradar\.co\.uk/lot/\d+$", href, re.I) and href not in seen:
                seen.add(href)
                lot_urls.append(href)
                if len(lot_urls) >= max_lot_pages:
                    break
    return index_url, lot_urls[:max_lot_pages]


def recover_month(month, max_lot_pages=300):
    index_url, lot_urls = discover_month(month, max_lot_pages=max_lot_pages)
    rows = []
    candidates = 0
    surviving = 0
    failures = []
    for lot_url in lot_urls:
        try:
            doc = soup(lot_url, use_browser=False)
            text = norm(doc.get_text(" ", strip=True))
            if "savills" not in text.lower():
                continue
            candidates += 1
            evidence_url = _first_party_link(doc)
            if not evidence_url:
                continue
            surviving += 1
            auction_day = _auction_date(text, month)
            if not auction_day:
                sd = soup(evidence_url, use_browser=False)
                st = norm(sd.get_text(" ", strip=True))
                start, end = savills._auction_dates(st, evidence_url)
                auction_day = end or start
            if not auction_day:
                failures.append({"index_url": lot_url, "evidence_url": evidence_url, "error": "exact auction date unresolved"})
                continue
            auction = {"start": auction_day, "end": auction_day, "catalogue": evidence_url, "label": f"Recovered via public results index {lot_url}"}
            lot = savills._detail(evidence_url, auction, source_commercial=False)
            if not lot:
                continue
            row = lot.finalise().to_dict()
            idx_lot = _lot_no(text)
            if not row.get("lot_number") and idx_lot:
                row["lot_number"] = f"Lot {idx_lot}"
            row["url"] = evidence_url
            row["evidence_url"] = evidence_url
            row["discovery_index_url"] = lot_url
            row["result_page_url"] = index_url
            rows.append(row)
        except Exception as exc:
            failures.append({"index_url": lot_url, "error": f"{type(exc).__name__}: {exc}"})
    return rows, {"index_url": index_url, "lot_pages_scanned": len(lot_urls), "savills_candidates": candidates, "surviving_first_party": surviving, "failures": failures}


def run(months=2, floor_year=2002, max_lot_pages=300):
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    if state.get("status") == "CAUGHT UP":
        state["status"] = "DISCOVERY EXPANSION"

    # Route 1: exhaustively enumerate the surviving first-party archive itself.  This is run on
    # every expansion pass because its pagination can grow or old cards can be restored.
    archive_pages, archive_earliest, archive_latest = scan_first_party_archive()
    state["first_party_archive_pages_scanned"] = len(archive_pages)
    state["first_party_archive_scan"] = archive_pages
    state["first_party_archive_earliest_date"] = archive_earliest.isoformat() if archive_earliest else None
    state["first_party_archive_latest_date"] = archive_latest.isoformat() if archive_latest else None

    # Route 2: use Savills' own sitemap to discover surviving lot pages that the archive cards no
    # longer link.  This is stronger evidence than a third-party index and is tried first.
    sitemap_rows, sitemap_meta = recover_first_party_sitemap(max_urls=max_lot_pages * 2, before_year=2023)
    state["first_party_sitemap"] = sitemap_meta
    if sitemap_rows:
        before_db = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
        before_count = _source_event_count(before_db)
        db = update_history_database(sitemap_rows, path=HISTORY_PATH)
        after_count = _source_event_count(db)
        added = max(0, after_count - before_count)
        state["legacy_commercial_rows_captured"] = int(state.get("legacy_commercial_rows_captured") or 0) + added
        state["lots_captured"] = after_count
        state["last_history_event_count"] = len(db.get("auction_events") or [])
        dates = [r.get("auction_date") for r in sitemap_rows if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
            em = earliest[:7]
            prevm = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(prevm, em) if prevm else em
        state["last_first_party_sitemap_rows_seen"] = len(sitemap_rows)
        state["last_first_party_sitemap_events_added"] = added
    else:
        state["last_first_party_sitemap_rows_seen"] = 0
        state["last_first_party_sitemap_events_added"] = 0
    save_progress(progress)

    # Route 3: third-party public result index is discovery-only.  It may reveal surviving Savills
    # detail URLs omitted from the current first-party sitemap; only the Savills page is evidence.
    cursor = state.get("legacy_discovery_cursor") or "2021-12"
    processed = []
    total_rows = 0
    total_failures = 0
    for month in month_sequence(cursor, floor_year=floor_year):
        rows, meta = recover_month(month, max_lot_pages=max_lot_pages)
        if rows:
            before_db = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
            before_count = _source_event_count(before_db)
            db = update_history_database(rows, path=HISTORY_PATH)
            after_count = _source_event_count(db)
            added = max(0, after_count - before_count)
            total_rows += added
            state["last_history_event_count"] = len(db.get("auction_events") or [])
            state["lots_captured"] = after_count
        else:
            added = 0
        total_failures += len(meta["failures"])
        processed.append({"month": month, **meta, "commercial_rows_seen": len(rows), "canonical_events_added": added})
        state["legacy_discovery_cursor"] = previous_month(month)
        state["legacy_months_scanned"] = int(state.get("legacy_months_scanned") or 0) + 1
        state["legacy_candidate_lot_pages"] = int(state.get("legacy_candidate_lot_pages") or 0) + meta["savills_candidates"]
        state["legacy_surviving_first_party"] = int(state.get("legacy_surviving_first_party") or 0) + meta["surviving_first_party"]
        state["legacy_commercial_rows_captured"] = int(state.get("legacy_commercial_rows_captured") or 0) + added
        state["last_legacy_month"] = month
        state["last_legacy_index_url"] = meta["index_url"]
        state["last_legacy_run_at"] = now_iso()
        if rows:
            earliest = min((r.get("auction_date") for r in rows if r.get("auction_date")), default=None)
            if earliest:
                prev = state.get("earliest_date_reached")
                state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
                em = earliest[:7]
                prevm = state.get("earliest_month_reached")
                state["earliest_month_reached"] = min(prevm, em) if prevm else em
        save_progress(progress)
        if len(processed) >= months:
            break
    state["status"] = "DISCOVERY EXPANSION" if processed else "DISCOVERY EXHAUSTED"
    state["last_legacy_run_rows"] = total_rows
    state["last_legacy_run_failures"] = total_failures
    state["last_legacy_processed"] = processed
    if processed and int(processed[-1]["month"][:4]) <= floor_year:
        state["discovery_exhausted"] = True
        state["status"] = "DISCOVERY EXHAUSTED"
    # Even when every known route is exhausted this flag stays false unless separately proven.
    state["historically_complete"] = False
    save_progress(progress)
    print(json.dumps({"source": SOURCE_KEY, "rows": total_rows, "processed": processed, "state": state}, indent=2, ensure_ascii=False, default=str))
    return total_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=2)
    ap.add_argument("--floor-year", type=int, default=2002)
    ap.add_argument("--max-lot-pages", type=int, default=300)
    args = ap.parse_args()
    run(months=args.months, floor_year=args.floor_year, max_lot_pages=args.max_lot_pages)


if __name__ == "__main__":
    main()
