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
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


PARSER_VERSION = 4
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DEFAULT_FLIPHTML_SEED = (
    Path(__file__).resolve().parents[1]
    / "data/historical_source_corpus/kivells-results/fliphtml5-result-books.json.gz"
)

ANNUAL_2023_ARTICLE_URL = "https://www.kivells.com/residentialsales/auctions/news/-9"
ANNUAL_2023_REVIEW_URL = "https://fliphtml5.com/hoau/vcml/Kivells_Collective_Property_Auction_Full_Year_Review_2023_/"
FLIPHTML_2023_EVENTS = (
    {
        "auction_date": "2023-01-25", "book_slug": "fhax",
        "source_url": "https://online.fliphtml5.com/hoau/fhax/",
        "public_text_url": "https://fliphtml5.com/hoau/fhax/Kivells_January_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/fhax/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/fhax/javascript/config.js",
        "expected_numbered_result_cards": 10, "expected_sold_cards": 8,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-02-22", "book_slug": "evpc",
        "source_url": "https://online.fliphtml5.com/hoau/evpc/",
        "public_text_url": "https://fliphtml5.com/hoau/evpc/Kivells_February_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/evpc/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/evpc/javascript/config.js",
        "expected_numbered_result_cards": 17, "expected_sold_cards": 14,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-03-22", "book_slug": "rxkw",
        "source_url": "https://online.fliphtml5.com/hoau/rxkw/",
        "public_text_url": "https://fliphtml5.com/hoau/rxkw/Kivells_March_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/rxkw/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/rxkw/javascript/config.js",
        "expected_numbered_result_cards": 9, "expected_sold_cards": 7,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-04-26", "book_slug": "rkfi",
        "source_url": "https://online.fliphtml5.com/hoau/rkfi/",
        "public_text_url": "https://fliphtml5.com/hoau/rkfi/Kivells_April_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/rkfi/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/rkfi/javascript/config.js",
        "expected_numbered_result_cards": 14, "expected_sold_cards": 10,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-05-24", "book_slug": "ujli",
        "source_url": "https://online.fliphtml5.com/hoau/ujli/",
        "public_text_url": "https://fliphtml5.com/hoau/ujli/Kivells_May_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/ujli/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/ujli/javascript/config.js",
        "expected_numbered_result_cards": 7, "expected_sold_cards": 6,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-06-21", "book_slug": "rvqi",
        "source_url": "https://online.fliphtml5.com/hoau/rvqi/",
        "public_text_url": "https://fliphtml5.com/hoau/rvqi/Kivells_June_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/rvqi/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/rvqi/javascript/config.js",
        "expected_numbered_result_cards": 11, "expected_sold_cards": 11,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-07-26", "book_slug": "ewcr",
        "source_url": "https://online.fliphtml5.com/hoau/ewcr/",
        "public_text_url": "https://fliphtml5.com/hoau/ewcr/Kivells_July_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/ewcr/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/ewcr/javascript/config.js",
        "expected_numbered_result_cards": 9, "expected_sold_cards": 9,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-09-13", "book_slug": "pufw",
        "source_url": "https://online.fliphtml5.com/hoau/pufw/",
        "public_text_url": "https://fliphtml5.com/hoau/pufw/Kivells_September_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/pufw/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/pufw/javascript/config.js",
        "expected_numbered_result_cards": 15, "expected_sold_cards": 15,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-10-18", "book_slug": "ulyl",
        "source_url": "https://online.fliphtml5.com/hoau/ulyl/",
        "public_text_url": "https://fliphtml5.com/hoau/ulyl/Kivells_October_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/ulyl/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/ulyl/javascript/config.js",
        "expected_numbered_result_cards": 16, "expected_sold_cards": 11,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
    {
        "auction_date": "2023-11-22", "book_slug": "keyr",
        "source_url": "https://online.fliphtml5.com/hoau/keyr/",
        "public_text_url": "https://fliphtml5.com/hoau/keyr/Kivells_November_2023_Auction_Results/",
        "search_config_url": "https://online.fliphtml5.com/hoau/keyr/javascript/search_config.js",
        "config_url": "https://online.fliphtml5.com/hoau/keyr/javascript/config.js",
        "expected_numbered_result_cards": 25, "expected_sold_cards": 20,
        "article_url": ANNUAL_2023_ARTICLE_URL,
        "annual_review_url": ANNUAL_2023_REVIEW_URL,
    },
)
EVENTS = (
    {
        "auction_date": "2024-06-12",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/kivells-continues-to-generate-remarkable-auction-results-with-sales-topping-1-2-million-at-june-s-auction",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20June%202024%20Auction%20Results.pdf",
        "published_lot_count": 13,
    },
    {
        "auction_date": "2024-07-24",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20July%202024%20Auction%20Results.pdf",
        "published_lot_count": 14,
    },
    {
        "auction_date": "2024-09-04",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-1",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20September%202024%20Auction%20Results.pdf",
        "published_lot_count": 14,
    },
    {
        "auction_date": "2024-10-09",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/-16",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20October%202024%20Auction%20Results.pdf",
        "published_lot_count": 10,
    },
    {
        "auction_date": "2024-11-13",
        "article_url": "https://www.kivells.com/residentialsales/auctions/news/over-1-3-million-worth-of-property-sells-at-kivells-november-auction",
        "pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20November%202024%20Auction%20Results.pdf",
        "published_lot_count": None,
    },
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

MAY_EVENT = {
    "auction_date": "2024-05-15",
    "event_url": "https://www.kivells.com/property-sales/property-auctions/15-may-kivells-collective-property-auction-may-2024",
    "review_pdf_url": "https://www.kivells.com/media/Auctions/Kivells%20Collective%20Property%20Auction%20Half%20Year%20Review%202024%20for%20web.pdf",
    "running_order_lot_count": 14,
    "offered_lot_count": 13,
    "published_sold_result_count": 10,
    "published_value_sold": 1295000,
}

# The review publishes only the ten sold properties.  Its 10/13 offered-lot
# denominator does not identify the three unsold lots, while the event page has
# a 14-lot running order.  Keep the four unmatched outcomes null rather than
# assigning an unsupported result to the omitted/withdrawn lot.
MAY_RESULTS = (
    {
        "lot_number": "1", "event_location": "2.51 acres of woodland at Lanivet, Bodmin",
        "review_location": "Woodland at Lanivet, Bodmin", "guide_price": 25000,
        "sale_price": 30000, "sector": "land",
    },
    {
        "lot_number": "2", "event_location": "45 Higher Glen Park, Pensilva, Liskeard",
        "review_location": "45 Higher Glen Park, Pensilva, Liskeard", "guide_price": 160000,
        "sale_price": 178000, "sector": "residential",
    },
    {
        "lot_number": "4", "event_location": "3.40 acres of land adjacent to St. Eval, Wadebridge",
        "review_location": "Land Adjacent to St. Eval Church, St. Eval", "guide_price": 40000,
        "sale_price": 45000, "sector": "land",
    },
    {
        "lot_number": "6", "event_location": "5.66 acres of land on Robins Hill, Cookbury, Holsworthy",
        "review_location": "Land at Robins Hill, Cookbury", "guide_price": 40000,
        "sale_price": 56000, "sector": "land",
    },
    {
        "lot_number": "7", "event_location": "3.99 acres of woodland at Pillaton, Saltash",
        "review_location": "Land at Pillaton, Saltash", "guide_price": 35000,
        "sale_price": 35000, "sector": "land",
    },
    {
        "lot_number": "8", "event_location": "The Old Manor House, The Bridge, Boscastle",
        "review_location": "The Old Manor House, Boscastle", "guide_price": 375000,
        "sale_price": 410000, "sector": "commercial",
        "review_description": (
            "The Old Manor House Restaurant, Takeaway and Tea Garden is a landmark "
            "Grade II listed property in the heart of Boscastle Harbour."
        ),
    },
    {
        "lot_number": "9", "event_location": "4.95 acres of land at Tartan Down, Landrake, Saltash",
        "review_location": "Land at Tartendown, Landrake", "guide_price": 60000,
        "sale_price": 100000, "sector": "land",
    },
    {
        "lot_number": "10", "event_location": "The Posting House, Treworld, Boscastle",
        "review_location": "The Posting House, Treworld, Boscastle", "guide_price": 300000,
        "sale_price": 330000, "sector": "residential",
    },
    {
        "lot_number": "12", "event_location": "10.32 acres of land at Bude Farm, Exbourne, Okehampton",
        "review_location": "Land at Exbourne, Okehampton", "guide_price": 70000,
        "sale_price": 65000, "sector": "land",
    },
    {
        "lot_number": "13", "event_location": "1.58 acres of land at Golberdon, Callington",
        "review_location": "Land at Golberdon, Callington", "guide_price": 20000,
        "sale_price": 46000, "sector": "land",
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
    r"Withdrawn|Postponed|Available|Usold)\b\s*:?[ \t]*(£\s*[\d][\d,.]*)?",
    re.I,
)
BARE_SALE_RE = re.compile(
    r"\bGuide(?:\s+Price)?\s*:?[ \t]*£\s*[\d][\d,.]*"
    r"(?:\s*(?:-|–|to)\s*£\s*[\d][\d,.]*)?\s*\|\s*(£\s*[\d][\d,.]*)",
    re.I,
)
ADDRESS_CUE_RE = re.compile(
    r"\b(?:farm|farmhouse|house|cottage|bungalow|flat|apartment|land|field|"
    r"woodland|building\s+plot|development\s+site|plot|barn|garage|yard|"
    r"unit|premises|hotel|inn|chapel|church)\b",
    re.I,
)
EVENT_PAGE_LOT_RE = re.compile(r"(?im)^\s*Lot\s+(\d+)\s*[\-–—]\s*(.+?)\s*$")


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,|:-")
    return value or None


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    if not match:
        return None
    printed = match.group(1)
    if ("," in printed or "." in printed) and not re.fullmatch(
        r"\d{1,3}(?:[,.]\d{3})+", printed
    ):
        # Keep malformed source text verbatim but do not turn a dropped digit
        # such as £330,00 into a fabricated structured guide price.
        return None
    digits = re.sub(r"\D", "", printed)
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
        "sold": "sold", "unsold": "unsold", "usold": "unsold", "withdrawn": "withdrawn",
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
        bare_sale_match = BARE_SALE_RE.search(block) if not outcome_match else None
        if not outcome_match and not bare_sale_match:
            raise ValueError(f"lot {lot_number} has no published outcome")
        guide_low = money(guide_match.group(1)) if guide_match else None
        guide_high = money(guide_match.group(2)) if guide_match and guide_match.group(2) else None
        outcome_label = clean(outcome_match.group(1)) if outcome_match else "Sold"
        sale_price_text = (
            outcome_match.group(2) if outcome_match and outcome_match.group(2)
            else bare_sale_match.group(1) if bare_sale_match else None
        )
        cards.append({
            "lot_number": str(lot_number),
            "location": location,
            "address": location if is_address(location) else None,
            "guide_price": guide_low,
            "guide_price_high": guide_high,
            "guide_price_text": clean(guide_match.group(0)) if guide_match else None,
            "sale_price": money(sale_price_text),
            "status": status_from_text(outcome_label),
            "source_result_text": clean(
                outcome_match.group(0) if outcome_match else bare_sale_match.group(1)
            ),
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


def load_fliphtml_seed(path: Path = DEFAULT_FLIPHTML_SEED) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        seed = json.load(handle)
    if seed.get("schema_version") != 1 or not seed.get("books"):
        raise ValueError("Kivells FlipHTML5 seed has no recognised result books")
    return seed



def public_fliphtml_pages(raw: bytes, source_url: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    containers = soup.select(".flip-basic-text")
    pages = []
    for container in containers:
        text = container.get_text("\n", strip=True)
        if text:
            pages.append(text)
    if not pages:
        raise ValueError(f"public FlipHTML5 page has no page-text inventory: {source_url}")
    return pages


def fetch_fliphtml_book(spec: dict) -> dict:
    """Fetch one retained result book, with a public text-page fallback.

    The viewer's search_config.js is the preferred complete page inventory.
    FlipHTML5 also publishes the same pages as accessible HTML; that materially
    different route is used when the JS asset redirects or is unavailable.
    """
    item = dict(spec)
    retrieved_at = corpus.now()
    asset_headers = dict(HEADERS, Referer=spec["source_url"])
    search_response = requests.get(
        spec["search_config_url"], headers=asset_headers, timeout=120,
    )
    search_text = search_response.text
    public_html = None
    resolved_public_url = None
    try:
        search_response.raise_for_status()
        probe = dict(item, search_config_js=search_text)
        fliphtml_pages(probe)
        resolved_search_url = search_response.url
    except Exception:
        public_response = requests.get(
            spec["public_text_url"], headers=HEADERS, timeout=120,
        )
        public_response.raise_for_status()
        public_html = public_response.content
        pages = public_fliphtml_pages(public_html, spec["public_text_url"])
        search_text = "var textForPages = " + json.dumps(
            pages, ensure_ascii=False, separators=(",", ":")
        ) + ";"
        resolved_search_url = None
        resolved_public_url = public_response.url

    config_response = requests.get(
        spec["config_url"], headers=asset_headers, timeout=120,
    )
    config_response.raise_for_status()
    config_text = config_response.text
    if not config_text.strip():
        raise ValueError(f"empty FlipHTML5 viewer config: {spec['source_url']}")

    search_raw = search_text.encode("utf-8")
    config_raw = config_text.encode("utf-8")
    item.update(
        retrieved_at=retrieved_at,
        search_config_js=search_text,
        config_js=config_text,
        search_config_sha256=corpus.digest(search_raw),
        search_config_size_bytes=len(search_raw),
        config_sha256=corpus.digest(config_raw),
        config_size_bytes=len(config_raw),
        resolved_search_config_url=resolved_search_url,
        resolved_config_url=config_response.url,
        resolved_public_text_url=resolved_public_url,
    )
    if public_html is not None:
        item["public_text_html"] = public_html.decode("utf-8", errors="replace")
    return item


def saved_fliphtml_books() -> list[dict]:
    prefix = corpus.DATA / "sources/kivells-results/fliphtml5"
    books = []
    for metadata_path in sorted(prefix.glob("*-metadata.json")):
        metadata = json.loads(metadata_path.read_text())
        search_path = corpus.ROOT / metadata["search_config_snapshot_path"]
        config_path = corpus.ROOT / metadata["config_snapshot_path"]
        item = {
            key: value for key, value in metadata.items()
            if key not in {
                "search_config_snapshot_path", "config_snapshot_path",
                "public_text_snapshot_path", "page_assets",
            }
        }
        item["search_config_js"] = gzip.decompress(search_path.read_bytes()).decode("utf-8")
        item["config_js"] = gzip.decompress(config_path.read_bytes()).decode("utf-8")
        books.append(item)
    return books


def fliphtml_pages(item: dict) -> list[str]:
    match = re.fullmatch(
        r"\s*var\s+textForPages\s*=\s*(\[[\s\S]*\])\s*;?\s*",
        item["search_config_js"],
    )
    if not match:
        raise ValueError(f"unrecognised FlipHTML5 page inventory: {item['source_url']}")
    pages = json.loads(match.group(1))
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"empty FlipHTML5 page inventory: {item['source_url']}")
    return pages


def snapshot_fliphtml_book(item: dict, pages: list[str]) -> dict:
    search_raw = item["search_config_js"].encode("utf-8")
    config_raw = item["config_js"].encode("utf-8")
    search_sha = corpus.digest(search_raw)
    config_sha = corpus.digest(config_raw)
    if search_sha != item["search_config_sha256"] or len(search_raw) != item["search_config_size_bytes"]:
        raise ValueError("FlipHTML5 page inventory checksum/size mismatch")
    if config_sha != item["config_sha256"] or len(config_raw) != item["config_size_bytes"]:
        raise ValueError("FlipHTML5 viewer config checksum/size mismatch")
    prefix = corpus.DATA / "sources/kivells-results/fliphtml5"
    slug = item["book_slug"]
    search_path = prefix / f"{slug}-search-{search_sha[:16]}.js.gz"
    config_path = prefix / f"{slug}-config-{config_sha[:16]}.js.gz"
    if not search_path.exists():
        corpus.atomic(search_path, gzip.compress(search_raw, mtime=0))
    if not config_path.exists():
        corpus.atomic(config_path, gzip.compress(config_raw, mtime=0))
    page_assets = []
    for page_number, page in enumerate(pages, 1):
        raw = page.encode("utf-8")
        sha = corpus.digest(raw)
        path = prefix / f"{slug}-page-{page_number:02d}-{sha[:16]}.txt.gz"
        if not path.exists():
            corpus.atomic(path, gzip.compress(raw, mtime=0))
        page_assets.append(
            {
                "page_number": page_number,
                "sha256": sha,
                "source_size_bytes": len(raw),
                "snapshot_path": str(path.relative_to(corpus.ROOT)),
            }
        )
    public_snapshot_path = None
    public_sha = None
    if item.get("public_text_html") is not None:
        public_raw = item["public_text_html"].encode("utf-8")
        public_sha = corpus.digest(public_raw)
        public_path = prefix / f"{slug}-public-{public_sha[:16]}.html.gz"
        if not public_path.exists():
            corpus.atomic(public_path, gzip.compress(public_raw, mtime=0))
        public_snapshot_path = str(public_path.relative_to(corpus.ROOT))

    evidence = {
        "source_url": item["source_url"],
        "search_config_url": item["search_config_url"],
        "config_url": item["config_url"],
        "public_text_url": item.get("public_text_url"),
        "annual_review_url": item.get("annual_review_url"),
        "article_url": item.get("article_url"),
        "original_urls": [
            value for value in (
                item["source_url"], item["search_config_url"], item["config_url"],
                item.get("public_text_url"), item.get("annual_review_url"),
                item.get("article_url"),
            ) if value
        ],
        "retrieved_at": item["retrieved_at"],
        "search_config_sha256": search_sha,
        "search_config_snapshot_path": str(search_path.relative_to(corpus.ROOT)),
        "config_sha256": config_sha,
        "config_snapshot_path": str(config_path.relative_to(corpus.ROOT)),
        "public_text_sha256": public_sha,
        "public_text_snapshot_path": public_snapshot_path,
        "page_assets": page_assets,
        "basis": (
            "complete first-party FlipHTML5 result-book page-text inventory and "
            "viewer config, with accessible public page text retained when used"
        ),
    }
    corpus.save_json(
        prefix / f"{slug}-metadata.json",
        {
            key: value for key, value in {
                **item,
                "search_config_js": None,
                "config_js": None,
                "public_text_html": None,
                "search_config_snapshot_path": evidence["search_config_snapshot_path"],
                "config_snapshot_path": evidence["config_snapshot_path"],
                "public_text_snapshot_path": public_snapshot_path,
                "page_assets": page_assets,
            }.items() if value is not None
        },
    )
    return evidence


def build_fliphtml_rows(item: dict, pages: list[str], evidence: dict) -> tuple[dict, list[dict]]:
    auction_date, cards = parse_text("\n".join(pages), item["auction_date"])
    expected = item["expected_numbered_result_cards"]
    if len(cards) != expected:
        raise ValueError(
            f"{auction_date} publishes {len(cards)} result cards, expected {expected}"
        )
    expected_sold = item.get("expected_sold_cards")
    sold_statuses = {"sold", "sold_after", "sold_prior"}
    published_sold = sum(card["status"] in sold_statuses for card in cards)
    if expected_sold is not None and published_sold != expected_sold:
        raise ValueError(
            f"{auction_date} publishes {published_sold} sold cards, expected {expected_sold}"
        )
    event = {
        "auction_date": auction_date,
        "article_url": item["source_url"],
        "published_lot_count": expected,
    }
    state, rows = build_rows(cards, event, item["source_url"], evidence)
    state.update(
        parser_version=PARSER_VERSION,
        source_format="FlipHTML5 page-text inventory",
        source_url=item["source_url"],
        numbered_result_cards_in_book=len(rows),
        numbered_lots_in_pdf=None,
        published_lot_count_from_event_page=None,
        published_result_card_denominator=expected,
        published_sold_result_denominator=expected_sold,
        published_sold_result_cards=published_sold,
        denominator_basis=(
            "every unique outcome-bearing card in the complete retained first-party result book; "
            "distinct properties sharing a printed lot label remain separate"
        ),
        completion_scope="all numbered result cards across every retained book page",
        page_assets_snapshotted=len(pages),
        article_url=None,
    )
    return state, rows


def parse_may_event_page(raw: bytes) -> list[dict]:
    text = BeautifulSoup(raw, "html.parser").get_text("\n")
    text = text.replace("\xa0", " ")
    if not re.search(r"\b15(?:th)?\s+May(?:\s+2024)?\b", text, re.I):
        raise ValueError("May event page has no exact 15 May 2024 date")
    by_lot = {}
    for match in EVENT_PAGE_LOT_RE.finditer(text):
        lot_number = str(int(match.group(1)))
        location = clean(match.group(2))
        if not location:
            raise ValueError(f"May event lot {lot_number} has no location")
        card = {
            "lot_number": lot_number,
            "location": location,
            "address": location if is_address(location) else None,
            "guide_price": None,
            "guide_price_high": None,
            "guide_price_text": None,
            "sale_price": None,
            "status": "unknown",
            "source_result_text": None,
            "source_card_text": f"Lot {lot_number} – {location}",
            "source_duplicate_count": 0,
        }
        prior = by_lot.get(lot_number)
        if prior and prior["location"] != location:
            raise ValueError(f"May event lot {lot_number} has conflicting locations")
        by_lot[lot_number] = card
    cards = sorted(by_lot.values(), key=lambda card: int(card["lot_number"]))
    numbers = [int(card["lot_number"]) for card in cards]
    expected = MAY_EVENT["running_order_lot_count"]
    if numbers != list(range(1, expected + 1)):
        raise ValueError(f"May event running order is not exactly 1-{expected}: {numbers}")
    return cards


def extract_may_review(raw: bytes) -> dict[str, dict]:
    reader = PdfReader(BytesIO(raw))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = re.sub(r"\s+", " ", text).strip()
    section_matches = list(re.finditer(
        r"15th\s+May(?P<section>[\s\S]+?)12th\s+June", normalized, re.I,
    ))
    if not section_matches:
        raise ValueError("review PDF has no bounded 15 May result section")
    section = next(
        (
            match.group("section") for match in section_matches
            if re.search(r"10\s*/\s*13", match.group("section"))
            and "£1,295,000" in match.group("section")
        ),
        None,
    )
    if section is None:
        raise ValueError("review PDF does not preserve the 10/13 offered denominator")
    results = {}
    for result in MAY_RESULTS:
        location = re.sub(r"\s+", " ", result["review_location"]).strip()
        if location.casefold() not in section.casefold():
            raise ValueError(f"review PDF is missing May result card: {location}")
        guide_text = f"£{result['guide_price']:,}"
        sale_text = f"£{result['sale_price']:,}"
        if guide_text not in section or sale_text not in section:
            raise ValueError(f"review PDF is missing prices for May lot {result['lot_number']}")
        results[result["lot_number"]] = dict(result)
    if len(results) != MAY_EVENT["published_sold_result_count"]:
        raise ValueError("review PDF result-card denominator mismatch")
    if sum(item["sale_price"] for item in results.values()) != MAY_EVENT["published_value_sold"]:
        raise ValueError("review PDF result cards do not reconcile to published value sold")
    return results


def build_may_rows(cards: list[dict], results: dict[str, dict], evidence: dict) -> tuple[dict, list[dict]]:
    by_lot = {card["lot_number"]: dict(card) for card in cards}
    for lot_number, result in results.items():
        card = by_lot[lot_number]
        if clean(card["location"]).casefold() != clean(result["event_location"]).casefold():
            raise ValueError(f"May lot {lot_number} event-page identity changed")
        card.update(
            guide_price=result["guide_price"],
            guide_price_text=f"Guide £{result['guide_price']:,}",
            sale_price=result["sale_price"],
            status="sold",
            source_result_text=f"SOLD £{result['sale_price']:,}",
            source_card_text=(
                f"{card['source_card_text']} | review title: {result['review_location']} | "
                f"Guide £{result['guide_price']:,} | SOLD £{result['sale_price']:,}" +
                (f" | {result['review_description']}" if result.get("review_description") else "")
            ),
        )
    event = {
        "auction_date": MAY_EVENT["auction_date"],
        "article_url": MAY_EVENT["event_url"],
        "published_lot_count": MAY_EVENT["running_order_lot_count"],
    }
    state, rows = build_rows(
        list(by_lot.values()), event, MAY_EVENT["event_url"], evidence,
    )
    result_by_lot = {item["lot_number"]: item for item in results.values()}
    for row in rows:
        row["identity_method"] = "exact_event_date_lot_number_and_first_party_running_order"
        row["auction_date_basis"] = "exact date and lot number published on first-party event page"
        result = result_by_lot.get(row["lot_number"])
        if result:
            row["sector"] = result["sector"]
        elif "woodland" in (row.get("locality") or "").casefold():
            row["sector"] = "land"
    state.update(
        parser_version=PARSER_VERSION,
        source_format="first-party event page plus half-year review PDF",
        source_url=MAY_EVENT["event_url"],
        review_pdf_url=MAY_EVENT["review_pdf_url"],
        event_page_lot_denominator=MAY_EVENT["running_order_lot_count"],
        offered_lot_denominator=MAY_EVENT["offered_lot_count"],
        published_sold_result_denominator=MAY_EVENT["published_sold_result_count"],
        published_value_sold=MAY_EVENT["published_value_sold"],
        result_cards_matched=len(results),
        unmatched_result_fields_null=len(cards) - len(results),
        result_inventory_complete=False,
        denominator_basis=(
            "all 14 first-party running-order lots retained; official review publishes ten "
            "sold cards and states 10/13 offered, so four unmatched outcomes remain null"
        ),
        completion_scope="complete event-page running order with partial published result enrichment",
        event_page_count_note="14 running-order lots; 13 offered; 10 individually published sold results",
    )
    return state, rows


def get_html(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    if b"<html" not in response.content[:1000].lower():
        raise ValueError("event URL did not return HTML")
    return response


def may_snapshot_metadata_path() -> Path:
    return corpus.DATA / "sources/kivells-results/may-2024/metadata.json"


def load_or_fetch_may_sources(saved_only: bool) -> tuple[bytes, bytes, dict]:
    metadata_path = may_snapshot_metadata_path()
    if saved_only:
        metadata = json.loads(metadata_path.read_text())
        event_path = corpus.ROOT / metadata["event_page_snapshot_path"]
        review_path = corpus.ROOT / metadata["review_pdf_snapshot_path"]
        return gzip.decompress(event_path.read_bytes()), gzip.decompress(review_path.read_bytes()), metadata

    event_response = get_html(MAY_EVENT["event_url"])
    review_response = get_pdf(MAY_EVENT["review_pdf_url"])
    event_raw, review_raw = event_response.content, review_response.content
    event_sha, review_sha = corpus.digest(event_raw), corpus.digest(review_raw)
    prefix = corpus.DATA / "sources/kivells-results/may-2024"
    event_path = prefix / f"event-page-{event_sha[:16]}.html.gz"
    review_path = prefix / f"half-year-review-{review_sha[:16]}.pdf.gz"
    if not event_path.exists():
        corpus.atomic(event_path, gzip.compress(event_raw, mtime=0))
    if not review_path.exists():
        corpus.atomic(review_path, gzip.compress(review_raw, mtime=0))
    metadata = {
        "auction_date": MAY_EVENT["auction_date"],
        "event_page_url": MAY_EVENT["event_url"],
        "resolved_event_page_url": event_response.url,
        "event_page_sha256": event_sha,
        "event_page_snapshot_path": str(event_path.relative_to(corpus.ROOT)),
        "review_pdf_url": MAY_EVENT["review_pdf_url"],
        "resolved_review_pdf_url": review_response.url,
        "review_pdf_sha256": review_sha,
        "review_pdf_snapshot_path": str(review_path.relative_to(corpus.ROOT)),
        "retrieved_at": corpus.now(),
    }
    corpus.save_json(metadata_path, metadata)
    return event_raw, review_raw, metadata


def get_pdf(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("result URL did not return a PDF")
    return response


def snapshot_metadata_path(snapshot: Path) -> Path:
    return snapshot.with_suffix("").with_suffix(".json")


def saved_snapshot_dates(existing: list[dict]) -> dict[str, str]:
    """Resolve saved PDFs without guessing a single collection year.

    New downloads get an adjacent metadata record before parsing. Existing
    snapshots are reconciled from their permanently banked row evidence, which
    keeps the multi-year saved-only recovery route deterministic.
    """
    dates = {}
    for row in existing:
        evidence = row.get("source_evidence") or {}
        snapshot_path = evidence.get("snapshot_path")
        auction_date = row.get("auction_date")
        if snapshot_path and auction_date:
            dates[snapshot_path] = auction_date
    source_dir = corpus.DATA / "sources/kivells-results/results"
    for metadata_path in sorted(source_dir.glob("*.json")):
        metadata = json.loads(metadata_path.read_text())
        snapshot_path = metadata.get("snapshot_path")
        auction_date = metadata.get("auction_date")
        if snapshot_path and auction_date:
            dates[snapshot_path] = auction_date
    return dates


def harvest(saved_only: bool = False, fliphtml_seed_path: Path = DEFAULT_FLIPHTML_SEED) -> None:
    summary_path = corpus.DATA / "kivells_results_collection.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    completed = (
        set() if saved_only else set(previous.get("completed_source_urls") or [])
    )
    appearances_path = corpus.DATA / "appearances/kivells-results/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearances_path)) if appearances_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    before_counts = Counter(
        address=sum(bool(row.get("address")) for row in existing),
        partial=sum(not row.get("address") for row in existing),
        guide=sum(row.get("guide_price") is not None for row in existing),
        sale=sum(row.get("sale_price") is not None for row in existing),
        guide_evidence=sum(
            row.get("guide_price") is not None
            or row.get("guide_price_high") is not None
            or bool(row.get("guide_price_text"))
            for row in existing
        ),
        rent=sum(row.get("annual_rent") is not None for row in existing),
    )
    merged = {row["appearance_id"]: row for row in existing}
    failures = []
    completed_this_run = []
    completed_fliphtml_this_run = []
    completed_may_this_run = []
    saved_by_date = {}
    if saved_only:
        known_snapshot_dates = saved_snapshot_dates(existing)
        for snapshot in sorted((corpus.DATA / "sources/kivells-results/results").glob("*.pdf.gz")):
            raw = gzip.decompress(snapshot.read_bytes())
            relative_path = str(snapshot.relative_to(corpus.ROOT))
            auction_date = known_snapshot_dates.get(relative_path)
            if auction_date:
                saved_by_date[auction_date] = (snapshot, raw)
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
                corpus.save_json(snapshot_metadata_path(snapshot), {
                    "auction_date": event["auction_date"],
                    "article_url": event["article_url"],
                    "pdf_url": event["pdf_url"],
                    "resolved_source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                })
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

    seed_books = []
    if fliphtml_seed_path.exists():
        seed_books = load_fliphtml_seed(fliphtml_seed_path)["books"]
    fliphtml_manifest = list(seed_books) + [dict(item) for item in FLIPHTML_2023_EVENTS]
    fliphtml_books = list(seed_books)
    if saved_only:
        saved_by_url = {item["source_url"]: item for item in saved_fliphtml_books()}
        for item in FLIPHTML_2023_EVENTS:
            if item["source_url"] in saved_by_url:
                fliphtml_books.append(saved_by_url[item["source_url"]])
            else:
                failures.append({
                    "auction_date": item["auction_date"],
                    "url": item["source_url"],
                    "error": "FileNotFoundError: no immutable saved FlipHTML5 snapshot metadata",
                })
    else:
        for spec in FLIPHTML_2023_EVENTS:
            if spec["source_url"] in completed:
                continue
            try:
                fliphtml_books.append(fetch_fliphtml_book(spec))
            except Exception as exc:
                failures.append({
                    "auction_date": spec["auction_date"],
                    "url": spec["source_url"],
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })

    for item in fliphtml_books:
        if item["source_url"] in completed and not saved_only:
            continue
        try:
            pages = fliphtml_pages(item)
            evidence = snapshot_fliphtml_book(item, pages)
            state, rows = build_fliphtml_rows(item, pages, evidence)
            sha = evidence["search_config_sha256"]
            corpus.save_json(
                corpus.DATA / "auctions/kivells-results" / f"{item['auction_date']}-{sha[:12]}.json",
                state,
            )
            prior = [
                row for row in merged.values()
                if row.get("auction_date") == item["auction_date"]
            ]
            for row in prior:
                merged.pop(row["appearance_id"], None)
            for row in rows:
                merged[row["appearance_id"]] = row
            completed.add(item["source_url"])
            completed_fliphtml_this_run.append(item["source_url"])
            print(
                "KIVELLS FLIPHTML", item["auction_date"], len(rows),
                "numbered result cards", flush=True,
            )
        except Exception as exc:
            failures.append(
                {
                    "auction_date": item.get("auction_date"),
                    "url": item.get("source_url"),
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )

    if MAY_EVENT["event_url"] not in completed or saved_only:
        try:
            event_raw, review_raw, metadata = load_or_fetch_may_sources(saved_only)
            cards = parse_may_event_page(event_raw)
            results = extract_may_review(review_raw)
            evidence = {
                "source_url": metadata["resolved_event_page_url"],
                "retrieved_at": metadata["retrieved_at"],
                "sha256": metadata["event_page_sha256"],
                "snapshot_path": metadata["event_page_snapshot_path"],
                "review_pdf_url": metadata["resolved_review_pdf_url"],
                "review_pdf_sha256": metadata["review_pdf_sha256"],
                "review_snapshot_path": metadata["review_pdf_snapshot_path"],
                "original_urls": [MAY_EVENT["event_url"], MAY_EVENT["review_pdf_url"]],
                "basis": (
                    "complete first-party exact-dated running order enriched only by "
                    "individually published sold cards in the official review PDF"
                ),
            }
            state, rows = build_may_rows(cards, results, evidence)
            combined_sha = corpus.digest(event_raw + b"\0" + review_raw)
            corpus.save_json(
                corpus.DATA / "auctions/kivells-results" / f"{MAY_EVENT['auction_date']}-{combined_sha[:12]}.json",
                state,
            )
            prior = [
                row for row in merged.values()
                if row.get("auction_date") == MAY_EVENT["auction_date"]
            ]
            for row in prior:
                merged.pop(row["appearance_id"], None)
            for row in rows:
                merged[row["appearance_id"]] = row
            completed.add(MAY_EVENT["event_url"])
            completed_may_this_run.append(MAY_EVENT["event_url"])
            print(
                "KIVELLS MAY", MAY_EVENT["auction_date"], len(rows),
                "running-order lots and", len(results), "published sold results", flush=True,
            )
        except Exception as exc:
            failures.append({
                "auction_date": MAY_EVENT["auction_date"],
                "url": MAY_EVENT["event_url"],
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
        guide_evidence=sum(
            row.get("guide_price") is not None
            or row.get("guide_price_high") is not None
            or bool(row.get("guide_price_text"))
            for row in merged.values()
        ),
        rent=sum(row.get("annual_rent") is not None for row in merged.values()),
    )
    summary = {
        "checked_at": corpus.now(), "parser_version": PARSER_VERSION,
        "retrieval_route": (
            "saved_immutable_first_party_event_result_pdfs_and_fliphtml5_page_text"
            if saved_only else (
                "first_party_event_result_pdfs_and_fliphtml5_page_text_with_"
                "accessible_public_html_fallback"
            )
        ),
        "event_pdfs_in_manifest": len(EVENTS),
        "event_pdfs_banked": sum(event["pdf_url"] in completed for event in EVENTS),
        "event_pdfs_completed_this_run": len(completed_this_run),
        "event_pdfs_pending": sum(event["pdf_url"] not in completed for event in EVENTS),
        "fliphtml5_result_books_in_manifest": len(fliphtml_manifest),
        "fliphtml5_result_books_banked": sum(
            item["source_url"] in completed for item in fliphtml_manifest
        ),
        "fliphtml5_result_books_completed_this_run": len(completed_fliphtml_this_run),
        "fliphtml5_result_cards_reconciled": sum(
            item["expected_numbered_result_cards"] for item in fliphtml_manifest
            if item["source_url"] in completed
        ),
        "fliphtml5_2023_result_books_in_manifest": len(FLIPHTML_2023_EVENTS),
        "fliphtml5_2023_result_books_banked": sum(
            item["source_url"] in completed for item in FLIPHTML_2023_EVENTS
        ),
        "fliphtml5_2023_offered_cards_reconciled": sum(
            item["expected_numbered_result_cards"] for item in FLIPHTML_2023_EVENTS
            if item["source_url"] in completed
        ),
        "fliphtml5_2023_sold_cards_reconciled": sum(
            item["expected_sold_cards"] for item in FLIPHTML_2023_EVENTS
            if item["source_url"] in completed
        ),
        "event_page_review_inventories_in_manifest": 1,
        "event_page_review_inventories_banked": int(MAY_EVENT["event_url"] in completed),
        "event_page_review_inventories_completed_this_run": len(completed_may_this_run),
        "may_running_order_lots_reconciled": (
            MAY_EVENT["running_order_lot_count"] if MAY_EVENT["event_url"] in completed else 0
        ),
        "may_offered_lot_denominator": (
            MAY_EVENT["offered_lot_count"] if MAY_EVENT["event_url"] in completed else 0
        ),
        "may_published_sold_result_cards": (
            MAY_EVENT["published_sold_result_count"] if MAY_EVENT["event_url"] in completed else 0
        ),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": after_counts["address"] - before_counts["address"],
        "run_new_partial_lots": after_counts["partial"] - before_counts["partial"],
        "run_new_guide_prices": after_counts["guide"] - before_counts["guide"],
        "run_new_guide_evidence": after_counts["guide_evidence"] - before_counts["guide_evidence"],
        "run_new_sale_prices": after_counts["sale"] - before_counts["sale"],
        "run_new_rents": after_counts["rent"] - before_counts["rent"],
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
    fliphtml_failures = {
        failure.get("url") for failure in failures
        if failure.get("url") in {item["source_url"] for item in fliphtml_manifest}
    }
    if fliphtml_books and fliphtml_failures and not completed_fliphtml_this_run:
        raise SystemExit(1)
    may_failed = any(failure.get("url") == MAY_EVENT["event_url"] for failure in failures)
    if may_failed and not completed_may_this_run:
        raise SystemExit(1)
    if failures and not completed_this_run and not completed:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(saved_only="--reparse-saved" in sys.argv)
