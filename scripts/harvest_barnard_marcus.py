#!/usr/bin/env python3
"""Harvest every public result-card row from one Barnard Marcus auction."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import hashlib
import json
import re
import time
import requests
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen


BASE = "https://www.barnardmarcusauctions.co.uk"
UA = "Mozilla/5.0 (compatible; Commercial-Auction-Sniper historical corpus)"


def fetch_json(url: str, attempts: int = 4) -> dict:
    for attempt in range(attempts):
        try:
            response=requests.get(url,headers={"User-Agent":UA},timeout=(10,30))
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def fetch_json_cached(url: str, cache_dir: Path | None = None) -> dict:
    """Checkpoint each response so a bounded run can resume mid-catalogue."""
    if cache_dir is None:
        return fetch_json(url)
    cache_dir = Path(cache_dir)
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + '.json')
    try:
        saved = json.loads(path.read_text())
        if saved['source_url'] == url and 0 <= time.time() - saved['retrieved_at_epoch'] < 21600:
            return saved['payload']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    payload = fetch_json(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'source_url': url, 'retrieved_at_epoch': time.time(), 'payload': payload}))
    temporary.replace(path)
    return payload


def fetch_text(url: str, attempts: int = 4) -> str:
    for attempt in range(attempts):
        try:
            response=requests.get(url,headers={"User-Agent":UA},timeout=(10,30))
            response.raise_for_status()
            return response.content.decode('utf-8')
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


def sitemap_lot_urls(page_url: str, sitemap_text: str | None = None) -> list[str]:
    """Return every first-party lot detail URL for one archived auction."""
    path = urlparse(page_url).path.rstrip("/") + "/"
    sitemap = sitemap_text if sitemap_text is not None else fetch_text(f"{BASE}/sitemap.xml")
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


def items_to_rows(items, auction_date):
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
            "result_price_gbp": price if descriptor and re.match(r'^sold\b',descriptor,re.I) else None,
            "result_status": result_status,
            "source": "Barnard Marcus Auctions",
            "source_auction_id": source_auction_id,
            "source_record_id": f"barnard-marcus-property:{item['id']}",
            "source_url": item.get("url"),
            "status": status,
        })

    return rows


def harvest(
    page_url: str,
    auction_date: str,
    workers: int = 4,
    allow_incomplete: bool = False,
    cache_dir: Path | None = None,
) -> dict:
    house_id, auction_id = parse_ids(page_url)
    endpoint = (
        f"{BASE}/umbraco/Api/SearchApi/Search?auctionHouseId={house_id}"
        f"&auctionId={auction_id}&lots=1&sortBy=LotAsc&page={{page}}"
    )
    first = fetch_json(endpoint.format(page=1))
    pagination = first["pagination"]
    pages = pagination["pageCount"]
    reconciliation_errors = []
    reported_totals = {pagination["totalCount"]}
    inventory_method = "search_api"
    inventory_urls: list[str] = []
    if pages:
        remaining = list(range(2, pages + 1))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            payloads = list(pool.map(lambda page: fetch_json_cached(endpoint.format(page=page), cache_dir), remaining))
        items = list(first["items"])
        for page, payload in zip(remaining, payloads):
            page_meta = payload["pagination"]
            if page_meta["currentPage"] != page:
                raise RuntimeError(f"page {page} returned a different page identity")
            reported_totals.add(page_meta["totalCount"])
            if page_meta["pageCount"] != pages or page_meta["totalCount"] != pagination["totalCount"]:
                message = f"page {page} reports {page_meta['totalCount']} lots / {page_meta['pageCount']} pages; first page reports {pagination['totalCount']} / {pages}"
                if not allow_incomplete:
                    raise RuntimeError(message)
                reconciliation_errors.append(message)
            items.extend(payload["items"])
        expected_rows = max(reported_totals)
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

    unique_items = {}
    for item in items:
        if item["id"] in unique_items:
            if not allow_incomplete:
                raise RuntimeError("source IDs are not unique")
            reconciliation_errors.append(f"duplicate source ID {item['id']} across source pages")
        else:
            unique_items[item["id"]] = item
    items = list(unique_items.values())
    reconciled = len(items) == expected_rows and not reconciliation_errors
    if not reconciled and not allow_incomplete:
        raise RuntimeError(f"expected {expected_rows} rows, got {len(items)}")

    rows = items_to_rows(items, auction_date)

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
        "source_auction_id": f"barnard-marcus:{auction_date}",
        "lot_enumeration_complete": reconciled,
        "catalogue_complete": reconciled,
        "catalogue_lot_count": expected_rows,
        "completion_scope": (
            f"all {expected_rows} first-party lot identities captured exactly once from "
            f"{pages} reconciled search pages"
            if inventory_method == "search_api"
            else f"all {expected_rows} first-party lot identities captured exactly once from "
            "the complete retained sitemap lot-page inventory"
        ),
        "published_rows": len(rows),
        "source_reported_rows": expected_rows,
        "reconciliation_shortfall": expected_rows - len(rows),
        "reconciliation_errors": reconciliation_errors,
        "source_reported_totals": sorted(reported_totals),
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
            else "official source pages traversed; source counts or identities remain unreconciled"
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



def recover_sitemap_rows(payload, lot_urls=None):
    """Recover and reconcile the exact retained first-party lot-page inventory.

    SearchApi totals can drift while its pages are being traversed, which leaves
    duplicated rows and mutually inconsistent count metadata.  The sitemap is a
    stable first-party identity inventory: completion is claimed only when the
    unique banked property IDs exactly equal every retained detail-page ID.
    Conflicting SearchApi metadata remains preserved as diagnostics.
    """
    if payload.get('catalogue_complete'):
        return payload
    records=payload.get('lot_records') or []
    have_ids=[row.get('source_record_id') for row in records]
    have=set(have_ids)
    try:
        urls=lot_urls if lot_urls is not None else sitemap_lot_urls(payload['source_url'])
    except Exception as exc:
        payload.setdefault('reconciliation_errors',[]).append(f'Sitemap discovery failed: {str(exc)[:200]}')
        return payload
    sitemap_ids={'barnard-marcus-property:'+url.rstrip('/').rsplit('/',1)[-1] for url in urls}
    missing=[url for url in urls if 'barnard-marcus-property:'+url.rstrip('/').rsplit('/',1)[-1] not in have]
    recovered=[];recovered_urls=[]
    for url in missing:
        try:
            recovered.extend(items_to_rows([item_from_lot_page(url)],payload['auction_date']))
            recovered_urls.append(url)
        except Exception as exc:
            payload.setdefault('reconciliation_errors',[]).append(f'Sitemap recovery failed {url}: {str(exc)[:200]}')
    payload['lot_records'].extend(recovered)
    payload['published_rows']=len(payload['lot_records'])
    row_ids=[row.get('source_record_id') for row in payload['lot_records']]
    row_id_set=set(row_ids)
    missing_after=sorted(sitemap_ids-row_id_set)
    extra_rows=sorted(row_id_set-sitemap_ids)
    exact_identity_match=(
        bool(sitemap_ids)
        and all(row_ids)
        and len(row_ids)==len(row_id_set)
        and row_id_set==sitemap_ids
    )
    payload['sitemap_recovery']={
        'expected_urls':len(urls),
        'missing_before_recovery':len(missing),
        'rows_recovered':len(recovered),
        'recovered_urls':recovered_urls,
        'missing_after_recovery':missing_after,
        'rows_not_in_sitemap':extra_rows,
        'identity_sha256':hashlib.sha256('\n'.join(sorted(sitemap_ids)).encode()).hexdigest(),
        'exact_identity_match':exact_identity_match,
    }
    if exact_identity_match:
        variances=payload.get('reconciliation_errors') or []
        if variances:
            payload['search_api_variance_errors']=variances
        payload['reconciliation_errors']=[]
        payload['source_reported_rows']=len(urls)
        payload['catalogue_lot_count']=len(urls)
        payload['reconciliation_shortfall']=0
        payload['lot_enumeration_complete']=True
        payload['catalogue_complete']=True
        payload['inventory_method']='search_api_plus_sitemap_identity_reconciliation'
        payload['completion_scope']=(
            f'all {len(urls)} retained first-party sitemap lot identities captured exactly once; '
            'SearchApi pagination variance retained separately as diagnostic evidence'
        )
        payload['capture_method']=(
            'official SearchApi result cards reconciled to the complete retained first-party '
            'sitemap lot-page identity inventory'
        )
    else:
        payload['reconciliation_shortfall']=len(missing_after)
    return payload

if __name__ == "__main__":
    main()
