"""Bank the complete retained Auction House North West online-results table.

The first-party page is paginated and exposes one stable redirect ID per lot,
the full address, exact auction end timestamp, guide and result.  These are lot
appearances, not auction-container discoveries.  Raw HTML is saved per page.
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
INDEX = BASE + "/northwest/auction/past-auctions"
LOT_RE = re.compile(r"https?://online\.auctionhouse\.co\.uk/lot/redirect/(\d+)", re.I)
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$")
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip(" ,")
    return value or None


def money_values(value: str | None) -> list[int]:
    values = []
    for raw in MONEY_RE.findall(value or ""):
        values.append(int(round(float(raw.replace(",", "")))))
    return values


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
    """Reject future pending rows while retaining a completed sold-prior result."""
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
               retrieved_at: str) -> list[dict]:
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
        end_text = cells[date_index]
        end_at = datetime.strptime(end_text, "%d/%m/%Y %H:%M")
        auction_date = end_at.date().isoformat()
        guide_text = cells[date_index + 1]
        result_text = cells[date_index + 2]
        guide_values = money_values(guide_text)
        status, sale_price, last_bid = result_details(result_text)
        postcode_match = corpus.PC.search(address)
        evidence = {
            "source_url": source_url,
            "snapshot_path": snapshot_path,
            "sha256": sha256,
            "retrieved_at": retrieved_at,
            "basis": "first-party paginated online-results row with stable lot redirect ID",
        }
        row = corpus.base_row(
            "Auction House North West",
            "auction-house-northwest:online:" + auction_date,
            auction_date,
            None,
            source_id,
            href,
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
            source_evidence=evidence,
        )
        row["appearance_id"] = "Auction House North West|online:" + source_id
        rows.append(row)
    return rows


def fetch(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000 or b"Past online auction results" not in raw:
        raise ValueError("source returned no results table")
    return raw


def harvest() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "Commercial-Auction-Sniper/1.0 (+historical lot research)"
    first_raw = fetch(session, INDEX)
    last_page = pagination_extent(first_raw.decode("utf-8", "replace"))
    if last_page < 1:
        raise SystemExit("no Auction House North West pagination discovered")

    existing_path = corpus.DATA / "appearances/auction-house-northwest/online-results.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    merged = {row["source_lot_id"]: row for row in existing}
    seen_current: dict[str, int] = {}
    page_counts: dict[str, int] = {}
    failures = []
    added = 0

    for page in range(1, last_page + 1):
        source_url = INDEX if page == 1 else f"{INDEX}?page={page}"
        try:
            raw = first_raw if page == 1 else fetch(session, source_url)
            sha256 = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/auction-house-northwest" / f"page-{page:03d}-{sha256[:16]}.json.gz"
            retrieved_at = corpus.now()
            html = raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "sha256": sha256,
                "html": html,
            })
            parsed = parse_page(
                html,
                source_url,
                str(snapshot.relative_to(corpus.ROOT)),
                sha256,
                retrieved_at,
            )
            if not parsed:
                raise ValueError("page exposed zero lot rows")
            page_counts[str(page)] = len(parsed)
            for row in parsed:
                source_id = row["source_lot_id"]
                if source_id in seen_current:
                    raise ValueError(
                        f"source ID {source_id} repeated on pages {seen_current[source_id]} and {page}"
                    )
                seen_current[source_id] = page
                previous = merged.get(source_id)
                if previous and (
                    previous.get("address") != row.get("address")
                    or previous.get("auction_end_time") != row.get("auction_end_time")
                ):
                    raise ValueError(f"source identity drift for lot {source_id}")
                if not previous:
                    added += 1
                merged[source_id] = row
        except Exception as exc:
            failures.append({"page": page, "url": source_url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
        time.sleep(0.35)

    rows = sorted((row for row in merged.values() if is_historical_outcome(row)),\n                  key=lambda row: (row.get("auction_date") or "", row["source_lot_id"]))
    corpus.write_rows("auction-house-northwest/online-results", rows)
    current_count = len(seen_current)
    row_total = sum(page_counts.values())
    archive_complete = (
        not failures
        and len(page_counts) == last_page
        and current_count == row_total
    )
    dates = [row["auction_date"] for row in rows if row.get("auction_date")]
    summary = {
        "checked_at": corpus.now(),
        "pages_expected": last_page,
        "pages_captured": len(page_counts),
        "current_archive_rows": current_count,
        "property_appearances_captured": len(rows),
        "run_new_appearances": added,
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "earliest_lot_end_date": min(dates) if dates else None,
        "latest_lot_end_date": max(dates) if dates else None,
        "by_status": dict(Counter(row["status"] for row in rows)),
        "page_counts": page_counts,
        "failures": failures,
        "archive_pagination_complete": archive_complete,
    }
    corpus.save_json(corpus.DATA / "auction_house_northwest_collection.json", summary)
    corpus.save_json(corpus.DATA / "auctions/auction-house-northwest/online-results.json", {
        "auctioneer": "Auction House North West",
        "source_auction_id": "auction-house-northwest:online-results",
        "auction_date": None,
        "catalogue_complete": False,
        "archive_pagination_complete": archive_complete,
        "lots_captured": len(rows),
        "current_archive_rows": current_count,
        "completion_scope": "all rows across every retained first-party online-results page",
        "source_property_ids": sorted(seen_current),
        "errors": failures + [{
            "error": "Rows are individual online lot endings; original catalogue denominators are not published"
        }],
        "checked_at": corpus.now(),
    })
    print(json.dumps(summary, indent=2), flush=True)
    if failures or not archive_complete:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
