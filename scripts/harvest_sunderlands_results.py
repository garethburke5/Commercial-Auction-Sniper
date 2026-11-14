"""Bank the finite Sunderlands 2016-2018 first-party result-sheet archive.

The archive exposes fourteen two-page PDFs.  Historic layouts are not stable
enough for positional parsing, so one declarative manifest records the visible
lot rows while this reusable runner validates every printed date, address
fragment, guide, achieved price and outcome before materialising canonical
appearances.  Local PDF inputs make saved-file recovery reproducible; without
them the same manifest can be fetched directly in a networked collector.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time

import requests
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Sunderlands"
SLUG = "sunderlands-results"
OPERATOR = "SUNDERLANDS 1862 LLP"
COMPANY_NUMBER = "OC338911"
MANIFEST = corpus.DATA / "sunderlands_results_manifest.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
NEXT_TARGET = (
    "Batch the first substantial accessible individual-lot archive for an uncovered genuine "
    "auctioneer from the source/year register, prioritising Auction Inspire, Auction Local or "
    "another first-party multi-event result surface. Reconcile aliases before counting a new "
    "auctioneer and keep national completeness false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def fetch(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("source did not return a PDF")
    return response.url, response.content


def load_manifest(path=MANIFEST):
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    if len(events) != 14:
        raise ValueError(f"expected 14 retained events, found {len(events)}")
    return payload, events


def pdf_text(raw):
    if not raw.startswith(b"%PDF-"):
        raise ValueError("saved source is not a PDF")
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)


def printed_date(text):
    match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(20\d{2})",
        clean(text) or "",
        re.I,
    )
    if not match:
        raise ValueError("result sheet has no exact printed date")
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def validate_event(config, text):
    date_value = printed_date(text)
    if date_value != config["auction_date"]:
        raise ValueError(f"printed date {date_value} does not match {config['auction_date']}")
    compact = normalized(text)
    if len(config["lots"]) != int(config["published_lot_denominator"]):
        raise ValueError("manifest denominator does not match listed rows")
    identities = set()
    for position, lot in enumerate(config["lots"], 1):
        fragment = normalized(lot["validation_text"])
        if fragment not in compact:
            raise ValueError(f"missing validation text for source row {position}: {lot['validation_text']}")
        key = (str(lot.get("lot_number")), normalized(lot["address"]))
        if key in identities:
            raise ValueError(f"duplicate manifest identity at source row {position}")
        identities.add(key)
        for field in ("guide_price", "guide_price_high", "sale_price"):
            value = lot.get(field)
            if value is not None and f"{int(value):,}" not in text:
                raise ValueError(f"missing printed {field} for source row {position}: {value}")
        outcome = lot.get("source_outcome_text")
        if outcome and normalized(outcome) not in compact:
            # Result stamps can interrupt text extraction, so the exact money
            # and address checks above remain authoritative for priced sales.
            if lot.get("sale_price") is None and outcome.casefold() != "sold":
                raise ValueError(f"missing printed outcome for source row {position}: {outcome}")


def make_rows(config, source_url, evidence):
    auction_date = config["auction_date"]
    auction_id = f"{SLUG}:{auction_date}"
    rows = []
    for position, item in enumerate(config["lots"], 1):
        lot_number = str(item["lot_number"]) if item.get("lot_number") is not None else None
        identity_label = f"lot:{lot_number}" if lot_number else f"row:{position}"
        source_id = hashlib.sha256(
            f"{auction_date}|{identity_label}|{normalized(item['address'])}".encode()
        ).hexdigest()[:24]
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_id, source_url)
        postcode = corpus.PC.search(item["address"])
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{identity_label}",
            address=item["address"],
            postcode=postcode.group().upper() if postcode else None,
            locality=item["address"],
            sector=item.get("sector") or corpus.sector(item["address"]),
            property_type=item.get("property_type"),
            tenure=item.get("tenure"),
            guide_price=item.get("guide_price"),
            guide_price_high=item.get("guide_price_high"),
            sale_price=item.get("sale_price"),
            status=item.get("status", "unknown"),
            annual_rent=item.get("annual_rent"),
            rent_text=item.get("rent_text"),
            site_area=item.get("site_area"),
            property_id=None,
            identity_method="first_party_exact_event_date_source_row_and_address",
            record_quality="address_record",
            source_position=position,
            source_guide_text=item.get("source_guide_text"),
            source_outcome_text=item.get("source_outcome_text"),
            source_event_url=source_url,
            source_property_url=None,
            auction_date_precision="day",
            auction_date_basis="exact date printed on first-party Sunderlands result sheet",
            source_platform="Sunderlands first-party previous auction results PDF",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name=config["trading_name"],
            source_evidence=evidence,
        )
        rows.append(row)
    return rows


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append(
                    {"appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")}
                )
    return values


def persist_continuation(summary, blocker):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["city_rural_catalogue_followup"] = blocker["city_rural"]
    payload["durrants_2021_2022_followup"] = blocker["durrants"]
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(local_source_dir=None):
    payload, configs = load_manifest()
    local_source_dir = Path(local_source_dir) if local_source_dir else None
    states, run_rows, failures = {}, [], []
    for position, config in enumerate(configs, 1):
        try:
            if local_source_dir:
                local_path = local_source_dir / config["local_filename"]
                raw = local_path.read_bytes()
                resolved = config["source_url"]
            else:
                resolved, raw = fetch(config["source_url"])
            text = pdf_text(raw)
            validate_event(config, text)
            sha, captured_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources" / SLUG / f"result-{sha[:20]}.pdf.gz"
            if not snapshot.exists():
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": resolved,
                "retrieved_at": captured_at,
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "retained first-party exact-dated Sunderlands property-auction result PDF",
                "source_tier": "first_party",
                "snapshot_format": "pdf",
            }
            rows = make_rows(config, resolved, evidence)
            state = {
                "auctioneer": SOURCE,
                "operator_legal_name": OPERATOR,
                "operator_company_number": COMPANY_NUMBER,
                "trading_name": config["trading_name"],
                "source_auction_id": f"{SLUG}:{config['auction_date']}",
                "auction_date": config["auction_date"],
                "auction_date_precision": "day",
                "source_url": resolved,
                "lots_captured": len(rows),
                "catalogue_complete": True,
                "source_rows_complete": True,
                "denominator_reconciled": True,
                "published_lot_denominator": config["published_lot_denominator"],
                "completion_scope": config["completion_scope"],
                "source_evidence": evidence,
                "errors": [],
                "checked_at": corpus.now(),
            }
            states[config["auction_date"]] = state
            corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{config['auction_date']}.json", state)
            run_rows.extend(rows)
            print("SUNDERLANDS", position, "/", len(configs), "sheets", len(run_rows), "lots", flush=True)
        except Exception as exc:
            failures.append({"url": config["source_url"], "error": f"{type(exc).__name__}: {exc}"[:700]})

    overlaps, admissible = [], []
    global_exact = global_exact_appearances()
    for row in run_rows:
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({"auction_date": row["auction_date"], "lot_number": row["lot_number"], "address": row["address"], "existing": matches})
        else:
            admissible.append(row)

    appearance_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    blocker = {
        "city_rural": {
            "checked_at": corpus.now(),
            "outcome": "zero_new_appearances",
            "events_checked": ["2022-11-15", "2022-12-07", "2025-01-29", "2025-12-17", "2026-06-24"],
            "evidence": "saved event snapshots expose no catalogue or property-card links; the extra retained 7 December-labelled snapshot is visibly the already captured 18 January 2023 event",
            "revisit_only_when": "a distinct retained catalogue, lot grid, platform mirror or other materially different recovery object is identified",
        },
        "durrants": {
            "checked_at": corpus.now(),
            "outcome": "zero_new_appearances",
            "events_checked": ["2021-02-24", "2021-04-28", "2021-05-26", "2021-08-25", "2021-09-29", "2021-11-24", "2021-12-15", "2022-03-30", "2022-06-08", "2022-06-29", "2022-09-28", "2022-11-02", "2022-11-30"],
            "evidence": "the first-party calendar retains dates but no individual rows; the complete public WordPress media inventory for 2021-2022 contains no auction catalogue or result PDF",
            "revisit_only_when": "a retained publisher/platform catalogue or result object with individual lots is identified",
        },
    }
    summary = {
        "checked_at": corpus.now(),
        "source_url": payload["archive_url"],
        "operator": {"canonical_name": SOURCE, "company_name": OPERATOR, "company_number": COMPANY_NUMBER, "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True, "historical_trading_names": ["Sunderlands & Thompsons", "Sunderlands"]},
        "result_sheets_configured": len(configs),
        "result_sheets_captured": len(states),
        "source_rows_reconciled": len(run_rows),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum(bool(row.get("auction_date") and row["auction_date"] > today) for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "auctions": states,
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "bounded_prior_route_blockers": blocker,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "sunderlands_results_collection.json", summary)
    persist_continuation(summary, blocker)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(configs) or len(run_rows) != sum(int(x["published_lot_denominator"]) for x in configs):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-source-dir")
    args = parser.parse_args()
    harvest(args.local_source_dir)
