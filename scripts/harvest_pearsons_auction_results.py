"""Bank Pearsons Auctions' retained first-party result tables.

The public archive exposes an exact date and a published offered-lot count for
each auction, then one unpaginated result row per visible property interest.
All visible rows are retained.  Where the result table is larger than the
published offered count, the discrepancy is recorded and the auction remains
incomplete rather than dropping source rows to force reconciliation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://pearsons.com"
INDEX = BASE + "/property-auction-results"
EVENT_RE = re.compile(r"^/property-auction-results/(\d+)/[^/]+/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
LAST_BID_RE = re.compile(r"last bid was\s*£\s*([\d,]+(?:\.\d+)?)", re.I)
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def parse_published_date(value: str | None) -> str:
    text = clean(value) or ""
    text = re.sub(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+", "", text, flags=re.I)
    text = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
    text = re.sub(r"\s*,\s*", " ", text)
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"unrecognised published auction date: {value!r}")


def table_headers(table) -> list[str]:
    return [clean(node.get_text(" ", strip=True)) or "" for node in table.select("thead th")]


def parse_index(html: str, index_url: str = INDEX) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = next(
        (
            item for item in soup.select("table.auctionTable")
            if [header.casefold() for header in table_headers(item)][:2] == ["auction", "lots offered"]
        ),
        None,
    )
    if table is None:
        raise ValueError("archive index has no recognised auction table")

    events, seen_ids, seen_urls = [], set(), set()
    for position, source_row in enumerate(table.select("tbody tr"), 1):
        cells = source_row.find_all("td", recursive=False)
        if len(cells) != 4:
            raise ValueError(f"malformed archive row at position {position}")
        anchor = cells[0].find("a", href=True)
        date_node = cells[0].find("span")
        date_text = clean((date_node or cells[0]).get_text(" ", strip=True))
        event_url = urljoin(index_url, anchor["href"] if anchor else "")
        match = EVENT_RE.match(urlparse(event_url).path)
        if not match:
            raise ValueError(f"archive row {position} has no stable event URL")
        event_id = match.group(1)
        if event_id in seen_ids or event_url in seen_urls:
            raise ValueError(f"duplicate event identity at archive row {position}")
        seen_ids.add(event_id)
        seen_urls.add(event_url)
        offered_text = clean(cells[1].get_text(" ", strip=True)) or ""
        if not offered_text.isdigit():
            raise ValueError(f"invalid offered-lot count at archive row {position}")
        events.append(
            {
                "event_id": event_id,
                "auction_date": parse_published_date(date_text),
                "published_date_text": date_text,
                "published_lots_offered": int(offered_text),
                "published_percent_sold": clean(cells[2].get_text(" ", strip=True)),
                "published_total_raised": clean(cells[3].get_text(" ", strip=True)),
                "url": event_url,
                "index_position": position,
            }
        )
    if not events:
        raise ValueError("archive index contains no auction rows")
    return events


def money_values(value: str | None) -> list[int]:
    return [int(round(float(item.replace(",", "")))) for item in MONEY_RE.findall(value or "")]


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None]:
    """Return status, achieved price and a non-sale last bid.

    Unsold rows sometimes concatenate a later sold phrase in the source cell.
    The leading unsold statement controls; only an explicitly labelled last
    bid is retained and no sale is inferred from that malformed concatenation.
    """
    text = clean(value) or ""
    lower = text.casefold()
    last_bid_match = LAST_BID_RE.search(text)
    last_bid = int(last_bid_match.group(1).replace(",", "")) if last_bid_match else None
    if not text:
        return "unknown", None, None
    if lower.startswith(("not sold", "unsold", "there were no bids")):
        return "unsold", None, last_bid
    if lower.startswith(("withdrawn", "withdarwn")):
        return "withdrawn", None, None
    prices = money_values(text)
    price = prices[0] if prices else None
    if lower.startswith("sold prior"):
        return "sold_prior", price, None
    if lower.startswith(("sold post", "sold after")):
        return "sold_post", price, None
    if lower.startswith("sold"):
        return "sold", price, None
    if re.fullmatch(r"£\s*[\d,]+(?:\.\d+)?", text):
        return "sold", price, None
    return "unknown", None, None


def normalized_address(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def parse_result_page(html: str, event: dict, evidence: dict) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    heading = next(
        (
            clean(node.get_text(" ", strip=True))
            for node in soup.find_all(["h1", "h2"])
            if "auction results" in (clean(node.get_text(" ", strip=True)) or "").casefold()
        ),
        None,
    )
    if not heading:
        raise ValueError("result page has no auction-results heading")
    heading_date_text = re.sub(r"^.*?auction results\s*:?\s*", "", heading, flags=re.I)
    heading_date = parse_published_date(heading_date_text)
    if heading_date != event["auction_date"]:
        raise ValueError(
            f"index/result date mismatch: {event['auction_date']} versus {heading_date}"
        )

    table = next(
        (
            item for item in soup.select("table.auctionTable")
            if [header.casefold() for header in table_headers(item)][:3]
            == ["lot no.", "address", "result"]
        ),
        None,
    )
    if table is None:
        raise ValueError("result page has no recognised property table")
    pagination = soup.select(".pagination a[href], a[rel~='next'][href]")
    if pagination:
        raise ValueError("unexpected pagination on retained result table")

    rows, exact_seen, duplicate_source_rows, blank_placeholder_rows = [], set(), 0, 0
    duplicate_lot_numbers = []
    lot_seen = set()
    for position, source_row in enumerate(table.select("tbody tr"), 1):
        cells = source_row.find_all("td", recursive=False)
        if len(cells) != 3:
            raise ValueError(f"malformed result row at source position {position}")
        lot_number = clean(cells[0].get_text(" ", strip=True))
        address = clean(cells[1].get_text(" ", strip=True))
        result_text = clean(cells[2].get_text(" ", strip=True))
        if not lot_number and not address and not result_text:
            # Two retained tables contain a completely empty HTML row before
            # lot 1.  It is a presentation placeholder, not a property.
            blank_placeholder_rows += 1
            continue
        if not lot_number or not address:
            raise ValueError(f"result row {position} lacks lot number or address")
        exact_key = (lot_number.casefold(), normalized_address(address), (result_text or "").casefold())
        if exact_key in exact_seen:
            duplicate_source_rows += 1
            continue
        exact_seen.add(exact_key)
        if lot_number.casefold() in lot_seen:
            duplicate_lot_numbers.append(lot_number)
        lot_seen.add(lot_number.casefold())

        status, sale_price, last_bid_price = status_and_prices(result_text)
        postcode_match = corpus.PC.search(address)
        postcode = postcode_match.group().upper().replace("\u00a0", " ") if postcode_match else None
        source_identity = hashlib.sha256(
            f"{event['event_id']}|{lot_number.casefold()}|{normalized_address(address)}".encode()
        ).hexdigest()[:24]
        auction_id = f"pearsons-auctions:{event['event_id']}"
        row = corpus.base_row(
            "Pearsons Auctions", auction_id, event["auction_date"], lot_number,
            source_identity, event["url"],
        )
        row.update(
            address=address,
            postcode=postcode,
            locality=address,
            sector=corpus.sector(address),
            status=status,
            sale_price=sale_price,
            property_id=None,
            identity_method="source_event_lot_and_exact_published_address",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            last_bid_price=last_bid_price,
            source_result_url=event["url"],
            source_evidence=evidence,
            auction_date_precision="day",
            auction_date_basis="first-party archive index and matching result heading",
            operator_company="Pearsons Southern Limited",
            operator_company_number="01517996",
        )
        rows.append(row)

    if not rows:
        raise ValueError("result table contains no property rows")
    denominator_reconciled = len(rows) == event["published_lots_offered"]
    errors = []
    if not denominator_reconciled:
        errors.append(
            "visible result rows do not equal the first-party published lots-offered count; "
            "all individually identified rows retained"
        )
    if duplicate_lot_numbers:
        errors.append("duplicate lot numbers in source table; addresses preserve separate identities")
    state = {
        "auctioneer": "Pearsons Auctions",
        "operator_company": "Pearsons Southern Limited",
        "operator_company_number": "01517996",
        "source_auction_id": f"pearsons-auctions:{event['event_id']}",
        "auction_date": event["auction_date"],
        "auction_date_precision": "day",
        "auction_date_basis": "first-party archive index and matching result heading",
        "published_heading": heading,
        "published_date_text": event["published_date_text"],
        "published_lots_offered": event["published_lots_offered"],
        "published_percent_sold": event["published_percent_sold"],
        "published_total_raised": event["published_total_raised"],
        "catalogue_complete": denominator_reconciled and not duplicate_lot_numbers,
        "source_rows_complete": True,
        "pagination_reconciled": True,
        "denominator_reconciled": denominator_reconciled,
        "visible_source_rows": len(rows),
        "lots_captured": len(rows),
        "duplicate_source_rows_not_counted": duplicate_source_rows,
        "blank_placeholder_rows_not_counted": blank_placeholder_rows,
        "duplicate_lot_numbers": sorted(set(duplicate_lot_numbers)),
        "source_url": event["url"],
        "completion_scope": "all visible rows in the first-party unpaginated result table",
        "errors": errors,
        "checked_at": corpus.now(),
    }
    return state, rows


def harvest(workers: int = 8) -> None:
    index_url, raw = get(INDEX)
    index_sha, retrieved_at = corpus.digest(raw), corpus.now()
    index_snapshot = corpus.DATA / "sources/pearsons-auctions" / f"archive-{index_sha[:16]}.json.gz"
    index_evidence = {
        "source_url": index_url,
        "retrieved_at": retrieved_at,
        "sha256": index_sha,
        "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party auction archive with dates and offered-lot denominators",
    }
    index_html = raw.decode("utf-8", "replace")
    corpus.save_gzip(index_snapshot, {"evidence": index_evidence, "html": index_html})
    events = parse_index(index_html, index_url)

    run_rows, states, failures = [], {}, []

    def capture(event: dict):
        resolved, page_raw = get(event["url"])
        page_sha, captured_at = corpus.digest(page_raw), corpus.now()
        page_html = page_raw.decode("utf-8", "replace")
        snapshot = (
            corpus.DATA / "sources/pearsons-auctions" /
            f"result-{event['event_id']}-{page_sha[:16]}.json.gz"
        )
        evidence = {
            "source_url": resolved,
            "retrieved_at": captured_at,
            "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party exact-dated unpaginated property result table",
        }
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        event = dict(event, url=resolved)
        state, rows = parse_result_page(page_html, event, evidence)
        return event["event_id"], state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(capture, event): event for event in events}
        for future in as_completed(jobs):
            event = jobs[future]
            try:
                event_id, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/pearsons-auctions/{event_id}.json", state)
                states[event_id] = state
                run_rows.extend(rows)
                print("PEARSONS", len(states), "/", len(events), "events", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"url": event["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    path = corpus.DATA / "appearances/pearsons-auctions/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("pearsons-auctions/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    incomplete = [state for state in states.values() if not state["catalogue_complete"]]
    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "operator": {
            "canonical_name": "Pearsons Auctions",
            "company_name": "Pearsons Southern Limited",
            "company_number": "01517996",
            "branches_are_not_counted_as_separate_auctioneers": True,
        },
        "events_discovered": len(events),
        "events_captured": len(states),
        "events_complete": len(states) - len(incomplete),
        "events_incomplete": len(incomplete),
        "published_lots_offered": sum(event["published_lots_offered"] for event in events),
        "visible_result_rows": sum(state["visible_source_rows"] for state in states.values()),
        "denominator_difference": sum(
            state["visible_source_rows"] - state["published_lots_offered"] for state in states.values()
        ),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_exact_dated_address_records": sum(
            bool(row.get("address")) and row.get("auction_date_precision") == "day" for row in added
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_last_bid_prices_not_sale_prices": sum(row.get("last_bid_price") is not None for row in added),
        "source_years": sorted({row["auction_date"][:4] for row in merged.values()}),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "index_evidence": index_evidence,
        "auctions": states,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "pearsons_auctions_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(events):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)
