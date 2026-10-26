"""Bank Robinson & Hall's surviving first-party EIG result-sheet archive.

The auctioneer's WordPress results page embeds an EIG ``pastauctions.aspx``
table.  Each date links to a flat result sheet containing stable EIG lot IDs,
addresses and published outcomes.  The published ``Lots Offered`` figure
excludes some withdrawn/postponed entries, so completeness is reconciled as
unique result rows >= lots offered; those extra appearances are retained.

This first pass intentionally does not infer guide prices or rents.  Those are
available only in per-lot catalogue/detail material and can be added without
changing the event/lot appearance identities established here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import gzip
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Robinson & Hall"
SLUG = "robinson-hall"
ARCHIVE_URL = "https://auctioneertemplates.eigroup.co.uk/pastauctions.aspx?a=384&c=rbh"
LEGACY_JUNE_ARTICLE_URL = (
    "https://robinsonandhall.co.uk/"
    "96-sold-so-far-this-year-at-our-land-and-property-auctions/"
)
LEGACY_APRIL_ARTICLE_URL = "https://robinsonandhall.co.uk/95-sold-so-far-this-year/"
LEGACY_APRIL_IMAGE_URL = (
    "https://robinsonandhall.co.uk/wp-content/uploads/2021/04/"
    "Auction-April-2021-Results.jpg"
)
LEGACY_APRIL_IMAGE_SHA256 = "c9a3de874f1fcae2f6b0d170e1cb8e6d9b039b5d57d72801a64f756cde6215bd"
LEGACY_JUNE_DATE = "2021-06-17"
LEGACY_APRIL_MONTH = "2021-04"
LEGACY_2023_SCHEDULE_URL = (
    "https://interactive.property-world.co.uk/robinsonandhall_feb23/Catalogue.pdf"
)
LEGACY_2023_SCHEDULE_SHA256 = "2a593fcc8cbda5a71ce720451c3761825d468007be216ef899cd6a2d75c9293d"
LEGACY_JUNE_2023_DATE = "2023-06-15"
LEGACY_JUNE_2023_ARTICLE_URL = "https://robinsonandhall.co.uk/89-sold-in-our-june-auction/"
LEGACY_JUNE_2023_IMAGE_URL = (
    "https://robinsonandhall.co.uk/wp-content/uploads/2023/07/"
    "Auction-June-2023-Results.jpg"
)
LEGACY_JUNE_2023_IMAGE_SHA256 = "95fd70e9cf8d62984c263b362f5e863048c4e1edb9ec61ad5ca833f27b8a82ff"
LEGACY_AUGUST_2023_DATE = "2023-08-03"
LEGACY_AUGUST_2023_ARTICLE_URL = "https://robinsonandhall.co.uk/83-sold-in-our-august-auction/"
LEGACY_AUGUST_2023_IMAGE_URL = (
    "https://robinsonandhall.co.uk/wp-content/uploads/2023/08/"
    "Auction-August-2023-Results-scaled.jpg"
)
LEGACY_AUGUST_2023_IMAGE_SHA256 = "772c9b892c8a744b9f1436831c5693a727cb4013332861bc26f80ec817285b02"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
RESULT_RE = re.compile(r"results\.aspx", re.I)
LOT_RE = re.compile(r"LotDetails\.aspx", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)
PARSER_VERSION = 3


# The April article publishes its results only as this first-party image. The
# rows below are a checked transcription of that immutable image, admitted
# only when the fetched bytes retain the expected SHA-256. The source does
# not publish an exact auction day, so auction_date must remain null.
APRIL_2021_ROWS = [
    ("1", "Land at Rookery House, The Lane, Wyboston, Bedford, Bedfordshire, MK44 3AP", "Sold for £80,000"),
    ("2", "Land at College Road North, Aston Clinton, Aylesbury, Buckinghamshire, HP22 5EZ", "Sold for £98,000"),
    ("3", "Land at 50 Brook Street East, Wellingborough, Northamptonshire, NN8 1ND", "Sold for £42,000"),
    ("4", "2 Ivy Road, Bedford, Bedfordshire, MK42 0QD", "Sold for £182,000"),
    ("5", "Plot 7, Land at Ringshall, Berkhamsted, Hertfordshire, HP4 1ND", "Sold for £15,000"),
    ("6", "18A High Street, Sandy, Bedfordshire, SG19 1AQ", "Sold Prior to auction, for an undisclosed amount"),
    ("7", "Priors Water Tower, Priors Hill, Pirton, Hitchin, Hertfordshire, SG5 3QA", "Unsold, the last bid was £159,000. Please refer to Auctioneer for Reserve"),
    ("8", "Flat 6, Guildhalls, 43 Ashburnham Road, Bedford, Bedfordshire, MK40 1DX", "Sold for £82,000"),
    ("9", "Flat 4, Guildhalls, 43 Ashburnham Road, Bedford, Bedfordshire, MK40 1DX", "Sold for £100,000"),
    ("10", "48 Miller Road, Bedford, Bedfordshire, MK42 9NZ", "Sold for £209,000"),
    ("11", "35 Upwell Road, Luton, Bedfordshire, LU2 9DZ", "Sold Prior to auction, for an undisclosed amount"),
    ("12", "40A Montagu Road, Datchet, Slough, Berkshire, SL3 9DW", "Sold for £600,000"),
    ("13", "Land R/O 39 Dunstable Road, Flitwick, Bedford, Bedfordshire, MK45 1HP", "Sold for £168,000"),
    ("14", "Flat D, 278 Hanworth Road, Hounslow, Middlesex, TW3 3TY", "Sold for £88,000"),
    ("15", "149 Queens Road, Watford, Hertfordshire, WD17 2QH", "Sold for £200,000"),
    ("16", "Land at Luton Road, Toddington, Dunstable, Bedfordshire, LU5 6HU", "Sold for £210,000"),
    ("17", "23 Fowler, Stantonbury, Milton Keynes, Buckinghamshire, MK14 6AP", "Sold for £175,000"),
]


# These first-party articles publish their complete visible result grids only
# as images. The checked transcriptions are admitted only while the image bytes
# retain the expected SHA-256 values above. Exact event dates are independently
# evidenced by the first-party February 2023 catalogue's published date list.
JUNE_2023_ROWS = [
    ("1", "10 Totternhoe Road, Dunstable, Bedfordshire, LU6 2AG", "Sold for £375,000."),
    ("2", "27E Kimbolton Road, Bedford, Bedfordshire, MK40 2NY", "Sold for £78,000."),
    ("3", "Manor Cottage, 59 High Road, Soulbury, Leighton Buzzard, Bedfordshire, LU7 0BT", "Sold for £420,000."),
    ("4", "55-57 High Street, Sandy, Bedfordshire, SG19 1AG", "Sold for £470,000."),
    ("5", "3 Chagford Close, Bedford, Bedfordshire, MK40 3AY", "Sold for £295,000."),
    ("6", "Former Barclays Bank, College Street, Rushden, Northamptonshire, NN10 0QQ", "Sold for £275,000."),
    ("7", "5 Cardigan Mews, Cardigan Street, Luton, Bedfordshire, LU1 1RN", "Sold for £90,000."),
    ("8", "2 Coronation Road, Stony Stratford, Milton Keynes, Buckinghamshire, MK11 1JJ", "Withdrawn Prior."),
    ("9", "4 Haynes Close, Bow Brickhill, Milton Keynes, Buckinghamshire, MK17 9JQ", "Sold for £440,000."),
    ("10", "120C, West Wycombe Road, High Wycombe, Buckinghamshire, HP12 3AA", "Sold post auction for an undisclosed amount."),
    ("11", "4 Swallow Close, Buckingham, Buckinghamshire, MK18 7ER", "Sold for £312,000."),
    ("12", "14 Chestnut Gardens, The Links, Kempston, Bedford, Bedfordshire, MK42 7PT", "Sold for £80,000."),
    ("13", "Flat 6, Hockliffe House, 87 Hockliffe Street, Leighton Buzzard, Bedfordshire, LU7 1EZ", "Sold post auction for an undisclosed amount."),
    ("14", "4 Hawk Drive, Sandy, Bedfordshire, SG19 2WA", "Sold for £330,000."),
    ("15", "17 Westbury Court, Torridge Rise, Bedford, Bedfordshire, MK41 7AN", "Sold prior to auction for £98,500."),
    ("16", "The Old Manse, 73 High Street, Newport Pagnell, Buckinghamshire, MK16 8AB", "Sold for £358,000."),
    ("17", "58 Clarendon Road, Luton, Bedfordshire, LU2 7PJ", "Sold for £247,000."),
    ("18", "Land at West End Road, Kempston, Bedford, Bedfordshire, MK43 8TH", "Sold for £200,000."),
    ("19", "Land at Gypsy Lane, Little Billington, Bedfordshire, LU7 9BP", "Withdrawn Prior."),
]

AUGUST_2023_ROWS = [
    ("1", "Land & Buildings at Dellfield Farm, Woburn Street, Millbrook, Bedford, MK45 2HY", "Sold for £395,000."),
    ("2", "The Walled Garden, Church End, Willington, Bedford, MK44 3PX", "Sold for £80,000."),
    ("3", "84 Putnoe Heights, Bedford, MK41 8ED", "Sold for £262,000."),
    ("4", "16 Newton Court, Hoppers Hill, Olney, MK46 5FN", "Unsold. The bidding reached £120,000. Contact the auctioneer."),
    ("5", "Plot 2, Land at Water Stratford, Buckingham, MK18 5DR", "Sold for £83,000."),
    ("6", "11 Roxburgh Way, Bletchley, Milton Keynes, MK3 7NZ", "Sold for £242,000."),
    ("7", "Frandean, 245 Icknield Way, Letchworth Garden City, SG6 4UE", "Unsold. The bidding reached £320,000. Contact the auctioneer."),
    ("8", "Barns at, 7A Brook End, Hatch, Sandy, SG19 1PP", "Sold for £440,000."),
    ("9", "Land on the south side of Highfield Road, Oakley, Bedford, MK43 7TA", "Sold for £38,000."),
    ("10", "Bury House, 8 London Road West, Amersham, HP7 0EZ", "Sold for £694,000."),
    ("11", "Barns at Manor Farm, Luton Road, Chalton, Luton, LU4 9UG", "Unsold. The bidding reached £396,000. Contact the auctioneer."),
    ("12", "Land At The Braid, Astrope Lane, Long Marston, Tring, HP23 4QT", "Sold prior to auction for £100,000."),
    ("13", "144 Arkwright Road, Irchester, Wellingborough, NN29 7HG", "Sold for £141,500."),
    ("14", "Land R/O 31A-C Mount Pleasant, Aspley Guise, Milton Keynes, MK17 8JZ", "Sold post auction for an undisclosed amount."),
    ("15", "215 and 216, West End, Elstow, Bedford, MK42 9XS", "Sold post auction for an undisclosed amount."),
    ("16", "Flats 3, 4, 6, 8, 9, 10 Cobham Mews, 3 West Street, Buckingham, MK18 1HL", "Withdrawn Prior."),
    ("17", "Plot 1, Land at Water Stratford, Buckingham, MK18 5DR", "Sold for £64,000."),
    ("18", "Flat 44, Dolphin Court, Kingsmead Road, High Wycombe, HP11 1XF", "Sold for £125,000."),
    ("19", "Parking Spaces, 20 High Street, Markyate, St. Albans, AL3 8PD", "Sold for £12,500."),
    ("20", "20 Manor Road, Bedford, MK41 9LQ", "Sold for £250,500."),
    ("21", "8 Church Street, Tempsford, Sandy, SG19 2AN", "Sold for £198,000."),
    ("22", "80 Someries Cottages, Someries, Luton, LU2 9PL", "Unsold. The bidding reached £420,000. Contact the auctioneer."),
    ("23", "Kiln Field, Keeley Lane, Wootton, Bedford, MK43 9HS", "Sold for £380,000."),
    ("24", "The Blue Barn and Land, West End, Kempston, Bedford, MK43 8TH", "Sold prior to auction for an undisclosed amount."),
]


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def exact_date(value: str) -> str:
    return datetime.strptime(clean(value) or "", "%A, %d %B %Y").date().isoformat()


def query_value(url: str, name: str) -> str | None:
    query = {key.casefold(): values for key, values in parse_qs(urlsplit(url).query).items()}
    values = query.get(name.casefold())
    return values[0] if values else None


def fetch(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def snapshot(raw: bytes, resolved: str, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def binary_snapshot(raw: bytes, resolved: str, name: str, suffix: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.{suffix}.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return evidence


def parse_archive(html: str, base_url: str = ARCHIVE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = []
    for row in soup.select("tr"):
        link = row.select_one('a[href*="results.aspx"]')
        cells = row.find_all(["td", "th"], recursive=False)
        if not link or len(cells) < 4:
            continue
        url = urljoin(base_url, link.get("href") or "")
        event_id = query_value(url, "au")
        offered_text = clean(cells[1].get_text(" ", strip=True)) or ""
        if not event_id or not offered_text.isdigit():
            continue
        events.append({
            "event_id": event_id,
            "auction_date": exact_date(link.get_text(" ", strip=True)),
            "result_url": url,
            "lots_offered": int(offered_text),
            "percent_sold": clean(cells[2].get_text(" ", strip=True)),
            "total_raised_text": clean(cells[3].get_text(" ", strip=True)),
        })
    identities = [event["event_id"] for event in events]
    if not events or len(identities) != len(set(identities)):
        raise ValueError("archive has no events or duplicate event identities")
    return events


def status_and_price(text: str | None) -> tuple[str, int | None, int | None]:
    value = clean(text) or ""
    lower = value.casefold()
    if "sold prior" in lower:
        status = "sold_prior"
    elif "sold post" in lower or "sold after" in lower:
        status = "sold_after"
    elif re.search(r"\bsold\b", lower):
        status = "sold"
    elif "withdrawn prior" in lower:
        status = "withdrawn_prior"
    elif "withdrawn" in lower:
        status = "withdrawn"
    elif "postponed" in lower:
        status = "postponed"
    elif "unsold" in lower or "no bid" in lower:
        status = "unsold"
    else:
        status = "unknown"
    sold_match = re.search(r"\bsold(?:\s+(?:prior|post|after)(?:\s+to\s+auction)?)?\s+for\s+£\s*([\d,]+(?:\.\d+)?)", value, re.I)
    sale_price = int(corpus.money(sold_match.group(1))) if sold_match and status.startswith("sold") else None
    bid_match = re.search(
        r"\b(?:bidding\s+reached|last\s+bid\s+was)\s+£\s*([\d,]+(?:\.\d+)?)",
        value,
        re.I,
    )
    bid_reached = int(corpus.money(bid_match.group(1))) if bid_match else None
    return status, sale_price, bid_reached


def classify_sector(address: str) -> str:
    """Classify only explicit address-level asset wording on this first pass."""
    value = address.casefold()
    if re.search(r"\bmixed[ -]?use\b", value):
        return "mixed-use"
    if re.search(r"\b(land|plot|paddock|woodland|field|meadow)\b", value):
        return "land"
    if re.search(r"\b(club|shop|retail|office|warehouse|factory|garage|industrial|pub|hotel|cafe|restaurant|commercial)\b", value):
        return "commercial"
    return corpus.sector(address)


def parse_result(html: str, event: dict, evidence: dict) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    rows, malformed = [], []
    for position, node in enumerate(soup.select("table.lot-table tr.lot-row, table.lot-table tr.lot-alt-row"), 1):
        cells = node.find_all("td", recursive=False)
        links = node.select('a[href*="LotDetails.aspx"]')
        lot = clean(cells[0].get_text(" ", strip=True)) if len(cells) >= 1 else None
        address = clean(cells[1].get_text(" ", strip=True)) if len(cells) >= 2 else None
        result_text = clean(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else None
        detail_url = urljoin(event["result_url"], links[0].get("href") or "") if links else None
        source_lot_id = query_value(detail_url, "LotID") if detail_url else None
        if not all((lot, address, result_text, detail_url, source_lot_id)):
            malformed.append({
                "position": position, "lot_number": lot, "address": address,
                "result_text": result_text, "detail_url": detail_url,
            })
            continue
        status, sale_price, bid_reached = status_and_price(result_text)
        row = corpus.base_row(
            SOURCE, f"{SLUG}:{event['event_id']}", event["auction_date"], lot,
            source_lot_id, detail_url,
        )
        postcode = corpus.PC.search(address)
        row.update(
            appearance_id=f"{SOURCE}|{SLUG}:{event['event_id']}|eig-lot:{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sale_price=sale_price,
            status=status,
            sector=classify_sector(address),
            property_id=f"eig-lot:{source_lot_id}",
            identity_method="first_party_eig_event_and_lot_id",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            source_platform="EIG",
            source_platform_lot_id=source_lot_id,
            reported_bid_reached=bid_reached,
            result_sheet_url=event["result_url"],
            source_evidence=evidence,
        )
        rows.append(row)
    return rows, malformed


def legacy_row(
    lot: str,
    address: str,
    result_text: str,
    source_lot_id: str,
    source_auction_id: str,
    original_url: str,
    evidence: dict,
    auction_date: str | None,
    position: int,
) -> dict:
    status, sale_price, bid_reached = status_and_price(result_text)
    row = corpus.base_row(
        SOURCE, source_auction_id, auction_date, lot, source_lot_id, original_url,
    )
    postcode = corpus.PC.search(address)
    row.update(
        appearance_id=f"{SOURCE}|{source_auction_id}|legacy-lot:{source_lot_id}",
        address=address,
        postcode=postcode.group().upper() if postcode else None,
        locality=address,
        sale_price=sale_price,
        status=status,
        sector=classify_sector(address),
        property_id=f"legacy-lot:{source_lot_id}",
        identity_method="first_party_event_lot_and_source_identity",
        record_quality="address_record",
        source_position=position,
        source_result_text=result_text,
        source_platform="EIG" if source_lot_id.isdigit() else "Robinson & Hall WordPress",
        source_platform_lot_id=source_lot_id if source_lot_id.isdigit() else None,
        reported_bid_reached=bid_reached,
        source_evidence=evidence,
    )
    return row


def parse_legacy_june_article(html: str, evidence: dict) -> tuple[list[dict], list[dict]]:
    """Parse the exact 17 June 2021 linked result table from the article."""
    soup = BeautifulSoup(html, "lxml")
    rows, malformed = [], []
    event_id = f"{SLUG}:wordpress-{LEGACY_JUNE_DATE}"
    for node in soup.select("tr"):
        cells = node.find_all(["td", "th"], recursive=False)
        link = node.select_one('a[href*="LotDetails.aspx"]')
        if len(cells) < 3 or not link:
            continue
        lot = clean(cells[0].get_text(" ", strip=True))
        address = clean(cells[1].get_text(" ", strip=True))
        result_text = clean(cells[2].get_text(" ", strip=True))
        detail_url = urljoin(LEGACY_JUNE_ARTICLE_URL, link.get("href") or "")
        source_lot_id = query_value(detail_url, "LotID")
        if not all((lot, address, result_text, source_lot_id)):
            malformed.append({"lot": lot, "address": address, "result": result_text, "url": detail_url})
            continue
        rows.append(legacy_row(
            lot, address, result_text, source_lot_id, event_id, detail_url,
            evidence, LEGACY_JUNE_DATE, len(rows) + 1,
        ))
    return rows, malformed


def april_image_rows(article_evidence: dict, image_evidence: dict) -> list[dict]:
    event_id = f"{SLUG}:wordpress-image-{LEGACY_APRIL_MONTH}"
    rows = []
    for position, (lot, address, result_text) in enumerate(APRIL_2021_ROWS, 1):
        source_lot_id = f"wordpress-image-{LEGACY_APRIL_MONTH}-lot-{lot}"
        row = legacy_row(
            lot, address, result_text, source_lot_id, event_id,
            LEGACY_APRIL_ARTICLE_URL, image_evidence, None, position,
        )
        row.update(
            source_month=LEGACY_APRIL_MONTH,
            source_date_text="April 2021",
            date_precision="month",
            article_published_date="2021-04-27",
            article_source_evidence=article_evidence,
            transcription_basis="checked transcription of immutable first-party results image",
        )
        rows.append(row)
    return rows


def dated_image_rows(
    source_rows: list[tuple[str, str, str]],
    auction_date: str,
    article_url: str,
    article_published_date: str,
    article_evidence: dict,
    image_evidence: dict,
    schedule_evidence: dict,
) -> list[dict]:
    event_id = f"{SLUG}:wordpress-image-{auction_date}"
    rows = []
    for position, (lot, address, result_text) in enumerate(source_rows, 1):
        source_lot_id = f"wordpress-image-{auction_date}-lot-{lot}"
        row = legacy_row(
            lot, address, result_text, source_lot_id, event_id,
            article_url, image_evidence, auction_date, position,
        )
        row.update(
            date_precision="day",
            article_published_date=article_published_date,
            article_source_evidence=article_evidence,
            auction_date_source_evidence=schedule_evidence,
            transcription_basis="checked transcription of immutable first-party results image",
        )
        rows.append(row)
    return rows


def address_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def existing_april_fingerprints(exclude_slug: str) -> set[tuple[str, str, int | None]]:
    """Find exact address/result matches already banked for April 2021."""
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            observed_month = (row.get("auction_date") or row.get("source_month") or "")[:7]
            if observed_month != LEGACY_APRIL_MONTH or not row.get("address"):
                continue
            values.add((address_key(row["address"]), row.get("status") or "unknown", row.get("sale_price")))
    return values


def existing_dated_fingerprints(exclude_slug: str) -> set[tuple[str, str, str, int | None]]:
    """Find exact date/address/result matches already banked elsewhere."""
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            if not row.get("auction_date") or not row.get("address"):
                continue
            values.add((
                row["auction_date"], address_key(row["address"]),
                row.get("status") or "unknown", row.get("sale_price"),
            ))
    return values


def existing_eig_appearances(exclude_slug: str) -> set[tuple[str, str]]:
    """Return exact event-date/EIG-lot pairs already banked elsewhere."""
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            url = row.get("original_url") or ""
            lot_id = query_value(url, "LotID") if LOT_RE.search(url) else None
            if lot_id and row.get("auction_date"):
                values.add((row["auction_date"], lot_id))
    return values


def harvest(workers: int = 8) -> dict:
    archive_raw, archive_resolved = fetch(ARCHIVE_URL)
    archive_evidence = snapshot(
        archive_raw, archive_resolved, "past-auctions",
        "first-party embedded EIG past-auction inventory",
    )
    events = parse_archive(archive_raw.decode("utf-8", "replace"), archive_resolved)
    fetched = {}
    failures = []
    with ThreadPoolExecutor(max_workers=min(workers, len(events))) as pool:
        futures = {pool.submit(fetch, event["result_url"]): event for event in events}
        for future in as_completed(futures):
            event = futures[future]
            try:
                fetched[event["event_id"]] = future.result()
            except Exception as exc:
                failures.append({
                    "event_id": event["event_id"], "url": event["result_url"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
    if failures:
        raise RuntimeError(f"result sheets failed before admission: {failures}")

    event_rows, event_summaries = {}, []
    for event in events:
        raw, resolved = fetched[event["event_id"]]
        evidence = snapshot(
            raw, resolved, f"event-{event['event_id']}",
            "first-party EIG auction result sheet",
            event_id=event["event_id"], auction_date=event["auction_date"],
        )
        rows, malformed = parse_result(raw.decode("utf-8", "replace"), event, evidence)
        identities = [(row["lot_number"], row["source_lot_id"]) for row in rows]
        reconciled = bool(
            not malformed and len(rows) >= event["lots_offered"]
            and len(identities) == len(set(identities))
        )
        if not reconciled:
            raise RuntimeError(
                f"event {event['event_id']} did not reconcile: rows={len(rows)}, "
                f"offered={event['lots_offered']}, malformed={len(malformed)}, "
                f"distinct={len(set(identities))}"
            )
        event_rows[event["event_id"]] = rows
        event_summaries.append({
            **event,
            "result_rows": len(rows),
            "additional_non_offered_rows": len(rows) - event["lots_offered"],
            "result_sheet_reconciled": True,
            "source_evidence": evidence,
        })

    rows = [row for event in events for row in event_rows[event["event_id"]]]
    archive_pairs = [(row["auction_date"], row["source_lot_id"]) for row in rows]
    if len(archive_pairs) != len(set(archive_pairs)):
        raise RuntimeError("same event-date/EIG-lot identity appears more than once in archive")

    global_pairs = existing_eig_appearances(SLUG)
    overlaps = [row for row in rows if (row["auction_date"], row["source_lot_id"]) in global_pairs]
    admissible = [row for row in rows if (row["auction_date"], row["source_lot_id"]) not in global_pairs]
    appearance_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]

    by_event = defaultdict(list)
    for row in admissible:
        by_event[row["source_auction_id"]].append(row)
    summaries_by_id = {f"{SLUG}:{event['event_id']}": event for event in event_summaries}
    for auction_id, date_rows in by_event.items():
        event = summaries_by_id[auction_id]
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event['auction_date']}-{event['event_id']}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": auction_id,
            "auction_date": event["auction_date"],
            "source_url": event["result_url"],
            "published_lots_offered": event["lots_offered"],
            "result_rows_captured": len(date_rows),
            "lots_captured": len(date_rows),
            "additional_non_offered_rows": event["additional_non_offered_rows"],
            "catalogue_complete": False,
            "source_rows_complete": True,
            "result_sheet_reconciled": True,
            "completion_scope": "all rows in the surviving first-party result sheet; per-lot catalogue/detail enrichment remains outstanding",
            "source_evidence": [archive_evidence, event["source_evidence"]],
            "errors": [],
            "checked_at": corpus.now(),
        })

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    historical = [row for row in added if cutoff <= (row.get("auction_date") or "") <= today]
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "parser_version": PARSER_VERSION,
        "source_url": archive_resolved,
        "archive_event_count": len(events),
        "published_lots_offered": sum(event["lots_offered"] for event in events),
        "visible_result_rows": len(rows),
        "additional_non_offered_rows": len(rows) - sum(event["lots_offered"] for event in events),
        "event_result_rows": {event["auction_date"]: event["result_rows"] for event in event_summaries},
        "result_sheets_reconciled": len(events),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "new_source_years": sorted(years_after - years_before),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "detail_pages_captured": 0,
        "catalogue_entries_captured": 0,
        "catalogue_detail_enrichment_complete": False,
        "completion_scope": "all rows in every event shown by the surviving first-party EIG archive; catalogue/detail guides, rents and richer sectors remain outstanding",
        "events": event_summaries,
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "robinson_hall_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def harvest_legacy(include_2021: bool = True) -> dict:
    """Bank pre-2024 first-party article evidence without refreshing completed sources."""
    june_rows = []
    april_rows = []
    if include_2021:
        june_raw, june_resolved = fetch(LEGACY_JUNE_ARTICLE_URL)
        june_evidence = snapshot(
            june_raw, june_resolved, "legacy-2021-06-17-article",
            "first-party WordPress article with linked individual result rows",
            auction_date=LEGACY_JUNE_DATE,
        )
        june_rows, june_malformed = parse_legacy_june_article(
            june_raw.decode("utf-8", "replace"), june_evidence,
        )
        june_ids = [row["source_lot_id"] for row in june_rows]
        if june_malformed or len(june_rows) != 20 or len(june_ids) != len(set(june_ids)):
            raise RuntimeError(
                f"legacy June article did not reconcile: rows={len(june_rows)}, "
                f"malformed={len(june_malformed)}, distinct={len(set(june_ids))}"
            )

        april_article_raw, april_article_resolved = fetch(LEGACY_APRIL_ARTICLE_URL)
        april_article_evidence = snapshot(
            april_article_raw, april_article_resolved, "legacy-2021-04-article",
            "first-party WordPress article publishing the April results image",
            source_month=LEGACY_APRIL_MONTH,
        )
        april_image_raw, april_image_resolved = fetch(LEGACY_APRIL_IMAGE_URL)
        if corpus.digest(april_image_raw) != LEGACY_APRIL_IMAGE_SHA256:
            raise RuntimeError("April 2021 results image changed; refusing checked transcription")
        if b"Auction-April-2021-Results" not in april_article_raw:
            raise RuntimeError("April article no longer references the checked results image")
        april_image_evidence = binary_snapshot(
            april_image_raw, april_image_resolved, "legacy-2021-04-results", "jpg",
            "immutable first-party results image with checked row transcription",
            source_month=LEGACY_APRIL_MONTH,
        )
        april_rows = april_image_rows(april_article_evidence, april_image_evidence)
        if len(april_rows) != 17 or len({row["lot_number"] for row in april_rows}) != 17:
            raise RuntimeError("April image transcription did not reconcile to 17 distinct lots")

    schedule_raw, schedule_resolved = fetch(LEGACY_2023_SCHEDULE_URL)
    if corpus.digest(schedule_raw) != LEGACY_2023_SCHEDULE_SHA256:
        raise RuntimeError("2023 first-party catalogue changed; refusing checked date evidence")
    schedule_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(schedule_raw)).pages
    )
    if "15th June 2023" not in schedule_text or "3rd August 2023" not in schedule_text:
        raise RuntimeError("2023 catalogue no longer contains both checked auction dates")
    schedule_evidence = binary_snapshot(
        schedule_raw, schedule_resolved, "legacy-2023-auction-schedule", "pdf",
        "first-party catalogue publishing the exact 2023 auction dates",
    )

    image_events = [
        {
            "auction_date": LEGACY_JUNE_2023_DATE,
            "article_url": LEGACY_JUNE_2023_ARTICLE_URL,
            "article_published_date": "2023-06-28",
            "image_url": LEGACY_JUNE_2023_IMAGE_URL,
            "image_sha256": LEGACY_JUNE_2023_IMAGE_SHA256,
            "rows": JUNE_2023_ROWS,
            "published_lots_offered": 17,
            "additional_non_offered_rows": 2,
        },
        {
            "auction_date": LEGACY_AUGUST_2023_DATE,
            "article_url": LEGACY_AUGUST_2023_ARTICLE_URL,
            "article_published_date": "2023-08-23",
            "image_url": LEGACY_AUGUST_2023_IMAGE_URL,
            "image_sha256": LEGACY_AUGUST_2023_IMAGE_SHA256,
            "rows": AUGUST_2023_ROWS,
            "published_lots_offered": None,
            "additional_non_offered_rows": None,
        },
    ]
    dated_rows = []
    dated_event_evidence = []
    for event in image_events:
        article_raw, article_resolved = fetch(event["article_url"])
        article_evidence = snapshot(
            article_raw, article_resolved,
            f"legacy-{event['auction_date']}-article",
            "first-party WordPress article publishing a complete results image",
            auction_date=event["auction_date"],
        )
        image_raw, image_resolved = fetch(event["image_url"])
        if corpus.digest(image_raw) != event["image_sha256"]:
            raise RuntimeError(
                f"{event['auction_date']} results image changed; refusing checked transcription"
            )
        image_name = Path(urlsplit(event["image_url"]).path).name
        if image_name.encode() not in article_raw:
            raise RuntimeError(
                f"{event['auction_date']} article no longer references the checked results image"
            )
        image_evidence = binary_snapshot(
            image_raw, image_resolved,
            f"legacy-{event['auction_date']}-results", "jpg",
            "immutable first-party results image with checked row transcription",
            auction_date=event["auction_date"],
        )
        rows = dated_image_rows(
            event["rows"], event["auction_date"], article_resolved,
            event["article_published_date"], article_evidence, image_evidence,
            schedule_evidence,
        )
        expected = len(event["rows"])
        if len(rows) != expected or len({row["lot_number"] for row in rows}) != expected:
            raise RuntimeError(
                f"{event['auction_date']} image transcription did not reconcile to {expected} distinct lots"
            )
        dated_rows.extend(rows)
        dated_event_evidence.append((event, article_resolved, article_evidence, image_evidence))

    global_pairs = existing_eig_appearances(SLUG)
    june_overlaps = [
        row for row in june_rows
        if (row["auction_date"], row["source_lot_id"]) in global_pairs
    ]
    april_fingerprints = existing_april_fingerprints(SLUG)
    april_overlaps = [
        row for row in april_rows
        if (address_key(row["address"]), row["status"], row.get("sale_price")) in april_fingerprints
    ]
    dated_fingerprints = existing_dated_fingerprints(SLUG)
    dated_overlaps = [
        row for row in dated_rows
        if (
            row["auction_date"], address_key(row["address"]), row["status"],
            row.get("sale_price"),
        ) in dated_fingerprints
    ]
    june_admissible = [row for row in june_rows if row not in june_overlaps]
    april_admissible = [row for row in april_rows if row not in april_overlaps]
    dated_admissible = [row for row in dated_rows if row not in dated_overlaps]
    admissible = june_admissible + april_admissible + dated_admissible

    appearance_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]

    if include_2021:
        corpus.save_json(corpus.DATA / "auctions" / SLUG / "2021-06-17-wordpress.json", {
            "auctioneer": SOURCE,
            "source_auction_id": f"{SLUG}:wordpress-{LEGACY_JUNE_DATE}",
            "auction_date": LEGACY_JUNE_DATE,
            "source_url": june_resolved,
            "published_lots_offered": 10,
            "result_rows_observed": 20,
            "lots_captured": len(june_admissible),
            "additional_non_offered_rows": 10,
            "duplicate_source_evidence_excluded": len(june_overlaps),
            "catalogue_complete": False,
            "source_rows_complete": True,
            "completion_scope": "all 20 linked rows in the surviving first-party article table",
            "source_evidence": [june_evidence],
            "errors": [],
            "checked_at": corpus.now(),
        })
        corpus.save_json(corpus.DATA / "auctions" / SLUG / "2021-04-undated-wordpress-image.json", {
            "auctioneer": SOURCE,
            "source_auction_id": f"{SLUG}:wordpress-image-{LEGACY_APRIL_MONTH}",
            "auction_date": None,
            "source_month": LEGACY_APRIL_MONTH,
            "date_precision": "month",
            "source_url": april_article_resolved,
            "published_lots_offered": None,
            "result_rows_observed": 17,
            "lots_captured": len(april_admissible),
            "duplicate_source_evidence_excluded": len(april_overlaps),
            "catalogue_complete": False,
            "source_rows_complete": True,
            "completion_scope": "all 17 rows in the immutable first-party April 2021 results image; exact auction day not published",
            "source_evidence": [april_article_evidence, april_image_evidence],
            "errors": [],
            "checked_at": corpus.now(),
        })
    for event, article_resolved, article_evidence, image_evidence in dated_event_evidence:
        event_rows = [
            row for row in dated_admissible
            if row["auction_date"] == event["auction_date"]
        ]
        event_overlaps = [
            row for row in dated_overlaps
            if row["auction_date"] == event["auction_date"]
        ]
        corpus.save_json(
            corpus.DATA / "auctions" / SLUG / f"{event['auction_date']}-wordpress-image.json",
            {
                "auctioneer": SOURCE,
                "source_auction_id": f"{SLUG}:wordpress-image-{event['auction_date']}",
                "auction_date": event["auction_date"],
                "date_precision": "day",
                "source_url": article_resolved,
                "published_lots_offered": event["published_lots_offered"],
                "result_rows_observed": len(event["rows"]),
                "lots_captured": len(event_rows),
                "additional_non_offered_rows": event["additional_non_offered_rows"],
                "duplicate_source_evidence_excluded": len(event_overlaps),
                "catalogue_complete": False,
                "source_rows_complete": True,
                "completion_scope": "all rows in the immutable first-party results image; exact date corroborated by first-party catalogue",
                "source_evidence": [article_evidence, image_evidence, schedule_evidence],
                "errors": [],
                "checked_at": corpus.now(),
            },
        )

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    historical = [row for row in added if cutoff <= (row.get("auction_date") or "") <= today]
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    summary_path = corpus.DATA / "robinson_hall_collection.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    summary.update({
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "parser_version": PARSER_VERSION,
        "legacy_article_events_reconciled": 4,
        "legacy_visible_result_rows": 80,
        "legacy_exact_dated_rows": 63,
        "legacy_month_only_rows": 17,
        "legacy_published_lots_offered": 27,
        "legacy_additional_non_offered_rows": 12,
        "legacy_source_urls": [
            LEGACY_JUNE_ARTICLE_URL, LEGACY_APRIL_ARTICLE_URL, LEGACY_APRIL_IMAGE_URL,
            schedule_resolved,
            *[
                value for event in dated_event_evidence
                for value in (event[1], event[3]["source_url"])
            ],
        ],
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_duplicate_source_evidence_excluded": (
            len(june_overlaps) + len(april_overlaps) + len(dated_overlaps)
        ),
        "new_source_years": sorted(years_after - years_before),
        "date_range": [
            min(row["auction_date"] for row in merged.values() if row.get("auction_date")),
            max(row["auction_date"] for row in merged.values() if row.get("auction_date")),
        ],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "legacy_failures": [],
        "catalogue_detail_enrichment_complete": False,
        "completion_scope": "2024-2026 EIG result sheets plus all surviving rows in four first-party 2021/2023 article sources; other pre-2024 event inventories remain unreconciled",
    })
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--legacy-only", action="store_true")
    parser.add_argument("--legacy-2023-only", action="store_true")
    args = parser.parse_args()
    if args.legacy_only or args.legacy_2023_only:
        harvest_legacy(include_2021=not args.legacy_2023_only)
    else:
        harvest(args.workers)


if __name__ == "__main__":
    main()
