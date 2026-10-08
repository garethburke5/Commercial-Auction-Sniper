#!/usr/bin/env python3
"""Reconcile a surviving legacy Savills result grid into the lot corpus.

The archived Savills catalogue establishes the auction date, offered total,
page extent, and its first visible lot page.  PropertyAuctions exposes the
complete result grid for the same AID.  This collector requires the two totals
to agree, requires one secondary row per lot label, and cross-checks every
first-party row before writing a complete source-corpus shard.  Existing
page-one partial rows are removed from the mixed legacy source so the normal
``bank-source-corpus`` pass can replace them without duplicate appearances.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/historical_source_corpus"
MIXED_SOURCE = CORPUS / "savills_2005_2009_saved_catalogue_grid_lots_20260928.json"
MIXED_SHARD = (
    ROOT
    / "data/auction_history/appearances/source-corpus"
    / "savills_2005_2009_saved_catalogue_grid_lots_20260928.jsonl.gz"
)
MIXED_SOURCE_KEY = f"source-corpus/{MIXED_SOURCE.stem}"
STAGING_SOURCE_GLOB = "savills_*saved_catalogue_grid_lots_*.json"
SECONDARY_URL = "https://propertyauctions.com/Results/LotList.aspx?AID={aid}"
USER_AGENT = "Commercial-Auction-Sniper historical corpus/1.0"
LOT_LABEL_RE = re.compile(r"(?:\d+[A-Za-z]?|[A-Za-z])")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def money(text: str) -> int | None:
    match = re.search(r"£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    amount *= {"": 1, "K": 1_000, "M": 1_000_000}[match.group(2).upper() if match.group(2) else ""]
    return round(amount)


def parse_secondary(html: bytes) -> tuple[int, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(id="resultsListContainer") or soup
    match = re.search(r"\bOffered:\s*(\d+)\b", container.get_text(" ", strip=True), re.I)
    if not match:
        raise ValueError("Secondary result grid has no Offered denominator")
    offered = int(match.group(1))
    candidates: list[list[dict[str, str]]] = []
    for table in container.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            if len(cells) == 4 and LOT_LABEL_RE.fullmatch(cells[0]):
                rows.append({"lot": cells[0], "type": cells[1], "location": cells[2], "result": cells[3]})
        if rows:
            candidates.append(rows)
    if not candidates:
        raise ValueError("Secondary result grid contains no lot-labelled rows")
    rows = max(candidates, key=len)
    return offered, rows


def parse_first_party(html: bytes) -> tuple[int, int, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"\btotal of\s*(\d+)\s*Lots\b", text, re.I)
    if not match:
        raise ValueError("First-party catalogue has no total-lot denominator")
    total = int(match.group(1))
    pages = {1}
    for anchor in soup.find_all("a", href=True):
        query = parse_qs(urlparse(anchor["href"]).query)
        for value in query.get("page", []):
            if value.isdigit():
                pages.add(int(value))
    candidates: list[list[dict[str, str]]] = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            if len(cells) >= 4 and LOT_LABEL_RE.fullmatch(cells[0]):
                rows.append({"lot": cells[0], "type": cells[1], "location": cells[2], "result": cells[3]})
        if rows:
            candidates.append(rows)
    if not candidates:
        raise ValueError("First-party catalogue contains no lot-labelled rows")
    return total, max(pages), max(candidates, key=len)


def normalized_type(value: str) -> str:
    normalized = re.sub(r"\bother\b", "", clean(value).lower()).strip()
    # The oldest saved first-party grids abbreviate "Investment" to
    # "Invest" in the fixed-width type column; the secondary grid preserves
    # the expanded label.
    return re.sub(r"\binvest\b", "investment", normalized)


def location_matches_address(location: str, address: str) -> bool:
    """Require a meaningful result-grid place token in the exact address."""
    location_tokens = {
        token for token in re.findall(r"[a-z0-9]+", clean(location).casefold())
        if len(token) >= 3
    }
    address_tokens = set(re.findall(r"[a-z0-9]+", clean(address).casefold()))
    return bool(location_tokens & address_tokens)


def collect_fragment_rows(
    source_auction_id: str,
    source_paths: list[Path],
    source_auction_aliases: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    accepted_ids = {source_auction_id, *source_auction_aliases}
    rows: list[dict[str, object]] = []
    for source_path in source_paths:
        payload = json.loads(source_path.read_text())
        for source_row in payload.get("lots", []):
            if source_row.get("source_auction_id") not in accepted_ids:
                continue
            row = dict(source_row)
            if row.get("source_auction_id") != source_auction_id:
                aliases = list(row.get("source_identity_aliases") or [])
                aliases.append({
                    "source_auction_id": row.get("source_auction_id"),
                    "source_record_id": row.get("source_record_id"),
                })
                row["source_identity_aliases"] = aliases
                row["source_auction_id"] = source_auction_id
                row["source_record_id"] = f"{source_auction_id}-pos{clean(row.get('lot_number'))}"
            rows.append(row)
    counts = Counter(clean(row.get("lot_number")).casefold() for row in rows)
    if not rows or any(not lot or count != 1 for lot, count in counts.items()):
        raise ValueError(f"Exact fragments do not contain one row per lot label: {counts}")
    return sorted(rows, key=lambda row: (int(clean(row["lot_number"])) if clean(row["lot_number"]).isdigit() else 10**9, clean(row["lot_number"])))


def reconcile_fragments(
    aid: int,
    auction_date: str,
    source_auction_id: str,
    offered: int,
    secondary_rows: list[dict[str, str]],
    exact_rows: list[dict[str, object]],
    captured_at: str,
    snapshot_path: str,
    snapshot_sha256: str,
    catalogue_total: int | None = None,
) -> dict[str, object]:
    """Complete a fragmented exact-lot capture with a reconciled result grid."""
    expected_rows = catalogue_total or offered
    counts = Counter(row["lot"].casefold() for row in secondary_rows)
    if (
        len(secondary_rows) != expected_rows
        or len(counts) != expected_rows
        or any(count != 1 for count in counts.values())
        or offered > expected_rows
    ):
        raise ValueError(
            f"Secondary rows do not reconcile: {len(secondary_rows)} rows, {len(counts)} unique, "
            f"{offered} offered, {expected_rows} catalogue rows"
        )
    secondary_by_lot = {row["lot"].casefold(): row for row in secondary_rows}
    exact_by_lot = {clean(row["lot_number"]).casefold(): row for row in exact_rows}
    if not set(exact_by_lot) < set(secondary_by_lot):
        raise ValueError("Exact fragments must be a strict subset of the complete result grid")
    for lot, exact in exact_by_lot.items():
        secondary = secondary_by_lot[lot]
        exact_location = clean(exact.get("address") or exact.get("locality"))
        if not location_matches_address(secondary["location"], exact_location):
            raise ValueError(
                f"Lot {lot} result-grid location {secondary['location']!r} is absent from exact address/locality "
                f"{exact_location!r}"
            )

    secondary_url = SECONDARY_URL.format(aid=aid)
    lots: list[dict[str, object]] = []
    for secondary in secondary_rows:
        lot_label = secondary["lot"]
        exact = exact_by_lot.get(lot_label.casefold())
        result = secondary["result"]
        available = result.casefold().startswith("available")
        result_price = None if available else money(result)
        result_status = (
            "Available"
            if available
            else ("Sold" if result_price is not None else (result or None))
        )
        if exact:
            row = dict(exact)
            row["locality"] = secondary["location"]
            row["result_status"] = result_status
            if result_price is not None:
                row["result_price_gbp"] = result_price
            else:
                row.pop("result_price_gbp", None)
            source_urls = list(
                dict.fromkeys(
                    value
                    for value in [row.get("source_url"), *row.get("source_urls", []), secondary_url]
                    if value
                )
            )
            row["source_urls"] = source_urls
            row["raw_source"] = {
                "first_party_exact_lot_page": {
                    "source_record_id": row["source_record_id"],
                    "source_url": row["source_url"],
                },
                "secondary_grid": secondary,
            }
            row["notes"] = clean(row.get("notes")) + (
                " The complete result grid independently matches this lot number and locality and supplies the result."
            )
        else:
            row = {
                "source_record_id": f"{source_auction_id}-lot{lot_label}",
                "source_auction_id": source_auction_id,
                "auction_date": auction_date,
                "lot_number": lot_label,
                "address": None,
                "locality": secondary["location"],
                "property_type": secondary["type"],
                "result_status": result_status,
                "notes": (
                    "Surviving result-grid row within a catalogue whose offered denominator and all lot labels "
                    "reconcile exactly; the street address and postcode are not exposed and remain null."
                ),
                "source_url": secondary_url,
                "source_urls": [secondary_url],
                "raw_source": {"secondary_grid": secondary},
            }
            if result_price is not None:
                row["result_price_gbp"] = result_price
        lots.append(row)

    address_count = sum(bool(row.get("address")) for row in lots)
    raw_table_text = "\n".join(
        "\t".join((row["lot"], row["type"], row["location"], row["result"])) for row in secondary_rows
    )
    remaining = expected_rows - len(exact_rows)
    remaining_note = (
        "The remaining row is retained as a partial lot without inferring an address."
        if remaining == 1
        else f"The remaining {remaining} rows are retained as partial lots without inferring addresses."
    )
    return {
        "schema": "historical_source_corpus_v1",
        "schema_version": 1,
        "auctioneer": "Savills Auctions",
        "captured_at_utc": captured_at,
        "capture_mode": "complete_secondary_result_grid_with_exact_first_party_lot_pages",
        "scope": (
            f"All {expected_rows} distinct lot-labelled rows from PropertyAuctions AID {aid} for the "
            f"{datetime.strptime(auction_date, '%Y-%m-%d').strftime('%-d %B %Y')} Savills sale. "
            f"The result grid separately reports Offered: {offered}; {len(exact_rows)} identities independently reconcile "
            "to exact archived first-party Savills lot pages and retain their full address, postcode, tenure, "
            f"guide, rent and lease fields. {remaining_note}"
        ),
        "source_auction_id": source_auction_id,
        "auction_date": auction_date,
        "catalogue_lot_count": expected_rows,
        "catalogue_complete": True,
        "completion_scope": (
            f"all {expected_rows} lot labels appear exactly once on the single result page; the page separately "
            f"reports Offered: {offered}, and {len(exact_rows)} rows are independently matched to exact first-party pages"
        ),
        "source_url": secondary_url,
        "saved_source_snapshot": snapshot_path,
        "saved_source_snapshot_sha256": snapshot_sha256,
        "source_summary": {
            "offered": offered,
            "catalogue_rows": expected_rows,
            "rows_observed": len(secondary_rows),
            "unique_lot_numbers": len(counts),
            "first_party_exact_rows_cross_checked": len(exact_rows),
            "result_pagination_pages": 1,
        },
        "raw_table_text": raw_table_text,
        "appearance_count": len(lots),
        "address_records": address_count,
        "partial_records": len(lots) - address_count,
        "reconciliation": {
            "reported_offered": offered,
            "source_rows_observed": len(secondary_rows),
            "unique_lot_numbers": len(counts),
            "first_party_exact_rows": len(exact_rows),
            "result_pagination_pages": 1,
            "reconciliation_shortfall": expected_rows - len(lots),
            "status": "complete surviving result grid",
        },
        "lots": lots,
    }


def guide_range(text: str) -> tuple[int | None, int | None]:
    """Return the lower and optional upper values from a first-party guide."""
    values = [money(value) for value in re.findall(r"£\s*[\d,]+(?:\.\d+)?\s*[MK]?", text, re.I)]
    values = [value for value in values if value is not None]
    return (values[0] if values else None, values[1] if len(values) > 1 else None)


def reconcile_first_party_fragments(
    aid: int,
    auction_date: str,
    source_auction_id: str,
    first_total: int,
    result_rows: list[dict[str, str]],
    supplemental_total: int,
    supplemental_rows: list[dict[str, str]],
    exact_rows: list[dict[str, object]],
    captured_at: str,
    result_url: str,
    supplemental_url: str,
    snapshot_path: str,
    snapshot_sha256: str,
) -> dict[str, object]:
    """Reconcile archived result-page and pre-auction-page fragments.

    Some late legacy catalogues have a preserved results page one but only a
    pre-auction capture for page two.  This path proves the full lot sequence
    while retaining null result fields for the pre-auction-only rows.
    """
    if first_total != supplemental_total:
        raise ValueError(
            f"First-party page totals disagree: result {first_total}, supplemental {supplemental_total}"
        )
    combined = [*result_rows, *supplemental_rows]
    counts = Counter(row["lot"].casefold() for row in combined)
    if len(combined) != first_total or len(counts) != first_total or any(count != 1 for count in counts.values()):
        raise ValueError(
            f"First-party fragments do not reconcile: {len(combined)} rows, "
            f"{len(counts)} unique, {first_total} total"
        )
    exact_by_lot = {clean(row["lot_number"]).casefold(): row for row in exact_rows}
    if set(exact_by_lot) != set(counts):
        missing = sorted(set(counts) - set(exact_by_lot))
        extra = sorted(set(exact_by_lot) - set(counts))
        raise ValueError(f"Exact fragments disagree with first-party rows; missing={missing}, extra={extra}")

    result_lots = {row["lot"].casefold() for row in result_rows}
    lots: list[dict[str, object]] = []
    for grid in combined:
        lot_key = grid["lot"].casefold()
        row = dict(exact_by_lot[lot_key])
        is_result = lot_key in result_lots
        page_url = result_url if is_result else supplemental_url
        row["locality"] = grid["location"]
        if not row.get("property_type"):
            row["property_type"] = grid["type"]
        source_urls = list(dict.fromkeys([
            *([row.get("source_url")] if row.get("source_url") else []),
            *row.get("source_urls", []),
            page_url,
        ]))
        row["source_urls"] = source_urls
        row["raw_source"] = {
            "preserved_exact_fragment": {
                "source_record_id": row["source_record_id"],
                "source_url": row.get("source_url"),
            },
            "first_party_grid": grid,
            "first_party_grid_stage": "result" if is_result else "pre_auction",
        }
        if is_result:
            result = grid["result"]
            result_price = money(result)
            row["result_status"] = "Sold" if result_price is not None else result
            if result_price is not None:
                row["result_price_gbp"] = result_price
            row["notes"] = clean(row.get("notes")) + (
                " The archived first-party results grid independently matches this lot number and locality "
                "and supplies its result."
            )
        else:
            guide_low, guide_high = guide_range(grid["result"])
            if guide_low is not None:
                row["guide_price_gbp"] = guide_low
            if guide_high is not None:
                row["guide_price_high_gbp"] = guide_high
            else:
                row.pop("guide_price_high_gbp", None)
            row.pop("result_price_gbp", None)
            row["result_status"] = None
            recovered_note = (
                "Archived first-party pre-auction page-two row. It supplies this lot number, type, locality "
                "and guide; no final result or street address is exposed and both remain null."
            )
            if clean(row.get("notes")).startswith("Explicit incomplete lot placeholder"):
                row["notes"] = recovered_note
                row["source_url"] = page_url
            else:
                row["notes"] = clean(row.get("notes")) + " " + recovered_note
        lots.append(row)

    lots.sort(key=lambda row: int(clean(row["lot_number"])))
    address_count = sum(bool(row.get("address")) for row in lots)
    return {
        "schema": "historical_source_corpus_v1",
        "schema_version": 1,
        "auctioneer": "Savills Auctions",
        "captured_at_utc": captured_at,
        "capture_mode": "complete_first_party_result_and_preauction_grid_reconciliation",
        "scope": (
            f"All {first_total} lot positions in Savills Commercial Auc {aid} on "
            f"{datetime.strptime(auction_date, '%Y-%m-%d').strftime('%-d %B %Y')}. The archived results page "
            f"preserves lots 1-{len(result_rows)} and reports {first_total} lots across two pages; the archived "
            f"pre-auction page two preserves the remaining {len(supplemental_rows)} rows. Exact saved lot "
            "fragments retain richer address and property fields. Pre-auction-only rows retain null final results."
        ),
        "source_auction_id": source_auction_id,
        "auction_date": auction_date,
        "catalogue_lot_count": first_total,
        "catalogue_complete": True,
        "completion_scope": (
            f"all {first_total} lot labels appear exactly once across the two archived first-party grids and "
            "match the complete set of persisted exact fragments"
        ),
        "source_url": result_url,
        "source_urls": [result_url, supplemental_url],
        "saved_source_snapshot": snapshot_path,
        "saved_source_snapshot_sha256": snapshot_sha256,
        "source_summary": {
            "first_party_catalogue_total": first_total,
            "result_page_rows": len(result_rows),
            "preauction_page_rows": len(supplemental_rows),
            "rows_observed": len(combined),
            "unique_lot_numbers": len(counts),
            "result_pagination_pages": 2,
        },
        "appearance_count": len(lots),
        "address_records": address_count,
        "partial_records": len(lots) - address_count,
        "reconciliation": {
            "first_party_catalogue_total": first_total,
            "source_rows_observed": len(combined),
            "unique_lot_numbers": len(counts),
            "reconciliation_shortfall": first_total - len(lots),
            "status": "complete first-party lot sequence",
            "final_result_rows": len(result_rows),
            "preauction_only_rows": len(supplemental_rows),
        },
        "lots": lots,
    }


def reconcile(
    aid: int,
    auction_date: str,
    first_party_url: str,
    offered: int,
    secondary_rows: list[dict[str, str]],
    first_party_total: int,
    first_party_pages: int,
    first_party_rows: list[dict[str, str]],
    captured_at: str,
) -> dict[str, object]:
    if offered != first_party_total:
        raise ValueError(f"Source denominators disagree: secondary {offered}, first party {first_party_total}")
    lot_counts = Counter(row["lot"].lower() for row in secondary_rows)
    if len(secondary_rows) != offered or len(lot_counts) != offered or any(count != 1 for count in lot_counts.values()):
        raise ValueError(f"Secondary rows do not reconcile: {len(secondary_rows)} rows, {len(lot_counts)} unique, {offered} offered")
    secondary_by_lot = {row["lot"].lower(): row for row in secondary_rows}
    first_by_lot = {row["lot"].lower(): row for row in first_party_rows}
    if len(first_by_lot) != len(first_party_rows):
        raise ValueError("First-party page contains duplicate lot numbers")
    result_updates: list[dict[str, str]] = []
    type_supplements: list[dict[str, str]] = []
    for lot, primary in first_by_lot.items():
        secondary = secondary_by_lot.get(lot)
        if secondary is None:
            raise ValueError(f"First-party lot {lot} is absent from secondary grid")
        if clean(primary["location"]).casefold() != clean(secondary["location"]).casefold():
            raise ValueError(
                f"Lot {lot} location disagrees: {primary['location']!r} vs {secondary['location']!r}"
            )
        primary_type = normalized_type(primary["type"])
        secondary_type = normalized_type(secondary["type"])
        if primary_type and secondary_type and primary_type != secondary_type:
            raise ValueError(f"Lot {lot} type disagrees: {primary['type']!r} vs {secondary['type']!r}")
        if not primary_type and secondary_type:
            type_supplements.append({
                "lot": primary["lot"],
                "first_party_type": primary["type"],
                "secondary_type": secondary["type"],
            })
        if clean(primary["result"]).casefold() != clean(secondary["result"]).casefold():
            result_updates.append({
                "lot": primary["lot"],
                "first_party_result": primary["result"],
                "secondary_result": secondary["result"],
            })

    secondary_url = SECONDARY_URL.format(aid=aid)
    original_catalogue_url = re.sub(r"^https://web\.archive\.org/web/[^/]+/", "", first_party_url)
    source_auction_id = f"savills-commercial-auc{aid}"
    lots = []
    for secondary in secondary_rows:
        lot = secondary["lot"]
        primary = first_by_lot.get(lot.lower())
        chosen_type = primary["type"] if primary and clean(primary["type"]) else secondary["type"]
        chosen_location = primary["location"] if primary else secondary["location"]
        result = secondary["result"]
        available = result.lower().startswith("available")
        result_price = None if available else money(result)
        result_status = "Available" if available else ("Sold" if result_price is not None else result)
        result_changed = bool(primary and clean(primary["result"]).casefold() != clean(result).casefold())
        note = (
            "Archived first-party Savills lot identity cross-checked against the surviving secondary grid; "
            + ("the secondary grid preserves a later result observation; " if result_changed else "")
            + "street address and postcode are not exposed."
            if primary else
            "Surviving secondary result-grid row within a catalogue whose total and first page were "
            "reconciled to the archived first-party Savills catalogue; street address and postcode are not exposed."
        )
        source_urls = [secondary_url]
        source_url = secondary_url
        if primary:
            source_url = first_party_url
            source_urls = [
                first_party_url,
                original_catalogue_url,
                f"http://auctions.savills.co.uk/commercial/comm_previous_auction_lot.asp?Auc={aid}&pos={lot}",
                secondary_url,
            ]
        raw_source: dict[str, object] = {"secondary_grid": secondary}
        if primary:
            raw_source["first_party_grid"] = f"{primary['type']} {primary['location']} {primary['result']}"
        row: dict[str, object] = {
            "source_record_id": f"{source_auction_id}-pos{lot}",
            "source_auction_id": source_auction_id,
            "auction_date": auction_date,
            "lot_number": lot,
            "address": None,
            "locality": chosen_location,
            "property_type": chosen_type,
            "notes": note,
            "source_url": source_url,
            "source_urls": source_urls,
            "result_status": result_status,
            "raw_source": raw_source,
        }
        if result_price is not None:
            row["result_price_gbp"] = result_price
        if available:
            row["available_price_gbp"] = money(result)
        lots.append(row)

    heading_date = datetime.strptime(auction_date, "%Y-%m-%d").strftime("%d %B %Y").upper()
    raw_table_text = "\n".join(
        "\t".join((row["lot"], row["type"], row["location"], row["result"])) for row in secondary_rows
    )
    return {
        "schema": "historical_source_corpus_v1",
        "schema_version": 1,
        "auctioneer": "Savills Auctions",
        "captured_at_utc": captured_at,
        "capture_mode": "complete_secondary_result_grid_with_first_party_catalogue_reconciliation",
        "scope": (
            f"All {offered} lot-labelled result rows from the surviving PropertyAuctions AID {aid} grid for the "
            f"{datetime.strptime(auction_date, '%Y-%m-%d').strftime('%-d %B %Y')} Savills Commercial sale. "
            f"The archived first-party Savills page identifies the date, states a total of {first_party_total} "
            f"lots across {first_party_pages} catalogue pages and exposes lots 1-{len(first_party_rows)} on page 1. "
            f"Those first {len(first_party_rows)} lot identities reconcile to the secondary grid; "
            f"{len(result_updates)} later result updates and {len(type_supplements)} missing-type supplement are "
            "preserved from the secondary grid. The secondary grid exposes "
            f"{offered} distinct lot labels exactly once and reports Offered: {offered}. Street addresses and "
            "postcodes are not exposed and remain null."
        ),
        "source_auction_id": source_auction_id,
        "auction_date": auction_date,
        "catalogue_lot_count": offered,
        "catalogue_complete": True,
        "completion_scope": (
            f"all {offered} lot labels appear exactly once in the result grid and reconcile to both the "
            f"first-party total of {first_party_total} and the secondary Offered: {offered} denominator"
        ),
        "source_url": secondary_url,
        "first_party_source_url": first_party_url,
        "source_summary": {
            "heading": f"{heading_date} SAVILLS (COMMERCIAL)",
            "offered": offered,
            "rows_observed": len(secondary_rows),
            "unique_lot_numbers": len(lot_counts),
            "first_party_rows_cross_checked": len(first_party_rows),
            "later_result_updates": len(result_updates),
            "secondary_type_supplements": len(type_supplements),
            "first_party_catalogue_total": first_party_total,
            "first_party_catalogue_pages": first_party_pages,
            "secondary_result_pages": 1,
        },
        "raw_table_text": raw_table_text,
        "appearance_count": len(lots),
        "address_records_added": 0,
        "partial_records_added": len(lots),
        "reconciliation": {
            "first_party_catalogue_total": first_party_total,
            "reported_offered": offered,
            "source_rows_observed": len(secondary_rows),
            "unique_lot_numbers": len(lot_counts),
            "result_pagination_pages": 1,
            "reconciliation_shortfall": offered - len(lots),
            "status": "complete surviving result grid",
            "result_updates": result_updates,
            "type_supplements": type_supplements,
        },
        "lots": lots,
    }


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def locate_staging_source(aid: int) -> Path:
    """Return the one saved page-one source that still owns this auction."""
    source_auction_id = f"savills-commercial-auc{aid}"
    matches = []
    for source_path in sorted(CORPUS.glob(STAGING_SOURCE_GLOB)):
        payload = json.loads(source_path.read_text())
        if any(row.get("source_auction_id") == source_auction_id for row in payload.get("lots", [])):
            matches.append(source_path)
    if len(matches) != 1:
        raise ValueError(
            f"Expected one saved catalogue-grid source for Auc {aid}; found {len(matches)}: "
            + ", ".join(path.name for path in matches)
        )
    return matches[0]


def derived_shard(source_path: Path) -> Path:
    return ROOT / "data/auction_history/appearances/source-corpus" / f"{source_path.stem}.jsonl.gz"


def migrate_mixed_source(aid: int, mixed_source: Path = MIXED_SOURCE) -> int:
    mixed = json.loads(mixed_source.read_text())
    source_auction_id = f"savills-commercial-auc{aid}"
    before = list(mixed["lots"])
    mixed["lots"] = [row for row in before if row.get("source_auction_id") != source_auction_id]
    removed = len(before) - len(mixed["lots"])
    if not removed:
        raise ValueError(f"Mixed legacy source has no rows for Auc {aid}; refusing a speculative migration")
    remaining = mixed["lots"]
    catalogue_ids = {row.get("source_auction_id") for row in remaining}
    link_only = sum(not any(row.get(key) for key in ("property_type", "locality", "result_status")) for row in remaining)
    migrated = sorted({int(value) for value in re.findall(r"Auc (\d+)", mixed.get("scope", ""))} | {aid})
    migrated_text = ", ".join(f"Auc {value}" for value in migrated[:-1])
    migrated_text += (" and " if migrated_text else "") + f"Auc {migrated[-1]}"
    if remaining:
        dates = sorted(row["auction_date"] for row in remaining if row.get("auction_date"))
        first = datetime.strptime(dates[0], "%Y-%m-%d").strftime("%-d %B %Y")
        last = datetime.strptime(dates[-1], "%Y-%m-%d").strftime("%-d %B %Y")
        mixed["scope"] = (
            f"{len(remaining)} individually identifiable appearances from the preserved first catalogue page of "
            f"{len(catalogue_ids)} Savills commercial auctions dated {first} through {last}. The saved grid text "
            f"retains type, locality and result for {len(remaining) - link_only} appearances; {link_only} later row "
            "retains only its exact individual lot link because the saved text sample was truncated. Street addresses "
            "are unknown and remain null. These are page-one recoveries only; none of the underlying catalogues is "
            f"declared complete. {migrated_text} were migrated to their own complete sources."
        )
    else:
        mixed["scope"] = (
            "No appearances remain in this preserved page-one staging source. Every saved catalogue-grid row was "
            f"migrated into a reconciled complete per-auction source: {migrated_text}."
        )
        mixed["retire_empty_derived_shard"] = True
    mixed["catalogue_grids_replayed"] = len(catalogue_ids)
    mixed["appearance_count"] = len(remaining)
    mixed["grid_rows_with_surviving_metadata"] = len(remaining) - link_only
    mixed["link_only_partial_rows"] = link_only
    atomic_json(mixed_source, mixed)
    return removed


def migrate_fragment_sources(
    source_auction_id: str,
    source_paths: list[Path],
    source_auction_aliases: tuple[str, ...] = (),
) -> int:
    """Remove explicitly consolidated rows and leave auditable staging files."""
    accepted_ids = {source_auction_id, *source_auction_aliases}
    removed_total = 0
    for source_path in source_paths:
        payload = json.loads(source_path.read_text())
        before = list(payload.get("lots", []))
        payload["lots"] = [row for row in before if row.get("source_auction_id") not in accepted_ids]
        removed = len(before) - len(payload["lots"])
        if not removed:
            raise ValueError(f"Fragment source {source_path.name} has no rows for {source_auction_id}")
        removed_total += removed
        payload["appearance_count"] = len(payload["lots"])
        if payload["lots"]:
            payload["scope"] = (
                f"{len(payload['lots'])} individually identifiable exact archived Savills lot-page appearances "
                f"remain after {removed} rows for {source_auction_id} were consolidated into a complete per-auction source."
            )
            payload["completeness_note"] = (
                "The remaining rows are individually admitted exact pages only; their catalogues are not declared complete."
            )
            atomic_json(source_path, payload)
        else:
            # Keep a small tracked tombstone rather than a misleading empty
            # incomplete catalogue.  The bank pass recognises this marker and
            # removes the superseded derived shard while the replacement
            # source preserves every row and its provenance.
            payload["scope"] = (
                f"All {removed} rows for {source_auction_id} were consolidated into a complete per-auction source."
            )
            payload["completeness_note"] = "This staging source is retired; use the reconciled replacement source."
            payload["retire_empty_derived_shard"] = True
            atomic_json(source_path, payload)
        derived_shard(source_path).unlink(missing_ok=True)
    return removed_total


def write_secondary_snapshot(
    aid: int,
    offered: int,
    secondary_rows: list[dict[str, str]],
    captured_at: str,
    capture_date: str,
) -> tuple[str, str]:
    snapshot_path = ROOT / "data/source_diagnostics" / f"savills_aid{aid}_result_grid_{capture_date}.json"
    payload = {
        "source_url": SECONDARY_URL.format(aid=aid),
        "captured_at_utc": captured_at,
        "reported_offered": offered,
        "rows_observed": len(secondary_rows),
        "unique_lot_numbers": len({row["lot"].casefold() for row in secondary_rows}),
        "result_pagination_pages": 1,
        "rows": secondary_rows,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(rendered)
    relative = str(snapshot_path.relative_to(ROOT))
    return relative, hashlib.sha256(rendered.encode()).hexdigest()


def write_first_party_fragment_snapshot(
    aid: int,
    result_url: str,
    result_rows: list[dict[str, str]],
    supplemental_url: str,
    supplemental_rows: list[dict[str, str]],
    catalogue_total: int,
    captured_at: str,
    capture_date: str,
) -> tuple[str, str]:
    snapshot_path = ROOT / "data/source_diagnostics" / f"savills_auc{aid}_first_party_grids_{capture_date}.json"
    payload = {
        "captured_at_utc": captured_at,
        "catalogue_lot_count": catalogue_total,
        "pages": [
            {"source_url": result_url, "stage": "result", "rows": result_rows},
            {"source_url": supplemental_url, "stage": "pre_auction", "rows": supplemental_rows},
        ],
        "rows_observed": len(result_rows) + len(supplemental_rows),
        "unique_lot_numbers": len({row["lot"].casefold() for row in [*result_rows, *supplemental_rows]}),
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(rendered)
    relative = str(snapshot_path.relative_to(ROOT))
    return relative, hashlib.sha256(rendered.encode()).hexdigest()


def retarget_address_enrichments(aid: int, target: Path) -> int:
    """Move internal enrichment pointers with rows split from the mixed shard."""
    return retarget_address_enrichments_for_source(f"savills-commercial-auc{aid}", target)


def retarget_address_enrichments_for_source(
    source_auction_id: str,
    target: Path,
    source_auction_aliases: tuple[str, ...] = (),
) -> int:
    """Move enrichment pointers when one auction is consolidated into a new shard."""
    target_prefixes = tuple(
        prefix
        for accepted_id in (source_auction_id, *source_auction_aliases)
        for prefix in (
            f"source-corpus|{accepted_id}-pos",
            f"source-corpus|{accepted_id}-lot",
        )
    )
    target_shard = f"source-corpus/{target.stem}"
    changed = 0
    for source_path in sorted(CORPUS.glob("*.json")):
        if source_path == target:
            continue
        payload = json.loads(source_path.read_text())
        enrichments = payload.get("appearance_enrichments")
        if not isinstance(enrichments, list):
            continue
        file_changed = False
        for enrichment in enrichments:
            if not isinstance(enrichment, dict):
                continue
            target_appearance = clean(enrichment.get("target_appearance_id"))
            current_shard = clean(enrichment.get("target_shard"))
            if target_appearance.startswith(target_prefixes) and current_shard != target_shard:
                if not current_shard.startswith("source-corpus/"):
                    raise ValueError(f"Unexpected enrichment shard for {target_appearance}: {current_shard}")
                enrichment["target_shard"] = target_shard
                changed += 1
                file_changed = True
        if file_changed:
            atomic_json(source_path, payload)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aid", required=True, type=int)
    parser.add_argument("--date", required=True, help="Exact auction date in YYYY-MM-DD form")
    parser.add_argument("--first-party-url")
    parser.add_argument(
        "--supplemental-first-party-url",
        help="Archived first-party page that supplies the remaining pre-auction lot rows",
    )
    parser.add_argument(
        "--fragment-source",
        action="append",
        default=[],
        help="Source-corpus JSON containing exact rows to consolidate; may be repeated",
    )
    parser.add_argument("--source-auction-id", help="Stable ID shared by rows in --fragment-source files")
    parser.add_argument(
        "--fragment-auction-alias",
        action="append",
        default=[],
        help="Earlier source-auction ID to normalize while consolidating fragments; may be repeated",
    )
    parser.add_argument("--capture-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument(
        "--catalogue-row-count",
        type=int,
        help="Complete distinct row count when the source's Offered statistic excludes catalogue rows",
    )
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    first_party_fragment_mode = bool(
        args.fragment_source and args.first_party_url and args.supplemental_first_party_url
    )
    if not first_party_fragment_mode:
        secondary_response = session.get(SECONDARY_URL.format(aid=args.aid), timeout=60)
        secondary_response.raise_for_status()
        offered, secondary_rows = parse_secondary(secondary_response.content)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if args.fragment_source:
        if not args.source_auction_id:
            parser.error("--source-auction-id is required with --fragment-source")
        fragment_paths = [
            Path(value) if Path(value).is_absolute() else CORPUS / value
            for value in args.fragment_source
        ]
        fragment_aliases = tuple(args.fragment_auction_alias)
        exact_rows = collect_fragment_rows(args.source_auction_id, fragment_paths, fragment_aliases)
        if first_party_fragment_mode:
            result_response = session.get(args.first_party_url, timeout=60)
            result_response.raise_for_status()
            supplemental_response = session.get(args.supplemental_first_party_url, timeout=60)
            supplemental_response.raise_for_status()
            first_total, first_pages, result_rows = parse_first_party(result_response.content)
            supplemental_total, _, supplemental_rows = parse_first_party(supplemental_response.content)
            if first_pages < 2:
                raise ValueError("First-party result page does not prove a second catalogue page")
            snapshot_path, snapshot_sha256 = write_first_party_fragment_snapshot(
                args.aid,
                result_response.url,
                result_rows,
                supplemental_response.url,
                supplemental_rows,
                first_total,
                captured_at,
                args.capture_date,
            )
            payload = reconcile_first_party_fragments(
                args.aid,
                args.date,
                args.source_auction_id,
                first_total,
                result_rows,
                supplemental_total,
                supplemental_rows,
                exact_rows,
                captured_at,
                result_response.url,
                supplemental_response.url,
                snapshot_path,
                snapshot_sha256,
            )
        else:
            snapshot_path, snapshot_sha256 = write_secondary_snapshot(
                args.aid, offered, secondary_rows, captured_at, args.capture_date
            )
            payload = reconcile_fragments(
                args.aid,
                args.date,
                args.source_auction_id,
                offered,
                secondary_rows,
                exact_rows,
                captured_at,
                snapshot_path,
                snapshot_sha256,
                args.catalogue_row_count,
            )
        target = CORPUS / f"savills_{args.date.replace('-', '_')}_auc{args.aid}_complete_results_{args.capture_date}.json"
        if target.exists():
            raise FileExistsError(target)
        removed = migrate_fragment_sources(args.source_auction_id, fragment_paths, fragment_aliases)
        atomic_json(target, payload)
        enrichments_retargeted = retarget_address_enrichments_for_source(
            args.source_auction_id, target, fragment_aliases
        )
        staging_source: Path | None = None
    else:
        if not args.first_party_url:
            parser.error("--first-party-url is required unless --fragment-source is used")
        primary_response = session.get(args.first_party_url, timeout=60)
        primary_response.raise_for_status()
        first_total, first_pages, first_rows = parse_first_party(primary_response.content)
        payload = reconcile(
            args.aid, args.date, primary_response.url, offered, secondary_rows,
            first_total, first_pages, first_rows, captured_at,
        )
        target = CORPUS / (
            f"savills_2005_{args.date[:4]}_auc{args.aid}_complete_results_{args.capture_date}.json"
        )
        if target.exists():
            raise FileExistsError(target)
        staging_source = locate_staging_source(args.aid)
        removed = migrate_mixed_source(args.aid, staging_source)
        atomic_json(target, payload)
        enrichments_retargeted = retarget_address_enrichments(args.aid, target)
        # The shard writer retains vanished rows. Delete the evidenced staging
        # shard so the bank pass regenerates it without superseded appearances.
        derived_shard(staging_source).unlink(missing_ok=True)
    print(json.dumps({
        "source_file": str(target.relative_to(ROOT)),
        "lots_reconciled": len(payload["lots"]),
        "legacy_rows_replaced": removed,
        "net_appearances": len(payload["lots"]) - removed,
        "address_enrichments_retargeted": enrichments_retargeted,
        "staging_source": str(staging_source.relative_to(ROOT)) if staging_source else None,
    }, indent=2))


if __name__ == "__main__":
    main()
