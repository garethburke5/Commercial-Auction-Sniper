from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
SOURCE_KEY = "Savills Auctions"
INDEX_BASE = "https://auctionradar.co.uk"


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
    y, mo = [int(x) for x in month.split("-")]
    # Never invent a day from month-only index evidence.
    return None


def _lot_no(text):
    m = re.search(r"\bLot\s+(\d{1,4}[A-Za-z]?)\b", text or "", re.I)
    return m.group(1) if m else None


def _first_party_link(doc):
    choices = []
    for a in doc.find_all("a", href=True):
        href = urljoin(INDEX_BASE, a.get("href") or "")
        host = (urlparse(href).hostname or "").lower()
        if host == "auctions.savills.co.uk" or host.endswith(".auctions.savills.co.uk"):
            if "/auctions/" in href or ("index.php" in href and "id=" in href):
                choices.append(href.split("#")[0])
    return choices[0] if choices else None


def discover_month(month, max_lot_pages=300):
    """Use AuctionRadar only as a candidate URL index; canonical evidence must be Savills."""
    index_url = f"{INDEX_BASE}/results/{month}"
    doc = soup(index_url, use_browser=False)
    lot_urls = []
    seen = set()
    for a in doc.find_all("a", href=True):
        href = urljoin(INDEX_BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"auctionradar\.co\.uk/lot/\d+$", href, re.I) or href in seen:
            continue
        card = norm(a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True))
        # Prefer obvious Savills cards; if markup is compact the lot page is the final check.
        if "savills" in card.lower():
            seen.add(href)
            lot_urls.append(href)
    # Some archive layouts do not put the auctioneer in the immediate anchor parent.
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
                # The surviving first-party page normally carries an exact sale date.
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
    # The modern archive route being exhausted is not historical completeness.
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    if state.get("status") == "CAUGHT UP":
        state["status"] = "DISCOVERY EXPANSION"
    cursor = state.get("legacy_discovery_cursor") or "2021-12"
    processed = []
    total_rows = 0
    total_failures = 0
    for month in month_sequence(cursor, floor_year=floor_year):
        rows, meta = recover_month(month, max_lot_pages=max_lot_pages)
        if rows:
            db = update_history_database(rows, path=HISTORY_PATH)
            total_rows += len(rows)
            state["last_history_event_count"] = len(db.get("auction_events") or [])
        total_failures += len(meta["failures"])
        processed.append({"month": month, **meta, "commercial_rows": len(rows)})
        state["legacy_discovery_cursor"] = previous_month(month)
        state["legacy_months_scanned"] = int(state.get("legacy_months_scanned") or 0) + 1
        state["legacy_candidate_lot_pages"] = int(state.get("legacy_candidate_lot_pages") or 0) + meta["savills_candidates"]
        state["legacy_surviving_first_party"] = int(state.get("legacy_surviving_first_party") or 0) + meta["surviving_first_party"]
        state["legacy_commercial_rows_captured"] = int(state.get("legacy_commercial_rows_captured") or 0) + len(rows)
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
            state["lots_captured"] = int(state.get("lots_captured") or 0) + len(rows)
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
