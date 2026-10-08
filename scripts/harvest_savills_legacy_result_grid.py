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
    return re.sub(r"\bother\b", "", clean(value).lower()).strip()


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


def migrate_mixed_source(aid: int) -> int:
    mixed = json.loads(MIXED_SOURCE.read_text())
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
    atomic_json(MIXED_SOURCE, mixed)
    return removed


def retarget_address_enrichments(aid: int, target: Path) -> int:
    """Move internal enrichment pointers with rows split from the mixed shard."""
    target_prefix = f"source-corpus|savills-commercial-auc{aid}-pos"
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
            if target_appearance.startswith(target_prefix) and current_shard != target_shard:
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
    parser.add_argument("--first-party-url", required=True)
    parser.add_argument("--capture-date", default=date.today().strftime("%Y%m%d"))
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    secondary_response = session.get(SECONDARY_URL.format(aid=args.aid), timeout=60)
    secondary_response.raise_for_status()
    primary_response = session.get(args.first_party_url, timeout=60)
    primary_response.raise_for_status()
    offered, secondary_rows = parse_secondary(secondary_response.content)
    first_total, first_pages, first_rows = parse_first_party(primary_response.content)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = reconcile(
        args.aid, args.date, primary_response.url, offered, secondary_rows,
        first_total, first_pages, first_rows, captured_at,
    )
    target = CORPUS / (
        f"savills_2005_{args.date[:4]}_auc{args.aid}_complete_results_{args.capture_date}.json"
    )
    if target.exists():
        raise FileExistsError(target)
    removed = migrate_mixed_source(args.aid)
    atomic_json(target, payload)
    enrichments_retargeted = retarget_address_enrichments(args.aid, target)
    # The general shard writer intentionally retains rows that disappear from a
    # later fetch.  Here the disappearance is an explicit, evidenced migration
    # into a complete per-auction shard, so force the mixed derived shard to be
    # regenerated from its updated source rather than merging the superseded
    # rows back in.
    MIXED_SHARD.unlink(missing_ok=True)
    print(json.dumps({
        "source_file": str(target.relative_to(ROOT)),
        "lots_reconciled": len(payload["lots"]),
        "legacy_rows_replaced": removed,
        "net_appearances": len(payload["lots"]) - removed,
        "address_enrichments_retargeted": enrichments_retargeted,
    }, indent=2))


if __name__ == "__main__":
    main()
