"""Bank individually evidenced Shepherd auction lots from the saved live board.

The current collector already retained first-party Shepherd detail records in
``data/properties.json``.  This importer turns those saved records into durable
historical appearances without refetching the live site.  It snapshots the
complete saved Shepherd subset, keeps future-dated lots separate, and does not
claim that the saved two-event inventory is Shepherd's complete archive.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE_NAME = "Shepherd Commercial Auctions"
SLUG = "shepherd-commercial"
DETAIL_ID_RE = re.compile(r"/property/details/(\d+)(?:/|$)", re.I)


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def canonical_payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def twenty_year_cutoff(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year - 20)
    except ValueError:
        return as_of.replace(year=as_of.year - 20, day=28)


def saved_rows(source_file: Path) -> tuple[dict, list[dict]]:
    document = json.loads(source_file.read_text())
    rows = []
    seen_urls = {}
    for bucket in ("properties", "archive", "excluded_properties"):
        for item in document.get(bucket) or []:
            if item.get("source") != SOURCE_NAME:
                continue
            if bucket == "excluded_properties":
                continue
            url = corpus.clean(item.get("url"))
            if not url or not corpus.clean(item.get("address")):
                raise ValueError("saved Shepherd row lacks an original URL or address")
            previous = seen_urls.get(url)
            if previous and previous != item:
                raise ValueError(f"conflicting saved Shepherd detail row: {url}")
            if previous:
                continue
            seen_urls[url] = item
            rows.append({"saved_bucket": bucket, "record": item})
    if not rows:
        raise ValueError("saved property file contains no Shepherd auction lots")
    rows.sort(key=lambda entry: (entry["record"].get("auction_date") or "", entry["record"]["url"]))
    return document, rows


def source_id(item: dict) -> str:
    match = DETAIL_ID_RE.search(urlsplit(item["url"]).path)
    if match:
        return match.group(1)
    value = corpus.clean(item.get("source_id"))
    if value:
        return value
    return hashlib.sha256(item["url"].encode()).hexdigest()[:24]


def row_from_saved(item: dict, saved_bucket: str, evidence: dict) -> dict:
    auction_date = corpus.clean(item.get("auction_date"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", auction_date):
        raise ValueError(f"invalid Shepherd auction date for {item['url']}: {auction_date!r}")
    date.fromisoformat(auction_date)
    sid = source_id(item)
    auction_id = corpus.clean(item.get("auction_id")) or f"shepherd:{auction_date}"
    address = corpus.clean(item.get("address"))
    description = corpus.clean(item.get("description")) or None
    property_type = corpus.clean(item.get("property_type")) or None
    text = " ".join(value for value in (address, property_type, description) if value)
    postcode_match = corpus.PC.search(address)
    row = corpus.base_row(
        SOURCE_NAME,
        auction_id,
        auction_date,
        item.get("lot_number"),
        sid,
        item["url"],
    )
    row.update(
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector=corpus.sector(text),
        property_type=property_type,
        tenure=corpus.clean(item.get("tenure")) or None,
        guide_price=item.get("guide_price"),
        guide_price_high=item.get("guide_price_upper"),
        sale_price=item.get("sale_price"),
        status="unknown",
        description=description,
        annual_rent=item.get("annual_rent"),
        tenant=corpus.clean(item.get("tenant")) or None,
        floor_area=item.get("area_sqft"),
        site_area=item.get("site_area_acres"),
        vat_togc=corpus.clean(item.get("vat_status")) or None,
        legal_pack_url=corpus.clean(item.get("legal_pack_url")) or None,
        image_urls=[item["image_url"]] if item.get("image_url") else [],
        property_id=f"shepherd-detail:{sid}",
        identity_method="same_auction_and_first_party_shepherd_detail_id",
        record_quality="address_record",
        auction_date_basis="exact date retained from first-party Shepherd detail page",
        source_evidence={**evidence, "listing_url": item["url"]},
        saved_source_bucket=saved_bucket,
        source_availability=item.get("source_availability"),
        source_collected_at=item.get("collected_at"),
        operator_reconciliation_pending=True,
        operator_reconciliation_note=(
            "Shepherd Commercial Ltd, John Shepherd Chartered Surveyors and branch labels "
            "must be reconciled before counting a legal operator"
        ),
    )
    row["yield"] = item.get("gross_yield")
    return row


def duplicate_reason(candidate: dict, matches: list[dict]) -> str | None:
    for match in matches:
        if candidate.get("guide_price") is not None and candidate.get("guide_price") == match.get("guide_price"):
            return "same date/address and guide price"
        if candidate.get("sale_price") is not None and candidate.get("sale_price") == match.get("sale_price"):
            return "same date/address and achieved price"
        left = re.sub(r"\s+", " ", (candidate.get("description") or "").casefold()).strip()
        right = re.sub(r"\s+", " ", (match.get("description") or "").casefold()).strip()
        if left and right and left == right:
            return "same date/address and description"
    return None


def run_import(source_file: Path, as_of: date) -> dict:
    document, saved = saved_rows(source_file)
    origin_bytes = source_file.read_bytes()
    snapshot_payload = {
        "source": SOURCE_NAME,
        "origin_file": str(source_file.relative_to(corpus.ROOT)),
        "origin_sha256": corpus.digest(origin_bytes),
        "origin_generated_at": document.get("generated_at"),
        "saved_inventory_scope": "all individually evidenced Shepherd rows retained in properties and archive buckets",
        "historical_archive_complete": False,
        "rows": saved,
    }
    snapshot_sha = corpus.digest(canonical_payload(snapshot_payload))
    snapshot_path = corpus.DATA / "sources" / SLUG / f"saved-properties-{snapshot_sha[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot_payload)
    evidence = {
        "source_url": "saved:data/properties.json",
        "retrieved_at": document.get("generated_at"),
        "response_sha256": snapshot_sha,
        "snapshot_path": str(snapshot_path.relative_to(corpus.ROOT)),
        "evidence_tier": "saved first-party detail records from protected production collection",
    }
    candidates = [row_from_saved(entry["record"], entry["saved_bucket"], evidence) for entry in saved]
    if len({row["appearance_id"] for row in candidates}) != len(candidates):
        raise ValueError("duplicate Shepherd appearance identity in saved source")

    appearance_path = corpus.DATA / "appearances" / SLUG / "saved-properties.jsonl.gz"
    previous_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    previous_ids = {row["appearance_id"] for row in previous_rows}
    previous_source_years = {
        row["auction_date"][:4] for row in previous_rows if row.get("auction_date")
    }

    candidate_keys = {
        (row["auction_date"], normalized_address(row["address"])) for row in candidates
    }
    overlap_index: dict[tuple[str, str], list[dict]] = {}
    appearances_root = corpus.DATA / "appearances"
    if appearances_root.exists():
        for path in appearances_root.rglob("*.jsonl.gz"):
            if path == appearance_path:
                continue
            for existing in corpus.iter_rows(path):
                key = (existing.get("auction_date"), normalized_address(existing.get("address")))
                if key in candidate_keys:
                    overlap_index.setdefault(key, []).append(existing)

    admitted, duplicate_exclusions, related_interest_candidates = [], [], []
    for row in candidates:
        key = (row["auction_date"], normalized_address(row["address"]))
        matches = overlap_index.get(key, [])
        reason = duplicate_reason(row, matches)
        if reason:
            duplicate_exclusions.append({
                "appearance_id": row["appearance_id"],
                "reason": reason,
                "matched_appearance_ids": [match.get("appearance_id") for match in matches],
            })
            continue
        if matches:
            related_interest_candidates.append(row["appearance_id"])
        admitted.append(row)

    retained = corpus.write_rows(f"{SLUG}/saved-properties", admitted)
    if retained != len(admitted):
        raise ValueError(f"retained {retained} Shepherd rows; expected {len(admitted)}")
    new_rows = [row for row in admitted if row["appearance_id"] not in previous_ids]
    cutoff = twenty_year_cutoff(as_of).isoformat()
    in_window = [row for row in new_rows if cutoff <= row["auction_date"] <= as_of.isoformat()]
    future = [row for row in new_rows if row["auction_date"] > as_of.isoformat()]
    undated = [row for row in new_rows if not row.get("auction_date")]
    partial = [row for row in new_rows if not row.get("address")]

    by_date = Counter(row["auction_date"] for row in admitted)
    for auction_date, count in sorted(by_date.items()):
        state = {
            "auctioneer": SOURCE_NAME,
            "source_auction_id": f"shepherd:{auction_date}",
            "auction_date": auction_date,
            "catalogue_complete": False,
            "saved_inventory_reconciled": True,
            "completion_scope": "all Shepherd rows retained in the saved production board for this date; not the original catalogue denominator",
            "lots_captured": count,
            "source_snapshot": evidence,
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{auction_date}.json", state)

    new_historical_years = {row["auction_date"][:4] for row in in_window}
    summary = {
        "checked_at": corpus.now(),
        "source": SLUG,
        "auctioneer": SOURCE_NAME,
        "source_file": str(source_file.relative_to(corpus.ROOT)),
        "source_snapshot": evidence,
        "visible_saved_source_rows": len(saved),
        "distinct_source_identities": len(candidates),
        "appearances_captured": len(admitted),
        "run_new_appearances": len(new_rows),
        "run_new_address_records": len(new_rows) - len(partial),
        "run_new_dated_twenty_year_address_records": len([row for row in in_window if row.get("address")]),
        "run_new_partial_lots": len(partial),
        "run_new_undated": len(undated),
        "run_new_future_dated": len(future),
        "run_new_commercial_or_mixed": sum(row["sector"] in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(duplicate_exclusions),
        "related_interest_candidates_preserved": len(related_interest_candidates),
        "duplicate_evidence": duplicate_exclusions,
        "related_interest_candidate_ids": related_interest_candidates,
        "new_source_years": sorted(new_historical_years - previous_source_years),
        "by_date": dict(sorted(by_date.items())),
        "by_sector": dict(Counter(row["sector"] for row in new_rows)),
        "saved_source_inventory_reconciled": True,
        "historical_archive_complete": False,
        "operator_reconciliation_pending": True,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "shepherd_saved_properties_collection.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", default="data/properties.json")
    parser.add_argument("--as-of-date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    source_file = Path(args.source_file)
    if not source_file.is_absolute():
        source_file = corpus.ROOT / source_file
    run_import(source_file, date.fromisoformat(args.as_of_date))


if __name__ == "__main__":
    main()
