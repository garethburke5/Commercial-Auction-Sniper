#!/usr/bin/env python3
"""Build conservative Savills legacy address enrichments from HMLR PPD CSVs.

The PropertyAuctions legacy grids retain auction date, result, locality and
property class but often omit the street address.  This script accepts official
HM Land Registry yearly Price Paid Data files and emits source-corpus
enrichments only when one transaction is uniquely compatible on:

* exact price;
* completion between the auction date and 60 days later;
* exact postcode district, or exact normalized town where no district survives;
* tenure and property class; and
* exclusive use of the matched HMLR transaction by one auction appearance.

It deliberately leaves unsold, unpriced, ambiguous, class-conflicting and
transaction-sharing lots unchanged.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
APPEARANCE_ROOT = ROOT / "data/auction_history/appearances/savills"
POSTCODE_DISTRICT = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b", re.I)


def normalized(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def compatible(source_type: object, ppd_type: str, duration: str) -> bool:
    """Return whether the coarse PPD class is compatible with the saved lot."""
    source = normalized(source_type)
    ppd_type = ppd_type.upper()
    duration = duration.upper()

    if "LAND" in source:
        return False
    if "FLAT" in source or "MAISONETTE" in source:
        return ppd_type == "F" and duration == "L"
    if "HOUSE" in source or "BUNGALOW" in source:
        if "SEMI DETACHED" in source and ppd_type != "S":
            return False
        if "TERRACED" in source and ppd_type != "T":
            return False
        if "DETACHED" in source and "SEMI DETACHED" not in source and ppd_type != "D":
            return False
        if ppd_type not in {"D", "S", "T"}:
            return False
        if "FREEHOLD" in source and duration != "F":
            return False
        if "LEASEHOLD" in source and duration != "L":
            return False
        return True
    if "GROUND RENT" in source:
        return ppd_type == "O" and duration == "F"
    if any(word in source for word in ("BUILDING", "COMMERCIAL", "RETAIL", "OFFICE", "INDUSTRIAL", "LEISURE")):
        if ppd_type != "O":
            return False
        if "FREEHOLD" in source and duration != "F":
            return False
        if "LEASEHOLD" in source and duration != "L":
            return False
        return True
    return False


def address_from_ppd(row: list[str]) -> str:
    paon, saon, street, town, postcode = row[7], row[8], row[9], row[11], row[3]
    parts: list[str] = []
    premise = " ".join(part for part in (saon, paon) if part)
    if premise:
        parts.append(premise.title())
    if street:
        parts.append(street.title())
    if town:
        parts.append(town.title())
    if postcode:
        parts.append(postcode.upper())
    return ", ".join(parts)


def load_legacy_rows() -> tuple[list[dict], dict[str, set[str]]]:
    rows: list[dict] = []
    existing_addresses: dict[str, set[str]] = defaultdict(set)
    for path in sorted(APPEARANCE_ROOT.glob("legacy-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                rows.append(row)
                address = row.get("address")
                if address:
                    existing_addresses[str(row.get("source_auction_id"))].add(normalized(address))
    return rows, existing_addresses


def parse_ppd_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected YEAR=/path/to/pp-YEAR.csv")
    year, raw_path = value.split("=", 1)
    if not re.fullmatch(r"20\d{2}", year):
        raise argparse.ArgumentTypeError(f"invalid year: {year}")
    path = Path(raw_path)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"missing PPD file: {path}")
    return year, path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppd", action="append", required=True, type=parse_ppd_arg)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--captured-at", required=True)
    args = parser.parse_args()

    ppd_paths = dict(args.ppd)
    legacy_rows, existing_addresses = load_legacy_rows()
    targets = [
        row for row in legacy_rows
        if str(row.get("auction_date") or "")[:4] in ppd_paths
        and not row.get("address")
        and row.get("sale_price") is not None
        and row.get("status") == "sold"
    ]
    prices_by_year: dict[str, set[int]] = defaultdict(set)
    for row in targets:
        prices_by_year[row["auction_date"][:4]].add(int(row["sale_price"]))

    ppd_by_year_price: dict[str, dict[int, list[list[str]]]] = defaultdict(lambda: defaultdict(list))
    for year, path in sorted(ppd_paths.items()):
        with path.open(newline="", encoding="utf-8") as handle:
            for ppd_row in csv.reader(handle):
                if len(ppd_row) < 16:
                    continue
                try:
                    price = int(ppd_row[1])
                except ValueError:
                    continue
                if price in prices_by_year[year]:
                    ppd_by_year_price[year][price].append(ppd_row)

    candidate_by_appearance: dict[str, tuple[dict, list[str]]] = {}
    counters = Counter()
    for row in targets:
        auction_date = dt.date.fromisoformat(row["auction_date"])
        latest = auction_date + dt.timedelta(days=60)
        locality = str(row.get("locality") or "")
        district_match = POSTCODE_DISTRICT.search(locality.upper())
        locality_town = normalized(locality.split(",", 1)[0])
        candidates: list[list[str]] = []
        for ppd_row in ppd_by_year_price[row["auction_date"][:4]][int(row["sale_price"])]:
            try:
                completion = dt.date.fromisoformat(ppd_row[2][:10])
            except ValueError:
                continue
            if not auction_date <= completion <= latest:
                continue
            if district_match:
                outward = (ppd_row[3] or "").split(" ", 1)[0].upper()
                if outward != district_match.group(1).upper():
                    continue
            elif not locality_town or normalized(ppd_row[11]) != locality_town:
                continue
            if compatible(row.get("property_type"), ppd_row[4], ppd_row[6]):
                candidates.append(ppd_row)
        if len(candidates) == 1:
            candidate_by_appearance[row["appearance_id"]] = (row, candidates[0])
        elif candidates:
            counters["ambiguous"] += 1
        else:
            counters["no_compatible_transaction"] += 1

    transaction_use = Counter(ppd_row[0] for _, ppd_row in candidate_by_appearance.values())
    enrichments = []
    for appearance_id, (row, ppd_row) in candidate_by_appearance.items():
        if transaction_use[ppd_row[0]] != 1:
            counters["shared_transaction"] += 1
            continue
        address = address_from_ppd(ppd_row)
        auction_id = str(row.get("source_auction_id"))
        if normalized(address) in existing_addresses.get(auction_id, set()):
            counters["address_already_used_by_another_lot"] += 1
            continue
        auction_date = dt.date.fromisoformat(row["auction_date"])
        completion = dt.date.fromisoformat(ppd_row[2][:10])
        locality = str(row.get("locality") or "")
        district_match = POSTCODE_DISTRICT.search(locality.upper())
        if district_match:
            location_query = "postcode=" + district_match.group(1).upper()
        else:
            location_query = "town=" + quote_plus(locality.split(",", 1)[0].strip())
        query_url = (
            "https://landregistry.data.gov.uk/app/ppd/search?limit=100"
            f"&min_price={int(row['sale_price'])}&max_price={int(row['sale_price'])}"
            f"&min_date={auction_date}&max_date={auction_date + dt.timedelta(days=60)}"
            f"&relative_url_root=%2Fapp%2Fppd&{location_query}"
        )
        aid = auction_id.split(":", 1)[-1]
        result_class = {"D": "detached", "S": "semi detached", "T": "terraced", "F": "flat maisonette", "O": "other"}.get(ppd_row[4], ppd_row[4])
        result_tenure = {"F": "freehold", "L": "leasehold"}.get(ppd_row[6], ppd_row[6])
        source_type = " ".join(str(row.get("property_type") or "").split()).lower()
        enrichments.append({
            "target_shard": f"savills/legacy-{aid}",
            "target_appearance_id": appearance_id,
            "address": address,
            "postcode": ppd_row[3].upper(),
            "address_basis": "conservative_official_hmlr_unique_exact_price_date_locality_tenure_and_property_class_match",
            "source_url": query_url,
            "source_urls": [str(row.get("original_url")), query_url],
            "evidence_note": (
                f"Saved Savills/PropertyAuctions AID {aid} lot {row.get('lot_number')} is a {source_type} "
                f"in {locality} sold for exactly GBP {int(row['sale_price']):,} on {auction_date}. "
                f"The official HM Land Registry result identifies {address} as the sole compatible exact-price "
                f"{result_class}/{result_tenure} transaction, completing {(completion - auction_date).days} days "
                f"later on {completion}."
            ),
        })

    enrichments.sort(key=lambda item: item["target_appearance_id"])
    years = sorted(ppd_paths)
    payload = {
        "schema": "historical_source_corpus_v1",
        "schema_version": 1,
        "auctioneer": "Savills Auctions",
        "capture_mode": "conservative official HM Land Registry exact-transaction legacy address enrichment",
        "captured_at_utc": args.captured_at,
        "source_note": (
            f"The official HM Land Registry Price Paid Data was run across all {len(targets):,} priced, "
            f"addressless sold Savills legacy appearances in {', '.join(years)}. {len(enrichments):,} "
            "matches were retained only where the exact hammer price, completion within 60 days, exact locality "
            "or postcode district, tenure and property class aligned to one compatible transaction used by no "
            "other lot. All no-result, ambiguous, class-conflicting, shared-transaction and already-used-address "
            "candidates remain unchanged. Original Savills/PropertyAuctions evidence and every repeat auction "
            "appearance remain preserved."
        ),
        "source_records": [
            {
                "source_url": f"https://price-paid-data.publicdata.landregistry.gov.uk/pp-{year}.csv",
                "source_name": "HM Land Registry Price Paid Data",
                "record_identity": f"Official Price Paid Data full-year file for {year}",
                "evidence_excerpt": "Exact-price records supply full address, completion date, tenure, property type and transaction category.",
            }
            for year in years
        ],
        "appearance_enrichments": enrichments,
        "appearance_count": 0,
        "appearances_enriched": len(enrichments),
        "address_records_added": len(enrichments),
        "partial_records_added": 0,
        "rejection_counts": dict(sorted(counters.items())),
        "historical_completeness_declared": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "targets": len(targets),
        "enrichments": len(enrichments),
        "rejections": dict(sorted(counters.items())),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
