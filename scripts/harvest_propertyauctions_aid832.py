#!/usr/bin/env python3
"""Capture the complete retained Allsop Residential AID 832 result grid.

PropertyAuctions currently exposes this catalogue as one unpaginated Telerik
grid.  The auction title and exact date still survive on the page, so this
collector deliberately refuses to run if that identity or any of the published
row/count invariants changes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.propertyauctions.com/Results/LotList.aspx?AID=832"
EXPECTED_TITLE = "29TH MAY 2013 ALLSOP RESIDENTIAL AUCTION - CUMBERLAND HOTEL"
AUCTION_DATE = "2013-05-29"
EXPECTED_OFFERED = 332
EXPECTED_SOLD = 268
EXPECTED_PUBLISHED_ROWS = 372
EXPECTED_BASE_LOTS = 361
EXPECTED_LETTERED_LOTS = {
    "56A", "56B", "56C", "56D", "57A", "112A", "112B", "199A",
    "235A", "293A", "293B",
}
OUTPUT = ROOT / "data/historical_source_corpus/allsop_2013_05_29_aid832_propertyauctions_results.json"
RAW = ROOT / "data/historical_source_corpus/raw/allsop_2013_05_29_aid832.html.gz"


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def money(value: object) -> float | None:
    text = clean(value).replace("£", "").replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([MK])?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    if match.group(2):
        amount *= {"M": 1_000_000, "K": 1_000}[match.group(2).upper()]
    return amount


def parse_result(text: str) -> tuple[str | None, float | None, float | None]:
    normalized = clean(text)
    lowered = normalized.casefold()
    if normalized.startswith("£"):
        return "sold", money(normalized), None
    if lowered.startswith("available at"):
        return "available", None, money(normalized)
    for label in ("sold prior", "sold post", "withdrawn", "available", "unsold", "sold"):
        if lowered.startswith(label):
            return label, None, None
    return lowered or None, None, None


def text_of(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return clean(node.get_text(" ", strip=True)) if node else ""


def capture() -> dict:
    response = requests.get(URL, timeout=90, headers={"User-Agent": "Commercial-Auction-Sniper historical corpus/1.0"})
    response.raise_for_status()
    html = response.content
    soup = BeautifulSoup(html, "html.parser")

    title = text_of(soup, "#ContentPlaceHolder1_lblAuctionTitle")
    offered = int(text_of(soup, "#ContentPlaceHolder1_lblIbOffered"))
    sold = int(text_of(soup, "#ContentPlaceHolder1_lblIbSold"))
    sold_percent = float(text_of(soup, "#ContentPlaceHolder1_lblIbSoldPercent"))
    disclosed_value = money(text_of(soup, "#ContentPlaceHolder1_lblIbValue"))
    if title != EXPECTED_TITLE:
        raise ValueError(f"AID 832 identity changed: {title!r}")
    if (offered, sold) != (EXPECTED_OFFERED, EXPECTED_SOLD):
        raise ValueError(f"AID 832 headline counts changed: offered={offered}, sold={sold}")

    lots = []
    for tr in soup.select("#ctl00_ContentPlaceHolder1_rgResults_ctl00 tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.select("td")]
        if len(cells) < 4 or not re.fullmatch(r"\d+[A-Za-z]?", cells[0]):
            continue
        lot, property_type, locality, result = cells[:4]
        status, result_price, available_price = parse_result(result)
        lots.append({
            "source_record_id": f"allsop-aid832-lot-{lot.casefold()}",
            "source_auction_id": "allsop:propertyauctions:832",
            "record_type": "lot_partial",
            "auction_date": AUCTION_DATE,
            "lot_number": lot,
            "address": None,
            "locality": locality or None,
            "property_type": property_type or None,
            "result": result or None,
            "result_status": status,
            "result_price_gbp": result_price,
            "available_price_gbp": available_price,
            "source_url": URL,
            "source_urls": [URL],
        })

    labels = [row["lot_number"] for row in lots]
    if len(lots) != EXPECTED_PUBLISHED_ROWS or len(set(labels)) != EXPECTED_PUBLISHED_ROWS:
        raise ValueError(f"AID 832 row reconciliation failed: rows={len(lots)}, unique={len(set(labels))}")
    base = {int(label) for label in labels if label.isdigit()}
    lettered = {label for label in labels if not label.isdigit()}
    if base != set(range(1, EXPECTED_BASE_LOTS + 1)) or lettered != EXPECTED_LETTERED_LOTS:
        raise ValueError("AID 832 lot-number reconciliation failed")
    if (not re.search(r'\\?"PageCount\\?":1', response.text) or
            not re.search(r'\\?"AllowPaging\\?":false', response.text)):
        raise ValueError("AID 832 no longer exposes a single unpaginated result grid")

    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_sha = hashlib.sha256(html).hexdigest()
    payload = {
        "schema_version": 1,
        "auctioneer": "Allsop",
        "auction_title": title,
        "auction_date": AUCTION_DATE,
        "propertyauctions_aid": 832,
        "archive_url": URL,
        "captured_at_utc": captured_at,
        "catalogue_complete": True,
        "catalogue_lot_count": EXPECTED_PUBLISHED_ROWS,
        "published_grid_rows": EXPECTED_PUBLISHED_ROWS,
        "published_base_lot_extent": EXPECTED_BASE_LOTS,
        "published_lettered_lots": sorted(EXPECTED_LETTERED_LOTS),
        "published_offered_count": offered,
        "published_sold_count": sold,
        "published_sold_percent": sold_percent,
        "published_disclosed_value_gbp": disclosed_value,
        "pages_expected": 1,
        "pages_captured": 1,
        "completion_scope": (
            "all 372 distinct rows in the surviving first-party-hosted result grid; "
            "the source's offered count of 332 is retained separately and does not omit "
            "withdrawn, available, sold-prior, sold-post or lettered published rows"
        ),
        "raw_snapshot_path": str(RAW.relative_to(ROOT)),
        "raw_snapshot_sha256": raw_sha,
        "lots": lots,
    }

    RAW.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    preserve_snapshot = False
    if OUTPUT.exists() and RAW.exists():
        previous = json.loads(OUTPUT.read_text())
        volatile = {"captured_at_utc", "raw_snapshot_sha256"}
        comparable = {key: value for key, value in payload.items() if key not in volatile}
        old_comparable = {key: value for key, value in previous.items() if key not in volatile}
        previous_raw_sha = previous.get("raw_snapshot_sha256")
        try:
            saved_raw_sha = hashlib.sha256(gzip.decompress(RAW.read_bytes())).hexdigest()
        except (OSError, EOFError):
            saved_raw_sha = None
        if comparable == old_comparable and saved_raw_sha == previous_raw_sha:
            preserve_snapshot = True
            payload["captured_at_utc"] = previous.get("captured_at_utc", captured_at)
            payload["raw_snapshot_sha256"] = previous_raw_sha
    if not preserve_snapshot:
        RAW.write_bytes(gzip.compress(html, mtime=0))
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    result = capture()
    print(json.dumps({
        "source": result["archive_url"],
        "auction_date": result["auction_date"],
        "published_rows": result["published_grid_rows"],
        "offered": result["published_offered_count"],
        "catalogue_complete": result["catalogue_complete"],
        "output": str(OUTPUT.relative_to(ROOT)),
    }))
