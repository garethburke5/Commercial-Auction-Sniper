"""Harvest one operator from Bamboo's complete public shared-platform archive.

The public Bamboo Proptech search exposes every surviving listing in a paginated
Next.js payload.  Each index row carries a stable property id and an explicit
``organisation`` slug, so one operator can be recovered without treating the
shared marketplace as the auctioneer.  The collector reconciles the global
page denominator, filters one exact organisation, captures every surviving
detail payload, and retains a compact immutable snapshot of that operator's
index rows and details.

This is intentionally a reusable operator batch rather than a dated workflow
step.  Branch and trading-name reconciliation must be supplied by the caller.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_bamboo_auctioneer import fetch, page_props, row_from_property


def collect_index(host: str, workers: int = 10) -> tuple[list[dict], int, int]:
    """Return the globally reconciled index, page count and source denominator."""
    base = f"https://{host}/"
    first = page_props(fetch(base))["propertiesData"]
    total_count = int(first["meta"]["totalCount"])
    page_size = len(first["data"])
    if total_count < 1 or page_size < 1:
        raise ValueError("shared Bamboo index exposed no property rows")
    page_count = math.ceil(total_count / page_size)
    pages: dict[int, dict] = {1: first}

    def one(page: int) -> tuple[int, dict]:
        value = page_props(fetch(base + f"?page={page}"))["propertiesData"]
        if int(value["meta"]["totalCount"]) != total_count:
            raise ValueError(f"page {page} denominator drifted from {total_count}")
        return page, value

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        jobs = [executor.submit(one, page) for page in range(2, page_count + 1)]
        for position, future in enumerate(as_completed(jobs), 1):
            page, value = future.result()
            pages[page] = value
            if position % 50 == 0 or position + 1 == page_count:
                print(f"BAMBOO SHARED INDEX {position + 1}/{page_count}", flush=True)

    rows = [row for page in sorted(pages) for row in pages[page]["data"]]
    identities = [str(row.get("_id") or row.get("id") or "") for row in rows]
    if len(rows) != total_count:
        raise ValueError(f"shared index returned {len(rows)} rows; expected {total_count}")
    if not all(identities) or len(set(identities)) != total_count:
        raise ValueError("shared index contains missing or duplicate stable property ids")
    return rows, page_count, total_count


def harvest(
    organisation: str,
    auctioneer: str,
    slug: str,
    expected_count: int,
    host: str = "app.bambooproptech.com",
    workers: int = 10,
    operator_legal_name: str | None = None,
    operator_company_number: str | None = None,
) -> dict:
    base = f"https://{host}/"
    index_rows, page_count, global_count = collect_index(host, workers)
    matches = [row for row in index_rows if row.get("organisation") == organisation]
    if len(matches) != expected_count:
        counts = Counter(row.get("organisation") or "(none)" for row in index_rows)
        raise ValueError(
            f"organisation {organisation!r} exposes {len(matches)} rows, expected "
            f"{expected_count}; largest current organisations: {counts.most_common(10)}"
        )
    by_id = {str(row.get("_id") or row.get("id")): row for row in matches}

    details: dict[str, dict] = {}
    failures: dict[str, str] = {}

    def one_detail(summary: dict) -> tuple[str, dict]:
        source_id = str(summary.get("_id") or summary.get("id"))
        detail = page_props(fetch(urljoin(base, "property/" + summary["handle"]))).get("propertyData")
        if not detail:
            raise ValueError("detail page no longer exposes propertyData")
        if str(detail.get("_id") or detail.get("id")) != source_id:
            raise ValueError(f"detail identity mismatch for {source_id}")
        if detail.get("organisation") not in {None, organisation}:
            raise ValueError(f"detail organisation drift for {source_id}")
        return source_id, detail

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        jobs = {executor.submit(one_detail, row): source_id for source_id, row in by_id.items()}
        for position, future in enumerate(as_completed(jobs), 1):
            source_id = jobs[future]
            try:
                returned_id, detail = future.result()
                details[returned_id] = detail
            except Exception as exc:
                # Stable index rows remain individual evidence when a retired
                # detail loses only its richer payload.
                details[source_id] = by_id[source_id]
                failures[source_id] = f"{type(exc).__name__}: {exc}"
            if position % 25 == 0 or position == expected_count:
                print(f"BAMBOO SHARED DETAIL {position}/{expected_count}", flush=True)

    snapshot = {
        "source_url": base,
        "retrieved_at": corpus.now(),
        "global_index_rows": global_count,
        "global_page_count": page_count,
        "organisation": organisation,
        "organisation_rows": expected_count,
        "index_matches": [by_id[source_id] for source_id in sorted(by_id)],
        "property_details": [details[source_id] for source_id in sorted(details)],
        "detail_failures": failures,
    }
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    sha256 = corpus.digest(raw)
    snapshot_path = corpus.DATA / "sources" / slug / "bamboo-shared" / f"archive-{sha256[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot)
    evidence = {
        "source_url": base,
        "snapshot_path": str(snapshot_path.relative_to(corpus.ROOT)),
        "retrieved_at": snapshot["retrieved_at"],
        "sha256": sha256,
        "basis": "complete shared Bamboo index filtered by exact organisation plus stable property details",
    }
    now_utc = datetime.now(timezone.utc)
    rows = [
        row_from_property(
            details[source_id], auctioneer, slug, host, evidence, now_utc,
            operator_legal_name=operator_legal_name,
            operator_company_number=operator_company_number,
        )
        for source_id in sorted(details)
    ]
    if len({row["appearance_id"] for row in rows}) != expected_count:
        raise ValueError("operator rows do not have unique stable appearance ids")

    appearance_path = corpus.DATA / "appearances" / slug / "bamboo-shared.jsonl.gz"
    existing_ids = ({row["appearance_id"] for row in corpus.iter_rows(appearance_path)}
                    if appearance_path.exists() else set())
    new_rows = [row for row in rows if row["appearance_id"] not in existing_ids]
    retained = corpus.write_rows(f"{slug}/bamboo-shared", rows)
    if retained != expected_count:
        raise ValueError(f"retained {retained} rows; source exposes {expected_count}")

    today = now_utc.date().isoformat()
    historical = [row for row in rows if row.get("auction_date") and row["auction_date"] <= today]
    future = [row for row in rows if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in rows if not row.get("auction_date")]
    state = {
        "auctioneer": auctioneer,
        "operator_legal_name": operator_legal_name,
        "operator_company_number": operator_company_number,
        "source_auction_id": f"{slug}:bamboo-shared",
        "source_url": base,
        "organisation": organisation,
        "global_index_rows": global_count,
        "global_page_count": page_count,
        "visible_source_rows": expected_count,
        "lots_captured": retained,
        "detail_payloads_captured": expected_count - len(failures),
        "index_fallback_rows": len(failures),
        "source_rows_complete": True,
        "catalogue_complete": True,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "errors": [{"source_id": key, "error": value} for key, value in sorted(failures.items())],
        "checked_at": corpus.now(),
        "completion_scope": (
            f"all {organisation!r} listings surviving in the {global_count}-row public shared Bamboo index; "
            "not a claim that deleted listings or earlier platforms are covered"
        ),
    }
    corpus.save_json(corpus.DATA / "auctions" / slug / "bamboo-shared.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": auctioneer,
        "operator": {
            "canonical_name": auctioneer,
            "company_name": operator_legal_name,
            "company_number": operator_company_number,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "source_url": base,
        "organisation": organisation,
        "shared_platform_rows_reconciled": global_count,
        "shared_platform_pages_reconciled": page_count,
        "archive_appearances_captured": retained,
        "run_new_appearances": len(new_rows),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "dated_historical_records": len(historical),
        "future_dated_records": len(future),
        "undated_records": len(undated),
        "detail_payloads_captured": expected_count - len(failures),
        "index_fallback_rows": len(failures),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": sum(row.get("sale_price") is not None for row in rows),
        "with_rent": sum(row.get("annual_rent") is not None for row in rows),
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_year": dict(Counter(row["auction_date"][:4] if row.get("auction_date") else "undated" for row in rows)),
        "source_years": sorted({row["auction_date"][:4] for row in historical}),
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "complete": True,
        "completion_scope": state["completion_scope"],
    }
    corpus.save_json(corpus.DATA / f"{slug.replace('-', '_')}_bamboo_shared_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organisation", required=True)
    parser.add_argument("--auctioneer", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--host", default="app.bambooproptech.com")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--operator-legal-name")
    parser.add_argument("--operator-company-number")
    args = parser.parse_args()
    harvest(
        args.organisation, args.auctioneer, args.slug, args.expected_count,
        host=args.host, workers=args.workers,
        operator_legal_name=args.operator_legal_name,
        operator_company_number=args.operator_company_number,
    )
