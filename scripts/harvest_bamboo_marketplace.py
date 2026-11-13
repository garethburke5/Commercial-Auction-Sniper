"""Bank the complete public Bamboo Proptech marketplace without alias inflation.

The marketplace exposes a paginated Next.js index and one structured detail
payload per stable property id.  Detail batches are stored as immutable,
checksum-addressed snapshots so a long collection can resume page by page.
Rows are attributed to the publishing organisation; branch names are retained
as evidence metadata and are never counted as separate auctioneers.

Stable Bamboo ids already banked through a white-label host are excluded from
the marketplace appearance shard.  Exact date/address overlaps with other
sources are also preserved as exclusions rather than counted twice.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import json
import math
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_bamboo_auctioneer import fetch, page_props, row_from_property


HOST = "app.bambooproptech.com"
SLUG = "bamboo-marketplace"


def stable_id(item: dict) -> str:
    return str(item.get("_id") or item.get("id") or "").strip()


def normal_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def organisation_name(item: dict) -> str:
    details = item.get("organisationDetails") or {}
    display = (
        corpus.clean(details.get("display"))
        or corpus.clean(details.get("name"))
        or corpus.clean(item.get("organisation"))
        or "Unknown Bamboo publisher"
    )
    # Preserve one canonical auctioneer where Bamboo's display is a trading-
    # name variant already reconciled in the corpus.
    return {"Clive Emson Auctioneers": "Clive Emson"}.get(display, display)


def load_json_gzip(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def reusable_detail_batch(source_dir: Path, page: int, expected_ids: set[str]) -> tuple[Path, dict] | None:
    for path in sorted(source_dir.glob(f"detail-page-{page:03d}-*.json.gz"), reverse=True):
        try:
            value = load_json_gzip(path)
        except (OSError, json.JSONDecodeError):
            continue
        rows = value.get("property_details") or []
        if {stable_id(row) for row in rows} == expected_ids:
            return path, value
    return None


def known_evidence(exclude_path: Path) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    bamboo_ids: dict[str, dict] = {}
    date_addresses: dict[tuple[str, str], dict] = {}
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == exclude_path:
            continue
        for row in corpus.iter_rows(path):
            source_id = str(row.get("source_lot_id") or "")
            if source_id and row.get("identity_method") == "bamboo_stable_property_id":
                bamboo_ids.setdefault(source_id, row)
            date = row.get("auction_date")
            address = normal_address(row.get("address"))
            if date and address:
                date_addresses.setdefault((date, address), row)
    return bamboo_ids, date_addresses


def fetch_archive(workers: int = 12) -> tuple[list[dict], dict[str, dict], dict[str, dict], dict]:
    base = f"https://{HOST}/"
    source_dir = corpus.DATA / "sources" / SLUG / "bamboo"
    first_raw = fetch(base)
    first_index = page_props(first_raw)["propertiesData"]
    total_count = int(first_index["meta"]["totalCount"])
    page_size = len(first_index["data"])
    if total_count < 1 or page_size < 1:
        raise SystemExit("Bamboo marketplace exposed no properties")
    page_count = math.ceil(total_count / page_size)
    index_pages: dict[int, dict] = {1: first_index}

    def collect_index(number: int) -> tuple[int, dict]:
        return number, page_props(fetch(base + f"?page={number}"))["propertiesData"]

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        jobs = [executor.submit(collect_index, page) for page in range(2, page_count + 1)]
        for position, future in enumerate(as_completed(jobs), 1):
            number, payload = future.result()
            index_pages[number] = payload
            if position % 20 == 0 or position + 1 == page_count:
                print(f"BAMBOO MARKETPLACE INDEX {position + 1}/{page_count}", flush=True)

    index_rows = [item for page in sorted(index_pages) for item in index_pages[page]["data"]]
    by_id = {stable_id(item): item for item in index_rows}
    if len(index_rows) != total_count:
        raise SystemExit(
            f"marketplace index reconciliation failed: rows={len(index_rows)} "
            f"ids={len(by_id)} expected={total_count}"
        )
    duplicate_index_cards = total_count - len(by_id)

    index_value = {
        "source_url": base,
        "retrieved_at": corpus.now(),
        "total_count": total_count,
        "page_size": page_size,
        "page_count": page_count,
        "index_pages": [index_pages[page] for page in sorted(index_pages)],
    }
    index_bytes = json.dumps(index_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    index_sha = corpus.digest(index_bytes)
    index_path = source_dir / f"index-{index_sha[:16]}.json.gz"
    if not index_path.exists():
        corpus.save_gzip(index_path, index_value)

    details: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    batch_paths: list[str] = []
    fetched_batches = 0
    reused_batches = 0
    batches: dict[int, tuple[Path, dict]] = {}
    missing_batches: list[tuple[int, list[dict], set[str]]] = []
    for page in sorted(index_pages):
        summaries = index_pages[page]["data"]
        expected_ids = {stable_id(item) for item in summaries}
        reusable = reusable_detail_batch(source_dir, page, expected_ids)
        if reusable:
            batches[page] = reusable
            reused_batches += 1
        else:
            missing_batches.append((page, summaries, expected_ids))

    def collect_batch(job: tuple[int, list[dict], set[str]]) -> tuple[int, Path, dict]:
        page, summaries, expected_ids = job
        page_details: dict[str, dict] = {}

        def collect_detail(summary: dict) -> tuple[str, dict]:
            source_id = stable_id(summary)
            payload = page_props(fetch(base + "property/" + summary["handle"]))["propertyData"]
            if stable_id(payload) != source_id:
                raise ValueError(f"detail identity mismatch for {source_id}")
            return source_id, payload

        with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
            jobs = [executor.submit(collect_detail, summary) for summary in summaries]
            for future in as_completed(jobs):
                source_id, payload = future.result()
                page_details[source_id] = payload
        if set(page_details) != expected_ids:
            raise ValueError(f"detail batch {page} did not reconcile")
        batch_value = {
            "source_url": base + f"?page={page}",
            "retrieved_at": corpus.now(),
            "index_snapshot_path": str(index_path.relative_to(corpus.ROOT)),
            "page": page,
            "property_details": [page_details[source_id] for source_id in sorted(page_details)],
        }
        batch_bytes = json.dumps(batch_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        batch_sha = corpus.digest(batch_bytes)
        batch_path = source_dir / f"detail-page-{page:03d}-{batch_sha[:16]}.json.gz"
        corpus.save_gzip(batch_path, batch_value)
        return page, batch_path, batch_value

    # Four page batches (up to 64 detail requests) is the reliable ceiling for
    # the public host; higher fan-out causes long tail retries rather than gain.
    batch_workers = max(1, min(4, workers // 4 or 1))
    with ThreadPoolExecutor(max_workers=batch_workers) as executor:
        jobs = [executor.submit(collect_batch, job) for job in missing_batches]
        for future in as_completed(jobs):
            page, batch_path, batch_value = future.result()
            batches[page] = (batch_path, batch_value)
            fetched_batches += 1
            if fetched_batches % 10 == 0 or len(batches) == page_count:
                print(
                    f"BAMBOO MARKETPLACE BATCHES {len(batches)}/{page_count} "
                    f"(fetched {fetched_batches}, reused {reused_batches})",
                    flush=True,
                )

    for page in sorted(batches):
        batch_path, batch_value = batches[page]
        batch_sha = corpus.digest(
            json.dumps(batch_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        )
        batch_evidence = {
            "source_url": batch_value["source_url"],
            "snapshot_path": str(batch_path.relative_to(corpus.ROOT)),
            "retrieved_at": batch_value["retrieved_at"],
            "sha256": batch_sha,
            "basis": "complete public Bamboo marketplace index and stable property detail payload",
        }
        batch_paths.append(str(batch_path.relative_to(corpus.ROOT)))
        for item in batch_value["property_details"]:
            source_id = stable_id(item)
            details[source_id] = item
            evidence[source_id] = batch_evidence
    if len(details) != len(by_id):
        raise SystemExit(f"detail reconciliation failed: {len(details)} of {len(by_id)} stable ids")
    archive_meta = {
        "source_url": base,
        "index_snapshot_path": str(index_path.relative_to(corpus.ROOT)),
        "index_sha256": index_sha,
        "total_count": total_count,
        "stable_property_ids": len(by_id),
        "duplicate_index_cards": duplicate_index_cards,
        "page_size": page_size,
        "page_count": page_count,
        "detail_batch_paths": batch_paths,
        "detail_batches_fetched": fetched_batches,
        "detail_batches_reused": reused_batches,
    }
    return index_rows, details, evidence, archive_meta


def harvest(workers: int = 12, initial_bank_report: bool = False) -> dict:
    index_rows, details, evidence, archive_meta = fetch_archive(workers)
    appearance_path = corpus.DATA / "appearances" / SLUG / "marketplace-archive.jsonl.gz"
    known_bamboo_ids, known_date_addresses = known_evidence(appearance_path)
    now_utc = datetime.now(timezone.utc)
    candidates: list[dict] = []
    exclusions: list[dict] = []
    for source_id in sorted(details):
        item = details[source_id]
        publisher = organisation_name(item)
        row = row_from_property(item, publisher, SLUG, HOST, evidence[source_id], now_utc)
        row.update(
            publisher_platform="Bamboo Proptech",
            source_organisation=corpus.clean(item.get("organisation")) or None,
            source_organisation_display=publisher,
            source_branch=corpus.clean(item.get("branchDisplay")) or None,
        )
        if source_id in known_bamboo_ids:
            prior = known_bamboo_ids[source_id]
            exclusions.append(
                {
                    "source_lot_id": source_id,
                    "reason": "stable Bamboo property id already banked through a white-label source",
                    "original_url": row["original_url"],
                    "banked_appearance_id": prior.get("appearance_id"),
                    "banked_auctioneer": prior.get("auctioneer"),
                }
            )
            continue
        overlap = known_date_addresses.get((row.get("auction_date"), normal_address(row.get("address"))))
        if overlap and row.get("auction_date") and row.get("address"):
            exclusions.append(
                {
                    "source_lot_id": source_id,
                    "reason": "exact auction-date and normalized-address evidence already banked",
                    "original_url": row["original_url"],
                    "banked_appearance_id": overlap.get("appearance_id"),
                    "banked_auctioneer": overlap.get("auctioneer"),
                }
            )
            continue
        candidates.append(row)

    prior_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    prior_ids = {row["appearance_id"] for row in prior_rows}
    # The stable marketplace id, rather than the display-derived appearance id,
    # is authoritative.  This lets a later alias reconciliation replace the
    # label in-place without creating a second appearance for the same listing.
    merged = {str(row["source_lot_id"]): row for row in prior_rows}
    for row in candidates:
        merged[str(row["source_lot_id"])] = row
    rows = sorted(merged.values(), key=lambda row: row["appearance_id"])
    # We have already merged every prior stable id above.  Opt out of the
    # appearance-id preservation layer so a proven trading-name alias repair
    # replaces, rather than duplicates, the same stable Bamboo property.
    retained = corpus.write_rows(f"{SLUG}/marketplace-archive", rows, preserve_existing=False)
    new_rows = rows if initial_bank_report else [row for row in rows if row["appearance_id"] not in prior_ids]
    today = now_utc.date().isoformat()
    dated_historical = [row for row in new_rows if row.get("auction_date") and row["auction_date"] <= today]
    future = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in new_rows if not row.get("auction_date")]
    by_reason = Counter(item["reason"] for item in exclusions)
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive_meta["source_url"],
        "publisher_platform": "Bamboo Proptech",
        "operator_reconciliation": "Each organisation display is the auctioneer attribution; branchDisplay is retained as branch evidence and is not counted as another auctioneer.",
        "visible_marketplace_properties": archive_meta["total_count"],
        "stable_property_ids": archive_meta["stable_property_ids"],
        "duplicate_index_cards_merged": archive_meta["duplicate_index_cards"],
        "index_pages": archive_meta["page_count"],
        "detail_payloads_captured": len(details),
        "appearances_retained": retained,
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(
            bool(
                row.get("address")
                and row.get("auction_date")
                and "2006-11-13" <= row["auction_date"] <= today
            )
            for row in new_rows
        ),
        "run_new_undated_appearances": len(undated),
        "run_new_future_dated_appearances": len(future),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(
            bool(row.get("annual_rent") is not None or row.get("rent_text")) for row in new_rows
        ),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "by_sector": dict(Counter(row.get("sector") for row in new_rows)),
        "by_auctioneer": dict(Counter(row.get("auctioneer") for row in new_rows)),
        "source_years": sorted({row["auction_date"][:4] for row in dated_historical}),
        "duplicate_source_evidence_excluded": len(exclusions),
        "exclusions_by_reason": dict(by_reason),
        "exclusions": exclusions,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "catalogue_complete": True,
        "completion_scope": "every stable listing in the surviving public Bamboo marketplace archive; deleted listings and pre-Bamboo catalogues are not claimed",
        "archive": archive_meta,
        "national_completeness_verified": False,
    }
    state = {
        "auctioneer": "Bamboo Proptech marketplace (attributed publishers)",
        "source_auction_id": f"{SLUG}:marketplace-archive",
        "source_url": archive_meta["source_url"],
        "source_rows_complete": True,
        "catalogue_complete": True,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "visible_source_rows": archive_meta["total_count"],
        "lots_captured": retained,
        "overlap_exclusions": len(exclusions),
        "errors": [],
        "checked_at": summary["checked_at"],
        "completion_scope": summary["completion_scope"],
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "marketplace-archive.json", state)
    corpus.save_json(corpus.DATA / "bamboo_marketplace_collection.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key not in {"exclusions", "by_auctioneer"}}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--initial-bank-report",
        action="store_true",
        help="Report every retained marketplace row as this checkout's initial bank after a post-write interrupted first run.",
    )
    args = parser.parse_args()
    harvest(args.workers, args.initial_bank_report)
