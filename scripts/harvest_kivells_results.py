"""Bank Kivells' exact-dated, first-party property-auction result PDFs.

The annual review is discovery evidence only.  This collector admits only the
numbered lot cards in complete event result PDFs, verifies their printed event
date, and keeps locality-only cards as partial lots rather than inventing an
address.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from io import BytesIO
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


PARSER_VERSION = 1
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
EVENTS = (
    {
        "auction_date": "2025-01-15",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-18",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20January%202025%20Auction%20Results.pdf",
        "published_lot_count": 9,
    },
    {
        "auction_date": "2025-06-18",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-21",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20June%202025%20Auction%20Results.pdf",
        "published_lot_count": 6,
    },
    {
        "auction_date": "2025-07-30",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-22",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20July%202025%20Auction%20Results.pdf",
        "published_lot_count": 15,
    },
    {
        "auction_date": "2025-09-03",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-23",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20September%202025%20Auction%20results.pdf",
        "published_lot_count": None,
    },
    {
        "auction_date": "2025-10-08",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-25",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20October%202025%20Auction%20Results.pdf",
        "published_lot_count": 12,
    },
    {
        "auction_date": "2025-11-12",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-26",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20November%202025%20Auction%20Results.pdf",
        "published_lot_count": 20,
    },
)

MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), 1
)}
DATE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(20\d{2}))?\b",
    re.I,
)
LOT_RE = re.compile(r"(?im)^\s*LOT\s+(\d+)\s*[|:]\s*(.+?)\s*$")
MONEY_RE = re.compile(r"£\s*([\d][\d,.]*)")
GUIDE_RE = re.compile(
    r"\bGuide(?:\s+Price)?\s*:?[ \t]*(£\s*[\d][\d,.]*)"
    r"(?:\s*(?:-|–|to)\s*(£\s*[\d][\d,.]*))?",
    re.I,
)
OUTCOME_RE = re.compile(
    r"\b(Sold\s+Post(?:[- ]Auction)?|Sold\s+After|Sold\s+Prior|Sold|Unsold|"
    r"Withdrawn|Postponed|Available)\b\s*:?[ \t]*(£\s*[\d][\d,.]*)?",
    re.I,
)
ADDRESS_CUE_RE = re.compile(
    r"\b(?:farm|farmhouse|house|cottage|bungalow|flat|apartment|land|field|"
    r"woodland|moor|building\s+plot|development\s+site|plot|barn|garage|yard|"
    r"shop|unit|premises|hotel|inn|chapel|church|property)\b",
    re.I,
)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,|:-")
    return value or None


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def parse_printed_date(text: str, expected_year: int) -> str:
    for match in DATE_RE.finditer(text):
        day, month, year = match.groups()
        parsed = date(int(year or expected_year), MONTHS[month.lower()], int(day))
        if parsed.year == expected_year:
            return parsed.isoformat()
    raise ValueError("result PDF has no exact printed auction date")


def status_from_text(value: str | None) -> str:
    normalized = clean(value).casefold() if clean(value) else ""
    if normalized.startswith("sold post") or normalized.startswith("sold after"):
        return "sold_after"
    if normalized.startswith("sold prior"):
        return "sold_prior"
    return {
        "sold": "sold", "unsold": "unsold", "withdrawn": "withdrawn",
        "postponed": "postponed", "available": "available",
    }.get(normalized, "unknown")


def is_address(location: str) -> bool:
    return bool(
        corpus.PC.search(location)
        or re.search(r"\d", location)
        or ADDRESS_CUE_RE.search(location)
        or location.count(",") >= 2
    )


def parse_text(text: str, expected_date: str) -> tuple[str, list[dict]]:
    normalized = text.replace("\u00ad", "").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    auction_date = parse_printed_date(normalized, int(expected_date[:4]))
    if auction_date != expected_date:
        raise ValueError(f"printed date {auction_date} does not match expected {expected_date}")

    anchors = list(LOT_RE.finditer(normalized))
    if not anchors:
        raise ValueError("result PDF has no numbered lot cards")
    cards = []
    for index, anchor in enumerate(anchors):
        block = normalized[anchor.start(): anchors[index + 1].start() if index + 1 < len(anchors) else None]
        lot_number = int(anchor.group(1))
        location = clean(anchor.group(2))
        if not location:
            raise ValueError(f"lot {lot_number} has no published location")
        guide_match = GUIDE_RE.search(block)
        outcome_match = OUTCOME_RE.search(block)
        if not outcome_match:
            raise ValueError(f"lot {lot_number} has no published outcome")
        guide_low = money(guide_match.group(1)) if guide_match else None
        guide_high = money(guide_match.group(2)) if guide_match and guide_match.group(2) else None
        outcome_label = clean(outcome_match.group(1))
        cards.append({
            "lot_number": str(lot_number),
            "location": location,
            "address": location if is_address(location) else None,
            "guide_price": guide_low,
            "guide_price_high": guide_high,
            "guide_price_text": clean(guide_match.group(0)) if guide_match else None,
            "sale_price": money(outcome_match.group(2)) if outcome_match.group(2) else None,
            "status": status_from_text(outcome_label),
            "source_result_text": clean(outcome_match.group(0)),
            "source_card_text": clean(block),
        })
    # Kivells' PDFs reuse the preceding spread as a page background, so text
    # extraction repeats some cards. Collapse only exact evidence repeats;
    # retain distinct properties even where the publisher reused a lot label.
    deduplicated = {}
    for card in cards:
        key = (
            card["lot_number"], card["location"], card["guide_price"],
            card["guide_price_high"], card["sale_price"], card["status"],
        )
        if key in deduplicated:
            deduplicated[key]["source_duplicate_count"] += 1
        else:
            card["source_duplicate_count"] = 0
            deduplicated[key] = card
    cards = list(deduplicated.values())
    numbers = [int(card["lot_number"]) for card in cards]
    if sorted(set(numbers)) != list(range(1, max(numbers) + 1)):
        raise ValueError(f"lot inventory is not contiguous: {numbers}")
    # Two-column source pages commonly extract in visual order (2, 1, 4, 3).
    # Lot identity and source position follow the published lot number instead.
    cards.sort(key=lambda card: int(card["lot_number"]))
    return auction_date, cards


def extract_pdf(raw: bytes, expected_date: str) -> tuple[str, list[dict]]:
    reader = PdfReader(BytesIO(raw))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return parse_text(text, expected_date)


def build_rows(cards: list[dict], event: dict, source_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    auction_date = event["auction_date"]
    auction_id = f"kivells-results:{auction_date}"
    rows = []
    for position, card in enumerate(cards, 1):
        lot_number = card["lot_number"]
        identity = hashlib.sha256(
            f"{auction_date}|{lot_number}|{card['location']}".encode()
        ).hexdigest()[:16]
        row = corpus.base_row(
            "Kivells", auction_id, auction_date, lot_number, identity, source_url,
        )
        address = card.get("address")
        postcode_match = corpus.PC.search(address or "")
        row.update(
            appearance_id=f"Kivells|{auction_id}|lot:{lot_number}:{identity}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=card["location"],
            sector=corpus.sector(card.get("source_card_text") or card["location"]),
            guide_price=card.get("guide_price"),
            guide_price_high=card.get("guide_price_high"),
            guide_price_text=card.get("guide_price_text"),
            sale_price=card.get("sale_price"),
            status=card.get("status") or "unknown",
            property_id=None,
            identity_method="exact_event_date_lot_number_and_first_party_result_card",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis="exact date printed in first-party result PDF and reconciled to event page",
            source_position=position,
            source_result_text=card.get("source_result_text"),
            source_card_text=card.get("source_card_text"),
            source_duplicate_count=card.get("source_duplicate_count", 0),
            source_evidence=evidence,
        )
        rows.append(row)
    expected_count = event.get("published_lot_count")
    state = {
        "auctioneer": "Kivells", "source_auction_id": auction_id,
        "auction_date": auction_date, "parser_version": PARSER_VERSION,
        "catalogue_complete": True, "source_rows_complete": True,
        "lots_captured": len(rows), "numbered_lots_in_pdf": len(rows),
        "published_lot_count_from_event_page": expected_count,
        "denominator_reconciled": True,
        "denominator_basis": "all unique outcome-bearing cards across the complete first-party event result PDF; exact repeated background cards collapsed",
        "completion_scope": "all numbered result cards in the event PDF",
        "source_url": source_url, "article_url": event["article_url"],
        "checked_at": corpus.now(),
        "exact_source_card_duplicates_collapsed": sum(
            card.get("source_duplicate_count", 0) for card in cards
        ),
        "event_page_count_note": (
            None if expected_count is None or expected_count == len(rows)
            else f"event page describes {expected_count} lots going under the hammer; PDF publishes {len(rows)} outcome cards"
        ),
        "errors": [],
    }
    return state, rows


def get_pdf(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("result URL did not return a PDF")
    return response


def harvest(saved_only: bool = False) -> None:
    summary_path = corpus.DATA / "kivells_results_collection.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    completed = set(previous.get("completed_source_urls") or [])
    appearances_path = corpus.DATA / "appearances/kivells-results/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearances_path)) if appearances_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    before_counts = Counter(
        address=sum(bool(row.get("address")) for row in existing),
        partial=sum(not row.get("address") for row in existing),
        guide=sum(row.get("guide_price") is not None for row in existing),
        sale=sum(row.get("sale_price") is not None for row in existing),
    )
    merged = {row["appearance_id"]: row for row in existing}
    failures = []
    completed_this_run = []
    saved_by_date = {}
    if saved_only:
        for snapshot in sorted((corpus.DATA / "sources/kivells-results/results").glob("*.pdf.gz")):
            raw = gzip.decompress(snapshot.read_bytes())
            reader = PdfReader(BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            saved_by_date[parse_printed_date(text, 2025)] = (snapshot, raw)
    for event in EVENTS:
        if event["pdf_url"] in completed:
            continue
        try:
            if saved_only:
                snapshot, raw = saved_by_date[event["auction_date"]]
                source_url = event["pdf_url"]
                retrieved_at = previous.get("checked_at") or corpus.now()
            else:
                response = get_pdf(event["pdf_url"])
                raw = response.content
                source_url = response.url
                retrieved_at = corpus.now()
            sha = corpus.digest(raw)
            if not saved_only:
                snapshot = corpus.DATA / "sources/kivells-results/results" / f"{sha[:16]}.pdf.gz"
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": source_url, "article_url": event["article_url"],
                "retrieved_at": retrieved_at, "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "complete first-party exact-dated property auction result PDF",
            }
            _, cards = extract_pdf(raw, event["auction_date"])
            state, rows = build_rows(cards, event, source_url, evidence)
            corpus.save_json(
                corpus.DATA / "auctions/kivells-results" / f"{event['auction_date']}-{sha[:12]}.json",
                state,
            )
            prior = [row for row in merged.values() if row.get("auction_date") == event["auction_date"]]
            for row in prior:
                merged.pop(row["appearance_id"], None)
            for row in rows:
                merged[row["appearance_id"]] = row
            completed.add(event["pdf_url"])
            completed_this_run.append(event["pdf_url"])
            print("KIVELLS", event["auction_date"], len(rows), "numbered result lots", flush=True)
        except Exception as exc:
            failures.append({
                "auction_date": event["auction_date"], "url": event["pdf_url"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

    total = corpus.write_rows(
        "kivells-results/canonical", list(merged.values()), preserve_existing=False,
    )
    after_counts = Counter(
        address=sum(bool(row.get("address")) for row in merged.values()),
        partial=sum(not row.get("address") for row in merged.values()),
        guide=sum(row.get("guide_price") is not None for row in merged.values()),
        sale=sum(row.get("sale_price") is not None for row in merged.values()),
    )
    summary = {
        "checked_at": corpus.now(), "parser_version": PARSER_VERSION,
        "retrieval_route": (
            "saved_immutable_first_party_event_result_pdfs" if saved_only
            else "direct_first_party_event_result_pdfs"
        ),
        "event_pdfs_in_manifest": len(EVENTS), "event_pdfs_banked": len(completed),
        "event_pdfs_completed_this_run": len(completed_this_run),
        "event_pdfs_pending": sum(event["pdf_url"] not in completed for event in EVENTS),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": after_counts["address"] - before_counts["address"],
        "run_new_partial_lots": after_counts["partial"] - before_counts["partial"],
        "run_new_guide_prices": after_counts["guide"] - before_counts["guide"],
        "run_new_sale_prices": after_counts["sale"] - before_counts["sale"],
        "exact_source_card_duplicates_collapsed": sum(
            row.get("source_duplicate_count", 0) for row in merged.values()
        ),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "covered_source_years": sorted({row["auction_date"][:4] for row in merged.values()}),
        "completed_source_urls": sorted(completed), "failures": failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    # Preserve and publish successful catalogues even if another event is
    # temporarily inaccessible; only a wholly zero-growth run is fatal.
    if failures and not completed_this_run and not completed:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(saved_only="--reparse-saved" in sys.argv)
