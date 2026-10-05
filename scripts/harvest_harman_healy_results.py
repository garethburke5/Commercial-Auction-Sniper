"""Bank Harman Healy's complete retained first-party past-auctions grid.

The EIG-powered page publishes an explicit archive denominator and stable lot
identities.  This collector walks every results page, preserves all property
types (including residential lots), and only marks the retained archive
complete after the denominator, pagination and identities reconcile exactly.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://harman-healy.co.uk"
ARCHIVE_URL = BASE + "/past-auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PAGE_SIZE = 50
COUNT_RE = re.compile(r"Showing\s+results\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)", re.I)
LOT_RE = re.compile(r"\bLot\s+([^|]+?)\s*\|", re.I)
DETAIL_RE = re.compile(r"/lot/details/([0-9a-f-]+|\d+)", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def archive_page_url(page: int) -> str:
    return (
        f"{ARCHIVE_URL}?page={page}&viewType=List&"
        "order=OrderOfSaleAscending&lotResultType=All"
    )


def published_total(html: str) -> int:
    match = COUNT_RE.search(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
    if not match:
        raise ValueError("retained archive denominator is absent")
    return int(match.group(1).replace(",", ""))


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").casefold()
    if "sold prior" in text:
        status = "sold_prior"
    elif "sold post" in text or "sold after" in text:
        status = "sold_after"
    elif "sold" in text:
        status = "sold"
    elif "withdrawn" in text:
        status = "withdrawn"
    elif "unsold" in text or "no bids" in text:
        status = "unsold"
    else:
        status = "unknown"
    return status, pounds(value) if status in {"sold", "sold_prior", "sold_after"} else None


def parse_page(html: str, page: int, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".lot-panel")
    if not cards:
        raise ValueError(f"archive page {page} contains no lot cards")
    rows = []
    for page_position, card in enumerate(cards, 1):
        heading = card.select_one(".panel-title")
        time_node = card.select_one("time[datetime]")
        address_node = card.select_one(".list-address")
        detail_node = card.select_one('a[href*="/lot/details/"]')
        lot_match = LOT_RE.search(clean(heading.get_text(" ", strip=True)) or "") if heading else None
        detail_url = urljoin(BASE, detail_node.get("href") or "") if detail_node else None
        id_match = DETAIL_RE.search(detail_url or "")
        if not all((heading, time_node, address_node, lot_match, detail_url, id_match)):
            raise ValueError(f"archive page {page} card {page_position} lacks identity, date, lot or address")
        source_id = id_match.group(1).lower()
        auction_date = datetime.fromisoformat(time_node["datetime"]).date().isoformat()
        lot_number = clean(lot_match.group(1))
        address = clean(address_node.get_text(" ", strip=True))
        if not lot_number or not address:
            raise ValueError(f"archive page {page} card {page_position} has an empty lot or address")
        type_node = card.select_one(".lot-data-heading")
        property_type = clean(type_node.get_text(" ", strip=True)) if type_node else None
        description_node = card.select_one(".list-info p")
        description = clean(description_node.get_text(" ", strip=True)) if description_node else None
        result_node = card.select_one(".list-guideprice")
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        status, sale_price = status_and_price(result_text)
        image_node = card.select_one("img.list-image[src]")
        image_url = urljoin(BASE, image_node["src"]) if image_node else None
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row(
            "Harman Healy", f"harman-healy:{auction_date}", auction_date,
            lot_number, source_id, detail_url,
        )
        row.update(
            appearance_id=f"Harman Healy|eig-lot:{source_id}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, property_type, description]))),
            property_type=property_type,
            sale_price=sale_price,
            status=status,
            description=description,
            image_urls=[image_url] if image_url else [],
            property_id=source_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record",
            source_position=(page - 1) * PAGE_SIZE + page_position,
            source_page=page,
            source_result_text=result_text,
            auction_date_basis="published individual lot auction end date",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError(f"archive page {page} contains duplicate EIG lot identities")
    return rows


def fetch(page: int) -> tuple[int, bytes, str]:
    response = requests.get(archive_page_url(page), headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"archive page {page} response is unexpectedly short")
    return page, response.content, response.url


def harvest() -> None:
    first_page, first_raw, first_resolved = fetch(1)
    first_html = first_raw.decode("utf-8", "replace")
    expected = published_total(first_html)
    total_pages = math.ceil(expected / PAGE_SIZE)
    fetched = {first_page: (first_raw, first_resolved, None)}
    state_path = corpus.DATA / "auctions/harman-healy/retained-past-auctions.json"
    cached_state = json.loads(state_path.read_text()) if state_path.exists() else None
    cached_pages = {}
    if cached_state and cached_state.get("catalogue_complete"):
        for evidence in cached_state.get("source_evidence") or []:
            snapshot_name = evidence.get("snapshot_path")
            snapshot = corpus.ROOT / snapshot_name if snapshot_name else None
            if snapshot and snapshot.exists() and evidence.get("page"):
                saved = corpus.read_gzip(snapshot)
                cached_pages[int(evidence["page"])] = (
                    saved["html"].encode("utf-8"), evidence["source_url"], saved["evidence"],
                )

    old_expected = int((cached_state or {}).get("published_lots_offered") or 0)
    old_pages = math.ceil(old_expected / PAGE_SIZE) if old_expected else 0
    if expected == old_expected:
        reusable = set(range(2, total_pages + 1))
    elif expected > old_expected and total_pages >= old_pages and old_pages:
        # New rows append to the retained archive. Re-fetch the old partial tail
        # plus every newly created page; immutable earlier full pages are reparsed
        # from their saved snapshots.
        reusable = set(range(2, max(2, old_pages)))
    else:
        reusable = set()
    for page in reusable:
        if page in cached_pages:
            fetched[page] = cached_pages[page]
    pages_to_fetch = [page for page in range(2, total_pages + 1) if page not in fetched]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, page): page for page in pages_to_fetch}
        for future in as_completed(futures):
            page, raw, resolved = future.result()
            fetched[page] = (raw, resolved, None)

    observed, evidence_pages = [], []
    for page in range(1, total_pages + 1):
        raw, resolved, saved_evidence = fetched[page]
        html = raw.decode("utf-8", "replace")
        page_expected = published_total(html)
        if page_expected != expected:
            raise ValueError("archive denominator changed during pagination; retry required")
        if saved_evidence:
            evidence = saved_evidence
        else:
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/harman-healy" / f"past-auctions-page-{page}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party retained past-auctions lot grid",
                "page": page,
                "total_pages": total_pages,
                "published_archive_lots": expected,
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        rows = parse_page(html, page, evidence)
        expected_on_page = PAGE_SIZE if page < total_pages else expected - PAGE_SIZE * (total_pages - 1)
        if len(rows) != expected_on_page:
            raise ValueError(f"archive page {page} reconciled {len(rows)} of {expected_on_page} expected rows")
        observed.extend(rows)
        evidence_pages.append(evidence)

    identities = [row["appearance_id"] for row in observed]
    if len(observed) != expected or len(identities) != len(set(identities)):
        raise ValueError(f"archive reconciled {len(observed)} rows and {len(set(identities))} identities of {expected}")

    appearance_path = corpus.DATA / "appearances/harman-healy/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in observed})
    total = corpus.write_rows("harman-healy/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    state = {
        "auctioneer": "Harman Healy",
        "source_auction_id": "harman-healy:retained-past-auctions",
        "auction_date": None,
        "catalogue_complete": True,
        "source_rows_complete": True,
        "published_lots_offered": expected,
        "visible_source_rows": len(observed),
        "lots_captured": len(observed),
        "source_url": first_resolved,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "completion_scope": "every lot card across every page of the first-party retained past-auctions grid",
        "source_evidence": evidence_pages,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(state_path, state)
    summary = {
        "checked_at": corpus.now(),
        "source_url": first_resolved,
        "published_archive_lots": expected,
        "pages_captured": total_pages,
        "pages_expected": total_pages,
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "catalogue_completion_claimed": True,
        "completion_scope": state["completion_scope"],
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "harman_healy_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    harvest()
