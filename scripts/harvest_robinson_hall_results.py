"""Bank Robinson & Hall's surviving first-party EIG result-sheet archive.

The auctioneer's WordPress results page embeds an EIG ``pastauctions.aspx``
table.  Each date links to a flat result sheet containing stable EIG lot IDs,
addresses and published outcomes.  The published ``Lots Offered`` figure
excludes some withdrawn/postponed entries, so completeness is reconciled as
unique result rows >= lots offered; those extra appearances are retained.

This first pass intentionally does not infer guide prices or rents.  Those are
available only in per-lot catalogue/detail material and can be added without
changing the event/lot appearance identities established here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Robinson & Hall"
SLUG = "robinson-hall"
ARCHIVE_URL = "https://auctioneertemplates.eigroup.co.uk/pastauctions.aspx?a=384&c=rbh"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
RESULT_RE = re.compile(r"results\.aspx", re.I)
LOT_RE = re.compile(r"LotDetails\.aspx", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)
PARSER_VERSION = 1


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def exact_date(value: str) -> str:
    return datetime.strptime(clean(value) or "", "%A, %d %B %Y").date().isoformat()


def query_value(url: str, name: str) -> str | None:
    query = {key.casefold(): values for key, values in parse_qs(urlsplit(url).query).items()}
    values = query.get(name.casefold())
    return values[0] if values else None


def fetch(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def snapshot(raw: bytes, resolved: str, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def parse_archive(html: str, base_url: str = ARCHIVE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = []
    for row in soup.select("tr"):
        link = row.select_one('a[href*="results.aspx"]')
        cells = row.find_all(["td", "th"], recursive=False)
        if not link or len(cells) < 4:
            continue
        url = urljoin(base_url, link.get("href") or "")
        event_id = query_value(url, "au")
        offered_text = clean(cells[1].get_text(" ", strip=True)) or ""
        if not event_id or not offered_text.isdigit():
            continue
        events.append({
            "event_id": event_id,
            "auction_date": exact_date(link.get_text(" ", strip=True)),
            "result_url": url,
            "lots_offered": int(offered_text),
            "percent_sold": clean(cells[2].get_text(" ", strip=True)),
            "total_raised_text": clean(cells[3].get_text(" ", strip=True)),
        })
    identities = [event["event_id"] for event in events]
    if not events or len(identities) != len(set(identities)):
        raise ValueError("archive has no events or duplicate event identities")
    return events


def status_and_price(text: str | None) -> tuple[str, int | None, int | None]:
    value = clean(text) or ""
    lower = value.casefold()
    if "sold prior" in lower:
        status = "sold_prior"
    elif "sold post" in lower or "sold after" in lower:
        status = "sold_after"
    elif re.search(r"\bsold\b", lower):
        status = "sold"
    elif "withdrawn prior" in lower:
        status = "withdrawn_prior"
    elif "withdrawn" in lower:
        status = "withdrawn"
    elif "postponed" in lower:
        status = "postponed"
    elif "unsold" in lower or "no bid" in lower:
        status = "unsold"
    else:
        status = "unknown"
    sold_match = re.search(r"\bsold(?:\s+(?:prior|post|after)(?:\s+to\s+auction)?)?\s+for\s+£\s*([\d,]+(?:\.\d+)?)", value, re.I)
    sale_price = int(corpus.money(sold_match.group(1))) if sold_match and status.startswith("sold") else None
    bid_match = re.search(r"\bbidding\s+reached\s+£\s*([\d,]+(?:\.\d+)?)", value, re.I)
    bid_reached = int(corpus.money(bid_match.group(1))) if bid_match else None
    return status, sale_price, bid_reached


def classify_sector(address: str) -> str:
    """Classify only explicit address-level asset wording on this first pass."""
    value = address.casefold()
    if re.search(r"\bmixed[ -]?use\b", value):
        return "mixed-use"
    if re.search(r"\b(land|plot|paddock|woodland|field|meadow)\b", value):
        return "land"
    if re.search(r"\b(club|shop|retail|office|warehouse|factory|garage|industrial|pub|hotel|cafe|restaurant|commercial)\b", value):
        return "commercial"
    return corpus.sector(address)


def parse_result(html: str, event: dict, evidence: dict) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    rows, malformed = [], []
    for position, node in enumerate(soup.select("table.lot-table tr.lot-row, table.lot-table tr.lot-alt-row"), 1):
        cells = node.find_all("td", recursive=False)
        links = node.select('a[href*="LotDetails.aspx"]')
        lot = clean(cells[0].get_text(" ", strip=True)) if len(cells) >= 1 else None
        address = clean(cells[1].get_text(" ", strip=True)) if len(cells) >= 2 else None
        result_text = clean(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else None
        detail_url = urljoin(event["result_url"], links[0].get("href") or "") if links else None
        source_lot_id = query_value(detail_url, "LotID") if detail_url else None
        if not all((lot, address, result_text, detail_url, source_lot_id)):
            malformed.append({
                "position": position, "lot_number": lot, "address": address,
                "result_text": result_text, "detail_url": detail_url,
            })
            continue
        status, sale_price, bid_reached = status_and_price(result_text)
        row = corpus.base_row(
            SOURCE, f"{SLUG}:{event['event_id']}", event["auction_date"], lot,
            source_lot_id, detail_url,
        )
        postcode = corpus.PC.search(address)
        row.update(
            appearance_id=f"{SOURCE}|{SLUG}:{event['event_id']}|eig-lot:{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sale_price=sale_price,
            status=status,
            sector=classify_sector(address),
            property_id=f"eig-lot:{source_lot_id}",
            identity_method="first_party_eig_event_and_lot_id",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            source_platform="EIG",
            source_platform_lot_id=source_lot_id,
            reported_bid_reached=bid_reached,
            result_sheet_url=event["result_url"],
            source_evidence=evidence,
        )
        rows.append(row)
    return rows, malformed


def existing_eig_appearances(exclude_slug: str) -> set[tuple[str, str]]:
    """Return exact event-date/EIG-lot pairs already banked elsewhere."""
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            url = row.get("original_url") or ""
            lot_id = query_value(url, "LotID") if LOT_RE.search(url) else None
            if lot_id and row.get("auction_date"):
                values.add((row["auction_date"], lot_id))
    return values


def harvest(workers: int = 8) -> dict:
    archive_raw, archive_resolved = fetch(ARCHIVE_URL)
    archive_evidence = snapshot(
        archive_raw, archive_resolved, "past-auctions",
        "first-party embedded EIG past-auction inventory",
    )
    events = parse_archive(archive_raw.decode("utf-8", "replace"), archive_resolved)
    fetched = {}
    failures = []
    with ThreadPoolExecutor(max_workers=min(workers, len(events))) as pool:
        futures = {pool.submit(fetch, event["result_url"]): event for event in events}
        for future in as_completed(futures):
            event = futures[future]
            try:
                fetched[event["event_id"]] = future.result()
            except Exception as exc:
                failures.append({
                    "event_id": event["event_id"], "url": event["result_url"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
    if failures:
        raise RuntimeError(f"result sheets failed before admission: {failures}")

    event_rows, event_summaries = {}, []
    for event in events:
        raw, resolved = fetched[event["event_id"]]
        evidence = snapshot(
            raw, resolved, f"event-{event['event_id']}",
            "first-party EIG auction result sheet",
            event_id=event["event_id"], auction_date=event["auction_date"],
        )
        rows, malformed = parse_result(raw.decode("utf-8", "replace"), event, evidence)
        identities = [(row["lot_number"], row["source_lot_id"]) for row in rows]
        reconciled = bool(
            not malformed and len(rows) >= event["lots_offered"]
            and len(identities) == len(set(identities))
        )
        if not reconciled:
            raise RuntimeError(
                f"event {event['event_id']} did not reconcile: rows={len(rows)}, "
                f"offered={event['lots_offered']}, malformed={len(malformed)}, "
                f"distinct={len(set(identities))}"
            )
        event_rows[event["event_id"]] = rows
        event_summaries.append({
            **event,
            "result_rows": len(rows),
            "additional_non_offered_rows": len(rows) - event["lots_offered"],
            "result_sheet_reconciled": True,
            "source_evidence": evidence,
        })

    rows = [row for event in events for row in event_rows[event["event_id"]]]
    archive_pairs = [(row["auction_date"], row["source_lot_id"]) for row in rows]
    if len(archive_pairs) != len(set(archive_pairs)):
        raise RuntimeError("same event-date/EIG-lot identity appears more than once in archive")

    global_pairs = existing_eig_appearances(SLUG)
    overlaps = [row for row in rows if (row["auction_date"], row["source_lot_id"]) in global_pairs]
    admissible = [row for row in rows if (row["auction_date"], row["source_lot_id"]) not in global_pairs]
    appearance_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]

    by_event = defaultdict(list)
    for row in admissible:
        by_event[row["source_auction_id"]].append(row)
    summaries_by_id = {f"{SLUG}:{event['event_id']}": event for event in event_summaries}
    for auction_id, date_rows in by_event.items():
        event = summaries_by_id[auction_id]
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event['auction_date']}-{event['event_id']}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": auction_id,
            "auction_date": event["auction_date"],
            "source_url": event["result_url"],
            "published_lots_offered": event["lots_offered"],
            "result_rows_captured": len(date_rows),
            "additional_non_offered_rows": event["additional_non_offered_rows"],
            "catalogue_complete": False,
            "source_rows_complete": True,
            "result_sheet_reconciled": True,
            "completion_scope": "all rows in the surviving first-party result sheet; per-lot catalogue/detail enrichment remains outstanding",
            "source_evidence": [archive_evidence, event["source_evidence"]],
            "errors": [],
            "checked_at": corpus.now(),
        })

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    historical = [row for row in added if cutoff <= (row.get("auction_date") or "") <= today]
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "parser_version": PARSER_VERSION,
        "source_url": archive_resolved,
        "archive_event_count": len(events),
        "published_lots_offered": sum(event["lots_offered"] for event in events),
        "visible_result_rows": len(rows),
        "additional_non_offered_rows": len(rows) - sum(event["lots_offered"] for event in events),
        "event_result_rows": {event["auction_date"]: event["result_rows"] for event in event_summaries},
        "result_sheets_reconciled": len(events),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "new_source_years": sorted(years_after - years_before),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "detail_pages_captured": 0,
        "catalogue_entries_captured": 0,
        "catalogue_detail_enrichment_complete": False,
        "completion_scope": "all rows in every event shown by the surviving first-party EIG archive; catalogue/detail guides, rents and richer sectors remain outstanding",
        "events": event_summaries,
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "robinson_hall_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)


if __name__ == "__main__":
    main()
