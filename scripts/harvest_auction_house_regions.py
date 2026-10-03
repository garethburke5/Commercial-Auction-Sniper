"""Bank dedicated Auction House regional online-results archives.

These pages overlap the National aggregator but can retain older rows. Stable
redirect IDs and the exact regional auctioneer name make that overlap safe: an
already-banked appearance is preserved unchanged and only unseen IDs are added.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.auctionhouse.co.uk"
LOT_RE = re.compile(r"https?://online\.auctionhouse\.co\.uk/lot/redirect/(\d+)", re.I)
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$")
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)

REGIONS = (
    ("wales", "Auction House Wales", "auction-house-wales"),
    ("nottsandderby", "Auction House Notts & Derby", "auction-house-nottsderby"),
    ("staffordshire", "Auction House Cheshire, Staffordshire & Shropshire", "auction-house-cheshirestaffordshireshropshire"),
    ("birmingham", "Auction House Birmingham & Black Country", "auction-house-birminghamblackcountry"),
    ("kent", "Auction House Kent", "auction-house-kent"),
    ("westyorkshire", "Auction House West Yorkshire", "auction-house-westyorkshire"),
    ("lincolnshire", "Auction House Lincolnshire, North Notts & South Yorks", "auction-house-lincolnshirenorthnottssouthyorks"),
)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip(" ,")
    return value or None


def money_values(value: str | None) -> list[int]:
    return [int(round(float(raw.replace(",", "")))) for raw in MONEY_RE.findall(value or "")]


def result_details(value: str | None) -> tuple[str, int | None, int | None]:
    text = clean(value) or ""
    lower = text.lower()
    values = money_values(text)
    sale_price = values[0] if lower.startswith("sold for") and values else None
    last_bid = values[0] if lower.startswith("last bid") and values else None
    if lower.startswith("sold prior"):
        status = "sold_prior"
    elif lower.startswith("sold after"):
        status = "sold_after"
    elif lower.startswith("sold"):
        status = "sold"
    elif lower.startswith("last bid"):
        status = "last_bid"
    elif lower.startswith("no bids"):
        status = "no_bids"
    elif lower.startswith("postponed"):
        status = "postponed"
    elif lower.startswith("withdrawn"):
        status = "withdrawn"
    elif lower.startswith("unsold"):
        status = "unsold"
    else:
        status = "unknown"
    return status, sale_price, last_bid


def is_historical_outcome(row: dict, today=None) -> bool:
    today = today or datetime.now().date()
    row_date = datetime.strptime(row["auction_date"], "%Y-%m-%d").date()
    return row_date <= today or row.get("status") in {"sold", "sold_prior", "sold_after"}


def pagination_extent(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for anchor in soup.find_all("a", href=True):
        query = parse_qs(urlparse(anchor["href"]).query)
        for value in query.get("page", []):
            if value.isdigit():
                pages.add(int(value))
    return max(pages)


def parse_page(html: str, source_url: str, snapshot_path: str, sha256: str,
               retrieved_at: str, auctioneer: str, canonical_slug: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        anchor = tr.find("a", href=LOT_RE)
        if not anchor:
            continue
        href = urljoin(source_url, anchor.get("href"))
        match = LOT_RE.fullmatch(href)
        if not match:
            continue
        source_id = match.group(1)
        cells = [clean(cell.get_text(" ", strip=True)) or "" for cell in tr.find_all("td")]
        date_index = next((i for i, value in enumerate(cells) if DATE_RE.fullmatch(value)), None)
        if date_index is None or date_index + 2 >= len(cells):
            raise ValueError(f"lot {source_id} has no complete date/guide/result columns")
        address = clean(anchor.get_text(" ", strip=True))
        if not address and date_index >= 2:
            address = clean(cells[date_index - 2])
        if not address:
            raise ValueError(f"lot {source_id} has no published address")
        end_at = datetime.strptime(cells[date_index], "%d/%m/%Y %H:%M")
        auction_date = end_at.date().isoformat()
        guide_text = cells[date_index + 1]
        result_text = cells[date_index + 2]
        guide_values = money_values(guide_text)
        status, sale_price, last_bid = result_details(result_text)
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row(
            auctioneer, f"{canonical_slug}:online:{auction_date}", auction_date,
            None, source_id, href,
        )
        row.update(
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address),
            guide_price=guide_values[0] if guide_values else None,
            guide_price_high=guide_values[1] if len(guide_values) > 1 else None,
            sale_price=sale_price,
            status=status,
            property_id=None,
            identity_method="source_lot_id",
            record_quality="address_record",
            auction_end_time=end_at.isoformat(),
            auction_date_basis="exact individual lot end timestamp published by source",
            guide_text=guide_text or None,
            result_text=result_text or None,
            last_bid_price=last_bid,
            source_evidence={
                "source_url": source_url,
                "snapshot_path": snapshot_path,
                "sha256": sha256,
                "retrieved_at": retrieved_at,
                "basis": "first-party dedicated regional online-results row with stable lot redirect ID",
            },
        )
        row["appearance_id"] = f"{auctioneer}|online:{source_id}"
        rows.append(row)
    return rows


def fetch(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000 or b"Past online auction results" not in raw:
        raise ValueError("source returned no results table")
    return raw


def harvest_region(session: requests.Session, url_slug: str, auctioneer: str,
                   canonical_slug: str) -> dict:
    index = f"{BASE}/{url_slug}/auction/past-auctions"
    first_raw = fetch(session, index)
    last_page = pagination_extent(first_raw.decode("utf-8", "replace"))
    existing_path = corpus.DATA / "appearances" / canonical_slug / "online-results.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    existing_ids = {str(row.get("source_lot_id")) for row in existing if row.get("source_lot_id")}
    seen_current: dict[str, int] = {}
    page_counts: dict[str, int] = {}
    failures = []
    new_rows = []

    for page in range(1, last_page + 1):
        source_url = index if page == 1 else f"{index}?page={page}"
        parsed = None
        last_error = None
        for attempt in range(3):
            try:
                raw = first_raw if page == 1 else fetch(session, source_url)
                sha256 = corpus.digest(raw)
                snapshot = corpus.DATA / "sources" / f"{canonical_slug}-regional" / f"page-{page:03d}-{sha256[:16]}.json.gz"
                retrieved_at = corpus.now()
                html = raw.decode("utf-8", "replace")
                corpus.save_gzip(snapshot, {
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "sha256": sha256,
                    "html": html,
                })
                parsed = parse_page(html, source_url, str(snapshot.relative_to(corpus.ROOT)),
                                    sha256, retrieved_at, auctioneer, canonical_slug)
                if not parsed:
                    raise ValueError("page exposed zero lot rows")
                break
            except Exception as exc:
                last_error = exc
                parsed = None
                if attempt < 2:
                    time.sleep(1.0 + attempt)
        if parsed is None:
            exc = last_error or ValueError("page could not be parsed")
            failures.append({"page": page, "url": source_url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
            continue
        page_counts[str(page)] = len(parsed)
        for row in parsed:
            source_id = row["source_lot_id"]
            if source_id in seen_current:
                raise ValueError(
                    f"source ID {source_id} repeated on pages {seen_current[source_id]} and {page}"
                )
            seen_current[source_id] = page
            if source_id not in existing_ids and is_historical_outcome(row):
                new_rows.append(row)
        time.sleep(0.25)

    key = f"{canonical_slug}/online-results"
    corpus.write_rows(key, new_rows)
    saved_path = corpus.DATA / "appearances" / f"{key}.jsonl.gz"
    saved = list(corpus.iter_rows(saved_path))
    archive_complete = (
        not failures and len(page_counts) == last_page
        and len(seen_current) == sum(page_counts.values())
    )
    dates = [row.get("auction_date") for row in saved if row.get("auction_date")]
    summary = {
        "auctioneer": auctioneer,
        "source_url": index,
        "pages_expected": last_page,
        "pages_captured": len(page_counts),
        "current_archive_rows": len(seen_current),
        "overlapping_existing_rows": len(existing_ids.intersection(seen_current)),
        "run_new_appearances": len(new_rows),
        "property_appearances_captured": len(saved),
        "address_records": sum(bool(row.get("address")) for row in saved),
        "partial_lots": sum(not row.get("address") for row in saved),
        "earliest_lot_end_date": min(dates) if dates else None,
        "latest_lot_end_date": max(dates) if dates else None,
        "by_status": dict(Counter(row.get("status") or "unknown" for row in saved)),
        "page_counts": page_counts,
        "failures": failures,
        "archive_pagination_complete": archive_complete,
    }
    corpus.save_json(corpus.DATA / "auctions" / canonical_slug / "regional-online-results.json", {
        "auctioneer": auctioneer,
        "source_auction_id": f"{canonical_slug}:regional-online-results",
        "auction_date": None,
        "catalogue_complete": False,
        "archive_pagination_complete": archive_complete,
        "lots_captured": len(saved),
        "current_archive_rows": len(seen_current),
        "source_property_ids": sorted(seen_current),
        "completion_scope": "all rows across every retained first-party dedicated regional results page",
        "errors": failures,
        "notes": ["Original auction catalogue denominators are not published by this retained results table"],
        "checked_at": corpus.now(),
    })
    return summary


def harvest() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "Commercial-Auction-Sniper/1.0 (+historical lot research)"
    summaries = []
    for url_slug, auctioneer, canonical_slug in REGIONS:
        summaries.append(harvest_region(session, url_slug, auctioneer, canonical_slug))
    overall = {
        "checked_at": corpus.now(),
        "regions_requested": len(REGIONS),
        "regions_complete": sum(item["archive_pagination_complete"] for item in summaries),
        "pages_captured": sum(item["pages_captured"] for item in summaries),
        "source_rows": sum(item["current_archive_rows"] for item in summaries),
        "overlapping_existing_rows": sum(item["overlapping_existing_rows"] for item in summaries),
        "run_new_appearances": sum(item["run_new_appearances"] for item in summaries),
        "failures": [failure for item in summaries for failure in item["failures"]],
        "regions": summaries,
    }
    corpus.save_json(corpus.DATA / "auction_house_regions_collection.json", overall)
    print(json.dumps(overall, indent=2), flush=True)
    if overall["failures"] or overall["regions_complete"] != len(REGIONS):
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
