#!/usr/bin/env python3
"""Harvest every public result-card row from one Barnard Marcus auction."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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


def fetch_text(url: str, attempts: int = 4) -> str:
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=60) as response:
                return response.read().decode("utf-8")
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
    page = fetch_text(page_url)
    match = re.search(r'endpointUrl&quot;:&quot;([^&]+(?:&amp;[^&]+)+)', page)
    if not match:
        raise RuntimeError("Barnard Marcus search endpoint was not found")
    query = parse_qs(urlparse(html.unescape(match.group(1))).query)
    return query["auctionHouseId"][0], query["auctionId"][0]


def sitemap_lot_urls(page_url: str) -> list[str]:
    """Return every first-party lot detail URL for one archived auction."""
    path = urlparse(page_url).path.rstrip("/") + "/"
    sitemap = fetch_text(f"{BASE}/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap, flags=re.I)
    lot_urls = []
    for url in urls:
        parsed = urlparse(html.unescape(url))
        if parsed.netloc != urlparse(BASE).netloc or not parsed.path.startswith(path):
            continue
        suffix = parsed.path[len(path):].strip("/")
        if re.fullmatch(r"\d+", suffix):
            lot_urls.append(urljoin(BASE, parsed.path))
    return sorted(set(lot_urls), key=lambda url: int(url.rstrip("/").rsplit("/", 1)[-1]))


def item_from_lot_page(url: str) -> dict:
    """Extract the active card JSON embedded in an archived lot detail page."""
    lot_id = int(url.rstrip("/").rsplit("/", 1)[-1])
    page = fetch_text(url)
    attrs = re.findall(r"data-dc-lot-item-options='([^']+)'", page)
    for value in attrs:
        payload = json.loads(html.unescape(value))
        item = payload.get("item", payload)
        if item.get("id") == lot_id:
            return item
    raise RuntimeError(f"active lot card {lot_id} was not found in {url}")


def harvest(
    page_url: str,
    auction_date: str,
    workers: int = 4,
    allow_incomplete: bool = False,
) -> dict:
    house_id, auction_id = parse_ids(page_url)
    endpoint = (
        f"{BASE}/umbraco/Api/SearchApi/Search?auctionHouseId={house_id}"
        f"&auctionId={auction_id}&lots=1&sortBy=LotAsc&page={{page}}"
    )
    first = fetch_json(endpoint.format(page=1))
    pagination = first["pagination"]
    pages = pagination["pageCount"]
    inventory_method = "search_api"
    inventory_urls: list[str] = []
    if pages:
        remaining = list(range(2, pages + 1))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            payloads = list(pool.map(lambda page: fetch_json(endpoint.format(page=page)), remaining))
        items = list(first["items"])
        for page, payload in zip(remaining, payloads):
            page_meta = payload["pagination"]
            if (
                page_meta["currentPage"] != page
                or page_meta["pageCount"] != pages
                or page_meta["totalCount"] != pagination["totalCount"]
            ):
                raise RuntimeError(f"page {page} did not reconcile")
            items.extend(payload["items"])
        expected_rows = pagination["totalCount"]
    else:
        # Some retained auction pages outlive their SearchApi index. The public
        # sitemap still provides an exact lot-page inventory, and every detail
        # page embeds the same lot-card JSON used by the search API.
        inventory_method = "sitemap_lot_pages"
        inventory_urls = sitemap_lot_urls(page_url)
        if not inventory_urls:
            raise RuntimeError("SearchApi returned zero rows and sitemap has no lot pages")
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            items = list(pool.map(item_from_lot_page, inventory_urls))
        expected_rows = len(inventory_urls)

    reconciled = len(items) == expected_rows
    if not reconciled and not allow_incomplete:
        raise RuntimeError(f"expected {expected_rows} rows, got {len(items)}")

    source_auction_id = f"barnard-marcus:{auction_date}"
    rows = []
    for item in items:
        address = ", ".join(filter(None, (clean(item.get("addressLine1")), clean(item.get("addressLine2"))))) or None
        lot_number = clean(item.get("lotNumber"))
        if lot_number and lot_number.upper() in {"TBC", "TBA", "N/A"}:
            lot_number = None
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
            "lot_number": lot_number,
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
    numbered_lots = [lot for lot in lots if lot is not None]
    if len(ids) != len(set(ids)):
        raise RuntimeError("source IDs are not unique")
    duplicate_lot_numbers = len(numbered_lots) - len(set(numbered_lots))
    if duplicate_lot_numbers and inventory_method == "search_api":
        raise RuntimeError("lot numbers are not unique")

    return {
        "schema_version": 1,
        "auctioneer": "Barnard Marcus Auctions",
        "capture_scope": f"all first-party result-card rows for the {auction_date} auction",
        "source_url": page_url,
        "archive_url": f"{BASE}/auctions/previous/",
        "auction_date": auction_date,
        "source_auction_id": source_auction_id,
        "lot_enumeration_complete": reconciled,
        "published_rows": len(rows),
        "source_reported_rows": expected_rows,
        "reconciliation_shortfall": expected_rows - len(rows),
        "unnumbered_rows": sum(row["lot_number"] is None for row in rows),
        "duplicate_lot_numbers": duplicate_lot_numbers,
        "pagination_pages_captured": list(range(1, pages + 1)),
        "pagination_pages_expected": pages,
        "inventory_method": inventory_method,
        "sitemap_lot_urls_expected": len(inventory_urls) if inventory_urls else None,
        "sitemap_lot_urls_captured": len(items) if inventory_urls else None,
        "capture_method": (
            "official SearchApi result cards with Show All; every API page reconciled"
            if reconciled and inventory_method == "search_api"
            else "official sitemap lot-page inventory; active embedded lot-card JSON "
            "extracted from every retained first-party detail page and reconciled"
            if reconciled
            else "official source inventory traversed, but the expected total exceeds "
            "the returned rows"
        ),
        "lot_records": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page_url")
    parser.add_argument("auction_date")
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    payload = harvest(
        args.page_url,
        args.auction_date,
        args.workers,
        args.allow_incomplete,
    )
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": payload["published_rows"],
        "address_rows": sum(bool(row["address"]) for row in payload["lot_records"]),
        "partial_rows": sum(not row["address"] for row in payload["lot_records"]),
        "pages": payload["pagination_pages_expected"],
    }))


if __name__ == "__main__":
    main()
