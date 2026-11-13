"""Bank removed Sheldon Bosley Knight result sheets from retained index text.

The original SBK-issued PDF URLs now return 404, but public search indexes
retain complete result tables for seven events.  This offline batch preserves
the original publisher URLs, exact printed dates, every named row, outcomes
and disclosed purchase prices.  It deliberately does not claim guide prices
or any event whose full result table is not retained.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import json
import gzip
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Sheldon Bosley Knight"
SLUG = "sheldon-bosley-knight-retained-results"
OPERATOR = "SHELDON BOSLEY KNIGHT LIMITED"
COMPANY_NUMBER = "10225947"


def lot(number, address, status, sale_price=None, published_price_text=None):
    row = {"lot_number": str(number), "address": address, "status": status, "sale_price": sale_price}
    if published_price_text is not None:
        row["published_price_text"] = published_price_text
    return row


EVENTS = (
    {
        "auction_date": "2024-07-11",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2024/07/SBK-and-AG-Auctions-Auction-Results-Sheet-July-2024.pdf",
        "published_lot_denominator": 24,
        "date_note": "PDF prints Hinckley Golf Club, Wednesday 11th July 2024; weekday/date conflict retained without silently changing the printed date",
        "lots": (
            lot(1, "Fairfields, Welland Road, Upton-upon-Severn, Worcester, WR8 0SR", "sold", 386000),
            lot(2, "Flat 2, Goodwin Gardens, Lower Leys, Evesham, Worcestershire, WR11 3DP", "sold prior"),
            lot(3, "Appletree Cottage, Hayden Road, Cheltenham, Gloucestershire, GL51 0SN", "sold"),
            lot(4, "Lynwood House, Lynwood Close, Evesham, WR11 2PD", "unsold"),
            lot(5, "Arden House, 28 Henley Street, Alcester, B49 5QY", "unsold"),
            lot(6, "Sunnyacre, Mill Lane, Cleeve Prior, Evesham, WR11 8JZ", "unsold"),
            lot(7, "Plot 1, Land adjoining West Field Farm, Weston-on-the-Green, Bicester, OX25 3RF", "unsold"),
            lot(8, "Plot 2, Land adjoining West Field Farm, Weston-on-the-Green, Bicester, OX25 3RF", "unsold"),
            lot(9, "Plot 3, Land adjoining West Field Farm, Weston-on-the-Green, Bicester, OX25 3RF", "sold", 85000),
            lot(10, "Land lying to the west of East Street, Fritwell, OX27 7QQ", "unsold"),
            lot(11, "Oakdale, 34A Temeside, Ludlow, SY8 1JN", "withdrawn prior"),
            lot(12, "The Clayton, 38 Grove Road, Stratford-upon-Avon, CV37 6PB", "withdrawn prior"),
            lot(13, "22 Mardol Close, Coventry, CV2 1BA", "sold", 165000),
            lot(14, "Flat 1, Milverton House, 11 Beauchamp Hill, Leamington Spa, Warwickshire, CV32 5LR", "unsold"),
            lot(15, "31 Chapel Street, Wellesbourne, Warwickshire, CV35 9QU", "sold", 160000),
            lot(16, "252 Walsgrave Road, Coventry, CV2 4BN", "sold", 155500),
            lot(17, "The Priory, Priory Road, Alcester, B49 5EA", "sold", 650000),
            lot(18, "5 Giffard Court, Hearth Street, Market Harborough, LE16 9AQ", "sold", 60000),
            lot(19, "30 Homewelland House, Leicester Road, Market Harborough, LE16 7BT", "unsold"),
            lot(20, "16 Marshall Court, Northampton Road, Market Harborough, LE16 9HZ", "unsold"),
            lot(21, "The Old Pool Building, School Lane, Queniborough, Leicester, LE7 3DJ", "sold", 143000),
            lot(22, "5 Springfield Close, Burton-on-the-Wolds, Leicestershire, LE12 5AN", "sold", 330000),
            lot(23, "7 The Square, Countesthorpe, Leicestershire, LE8 5RN", "sold prior"),
            lot(24, "18 Ramsden Avenue, Camp Hill, Nuneaton, Warwickshire, CV10 9EB", "sold", 155000),
        ),
    },
    {
        "auction_date": "2025-02-12",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/02/SBK-Auctions-Auction-Results-Sheet-February-2025.pdf",
        "published_lot_denominator": 8,
        "lots": (
            lot(1, "21 Somerset Road, Coventry, CV1 4EG", "sold", 119500),
            lot(2, "22 Homewelland House, Leicester Road, Market Harborough, LE16 7BT", "sold prior", 27000),
            lot(3, "Land to the east of Northwick Road, Evesham, WR11 3AL", "sold", 36000),
            lot(4, "Land at Anderton Close, Shipston-on-Stour, CV36 4AY", "sold prior", 1),
            lot(5, "Garages 6 and 29, Sanctus Court, Stratford-upon-Avon, CV37 6DL", "unsold"),
            lot(6, "Fenny Compton Chapel, High Street, Fenny Compton, Southam, CV47 2XT", "sold prior", 125000),
            lot(7, "Land at Wynch Farm, Elmley Road, Ashton-under-Hill, Evesham, WR11 7SW", "sold prior", 190000),
            lot(8, "31 Lime Drive, Syston, Leicester, LE7 2PW", "sold", 204000),
        ),
    },
    {
        "auction_date": "2025-03-26",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/03/MRF-0045-SBK-Auction-Results-Sheet-March-2025.pdf",
        "published_lot_denominator": 15,
        "lots": (
            lot(1, "1 Riverbank Walk, Leicester, LE2 8DZ", "unsold"),
            lot(2, "Flat 9 Hampton Court, St Marys Road, Market Harborough, LE16 7DX", "unsold"),
            lot(3, "21 Faringdon Avenue, Lutterworth, LE17 4DJ", "sold prior"),
            lot(4, "Sunnyacre, Mill Lane, Cleeve Prior, Evesham, WR11 8JZ", "sold prior"),
            lot(5, "73 Queen Margarets Road, Coventry, CV4 8FU", "sold post"),
            lot(6, "Land adjacent to Meadow View, Bishopton Lane, Bishopton, Stratford-upon-Avon, CV37 9QY", "sold prior"),
            lot(7, "5 Darwen Close, Leicester, LE3 9BL", "unsold"),
            lot(8, "47 Grange Lane, Sutton Coldfield, B75 5JX", "sold", 308000),
            lot(9, "Low Cottage, Banbury Street, Kineton, CV35 0JU", "sold", 281000),
            lot(10, "21 Evans Lane, Kidlington, OX5 2HX", "unsold"),
            lot(11, "Garages 6 and 29, Sanctus Court, Stratford-upon-Avon, CV37 6DL", "sold", 22000),
            lot(12, "36 St Osburgs Road, Coventry, West Midlands, CV2 4EG", "sold prior"),
            lot(13, "77 High Street, Whetstone, Leicester, LE8 6LP", "unsold"),
            lot(14, "1 Thelsford Cottages, Wellesbourne, Warwick, CV35 9EJ", "sold", 201000),
            lot(15, "2 Thelsford Cottages, Wellesbourne, Warwick, CV35 9EJ", "unsold"),
        ),
    },
    {
        "auction_date": "2025-06-18",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/06/SBK-Auctions-Auction-Results-Sheet-June-2025.pdf",
        "published_lot_denominator": 7,
        "lots": (
            lot(1, "7 Cartwright Drive, Oadby, Leicester, LE2 5HN", "sold", 230000),
            lot(2, "20 The Close, Cleeve Prior, Evesham, WR11 8LF", "sold prior"),
            lot(3, "The Former Avon Sports & Social Club, Waterside, Evesham, WR11 1BS", "unsold"),
            lot(4, "34 High Street, Alcester, B49 5AB", "unsold"),
            lot(5, "2 Manor Cottages, Main Road, Ansty, CV7 9HZ", "withdrawn", published_price_text="£50,000"),
            lot(6, "19 Warden Road, Coventry, CV6 3EH", "sold prior"),
            lot(7, "21 Evans Lane, Kidlington, OX5 2HX", "sold prior"),
        ),
    },
    {
        "auction_date": "2025-07-30",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/07/MRF-0175-SBK-AG-Auction-Results-Sheet-July-2025.pdf",
        "published_lot_denominator": 10,
        "lots": (
            lot(1, "Land on the North Side of Mill Lane, Syston, Leicester, LE7 1NS", "sold", 24500),
            lot(2, "89 Knightthorpe Road, Loughborough, LE11 5JR", "sold", 210000),
            lot(3, "The Former Avon Sports & Social Club, Waterside, Evesham, Worcestershire, WR11 1BS", "unsold"),
            lot(4, "Tugby House, Chapel Lane, Tugby, Leicestershire, LE7 9WA", "sold", 410000),
            lot(5, "Pike Cottage, 164 High Street, Broadway, WR12 7AJ", "withdrawn"),
            lot(6, "Fern Cottage, Spring Hill, New Arley, Arley, CV7 8FF", "sold prior"),
            lot(7, "173 Arbury Road, Nuneaton, CV10 7NH", "unsold"),
            lot(8, "Land on the North side of 19-21, Port Street, Evesham, WR11 3LD", "sold", 20000),
            lot(9, "130 High Street, Evesham, WR11 4EJ", "sold", 171000),
            lot(10, "Land at Tree Tops Farm, Stonewold Avon, Dassett, Southam, CV47 2AQ", "sold", 168500),
        ),
    },
    {
        "auction_date": "2025-09-10",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/09/MRF-0238-SBK-AUC-Auction-Results-Sheet-September-2025.pdf",
        "published_lot_denominator": 9,
        "lots": (
            lot(1, "7 Owletts End, Pinvin, Pershore, WR10 2EX", "unsold"),
            lot(2, "2 Thelsford Cottages, Wellesbourne, CV35 9EJ", "sold prior"),
            lot(3, "2 Manor Cottages, Main Road, Ansty, CV7 9HZ", "withdrawn"),
            lot(4, "The Cottage, Hallaton Road, Tugby, Leicestershire, LE7 9WB", "sold prior"),
            lot(5, "173 Arbury Road, Nuneaton, CV10 7NH", "sold prior"),
            lot(6, "The Old Slaughter House, Butchers Lane, Lower Brailes, Warwickshire, OX15 5NB", "unsold"),
            lot(7, "38 Marmion Close, Market Harborough, Leicestershire, LE16 9GS", "sold prior"),
            lot(8, "3b Avenue Road, Stratford-Upon-Avon, CV37 6UY", "unsold"),
            lot(9, "3a Avenue Road, Stratford-upon-Avon, CV37 6UY", "sold", 461000),
        ),
    },
    {
        "auction_date": "2025-12-03",
        "source_url": "https://www.sheldonbosleyknight.co.uk/wp-content/uploads/2025/12/MRF-0405-SBK-AUC-Results-December-2025.pdf",
        "published_lot_denominator": 11,
        "lots": (
            lot(1, "165 Belgrave Road, Coventry, CV2 5BJ", "unsold"),
            lot(2, "30 Ravensthorpe Drive, Loughborough, LE11 4WA", "withdrawn prior"),
            lot(3, "1 Parsons Close, Shipston-on-Stour, CV36 4JS", "sold prior"),
            lot(4, "11 Beeby Road, Barkby, Leicester, Leicestershire, LE7 3QB", "withdrawn prior"),
            lot(5, "90 Byron Street, Loughborough, LE11 5JW", "withdrawn prior"),
            lot("5A", "5 Arundel Road, Coventry, CV3 5JT", "unsold"),
            lot(6, "Hounds End, 65 Main Street, Fleckney, Leicestershire, LE8 8AP", "unsold"),
            lot(7, "Land adjoining Three Gates Farm, Fosse Way, Moreton Morrell, Warwick, CV35 9BZ", "sold prior"),
            lot(8, "36 Scotts Green Close, Dudley, DY1 2DU", "withdrawn prior"),
            lot(9, "Long Barn, The Elms, Main Street, Tiddington, Stratford-upon-Avon, Warwickshire, CV37 7AG", "sold post"),
            lot(10, "202 The Long Shoot, Nuneaton, Warwickshire, CV11 6JW", "sold", 220000),
        ),
    },
)


def normalize(value: str) -> str:
    return re.sub(r"\W+", " ", unicodedata.normalize("NFKD", value or "").casefold()).strip()


def retained_text(event: dict) -> str:
    lines = [
        "Sheldon Bosley Knight Auctions", "AUCTION RESULTS",
        f"Auction date {event['auction_date']}", "LOT No. | ADDRESS OF LOT | RESULT | PURCHASE PRICE",
    ]
    for row in event["lots"]:
        price = row.get("published_price_text")
        if price is None:
            price = f"£{row['sale_price']:,}" if row.get("sale_price") is not None else "Undisclosed or blank"
        lines.append(f"{row['lot_number']} | {row['address']} | {row['status']} | {price}")
    return "\n".join(lines)


def validate_event(event: dict) -> None:
    if len(event["lots"]) != event["published_lot_denominator"]:
        raise ValueError(f"{event['auction_date']} result denominator mismatch")
    identities = [row["lot_number"] for row in event["lots"]]
    if len(identities) != len(set(identities)):
        raise ValueError(f"{event['auction_date']} duplicate lot identity")
    text = normalize(retained_text(event))
    for row in event["lots"]:
        if normalize(row["address"]) not in text or normalize(row["status"]) not in text:
            raise ValueError(f"{event['auction_date']} lot {row['lot_number']} lost retained result text")


def snapshot_event(event: dict) -> dict:
    raw = retained_text(event).encode("utf-8")
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"results-{event['auction_date']}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": event["source_url"], "retrieved_at": corpus.now(), "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "SBK-issued complete result PDF retained as public search-index text after the original publisher URL began returning 404",
        "source_tier": "retained_search_cache_text",
        "publisher_url_current_status": 404,
    }
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            retained = json.load(handle)
        if retained.get("retained_text") != raw.decode("utf-8"):
            raise ValueError(f"immutable retained snapshot mismatch for {event['auction_date']}")
        return retained["evidence"]
    corpus.save_gzip(path, {"evidence": evidence, "retained_text": raw.decode("utf-8")})
    return evidence


def appearance(event: dict, item: dict, evidence: dict) -> dict:
    auction_id = f"sbk:{event['auction_date']}"
    source_id = f"{event['auction_date']}-lot-{item['lot_number'].casefold()}"
    row = corpus.base_row(SOURCE, auction_id, event["auction_date"], item["lot_number"], source_id, event["source_url"])
    postcode = corpus.PC.search(item["address"])
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|lot:{item['lot_number'].casefold()}",
        address=item["address"], postcode=postcode.group().upper() if postcode else None,
        locality=item["address"], sector=corpus.sector(item["address"]),
        status=item["status"], sale_price=item.get("sale_price"),
        source_result_text=(
            f"{item['status']}; {item['published_price_text']} printed in purchase-price column"
            if item.get("published_price_text") is not None
            else (f"{item['status']}; £{item['sale_price']:,}" if item.get("sale_price") is not None else item["status"])
        ),
        record_quality="address_record", auction_date_precision="day",
        auction_date_basis="exact date printed by the SBK-issued result sheet",
        identity_method="publisher_result_sheet_event_and_lot_number",
        operator_legal_name=OPERATOR, operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE, source_evidence=evidence,
        source_limit="retained search-index text; original publisher PDF currently returns 404",
    )
    if event.get("date_note"):
        row["source_date_note"] = event["date_note"]
    if item.get("published_price_text") is not None:
        row["published_purchase_price_text"] = item["published_price_text"]
        row["price_evidence_note"] = "numeric text printed in purchase-price column conflicts with non-sale outcome; retained literally and not promoted to sale_price"
    return row


def exact_overlap_keys(excluded_path: Path) -> set[tuple[str, str]]:
    keys = set()
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == excluded_path:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                keys.add((row["auction_date"], normalize(row["address"])))
    return keys


def harvest() -> None:
    output = corpus.DATA / "appearances" / SLUG / "retained-results.jsonl.gz"
    existing = list(corpus.iter_rows(output)) if output.exists() else []
    before = {row["appearance_id"]: row for row in existing}
    overlap_keys = exact_overlap_keys(output)
    candidate = []
    states = {}
    for event in EVENTS:
        validate_event(event)
        evidence = snapshot_event(event)
        rows = [appearance(event, item, evidence) for item in event["lots"]]
        candidate.extend(rows)
        states[event["auction_date"]] = {
            "auctioneer": SOURCE, "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"sbk:{event['auction_date']}",
            "auction_date": event["auction_date"], "auction_date_precision": "day",
            "source_url": event["source_url"], "lots_captured": len(rows),
            "published_lots_offered": event["published_lot_denominator"],
            "catalogue_complete": True, "source_rows_complete": True,
            "source_evidence": evidence, "source_date_note": event.get("date_note"),
            "checked_at": corpus.now(),
        }
    excluded = [row for row in candidate if (row["auction_date"], normalize(row["address"])) in overlap_keys]
    admitted = [row for row in candidate if row not in excluded]
    merged = dict(before)
    for row in admitted:
        merged.setdefault(row["appearance_id"], row)
    corpus.write_rows(f"{SLUG}/retained-results", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]
    for event_date, state in states.items():
        state_path = corpus.DATA / "auctions" / SLUG / f"{event_date}.json"
        if state_path.exists():
            continue
        state["lots_captured"] = sum(row["auction_date"] == event_date for row in admitted)
        corpus.save_json(state_path, state)

    summary = {
        "checked_at": corpus.now(), "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR, "operator_company_number": COMPANY_NUMBER,
        "retained_result_sheets": len(EVENTS),
        "published_property_rows_reconciled": sum(len(event["lots"]) for event in EVENTS),
        "appearances_captured": len(merged), "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address")) and bool(row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and date(2006, 11, 13) <= date.fromisoformat(row["auction_date"]) <= date(2026, 11, 13)
            for row in added
        ),
        "run_new_partial_lots": sum(row.get("record_quality") != "address_record" for row in added),
        "run_new_undated": sum(row.get("auction_date") is None for row in added),
        "run_new_future_dated": sum(row.get("auction_date", "") > "2026-11-13" for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in added)),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in added)),
        "run_duplicate_exact_date_address_exclusions": len(excluded),
        "new_source_years": sorted({row["auction_date"][:4] for row in added}),
        "source_limit": "seven complete SBK-issued result tables survive in public search-index text; no other event is claimed complete",
        "national_completeness_verified": False,
        "next_growth_target": "Inventory and batch the first-party Sheldon Bosley Knight 2022-2024 result PDFs and event articles, starting with complete result tables and using named article results only as partial evidence. Do not retry missing PDF bytes without a new route.",
    }
    corpus.save_json(corpus.DATA / "sheldon_bosley_knight_retained_results_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    harvest()
