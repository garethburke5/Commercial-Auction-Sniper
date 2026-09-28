#!/usr/bin/env python3
"""Harvest every public result-card row from one Barnard Marcus auction."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen


BASE = "https://www.barnardmarcusauctions.co.uk"
UA = "Mozilla/5.0 (compatible; Commercial-Auction-Sniper historical corpus)"


def fetch_json(url: str, attempts: int = 4) -> dict:
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def money(value: str | None) -> int | None:
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else None


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    return value or None


def first_image(value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(BASE, value.split(",", 1)[0].strip().split()[0])


def parse_ids(page_url: str) -> tuple[str, str]:
    with urlopen(Request(page_url, headers={"User-Agent": UA}), timeout=45) as response:
        page = response.read().decode("utf-8")
    match = re.search(r'endpointUrl&quot;:&quot;([^&]+(?:&amp;[^&]+)+)', page)
    if not match:
        raise RuntimeError("Barnard Marcus search endpoint was not found")
    query = parse_qs(urlparse(html.unescape(match.group(1))).query)
    return query["auctionHouseId"][0], query["auctionId"][0]


def harvest(page_url: str, auction_date: str) -> dict:
    house_id, auction_id = parse_ids(page_url)
    endpoint = (
        f"{BASE}/umbraco/Api/SearchApi/Search?auctionHouseId={house_id}"
        f"&auctionId={auction_id}&lots=1&sortBy=LotAsc&page={{page}}"
    )
    first = fetch_json(endpoint.format(page=1))
    pagination = first["pagination"]
    pages = pagination["pageCount"]
    items = list(first["items"])
    for page in range(2, pages + 1):
        payload = fetch_json(endpoint.format(page=page))
        if payload["pagination"]["currentPage"] != page:
            raise RuntimeError(f"page {page} did not reconcile")
        items.extend(payload["items"])

    if len(items) != pagination["totalCount"]:
        raise RuntimeError(f"expected {pagination['totalCount']} rows, got {len(items)}")

    slug = auction_date.replace("-", "_")
    source_auction_id = f"barnard-marcus:{auction_date}"
    rows = []
    for item in items:
        address = ", ".join(filter(None, (clean(item.get("addressLine1")), clean(item.get("addressLine2"))))) or None
        descriptor = clean(item.get("priceDescriptor"))
        if descriptor and item.get("showPriceAsterix"):
            descriptor += "*"
        price_text = clean(item.get("price"))
        price = money(price_text)
        status = clean(item.get("statusLabel"))
        result_status = " ".join(filter(None, (descriptor, price_text))) or status
        raw = "\n".join(filter(None, (
            f"LOT {item.get('lotNumber')}" if item.get("lotNumber") else None,
            status.upper() if status else None,
            clean(item.get("addressLine1")),
            clean(item.get("addressLine2")),
            descriptor,
            price_text,
        )))
        rows.append({
            "address": address,
            "auction_date": auction_date,
            "description": clean(item.get("description")),
            "guide_price_gbp": price if descriptor and re.search(r"guide|available|withdrawn", descriptor, re.I) else None,
            "image_url": first_image(item.get("image")),
            "lot_number": clean(item.get("lotNumber")),
            "property_type": None,
            "raw_card_text": raw,
            "result_price_gbp": price if descriptor and "sold" in descriptor.lower() else None,
            "result_status": result_status,
            "source": "Barnard Marcus Auctions",
            "source_auction_id": source_auction_id,
            "source_record_id": f"barnard-marcus-property:{item['id']}",
            "source_url": item.get("url"),
            "status": status,
        })

    ids = [row["source_record_id"] for row in rows]
    lots = [row["lot_number"] for row in rows]
    if len(ids) != len(set(ids)) or len(lots) != len(set(lots)):
        raise RuntimeError("source IDs or lot numbers are not unique")

    return {
        "schema_version": 1,
        "auctioneer": "Barnard Marcus Auctions",
        "capture_scope": f"all first-party result-card rows for the {auction_date} auction",
        "source_url": page_url,
        "archive_url": f"{BASE}/auctions/previous/",
        "auction_date": auction_date,
        "source_auction_id": source_auction_id,
        "lot_enumeration_complete": True,
        "published_rows": len(rows),
        "unnumbered_rows": sum(row["lot_number"] is None for row in rows),
        "pagination_pages_captured": list(range(1, pages + 1)),
        "pagination_pages_expected": pages,
        "capture_method": "official SearchApi result cards with Show All; every API page reconciled",
        "lot_records": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page_url")
    parser.add_argument("auction_date")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = harvest(args.page_url, args.auction_date)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": payload["published_rows"],
        "address_rows": sum(bool(row["address"]) for row in payload["lot_records"]),
        "partial_rows": sum(not row["address"] for row in payload["lot_records"]),
        "pages": payload["pagination_pages_expected"],
    }))


if __name__ == "__main__":
    main()
