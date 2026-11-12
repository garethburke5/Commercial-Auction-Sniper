"""Bank Sunderlands' complete retained 2016-2018 result-PDF archive.

The first-party previous-results page is a finite fourteen-event inventory.
Each linked PDF prints an exact event date and individually named property
rows with guides and, where published, outcomes and achieved prices.  The
manifest is deliberately declarative because several two-column sheets do not
have a stable PDF text order.  Every manifest row is validated against the
immutable PDF text before admission, and all fourteen files are processed in
one reusable run.
"""
from __future__ import annotations

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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Sunderlands"
SLUG = "sunderlands"
MANIFEST = corpus.DATA / "sunderlands_result_manifest.json"
ARCHIVE = "https://www.sunderlands.co.uk/property-auctions/previous-results"
OPERATOR = "SUNDERLANDS 1862 LLP"
FORMER_NAME = "SUNDERLANDS AND THOMPSONS LLP"
COMPANY_NUMBER = "OC338911"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(20\d{2})\b",
    re.I,
)
NEXT_TARGET = (
    "Inventory Sunderlands' post-2018 property-auction result and catalogue assets, then batch every "
    "surviving address-level event through this reusable runner. If no later finite archive survives, "
    "move to another uncovered genuine auctioneer with an accessible multi-catalogue inventory. "
    "National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def load_manifest(path=MANIFEST):
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    if len(events) != 14:
        raise ValueError(f"expected 14 retained result PDFs, found {len(events)}")
    if len({event["source_url"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate result URLs")
    if sum(len(event["lots"]) for event in events) != 61:
        raise ValueError("manifest must retain the 61 individually published properties")
    return payload


def discover_result_pdfs(html, archive_url=ARCHIVE):
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(archive_url, anchor["href"])
        parsed = urlparse(url)
        if parsed.netloc.casefold() not in {"sunderlands.co.uk", "www.sunderlands.co.uk"}:
            continue
        if "/previous-auction-results/" not in parsed.path.casefold():
            continue
        if parsed.path.casefold().endswith(".pdf"):
            found.add(url)
    if len(found) != 14:
        raise ValueError(f"first-party previous-results page exposes {len(found)} PDFs, expected 14")
    return found


def pdf_text(raw):
    if not raw.startswith(b"%PDF-"):
        raise ValueError("result link did not return a PDF")
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)


def parse_date(text):
    match = DATE_RE.search(text)
    if not match:
        raise ValueError("result PDF has no exact event date")
    day, month, year = match.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()


def validate_event(text, config):
    auction_date = parse_date(text)
    if auction_date != config["auction_date"]:
        raise ValueError(f"PDF date {auction_date} differs from manifest {config['auction_date']}")
    folded = normalized(text)
    seen_ids = set()
    for position, item in enumerate(config["lots"], 1):
        marker = normalized(item["validation_text"])
        if marker not in folded:
            raise ValueError(f"lot {item.get('lot_number') or position} validation text is absent")
        source_id = item.get("source_lot_id") or f"lot:{item.get('lot_number')}"
        if source_id in seen_ids:
            raise ValueError(f"duplicate source identity {source_id}")
        seen_ids.add(source_id)
        for field in ("guide_price", "guide_price_high", "sale_price"):
            amount = item.get(field)
            if amount is not None and f"{int(amount):,}" not in text:
                raise ValueError(f"{field} {amount} for {source_id} is absent from PDF")
    if len(config["lots"]) != int(config["published_lot_denominator"]):
        raise ValueError("manifest lot count does not reconcile to published denominator")
    return auction_date


def source_outcome_text(item):
    if item.get("source_outcome_text"):
        return item["source_outcome_text"]
    status = item.get("status", "unknown")
    amount = item.get("sale_price")
    if status == "sold" and amount:
        return f"Sold for £{int(amount):,}"
    return {
        "sold_after": "Sold after auction",
        "sold_prior": "Sold prior to auction",
        "withdrawn": "Withdrawn",
        "unsold": "Not sold",
        "unknown": None,
    }.get(status)


def materialize_event(config, resolved_url, evidence, text):
    auction_date = validate_event(text, config)
    auction_id = f"{SLUG}:{auction_date}"
    rows = []
    for position, item in enumerate(config["lots"], 1):
        lot_number = item.get("lot_number")
        source_lot_id = item.get("source_lot_id") or f"lot:{lot_number}"
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_lot_id, resolved_url)
        postcode = corpus.PC.search(item["address"])
        sector = item.get("sector") or corpus.sector(item["address"])
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
            address=item["address"],
            postcode=postcode.group().upper() if postcode else None,
            locality=item["address"],
            sector=sector,
            status=item.get("status", "unknown"),
            guide_price=item.get("guide_price"),
            guide_price_high=item.get("guide_price_high"),
            sale_price=item.get("sale_price"),
            annual_rent=None,
            description=item.get("description"),
            identity_method="first_party_exact_event_date_lot_or_source_position_and_address",
            record_quality="address_record",
            source_position=position,
            source_guide_text=item.get("source_guide_text"),
            source_outcome_text=source_outcome_text(item),
            source_note=item.get("source_note"),
            source_event_url=resolved_url,
            source_property_url=None,
            auction_date_precision="day",
            auction_date_basis="exact date printed on first-party result PDF",
            source_platform="Sunderlands first-party previous auction result PDF",
            operator_legal_name=OPERATOR,
            operator_former_name=FORMER_NAME,
            operator_company_number=COMPANY_NUMBER,
            trading_name=SOURCE,
            source_evidence=evidence,
        )
        rows.append(row)
    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_former_name": FORMER_NAME,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": auction_id,
        "auction_date": auction_date,
        "auction_date_precision": "day",
        "source_url": resolved_url,
        "lots_captured": len(rows),
        "published_lots_offered": int(config["published_lot_denominator"]),
        "catalogue_complete": True,
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "completion_scope": "all individually named property rows in the retained first-party result PDF",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                })
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    if not path.exists():
        return
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
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    manifest = load_manifest()
    archive_url, archive_raw = get(manifest.get("archive_url") or ARCHIVE)
    archive_sha, archive_time = corpus.digest(archive_raw), corpus.now()
    archive_snapshot = corpus.DATA / "sources" / SLUG / f"previous-results-{archive_sha[:20]}.html.gz"
    if not archive_snapshot.exists():
        corpus.atomic(archive_snapshot, gzip.compress(archive_raw, mtime=0))
    archive_evidence = {
        "source_url": archive_url,
        "retrieved_at": archive_time,
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party finite previous property-auction result archive",
    }
    discovered = discover_result_pdfs(archive_raw.decode("utf-8", "replace"), archive_url)
    configured = {event["source_url"] for event in manifest["events"]}
    if discovered != configured:
        raise ValueError("manifest URLs do not exactly reconcile to the live fourteen-PDF archive")

    states, run_rows, failures = {}, [], []
    for position, config in enumerate(manifest["events"], 1):
        try:
            resolved, raw = get(config["source_url"])
            sha, captured_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources" / SLUG / f"result-{config['auction_date']}-{sha[:20]}.pdf.gz"
            if not snapshot.exists():
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": resolved,
                "retrieved_at": captured_at,
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "retained first-party exact-dated property-auction result PDF",
            }
            text = pdf_text(raw)
            state, rows = materialize_event(config, resolved, evidence, text)
            states[state["auction_date"]] = state
            corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)
            run_rows.extend(rows)
            print("SUNDERLANDS", position, "/", len(manifest["events"]), "PDFs", len(run_rows), "lots", flush=True)
        except Exception as exc:
            failures.append({"url": config["source_url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    overlaps, admissible = [], []
    global_exact = global_exact_appearances()
    for row in run_rows:
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({
                "auction_date": row["auction_date"], "lot_number": row["lot_number"],
                "address": row["address"], "existing": matches,
            })
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
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
    summary = {
        "checked_at": corpus.now(),
        "source_url": ARCHIVE,
        "operator": {
            "canonical_name": SOURCE, "legal_name": OPERATOR, "former_name": FORMER_NAME,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "result_pdfs_discovered": len(discovered),
        "result_pdfs_captured": len(states),
        "published_property_rows_reconciled": len(run_rows),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "archive_evidence": archive_evidence,
        "auctions": states,
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "sunderlands_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(manifest["events"]) or len(run_rows) != 61:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    harvest()
