#!/usr/bin/env python3
"""Bank Halls' retained collective property and land auction evidence.

The runner deliberately batches whole first-party catalogues/results.  It does
not treat event or directory pages as property rows and it never infers a
missing original catalogue denominator.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import io
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "auction_history"
SOURCE_DIR = DATA / "sources" / "halls" / "first-party"
APPEARANCE_SHARD = DATA / "appearances" / "halls" / "canonical.jsonl.gz"
AUCTION_DIR = DATA / "auctions" / "halls"
SUMMARY_PATH = DATA / "halls_collective_collection.json"
CONTINUATION_PATH = DATA / "continuation_collection.json"
AUCTIONEER = "Halls"
LEGAL_NAME = "HALLS HOLDINGS LIMITED"
COMPANY_NUMBER = "06597073"
USER_AGENT = "AuctionGeekHistoricalCorpus/1.0 (+https://auctiongeek.co.uk)"

NOVEMBER_RESULTS_URL = (
    "https://estate-agents.hallsgb.com/blog/"
    "lots-sell-for-over-2m-at-collective-property-and-land-auction"
)
SEPTEMBER_2025_RESULTS_URL = (
    "https://estate-agents.hallsgb.com/blog/"
    "sixteen-lots-sell-for-2m-in-our-latest-property-and-land-auction"
)
SEPTEMBER_2026_RESULTS_URL = (
    "https://estate-agents.hallsgb.com/"
    "september-2026-property-and-land-auction-results"
)

EVENTS = [
    {
        "date": "2025-07-25",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-25-july-2025",
        "catalogue_url": "https://cdn.webdadi.net/media/14a38cd9-5c81-46e2-9cb3-054b31717756.pdf",
        "expected_lots": 12,
    },
    {
        "date": "2025-09-26",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-26-sep-2025",
        "results_url": SEPTEMBER_2025_RESULTS_URL,
        "expected_lots": 16,
        "identifiable_rows": 15,
    },
    {
        "date": "2025-11-28",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-28-nov-2025",
        "catalogue_url": "https://cdn.webdadi.net/media/43e068fe-1eba-43b6-bfef-d3b38f4f6ca2.pdf",
        "results_url": NOVEMBER_RESULTS_URL,
        "expected_lots": 21,
    },
    {
        "date": "2026-05-01",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-1-may-2026",
        "catalogue_url": "https://cdn.webdadi.net/media/6692462c-430e-4690-8c0e-88e12e20b11f.pdf",
        "expected_lots": 16,
    },
    {
        "date": "2026-07-24",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-24-july-2026",
        "catalogue_url": "https://cdn.webdadi.net/media/4086885f-6c7e-4618-a1ca-42918afa2386.pdf",
        "expected_lots": 21,
    },
    {
        "date": "2026-09-25",
        "event_url": "https://estate-agents.hallsgb.com/event/collective-property-and-land-auction-25-sept-2026",
        "results_url": SEPTEMBER_2026_RESULTS_URL,
        "expected_lots": 22,
    },
]

EVENT_PROPERTY_LOTS = {
    "2026-05-01": {"34570198": 14},
    "2026-07-24": {
        "34718318": 1,
        "34726819": 12,
        "34756535": 13,
        "34729135": 20,
    },
    "2026-09-25": {
        "34883994": 1,
        "34877178": 2,
        "33347576": 4,
        "34877163": 6,
        "34877160": 8,
        "34877169": 9,
        "34884244": 10,
        "34884253": 11,
        "34892497": 12,
        "34892499": 13,
        "34877175": 14,
        "34877164": 16,
        "34889374": 17,
        "34862829": 22,
    },
}

# The November result article identifies 17 of the 21 catalogue lots and
# publishes their achieved prices.  The remaining four retain null outcomes.
NOVEMBER_SALE_PRICES = {
    1: 70000,
    2: 84000,
    3: 80000,
    5: 152000,
    6: 123000,
    7: 80000,
    8: 221000,
    11: 38000,
    12: 125000,
    13: 109000,
    14: 130000,
    15: 140000,
    16: 160000,
    17: 104000,
    18: 111000,
    20: 125000,
    21: 350000,
}

NOVEMBER_RESULT_TOKENS = {
    1: "Mill Meadow",
    2: "4 and 12, Kenrick Close",
    3: "4 and 12, Kenrick Close",
    5: "2, The Elms",
    6: "5, Balmer Crescent",
    7: "Ercall Heath",
    8: "38, Diksmuide Drive",
    11: "paddock at Brynffynon",
    12: "8, Highfields",
    13: "83, Shrewsbury Road",
    14: "2, Rea Bridge",
    15: "9 and 13, Cross Bank",
    16: "9 and 13, Cross Bank",
    17: "2, Caldecott Crescent",
    18: "22, Kerry Green",
    20: "Blue School",
    21: "Bank Cottage",
}

# Fifteen of the sixteen sold September 2025 lots are individually named in
# the first-party result article.  The unidentified sixteenth stays denominator
# evidence only and is never fabricated as a property row.
SEPTEMBER_2025_ROWS = [
    (1, "1 and 2 Milebarn Cottages, Holt Road, Llan-y-Pwll, Wrexham", 150000, None, 252000, "residential"),
    (2, "2 Rockhall Villas, Preston Brockhurst, Shrewsbury", 126000, 144000, 150000, "residential"),
    (3, "Farthings, Fox Lane, West Felton, Oswestry", 100000, None, 186500, "residential"),
    (4, "Dove Barn, Lighteach Road, Prees", 50000, 75000, 115000, "unknown"),
    (5, "59 Grotto Road, Market Drayton", 126000, 144000, 127000, "residential"),
    (6, "61 Grotto Road, Market Drayton", 126000, 144000, 126000, "residential"),
    (7, "12 Weston Road, Bucknell", 90000, None, 126000, "residential"),
    (8, "28 Highfields, Market Drayton", 72000, 90000, 120000, "residential"),
    (9, "3 Manor Cottages, Marton", 99000, 117000, 115000, "residential"),
    (10, "1 Vine Cottages, Weston Rhyn, Oswestry", 90000, None, 100000, "residential"),
    (11, "3 Highfields, Market Drayton", 72000, 90000, 100000, "residential"),
    (12, "18 Barnard Street, Wem", 94500, 117000, 95000, "residential"),
    (13, "20 Barnard Street, Wem", 94500, 117000, 92000, "residential"),
    (14, "11 Market Street, Craven Arms", 80000, 100000, 100000, "mixed-use"),
    (15, "0.5 acres of amenity land at Sarnau, Llanymynech", 5000, 10000, 38000, "land"),
]

NEXT_TARGET = (
    "Extend the Halls runner to the retained 2024 collective-auction catalogue and result assets. "
    "Start with exact-dated first-party PDFs or result articles that expose complete numbered lot inventories, "
    "then move backward through 2023 and earlier years. Keep inaccessible WordPress PDF objects as bounded "
    "blockers unless a byte-accessible CDN, saved snapshot or materially different retained publisher route exists. "
    "National completeness remains false."
)

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", compact(value).lower()).strip()


def money(value: str | None) -> int | None:
    if not value:
        return None
    match = MONEY_RE.search(value)
    return int(match.group(1).replace(",", "")) if match else None


def source_id(date: str) -> str:
    return f"halls:collective:{date}"


def snapshot(data: bytes, stem: str, suffix: str, source_url: str, retrieved_at: str) -> dict[str, Any]:
    sha = hashlib.sha256(data).hexdigest()
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCE_DIR / f"{stem}-{sha[:20]}.{suffix}.gz"
    if not path.exists():
        path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "sha256": sha,
        "snapshot_path": str(path.relative_to(ROOT)),
    }


def fetch(session: requests.Session, url: str, expected: str | None = None) -> tuple[bytes, str]:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    if expected == "pdf" and not response.content.startswith(b"%PDF"):
        raise ValueError(f"expected PDF from {url}; received {response.headers.get('content-type')}")
    if expected == "html" and b"<html" not in response.content[:5000].lower():
        raise ValueError(f"expected HTML from {url}")
    return response.content, now()


def guide_values(text: str) -> tuple[int | None, int | None, str | None]:
    match = re.search(
        r"Guide\s*Price\s*[:\-]?\s*(£\s*[\d,]+)(?:\s*(?:-|–|to)\s*(£\s*[\d,]+))?",
        text,
        re.I,
    )
    if not match:
        return None, None, None
    return money(match.group(1)), money(match.group(2)), compact(match.group(0))


def page_address(text: str) -> tuple[str, str]:
    chunks = re.split(r"(?im)^\s*Email\s*:[^\n]*\n", text)
    tail = chunks[-1].strip()
    postcodes = list(POSTCODE_RE.finditer(tail))
    if not postcodes:
        raise ValueError("lot detail page has no trailing postcode address")
    end = postcodes[-1].end()
    lines = [compact(line).strip(" ,") for line in tail[:end].splitlines() if compact(line)]
    kept: list[str] = []
    for line in reversed(lines):
        if kept and line.upper().startswith(("ENQUIRIES", "OFFICE:", "TEL:", "AGENTS NOTE", "BUYERS PREMIUM")):
            break
        kept.append(line)
        if len(kept) >= 4:
            break
    address = ", ".join(reversed(kept))
    address = re.sub(r"\bStoke St\.,\s*Milborough\b", "Stoke St. Milborough", address, flags=re.I)
    postcode = compact(postcodes[-1].group(1)).upper()
    return address, postcode


def description_from_page(text: str) -> str | None:
    match = re.search(r"DESCRIPTION\s*(.*?)(?:\n\s*LOCATION\b)", text, re.I | re.S)
    return compact(match.group(1)) if match else None


def annual_rent(text: str) -> tuple[int | None, str | None]:
    match = re.search(
        r"((?:total\s+)?rental\s+income\s+of\s+£\s*[\d,]+\s+per\s+annum)",
        compact(text),
        re.I,
    )
    if not match:
        return None, None
    return money(match.group(1)), compact(match.group(1))


def sector(address: str, description: str | None) -> str:
    text = norm(f"{address} {description or ''}")
    if "mixed use" in text or (("shop" in text or "commercial" in text) and any(k in text for k in ["flat", "cottage", "residential", "house"])):
        return "mixed-use"
    if any(k in text for k in [" acres ", "land at", "land to", "woodland", "plantation", "paddock", "pasture land", "amenity land"]):
        return "land"
    if any(k in text for k in ["chapel", "church", "school", "garages", "garage site", "commercial property", "poultry farm"]):
        return "commercial"
    if any(k in text for k in ["house", "cottage", "bungalow", "apartment", " flat ", "residential", "townhouse"]):
        return "residential"
    return "unknown"


def parse_catalogue(data: bytes, expected_lots: int) -> list[dict[str, Any]]:
    reader = PdfReader(io.BytesIO(data))
    rows: dict[int, dict[str, Any]] = {}
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lot_match = re.search(r"(?im)^\s*LOT\s+(\d+)\s*$", text)
        if not lot_match or "DESCRIPTION" not in text.upper():
            continue
        lot = int(lot_match.group(1))
        if lot in rows:
            raise ValueError(f"duplicate catalogue detail for lot {lot}")
        address, postcode = page_address(text)
        guide, guide_high, guide_text = guide_values(text)
        description = description_from_page(text)
        rent, rent_text = annual_rent(text)
        rows[lot] = {
            "lot_number": str(lot),
            "source_lot_id": str(lot),
            "address": address,
            "postcode": postcode,
            "description": description,
            "guide_price": guide,
            "guide_price_high": guide_high,
            "source_guide_text": guide_text,
            "annual_rent": rent,
            "rent_text": rent_text,
            "sector": sector(address, description),
            "catalogue_page": page_number,
        }
    expected = set(range(1, expected_lots + 1))
    if set(rows) != expected:
        raise ValueError(f"catalogue denominator mismatch: expected {sorted(expected)} got {sorted(rows)}")
    return [rows[number] for number in sorted(rows)]


def article_body(data: bytes, heading: str) -> str:
    soup = BeautifulSoup(data, "html.parser")
    main = soup.select_one("main") or soup
    text = main.get_text("\n", strip=True)
    start = text.find(heading)
    end = text.find("Back to Articles", start)
    if start < 0 or end < 0:
        raise ValueError(f"could not isolate article body: {heading}")
    return text[start:end]


def september_2025_rows(article: str) -> list[dict[str, Any]]:
    required = [
        "Sixteen properties and parcels of land sold",
        "Milebarn Cottages",
        "2, Rockall Villas",
        "Farthings, Fox Lane",
        "half an acre at Sarnau",
    ]
    for token in required:
        if token not in article:
            raise ValueError(f"September 2025 result token disappeared: {token}")
    rows = []
    for lot, address, guide, guide_high, sale, classified in SEPTEMBER_2025_ROWS:
        rows.append({
            "lot_number": str(lot),
            "source_lot_id": f"result-article-{lot}",
            "address": address,
            "postcode": None,
            "description": None,
            "guide_price": guide,
            "guide_price_high": guide_high,
            "source_guide_text": f"Guide Price £{guide:,}" + (f" - £{guide_high:,}" if guide_high else ""),
            "sale_price": sale,
            "source_outcome_text": f"Sold for £{sale:,}",
            "status": "sold",
            "annual_rent": None,
            "rent_text": None,
            "sector": classified,
        })
    return rows


def parse_september_2026(data: bytes) -> list[dict[str, Any]]:
    soup = BeautifulSoup(data, "html.parser")
    main = soup.select_one("main") or soup
    text = main.get_text("\n", strip=True)
    start = text.find("Property & Land Auction Results - September 2026")
    footer = re.search(r"Find\s+properties(?: in your local area)?", text[start:]) if start >= 0 else None
    end = start + footer.start() if footer else -1
    if start < 0 or end < 0:
        raise ValueError("could not isolate September 2026 result inventory")
    inventory = text[start:end]
    marks = list(re.finditer(r"(?m)^LOT[\s\xa0]*(\d+)\s*$", inventory))
    rows = []
    for index, mark in enumerate(marks):
        lot = int(mark.group(1))
        body = inventory[mark.end() : marks[index + 1].start() if index + 1 < len(marks) else len(inventory)]
        lines = [compact(line) for line in body.splitlines() if compact(line)]
        boundary = next((i for i, line in enumerate(lines) if line in {"GUIDE PRICE", "SOLD"}), None)
        if boundary is None:
            raise ValueError(f"September 2026 lot {lot} lacks a guide/status boundary")
        address = ", ".join(lines[:boundary])
        postcode_match = POSTCODE_RE.search(address)
        postcode = compact(postcode_match.group(1)).upper() if postcode_match else None
        status = "sold" if lines[boundary] == "SOLD" else "unknown"
        price_line = lines[boundary + 1] if status == "unknown" and boundary + 1 < len(lines) else None
        values = [int(value.replace(",", "")) for value in re.findall(r"£\s*([\d,]+)", price_line or "")]
        rows.append({
            "lot_number": str(lot),
            "source_lot_id": str(lot),
            "address": address,
            "postcode": postcode,
            "description": None,
            "guide_price": values[0] if values else None,
            "guide_price_high": values[1] if len(values) > 1 else None,
            "source_guide_text": f"GUIDE PRICE {price_line}" if values else None,
            "sale_price": None,
            "source_outcome_text": "SOLD" if status == "sold" else None,
            "status": status,
            "annual_rent": None,
            "rent_text": None,
            "sector": sector(address, None),
        })
    if [int(row["lot_number"]) for row in rows] != list(range(1, 23)):
        raise ValueError("September 2026 inventory no longer reconciles to lots 1-22")
    return rows


def event_cards(data: bytes, date: str) -> dict[int, dict[str, Any]]:
    mapping = EVENT_PROPERTY_LOTS.get(date, {})
    if not mapping:
        return {}
    soup = BeautifulSoup(data, "html.parser")
    found: dict[int, dict[str, Any]] = {}
    for anchor in soup.select('a[href*="/property/"]'):
        href = urljoin("https://estate-agents.hallsgb.com", anchor.get("href"))
        match = re.search(r"/property/(\d+)/", href)
        if not match or match.group(1) not in mapping:
            continue
        text = compact(anchor.get_text(" ", strip=True))
        lowered = text.lower()
        status = "unknown"
        if lowered.startswith("withdrawn"):
            status = "withdrawn"
        elif lowered.startswith("sold stc"):
            status = "sold"
        elif lowered.startswith("sold"):
            status = "sold"
        found[mapping[match.group(1)]] = {
            "property_id": match.group(1),
            "property_url": href,
            "card_text": text,
            "status": status,
        }
    if set(found) != set(mapping.values()):
        raise ValueError(f"event card identity mismatch for {date}: {sorted(found)}")
    return found


def existing_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    root = DATA / "appearances"
    for path in root.rglob("*.jsonl.gz"):
        if path.resolve() == APPEARANCE_SHARD.resolve():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("auction_date") and row.get("address"):
                    keys.add((row["auction_date"], norm(row["address"])))
    return keys


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows).encode()
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))


def update_continuation(summary: dict[str, Any]) -> None:
    payload = json.loads(CONTINUATION_PATH.read_text())
    run = {
        "source": "halls",
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload["next_growth_target"] = NEXT_TARGET
    payload["halls_collective"] = summary
    payload.setdefault("latest_by_source", {})["halls"] = run
    payload.setdefault("runs", []).append(run)
    payload.setdefault("coverage_follow_through_2026_11_07", {})["different_next_target"] = NEXT_TARGET
    write_json(CONTINUATION_PATH, payload)


def row_from_source(base: dict[str, Any], event: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    lot = base["lot_number"]
    date = event["date"]
    original_url = base.get("property_url") or event.get("catalogue_url") or event.get("results_url") or event["event_url"]
    return {
        "schema_version": 1,
        "appearance_id": f"{AUCTIONEER}|{source_id(date)}|{lot}",
        "auctioneer": AUCTIONEER,
        "source_auction_id": source_id(date),
        "auction_date": date,
        "lot_number": lot,
        "source_lot_id": base.get("source_lot_id") or lot,
        "address": base["address"],
        "postcode": base.get("postcode"),
        "locality": base["address"],
        "sector": base.get("sector") or "unknown",
        "property_type": None,
        "tenure": base.get("tenure"),
        "guide_price": base.get("guide_price"),
        "guide_price_high": base.get("guide_price_high"),
        "reserve_price": None,
        "sale_price": base.get("sale_price"),
        "available_price": None,
        "status": base.get("status") or "unknown",
        "description": base.get("description"),
        "annual_rent": base.get("annual_rent"),
        "rent_text": base.get("rent_text"),
        "tenant": None,
        "lease_information": None,
        "lease_start": None,
        "lease_expiry": None,
        "break_clauses": None,
        "rent_reviews": None,
        "yield": None,
        "floor_area": None,
        "site_area": None,
        "vacancy": None,
        "epc": None,
        "rateable_value": None,
        "planning": None,
        "vat_togc": None,
        "legal_pack_url": None,
        "image_urls": [],
        "original_url": original_url,
        "property_id": None,
        "identity_method": "first_party_halls_event_date_and_numbered_lot",
        "record_quality": "address_record",
        "source_position": int(lot),
        "source_guide_text": base.get("source_guide_text"),
        "source_outcome_text": base.get("source_outcome_text"),
        "source_event_url": event["event_url"],
        "source_property_url": base.get("property_url"),
        "auction_date_precision": "day",
        "auction_date_basis": "exact date printed on first-party Halls event page and retained event asset",
        "source_platform": "Halls first-party collective property and land archive",
        "operator_legal_name": LEGAL_NAME,
        "operator_company_number": COMPANY_NUMBER,
        "trading_name": "Halls",
        "source_evidence": evidence,
    }


def collect() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    existing = existing_keys()
    all_rows: list[dict[str, Any]] = []
    duplicate_exclusions: list[dict[str, str]] = []
    states: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for event in EVENTS:
        date = event["date"]
        try:
            event_bytes, event_retrieved = fetch(session, event["event_url"], "html")
            event_evidence = snapshot(event_bytes, f"event-{date}", "html", event["event_url"], event_retrieved)
            cards = event_cards(event_bytes, date)
            catalogue_evidence = None
            result_evidence = None
            result_article = None

            if event.get("catalogue_url"):
                catalogue_bytes, catalogue_retrieved = fetch(session, event["catalogue_url"], "pdf")
                catalogue_evidence = snapshot(
                    catalogue_bytes, f"catalogue-{date}", "pdf", event["catalogue_url"], catalogue_retrieved
                )
                rows = parse_catalogue(catalogue_bytes, event["expected_lots"])
            elif date == "2025-09-26":
                result_bytes, result_retrieved = fetch(session, event["results_url"], "html")
                result_evidence = snapshot(result_bytes, f"results-{date}", "html", event["results_url"], result_retrieved)
                result_article = article_body(result_bytes, "Sixteen Lots Sell For £2m")
                rows = september_2025_rows(result_article)
            elif date == "2026-09-25":
                result_bytes, result_retrieved = fetch(session, event["results_url"], "html")
                result_evidence = snapshot(result_bytes, f"results-{date}", "html", event["results_url"], result_retrieved)
                rows = parse_september_2026(result_bytes)
            else:
                raise ValueError(f"no row-bearing source configured for {date}")

            if date == "2025-11-28":
                result_bytes, result_retrieved = fetch(session, NOVEMBER_RESULTS_URL, "html")
                result_evidence = snapshot(result_bytes, f"results-{date}", "html", NOVEMBER_RESULTS_URL, result_retrieved)
                result_article = article_body(result_bytes, "Lots Sell for £2.2m")
                for lot, price in NOVEMBER_SALE_PRICES.items():
                    token = NOVEMBER_RESULT_TOKENS[lot]
                    if token not in result_article:
                        raise ValueError(f"November result token disappeared for lot {lot}: {token}")
                    row = rows[lot - 1]
                    row.update({
                        "sale_price": price,
                        "status": "sold",
                        "source_outcome_text": f"Sold for £{price:,}",
                    })

            for row in rows:
                lot = int(row["lot_number"])
                card = cards.get(lot)
                detail_evidence = None
                if card:
                    row["status"] = card["status"]
                    row["source_outcome_text"] = card["card_text"]
                    row["property_url"] = card["property_url"]
                    detail_bytes, detail_retrieved = fetch(session, card["property_url"], "html")
                    detail_evidence = snapshot(
                        detail_bytes,
                        f"property-{date}-{lot}-{card['property_id']}",
                        "html",
                        card["property_url"],
                        detail_retrieved,
                    )
                evidence = {
                    "event_page": {**event_evidence, "basis": "first-party exact event date and retained event page"},
                    "catalogue": ({**catalogue_evidence, "basis": "complete first-party numbered catalogue"} if catalogue_evidence else None),
                    "results": ({**result_evidence, "basis": "first-party result inventory or result article"} if result_evidence else None),
                    "property_detail": ({**detail_evidence, "basis": "linked first-party property detail"} if detail_evidence else None),
                    "basis": "first-party exact-dated numbered lot or individually identified result property",
                }
                canonical = row_from_source(row, event, evidence)
                key = (date, norm(canonical["address"]))
                if key in existing:
                    duplicate_exclusions.append({
                        "auction_date": date,
                        "address": canonical["address"],
                        "appearance_id": canonical["appearance_id"],
                    })
                    continue
                existing.add(key)
                all_rows.append(canonical)

            captured = len(rows)
            complete = captured == event["expected_lots"] and date != "2025-09-26"
            state = {
                "auctioneer": AUCTIONEER,
                "operator_legal_name": LEGAL_NAME,
                "operator_company_number": COMPANY_NUMBER,
                "source_auction_id": source_id(date),
                "auction_date": date,
                "auction_date_precision": "day",
                "source_url": event.get("catalogue_url") or event.get("results_url"),
                "event_url": event["event_url"],
                "lots_captured": captured,
                "published_lots_offered": event["expected_lots"],
                "catalogue_complete": complete,
                "source_rows_complete": complete,
                "denominator_reconciled": complete,
                "completion_scope": (
                    "complete numbered first-party lot inventory"
                    if complete
                    else "15 individually named result properties against a published 16-sold denominator; one unnamed result remains denominator evidence only"
                ),
                "source_evidence": {
                    "event_page": event_evidence,
                    "catalogue": catalogue_evidence,
                    "results": result_evidence,
                },
                "errors": [],
                "checked_at": now(),
            }
            states.append(state)
            write_json(AUCTION_DIR / f"{date}.json", state)
        except Exception as error:  # preserve bounded failure evidence in the summary
            failures.append({"date": date, "error": f"{type(error).__name__}: {error}"})

    if failures:
        raise RuntimeError(json.dumps(failures, indent=2))

    all_rows.sort(key=lambda row: (row["auction_date"], int(row["lot_number"])))
    write_rows(APPEARANCE_SHARD, all_rows)
    sectors = Counter(row["sector"] for row in all_rows)
    statuses = Counter(row["status"] for row in all_rows)
    source_years = sorted({row["auction_date"][:4] for row in all_rows})
    summary = {
        "checked_at": now(),
        "operator": {
            "canonical_name": AUCTIONEER,
            "legal_name": LEGAL_NAME,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "events_attempted": len(EVENTS),
        "events_reconciled": len(states),
        "complete_event_inventories": sum(bool(state["catalogue_complete"]) for state in states),
        "partial_event_inventories": sum(not bool(state["catalogue_complete"]) for state in states),
        "published_lot_denominator": sum(event["expected_lots"] for event in EVENTS),
        "individually_identified_source_rows": sum(state["lots_captured"] for state in states),
        "appearances_captured": len(all_rows),
        "run_new_appearances": len(all_rows),
        "run_new_address_records": len(all_rows),
        "run_new_exact_dated_address_records": len(all_rows),
        "run_new_dated_twenty_year_address_records": len(all_rows),
        "run_new_partial_lots": 0,
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in all_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in all_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in all_rows),
        "run_new_commercial_or_mixed": sectors["commercial"] + sectors["mixed-use"],
        "source_years": source_years,
        "newly_covered_source_years": source_years,
        "by_sector": dict(sectors),
        "by_status": dict(statuses),
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(duplicate_exclusions),
        "duplicate_source_evidence_exclusions": duplicate_exclusions,
        "unidentified_denominator_only_rows": 1,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    write_json(SUMMARY_PATH, summary)
    update_continuation(summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
