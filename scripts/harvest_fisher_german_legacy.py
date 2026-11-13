"""Bank Fisher German's retained pre-Bamboo room-auction evidence.

The public BriefYourMarket archive is a finite first-party newsletter index.
Issue 6 retains one complete eight-lot 15 February 2017 inventory, four linked
brochures, and two individually identifiable 2016 results.  This runner
snapshots the newsletter and brochures, validates every admitted interest
against those bytes, and preserves the 2016 rows as year-precision/undated
rather than inventing an auction day.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


INDEX_URL = "https://fishergerman.briefyourmarket.com/Default.aspx"
NEWSLETTER_URL = "https://fishergerman.briefyourmarket.com/PrintableNewsletter.aspx?Id=652"
BASE = "https://fishergerman.briefyourmarket.com"
SOURCE_KEY = "fisher-german-legacy"
CANONICAL_AUCTIONEER = "Fisher German Online Auction"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}

DOCUMENTS = {
    "calveley": "/Documents/Land_at_Calveley_Green_Farm_4pg_Auction_Brochure.pdf",
    "churton-1": "/Documents/1_Churton_Road_4pg_FG_Auction_Brochure_Web.pdf",
    "churton-2": "/Documents/2_Churton_Road_4pg_FG_Auction_Brochure_Web.pdf",
    "hollowmoor": "/Documents/Land_at_Hollowmoor_Heath_4pg_FG_Auction_Brochure_SD.pdf",
}

EVENT_LOTS = (
    {
        "lot_number": "1", "source_lot_id": "2017-02-15-calveley-1",
        "document": "calveley", "validation_text": "Lot 1 - 135.28 Acres",
        "address": "Lot 1, 135.28 acres, Land at Calveley Green Farm, Cholmondeston Road, Calveley, Tarporley, Cheshire CW6 9LF",
        "postcode": "CW6 9LF", "site_area": "135.28 acres", "sector": "land",
    },
    {
        "lot_number": "2", "source_lot_id": "2017-02-15-calveley-2",
        "document": "calveley", "validation_text": "Lot 2 - 4.52 Acres",
        "address": "Lot 2, 4.52 acres, Land at Calveley Green Farm, Cholmondeston Road, Calveley, Tarporley, Cheshire CW6 9LF",
        "postcode": "CW6 9LF", "site_area": "4.52 acres", "sector": "land",
    },
    {
        "lot_number": "3", "source_lot_id": "2017-02-15-calveley-3",
        "document": "calveley", "validation_text": "Lot 3 - 4.00 Acres",
        "address": "Lot 3, 4.00 acres, Land at Calveley Green Farm, Cholmondeston Road, Calveley, Tarporley, Cheshire CW6 9LF",
        "postcode": "CW6 9LF", "site_area": "4.00 acres", "sector": "land",
    },
    {
        "lot_number": "4", "source_lot_id": "2017-02-15-calveley-4",
        "document": "calveley", "validation_text": "Lot 4 - 5.48 Acres",
        "address": "Lot 4, 5.48 acres, Land at Calveley Green Farm, Cholmondeston Road, Calveley, Tarporley, Cheshire CW6 9LF",
        "postcode": "CW6 9LF", "site_area": "5.48 acres", "sector": "land",
    },
    {
        "lot_number": "5", "source_lot_id": "2017-02-15-calveley-5",
        "document": "calveley", "validation_text": "Lot 5 - 25.23 Acres",
        "address": "Lot 5, 25.23 acres, Land at Calveley Green Farm, Cholmondeston Road, Calveley, Tarporley, Cheshire CW6 9LF",
        "postcode": "CW6 9LF", "site_area": "25.23 acres", "sector": "land",
    },
    {
        "lot_number": "6", "source_lot_id": "2017-02-15-1-churton-road",
        "document": "churton-1", "validation_text": "1 Churton Road",
        "address": "1 Churton Road, Farndon, Chester, Cheshire CH3 6QP",
        "postcode": "CH3 6QP", "sector": "residential",
        "guide_price": 100000, "guide_price_high": 130000,
        "source_guide_text": "Guide price £100 - £130,000",
    },
    {
        "lot_number": "7", "source_lot_id": "2017-02-15-2-churton-road",
        "document": "churton-2", "validation_text": "2 Churton Road",
        "address": "2 Churton Road, Farndon, Chester, Cheshire CH3 6QP",
        "postcode": "CH3 6QP", "sector": "residential",
        "guide_price": 125000, "guide_price_high": 150000,
        "source_guide_text": "Guide price £125 - £150,000",
    },
    {
        "lot_number": "8", "source_lot_id": "2017-02-15-hollowmoor-heath",
        "document": "hollowmoor", "validation_text": "Land at Hollowmoor Heath",
        "address": "Land at Hollowmoor Heath, Great Barrow, Chester, Cheshire CH3 7LG",
        "postcode": "CH3 7LG", "site_area": "0.167 acres", "sector": "land",
        "guide_price": 10000, "guide_price_high": 15000,
        "source_guide_text": "Guide price £10,000 - £15,000",
    },
)

RETROSPECTIVE_RESULTS = (
    {
        "source_lot_id": "2016-retrospective-3-broad-lane",
        "validation_text": "No. 3 Broad Lane, Aughton, Ormskirk",
        "address": "3 Broad Lane, Aughton, Ormskirk, Lancashire",
        "sector": "residential", "guide_price": 200000,
        "guide_price_high": 250000, "sale_price": 310000,
        "source_guide_text": "guide price of £200,000 - £250,000",
        "source_result_text": "sold for £310,000",
    },
    {
        "source_lot_id": "2016-retrospective-bradwall-methodist-chapel",
        "validation_text": "first at Bradwall, near Sandbach sold for £172,000",
        "address": "Methodist Chapel, Bradwall, near Sandbach, Cheshire",
        "sector": "residential", "sale_price": 172000,
        "source_result_text": "sold for £172,000",
    },
)


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.replace("½", "1/2").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip().casefold()


def newsletter_text(html: str) -> str:
    return " ".join(BeautifulSoup(html, "lxml").stripped_strings)


def validate_newsletter(html: str) -> None:
    text = normalized(newsletter_text(html))
    required = [
        "our first auction of 2017 is on 15 th february",
        "available in 5 lots", "1 churton road farndon chester",
        "2 churton road farndon chester", "single block of amenity land at great barrow",
        "no. 3 broad lane, aughton, ormskirk", "sold for £310.000",
        "first at bradwall, near sandbach sold for £172,000",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"newsletter lost required auction evidence: {missing}")
    soup = BeautifulSoup(html, "lxml")
    linked = {urljoin(BASE, a.get("href")) for a in soup.find_all("a", href=True)}
    expected = {urljoin(BASE, value) for value in DOCUMENTS.values()}
    if not expected.issubset(linked):
        raise ValueError(f"newsletter lost brochure links: {sorted(expected - linked)}")


def pdf_text(raw: bytes) -> str:
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "source.pdf"
        target = Path(folder) / "source.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(target)],
            check=True, capture_output=True,
        )
        return target.read_text("utf-8", errors="replace")


def validate_documents(texts: dict[str, str]) -> None:
    for key, text in texts.items():
        clean = normalized(text)
        if "15 february 2017 at 7.00pm" not in clean and "15th february 2017 at 7.00pm" not in clean:
            raise ValueError(f"{key} lost exact auction date")
    for lot in EVENT_LOTS:
        if normalized(lot["validation_text"]) not in normalized(texts[lot["document"]]):
            raise ValueError(f"{lot['source_lot_id']} missing from retained brochure")
    if "cheshire ch3 6qp" not in normalized(texts["churton-1"]):
        raise ValueError("1 Churton Road postcode missing")
    if "cheshire ch3 6qp" not in normalized(texts["churton-2"]):
        raise ValueError("2 Churton Road postcode missing")
    if "cheshire cw6 9lf" not in normalized(texts["calveley"]):
        raise ValueError("Calveley postcode missing")


def snapshot_html(raw: bytes, url: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SOURCE_KEY / f"newsletter-{sha[:16]}.json.gz"
    evidence = {
        "source_url": url, "retrieved_at": corpus.now(), "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "first-party Fisher German legacy newsletter and linked auction inventory",
    }
    corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def snapshot_pdf(raw: bytes, url: str, key: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SOURCE_KEY / f"{key}-{sha[:16]}.pdf.gz"
    corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": url, "retrieved_at": corpus.now(), "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "first-party Fisher German room-auction brochure",
    }


def event_appearance(lot: dict, newsletter_evidence: dict, document_evidence: dict) -> dict:
    url = document_evidence["source_url"]
    row = corpus.base_row(
        CANONICAL_AUCTIONEER, "fisher-german:2017-02-15-room-auction",
        "2017-02-15", lot["lot_number"], lot["source_lot_id"], url,
    )
    row.update(
        appearance_id=f"{CANONICAL_AUCTIONEER}|fisher-german-legacy:{lot['source_lot_id']}",
        address=lot["address"], postcode=lot.get("postcode"),
        locality=lot["address"], sector=lot["sector"],
        property_type="land" if lot["sector"] == "land" else "cottage",
        guide_price=lot.get("guide_price"), guide_price_high=lot.get("guide_price_high"),
        source_guide_text=lot.get("source_guide_text"),
        site_area=lot.get("site_area"), record_quality="address_record",
        auction_date_precision="day", auction_date_basis="exact date printed by first-party brochure",
        identity_method="first_party_brochure_numbered_legal_interest",
        published_auctioneer="Fisher German LLP", auction_format="traditional room auction",
        operator_legal_name="FISHER GERMAN LLP", operator_company_number="OC317554",
        source_evidence=document_evidence,
        supporting_source_evidence=[newsletter_evidence],
    )
    return row


def retrospective_appearance(item: dict, newsletter_evidence: dict) -> dict:
    row = corpus.base_row(
        CANONICAL_AUCTIONEER, "fisher-german:2016-retrospective",
        None, None, item["source_lot_id"], NEWSLETTER_URL,
    )
    row.update(
        appearance_id=f"{CANONICAL_AUCTIONEER}|fisher-german-legacy:{item['source_lot_id']}",
        address=item["address"], locality=item["address"], sector=item["sector"],
        guide_price=item.get("guide_price"), guide_price_high=item.get("guide_price_high"),
        sale_price=item.get("sale_price"), status="sold",
        source_guide_text=item.get("source_guide_text"),
        source_result_text=item.get("source_result_text"),
        record_quality="address_record", auction_year=2016,
        auction_date_precision="year", auction_date_basis="first-party retrospective identifies 2016 only; exact day remains unknown",
        identity_method="first_party_retrospective_named_result",
        published_auctioneer="Fisher German LLP", auction_format="traditional room auction",
        operator_legal_name="FISHER GERMAN LLP", operator_company_number="OC317554",
        source_evidence=newsletter_evidence,
    )
    pc = corpus.PC.search(item["address"])
    if pc:
        row["postcode"] = pc.group().upper()
    return row


def exact_overlap_keys(excluded_path: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == excluded_path:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                keys.add((row["auction_date"], normalized(row["address"])))
    return keys


def harvest() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    index = session.get(INDEX_URL, timeout=45)
    index.raise_for_status()
    index_text = index.text
    if "/Newsletters/Fisher-German-Regional-Newsletter-issue-6/" not in index_text:
        raise ValueError("legacy newsletter index no longer exposes issue 6")

    page = session.get(NEWSLETTER_URL, timeout=45)
    page.raise_for_status()
    validate_newsletter(page.text)
    newsletter_evidence = snapshot_html(page.content, page.url)

    document_evidence: dict[str, dict] = {}
    texts: dict[str, str] = {}
    for key, relative in DOCUMENTS.items():
        response = session.get(urljoin(BASE, relative), timeout=60)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError(f"{key} is no longer a PDF")
        document_evidence[key] = snapshot_pdf(response.content, response.url, key)
        texts[key] = pdf_text(response.content)
    validate_documents(texts)

    candidate = [
        event_appearance(lot, newsletter_evidence, document_evidence[lot["document"]])
        for lot in EVENT_LOTS
    ]
    candidate.extend(retrospective_appearance(item, newsletter_evidence) for item in RETROSPECTIVE_RESULTS)

    output = corpus.DATA / "appearances" / SOURCE_KEY / "legacy-room-auctions.jsonl.gz"
    existing = list(corpus.iter_rows(output)) if output.exists() else []
    before = {row["appearance_id"]: row for row in existing}
    overlaps = exact_overlap_keys(output)
    excluded = [
        row for row in candidate
        if row.get("auction_date") and (row["auction_date"], normalized(row["address"])) in overlaps
    ]
    admitted = [row for row in candidate if row not in excluded]
    merged = dict(before)
    merged.update({row["appearance_id"]: row for row in admitted})
    total = corpus.write_rows(f"{SOURCE_KEY}/legacy-room-auctions", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]

    events = {
        "2017-02-15": [row for row in admitted if row.get("auction_date") == "2017-02-15"],
        "2016-retrospective": [row for row in admitted if row.get("auction_year") == 2016],
    }
    for event, rows in events.items():
        corpus.save_json(corpus.DATA / "auctions" / SOURCE_KEY / f"{event}.json", {
            "auctioneer": CANONICAL_AUCTIONEER,
            "published_auctioneer": "Fisher German LLP",
            "operator_legal_name": "FISHER GERMAN LLP",
            "operator_company_number": "OC317554",
            "source_auction_id": (
                "fisher-german:2017-02-15-room-auction"
                if event != "2016-retrospective"
                else "fisher-german:2016-retrospective"
            ),
            "auction_date": event if event != "2016-retrospective" else None,
            "auction_date_precision": "day" if event != "2016-retrospective" else "year",
            "lots_captured": len(rows),
            "published_lots_offered": 8 if event != "2016-retrospective" else None,
            "catalogue_complete": event != "2016-retrospective",
            "source_url": NEWSLETTER_URL,
            "source_evidence": newsletter_evidence,
            "checked_at": corpus.now(),
        })

    by_sector = Counter(row.get("sector") or "unknown" for row in merged.values())
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": CANONICAL_AUCTIONEER,
        "published_auctioneer": "Fisher German LLP",
        "operator_legal_name": "FISHER GERMAN LLP",
        "operator_company_number": "OC317554",
        "source_url": NEWSLETTER_URL,
        "indexed_newsletter_archive_checked": True,
        "linked_brochures_captured": len(DOCUMENTS),
        "complete_event_inventories": 1,
        "partial_retrospective_inventories": 1,
        "banked_appearances": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and row.get("auction_date") is not None
            and date(2006, 11, 13) <= date.fromisoformat(row["auction_date"]) <= date(2026, 11, 13)
            for row in added
        ),
        "run_new_partial_lots": sum(row.get("record_quality") != "address_record" for row in added),
        "run_new_undated": sum(row.get("auction_date") is None for row in added),
        "run_new_future_dated": sum(
            bool(row.get("auction_date")) and row["auction_date"] > "2026-11-13" for row in added
        ),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_duplicate_exact_date_address_exclusions": len(excluded),
        "new_source_years": [2016, 2017] if added else [],
        "by_sector": dict(sorted(by_sector.items())),
        "completion_scope": "complete retained 15 February 2017 eight-lot inventory plus two individually named 2016 retrospective results; the unidentified second chapel and other unnamed 2016 lots are denominator evidence only",
        "national_completeness_verified": False,
        "next_growth_target": "Extend the reusable Sheldon Bosley Knight retained-result runner to the complete June, July and September 2025 tables, then inventory its first-party 2022-2024 result assets. Do not refresh the now-reconciled Fisher German newsletter unless a new brochure or result route appears.",
    }
    corpus.save_json(corpus.DATA / "fisher_german_legacy_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    harvest()
