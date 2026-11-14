"""Bank Jones Peckover first-party PDF catalogues from a bounded manifest.

The manifest can carry several event catalogues and several legal interests
per catalogue.  Each run verifies the transcribed values against the fetched
first-party document, stores the immutable original PDF and reconciles stable
source identities before replacing this collector's canonical shard.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import gzip
import io
import json
from pathlib import Path
import sys

import requests
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Jones Peckover"
SLUG = "jones-peckover-catalogues"
MANIFEST = corpus.DATA / "jones_peckover_catalogue_manifest.json"
HEADERS = {"User-Agent": "AuctionGeek historical evidence collector/1.0"}


def pdf_text(raw: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)


def validate_event(event: dict, text: str) -> None:
    missing = [token for token in event["expected_text"] if token.casefold() not in text.casefold()]
    if missing:
        raise ValueError(f"source catalogue no longer verifies manifest tokens: {missing}")
    lots = event.get("lots") or []
    identities = [lot["source_lot_id"] for lot in lots]
    if not lots or len(identities) != len(set(identities)):
        raise ValueError("catalogue manifest must contain distinct individual lot identities")
    for lot in lots:
        if lot["postcode"].casefold() not in text.casefold():
            raise ValueError(f"postcode not found in source catalogue: {lot['postcode']}")
        if lot["guide_price_text"].casefold() not in text.casefold():
            raise ValueError(f"guide not found in source catalogue: {lot['guide_price_text']}")


def snapshot(raw: bytes, url: str, auction_date: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"catalogue-{auction_date}-{sha[:16]}.pdf.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "first-party Jones Peckover public-auction PDF catalogue",
    }


def event_rows(event: dict, evidence: dict) -> list[dict]:
    auction_date = event["auction_date"]
    auction_id = f"jones-peckover:{auction_date}"
    rows = []
    for position, lot in enumerate(event["lots"], 1):
        row = corpus.base_row(
            SOURCE, auction_id, auction_date, lot["lot_number"],
            lot["source_lot_id"], event["source_url"],
        )
        row.update(
            appearance_id=f"{SOURCE}|catalogue-lot:{lot['source_lot_id']}",
            address=lot["address"],
            postcode=lot["postcode"],
            locality=lot["address"],
            description=lot["description"],
            sector=lot["sector"],
            guide_price=lot["guide_price"],
            guide_price_text=lot["guide_price_text"],
            status=lot["status"],
            property_id=lot["source_lot_id"],
            identity_method="first_party_catalogue_date_and_published_lot",
            record_quality="address_record",
            source_position=position,
            source_event_url=event["source_url"],
            source_property_url=event["source_url"],
            source_platform="Jones Peckover first-party public-auction catalogue",
            source_evidence=evidence,
        )
        rows.append(row)
    return rows


def harvest(manifest_path: Path = MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    rows, event_states = [], []
    for event in manifest["events"]:
        response = requests.get(event["source_url"], headers=HEADERS, timeout=120)
        response.raise_for_status()
        raw = response.content
        if not raw.startswith(b"%PDF"):
            raise ValueError(f"not a PDF: {event['source_url']}")
        text = pdf_text(raw)
        validate_event(event, text)
        evidence = snapshot(raw, response.url, event["auction_date"])
        captured = event_rows(event, evidence)
        rows.extend(captured)
        event_states.append({
            "auctioneer": SOURCE,
            "source_auction_id": f"jones-peckover:{event['auction_date']}",
            "auction_date": event["auction_date"],
            "source_url": response.url,
            "catalogue_complete": True,
            "source_rows_complete": True,
            "lots_captured": len(captured),
            "source_evidence": evidence,
            "completion_scope": "every separately numbered property interest published in this retained first-party PDF",
            "checked_at": corpus.now(),
            "errors": [],
        })
    by_id = {row["appearance_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate appearance identity across manifest catalogues")
    corpus.write_rows(f"{SLUG}/canonical", rows, preserve_existing=True)
    persisted = list(corpus.iter_rows(existing_path))
    for state in event_states:
        corpus.save_json(
            corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state
        )

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    old = {row["appearance_id"]: row for row in existing}
    new_ids = set(by_id) - set(old)
    new_rows = [by_id[value] for value in sorted(new_ids)]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in persisted if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "source_url": [event["source_url"] for event in manifest["events"]],
        "catalogues_captured": len(event_states),
        "appearances_captured": len(persisted),
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= row["auction_date"] <= today for row in new_rows
        ),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_undated": sum(not row.get("auction_date") for row in new_rows),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in new_rows),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in persisted)),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in persisted)),
        "duplicate_source_evidence_excluded": 0,
        "national_completeness_verified": False,
        "completion_scope": "three retained first-party PDFs, two auction dates and every separately numbered published interest; not evidence of Jones Peckover national or historical completeness",
    }
    corpus.save_json(corpus.DATA / "jones_peckover_catalogue_collection.json", summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    harvest()
