"""Recover Goldings' 22 July 2020 lots from a retained cached catalogue.

The later first-party result archive reports 13 offered lots but now exposes
zero property cards.  A public cached copy of the auctioneer's 36-page
catalogue preserves 14 advertised lot pages.  This collector banks those
catalogue appearances without inferring which lot left the offered result
denominator, and without assigning any outcome or achieved price.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import historical_corpus as corpus


SNAPSHOT = corpus.DATA / "sources/goldings/cached-catalogue-2020-07-22.json"
SHARD = corpus.DATA / "appearances/goldings/canonical.jsonl.gz"
STATE = corpus.DATA / "auctions/goldings/22-07-2020.json"
SUMMARY = corpus.DATA / "goldings_2020_cached_catalogue_collection.json"
STANDARD_SUMMARY = corpus.DATA / "goldings_collection.json"


def load_snapshot(path: Path = SNAPSHOT) -> dict:
    raw = path.read_bytes()
    snapshot = json.loads(raw)
    validate_snapshot(snapshot)
    snapshot["_sha256"] = corpus.digest(raw)
    snapshot["_snapshot_path"] = str(path.relative_to(corpus.ROOT))
    return snapshot


def validate_snapshot(snapshot: dict) -> None:
    if snapshot.get("auction_date") != "2020-07-22":
        raise ValueError("cached catalogue must preserve the exact auction date")
    if snapshot.get("source_auction_id") != "goldings:22-07-2020":
        raise ValueError("cached catalogue has an unexpected source auction identity")
    lots = snapshot.get("lots") or []
    if len(lots) != 14 or [row.get("lot_number") for row in lots] != [str(i) for i in range(1, 15)]:
        raise ValueError("cached catalogue must contain the 14 sequential advertised lot pages")
    if snapshot.get("published_catalogue_rows") != len(lots):
        raise ValueError("catalogue row denominator does not match retained lots")
    if snapshot.get("result_archive_lots_offered") != 13:
        raise ValueError("first-party result denominator must remain distinct from the catalogue")
    for lot in lots:
        if not corpus.PC.fullmatch(lot.get("postcode") or ""):
            raise ValueError(f"lot {lot.get('lot_number')} has no exact postcode")
        if (lot.get("guide_price") is not None or lot.get("guide_price_high") is not None) and not lot.get("guide_decode_confident"):
            raise ValueError(f"lot {lot.get('lot_number')} admits an ambiguous guide")
        if lot.get("sector") not in {"residential", "commercial", "mixed-use", "land", "unknown"}:
            raise ValueError(f"lot {lot.get('lot_number')} has an invalid sector")


def evidence(snapshot: dict) -> dict:
    return {
        "source_url": snapshot["original_url"],
        "retrieved_at": snapshot["retrieved_at"],
        "sha256": snapshot["_sha256"],
        "snapshot_path": snapshot["_snapshot_path"],
        "basis": snapshot["retrieval_basis"],
        "cache_metadata": snapshot["cache_metadata"],
    }


def rows_from_snapshot(snapshot: dict) -> list[dict]:
    source_evidence = evidence(snapshot)
    rows = []
    for position, lot in enumerate(snapshot["lots"], 1):
        lot_number = lot["lot_number"]
        row = corpus.base_row(
            "Goldings Auctions",
            snapshot["source_auction_id"],
            snapshot["auction_date"],
            lot_number,
            f"cached-catalogue-lot-{lot_number}",
            snapshot["original_url"],
        )
        row.update(
            appearance_id=f"Goldings Auctions|2020-07-22|cached-catalogue-lot:{lot_number}",
            address=lot["address"],
            postcode=lot["postcode"],
            sector=lot["sector"],
            property_type=lot["property_type"],
            tenure=lot.get("tenure"),
            guide_price=lot.get("guide_price"),
            guide_price_high=lot.get("guide_price_high"),
            sale_price=None,
            status="unknown",
            description=lot["title"],
            annual_rent=lot.get("annual_rent"),
            rent_text=lot.get("rent_text"),
            lease_information=lot.get("lease_information"),
            identity_method="cached_catalogue_exact_auction_date_and_printed_lot_number",
            record_quality="address_record",
            source_position=position,
            source_page=lot["page"],
            source_line_range=lot["source_line_range"],
            source_guide_text=lot.get("guide_text"),
            ambiguous_guide_extraction=lot.get("ambiguous_guide_extraction"),
            source_address_note=lot.get("address_note"),
            auction_date_basis="catalogue introduction and live-sale date",
            source_evidence=source_evidence,
            result_evidence_status="unknown; first-party result archive has no surviving individual cards",
        )
        rows.append(row)
    return rows


def exact_key(row: dict) -> tuple[str, str, str] | None:
    if not row.get("auction_date") or not row.get("address") or not row.get("postcode"):
        return None
    address = re.sub(r"[^a-z0-9]+", " ", row["address"].casefold()).strip()
    postcode = re.sub(r"\s+", "", row["postcode"].upper())
    return row["auction_date"], address, postcode


def external_exact_appearances(target_ids: set[str]) -> dict[tuple[str, str, str], list[str]]:
    matches: dict[tuple[str, str, str], list[str]] = {}
    for path in sorted((corpus.DATA / "appearances").rglob("*.jsonl.gz")):
        for row in corpus.iter_rows(path):
            if row.get("appearance_id") in target_ids:
                continue
            key = exact_key(row)
            if key:
                matches.setdefault(key, []).append(row["appearance_id"])
    return matches


def recover() -> dict:
    snapshot = load_snapshot()
    proposed = rows_from_snapshot(snapshot)
    target_ids = {row["appearance_id"] for row in proposed}
    external = external_exact_appearances(target_ids)
    overlaps = []
    admitted = []
    for row in proposed:
        prior = external.get(exact_key(row), [])
        if prior:
            overlaps.append({
                "lot_number": row["lot_number"],
                "address": row["address"],
                "overlapping_appearance_ids": sorted(prior),
            })
        else:
            admitted.append(row)

    existing = list(corpus.iter_rows(SHARD)) if SHARD.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admitted})
    corpus.write_rows("goldings/canonical", list(merged.values()))
    added = [row for row in admitted if row["appearance_id"] not in before_ids]

    prior_state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state = {
        "auctioneer": "Goldings Auctions",
        "source_auction_id": snapshot["source_auction_id"],
        "auction_date": snapshot["auction_date"],
        "published_date": prior_state.get("published_date") or "Wednesday, 22 July 2020",
        "published_lots_offered": snapshot["result_archive_lots_offered"],
        "published_percent_sold": prior_state.get("published_percent_sold"),
        "published_total_raised": prior_state.get("published_total_raised"),
        "source_url": snapshot["result_archive_url"],
        "catalogue_source_url": snapshot["original_url"],
        "catalogue_complete": False,
        "source_rows_complete": True,
        "published_catalogue_rows": snapshot["published_catalogue_rows"],
        "visible_source_rows": len(proposed),
        "lots_captured": len(proposed),
        "appearances_banked": len(admitted),
        "exact_date_address_overlaps_excluded": len(overlaps),
        "pagination_reconciled": True,
        "denominator_reconciled": False,
        "denominator_basis": "14 advertised catalogue lot pages versus 13 lots offered on the later first-party result archive",
        "completion_scope": "all 14 advertised lot pages in the retained cached catalogue; individual result cards and the removed/withdrawn identity do not survive",
        "incomplete_reason": "catalogue and result denominators differ and no individual result rows survive",
        "source_evidence": evidence(snapshot),
        "result_source_evidence": prior_state.get("source_evidence"),
        "reconciliation_errors": [snapshot["result_reconciliation_note"]],
        "overlapping_source_evidence": overlaps,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(STATE, state)

    summary = {
        "checked_at": corpus.now(),
        "source": "Goldings Auctions cached 22 July 2020 catalogue",
        "source_url": snapshot["original_url"],
        "source_snapshot": evidence(snapshot),
        "auction_date": snapshot["auction_date"],
        "catalogue_rows_captured": len(proposed),
        "result_archive_lots_offered": snapshot["result_archive_lots_offered"],
        "denominator_reconciled": False,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_address_records_in_twenty_year_window": len(added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_appearances": 0,
        "run_new_future_dated_appearances": 0,
        "run_new_commercial_appearances": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use_appearances": sum(row.get("sector") == "mixed-use" for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rent_values": sum(row.get("annual_rent") is not None for row in added),
        "new_source_year_pairs": 1 if added and not any(row.get("auction_date", "").startswith("2020-") for row in existing) else 0,
        "duplicate_appearance_ids": len(proposed) - len(target_ids),
        "exact_date_address_overlaps_excluded": len(overlaps),
        "ambiguous_guides_left_null": sum(not lot.get("guide_decode_confident") for lot in snapshot["lots"]),
        "by_sector_new": dict(Counter(row.get("sector") or "unknown" for row in added)),
        "by_status_new": dict(Counter(row.get("status") or "unknown" for row in added)),
        "catalogue_complete": False,
        "source_rows_complete": True,
        "national_completeness_verified": False,
        "failures": [],
    }
    corpus.save_json(SUMMARY, summary)

    if STANDARD_SUMMARY.exists():
        standard = json.loads(STANDARD_SUMMARY.read_text())
        standard.update(
            checked_at=summary["checked_at"],
            appearances_captured=len(merged),
            run_new_appearances=len(added),
            run_new_address_records=summary["run_new_address_records"],
            run_new_partial_lots=summary["run_new_partial_lots"],
            by_status=dict(Counter(row.get("status") or "unknown" for row in merged.values())),
            by_sector=dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
            cached_catalogue_recovery=summary,
        )
        corpus.save_json(STANDARD_SUMMARY, standard)

    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    recover()
