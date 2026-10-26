"""Harvest a complete public Bamboo Auctions white-label property archive.

Bamboo white-label home pages expose a paginated structured property index in
Next.js page data.  Each public property page exposes the richer property JSON,
including the stable source id, exact close time, guide price, bid history and
whether the reserve was met.  This collector reconciles the index denominator,
captures every detail payload, and banks one appearance per stable listing.

The default target is 247 Property Auctions.  Host/name/slug are arguments so
the same collector can be reused for other genuine UK Bamboo operators after
their trading names have been reconciled.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.S | re.I
)


def fetch(url: str, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - exercised by live retries
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def extract_next_data(raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace")
    match = NEXT_DATA_RE.search(text)
    if not match:
        raise ValueError("page has no __NEXT_DATA__ payload")
    return json.loads(match.group(1))


def page_props(raw: bytes) -> dict:
    return extract_next_data(raw)["props"]["pageProps"]


def exact_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(BeautifulSoup(value, "html.parser").get_text(" ", strip=True).split())
    return text or None


def positive_money(value) -> int | float | None:
    parsed = corpus.money(value)
    return int(parsed) if isinstance(parsed, float) and parsed.is_integer() else parsed


def row_from_property(
    item: dict,
    auctioneer: str,
    source_prefix: str,
    host: str,
    evidence: dict,
    now_utc: datetime | None = None,
) -> dict:
    source_id = str(item.get("_id") or item.get("id") or "").strip()
    handle = str(item.get("handle") or "").strip()
    date = exact_date(item.get("endDate"))
    if not source_id or not handle:
        raise ValueError("property payload has no stable id/handle")
    original_url = f"https://{host}/property/{handle}"
    auction_id = f"{source_prefix}:{source_id}"
    row = corpus.base_row(auctioneer, auction_id, date, None, source_id, original_url)

    full_address = corpus.clean(item.get("fullAddress")) or None
    address_parts = [
        corpus.clean(item.get("addressLineOne")),
        corpus.clean(item.get("addressLineTwo")),
        corpus.clean(item.get("city")),
        corpus.clean(item.get("postcode")),
    ]
    address = full_address or ", ".join(part for part in address_parts if part) or None
    postcode = corpus.clean(item.get("postcode")) or None
    if postcode and not corpus.PC.fullmatch(postcode):
        match = corpus.PC.search(address or "")
        postcode = match.group().upper() if match else None
    elif postcode:
        postcode = postcode.upper()

    description = clean_html(item.get("description"))
    property_type = corpus.clean(item.get("type")) or None
    title = corpus.clean(item.get("title")) or None
    now_utc = now_utc or datetime.now(timezone.utc)
    reserve_met = item.get("isReserveMet") is True
    end_time = None
    if item.get("endDate"):
        end_time = datetime.fromisoformat(item["endDate"].replace("Z", "+00:00"))
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
    ended = end_time is not None and end_time <= now_utc
    highest_bid = positive_money(item.get("highestBid"))
    status = "sold" if ended and reserve_met else ("available" if not ended else "unknown")
    sale_price = highest_bid if status == "sold" else None

    images = []
    for candidate in [item.get("thumbnailImage")] + [
        image.get("url") for image in item.get("galleryImages", []) if isinstance(image, dict)
    ]:
        if candidate and candidate not in images:
            images.append(candidate)

    row.update(
        appearance_id=f"{auctioneer}|bamboo:{source_id}",
        address=address,
        postcode=postcode,
        locality=corpus.clean(item.get("city")) or None,
        property_type=property_type,
        tenure=corpus.clean(item.get("tenure")) or None,
        guide_price=positive_money(item.get("guidePrice")),
        sale_price=sale_price,
        status=status if end_time is not None else "unknown",
        description=description,
        sector=corpus.sector(" ".join(v for v in (title, property_type, description) if v)),
        epc=corpus.clean(item.get("epcRating")) or None,
        vat_togc="VAT applicable" if item.get("isVatApplicable") is True else None,
        image_urls=images,
        identity_method="bamboo_stable_property_id",
        record_quality="address_record" if address else "partial_lot",
        source_evidence=evidence,
        auction_date_basis="exact close date in public Bamboo property payload" if date else "no close date published in public Bamboo property payload",
        auction_end_time=item.get("endDate"),
        source_status=item.get("status"),
        reserve_met=reserve_met,
        bid_count=len(item.get("bids") or []),
    )
    return row


def harvest(host: str, auctioneer: str, slug: str, workers: int = 10) -> dict:
    base = f"https://{host}/"
    first_raw = fetch(base)
    first_props = page_props(first_raw)
    first_index = first_props["propertiesData"]
    total_count = int(first_index["meta"]["totalCount"])
    page_size = len(first_index["data"])
    if total_count < 1 or page_size < 1:
        raise SystemExit("Bamboo archive exposed no properties")
    page_count = math.ceil(total_count / page_size)

    index_pages: dict[int, dict] = {1: first_index}

    def collect_page(number: int) -> tuple[int, dict]:
        raw = fetch(base + f"?page={number}")
        return number, page_props(raw)["propertiesData"]

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        jobs = [executor.submit(collect_page, page) for page in range(2, page_count + 1)]
        for future in as_completed(jobs):
            number, payload = future.result()
            index_pages[number] = payload
            print(f"BAMBOO INDEX {number}/{page_count}", flush=True)

    index_rows = [item for page in sorted(index_pages) for item in index_pages[page]["data"]]
    by_id = {str(item.get("_id") or item.get("id")): item for item in index_rows}
    if len(index_rows) != total_count:
        raise SystemExit(f"Bamboo pagination returned {len(index_rows)} rows; expected {total_count}")
    if len(by_id) != total_count:
        raise SystemExit(f"Bamboo pagination contains {total_count - len(by_id)} duplicate stable ids")

    detail_payloads: dict[str, dict] = {}

    def collect_detail(summary: dict) -> tuple[str, dict]:
        source_id = str(summary.get("_id") or summary.get("id"))
        url = urljoin(base, "property/" + summary["handle"])
        detail = page_props(fetch(url))["propertyData"]
        if str(detail.get("_id") or detail.get("id")) != source_id:
            raise ValueError(f"detail identity mismatch for {source_id}")
        return source_id, detail

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        jobs = {executor.submit(collect_detail, summary): source_id for source_id, summary in by_id.items()}
        for position, future in enumerate(as_completed(jobs), 1):
            source_id, detail = future.result()
            detail_payloads[source_id] = detail
            if position % 20 == 0 or position == total_count:
                print(f"BAMBOO DETAIL {position}/{total_count}", flush=True)

    snapshot_value = {
        "source_url": base,
        "retrieved_at": corpus.now(),
        "total_count": total_count,
        "page_size": page_size,
        "page_count": page_count,
        "index_pages": [index_pages[page] for page in sorted(index_pages)],
        "property_details": [detail_payloads[source_id] for source_id in sorted(detail_payloads)],
    }
    snapshot_bytes = json.dumps(snapshot_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    snapshot_sha = corpus.digest(snapshot_bytes)
    snapshot_path = corpus.DATA / "sources" / slug / "bamboo" / f"archive-{snapshot_sha[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot_value)
    evidence = {
        "source_url": base,
        "snapshot_path": str(snapshot_path.relative_to(corpus.ROOT)),
        "retrieved_at": snapshot_value["retrieved_at"],
        "sha256": snapshot_sha,
        "basis": "complete public Bamboo index and stable property detail payloads",
    }
    now_utc = datetime.now(timezone.utc)
    rows = [
        row_from_property(detail_payloads[source_id], auctioneer, slug, host, evidence, now_utc)
        for source_id in sorted(detail_payloads)
    ]
    appearance_path = corpus.DATA / "appearances" / slug / "bamboo-archive.jsonl.gz"
    existing_ids = {row["appearance_id"] for row in corpus.iter_rows(appearance_path)} if appearance_path.exists() else set()
    new_rows = [row for row in rows if row["appearance_id"] not in existing_ids]
    retained = corpus.write_rows(f"{slug}/bamboo-archive", rows)
    if retained != total_count:
        raise SystemExit(f"retained {retained} rows; reconciled source exposes {total_count}")

    today = now_utc.date().isoformat()
    historical_rows = [row for row in rows if row.get("auction_date") and row["auction_date"] <= today]
    future_rows = [row for row in rows if row.get("auction_date") and row["auction_date"] > today]
    undated_rows = [row for row in rows if not row.get("auction_date")]
    state = {
        "auctioneer": auctioneer,
        "source_auction_id": f"{slug}:bamboo-archive",
        "source_url": base,
        "source_rows_complete": True,
        "catalogue_complete": True,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "visible_source_rows": total_count,
        "lots_captured": len(rows),
        "detail_payloads_captured": len(detail_payloads),
        "page_count": page_count,
        "errors": [],
        "checked_at": corpus.now(),
        "completion_scope": "all listings in the surviving public Bamboo white-label archive; not a claim that deleted listings or earlier platforms are covered",
    }
    corpus.save_json(corpus.DATA / "auctions" / slug / "bamboo-archive.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": auctioneer,
        "source_url": base,
        "archive_appearances_captured": retained,
        "run_new_appearances": len(new_rows),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "dated_historical_records": len(historical_rows),
        "future_dated_records": len(future_rows),
        "undated_records": len(undated_rows),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": sum(row.get("sale_price") is not None for row in rows),
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_year": dict(Counter(row["auction_date"][:4] if row.get("auction_date") else "undated" for row in rows)),
        "source_years": sorted({row["auction_date"][:4] for row in historical_rows}),
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "complete": True,
        "completion_scope": state["completion_scope"],
    }
    corpus.save_json(corpus.DATA / f"{slug.replace('-', '_')}_bamboo_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="247auction.bambooauctions.com")
    parser.add_argument("--auctioneer", default="247 Property Auctions")
    parser.add_argument("--slug", default="247-property-auctions")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    harvest(args.host, args.auctioneer, args.slug, args.workers)
