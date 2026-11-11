"""Bank Durrants' retained first-party property-auction result sheets.

The official auction calendar is the event inventory.  Its retained result
links are exact-dated, finite PDF sheets containing numbered property rows,
guide prices and published outcomes.  One reusable run discovers and parses
every linked sheet; the calendar and each PDF are kept as immutable evidence.
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


SOURCE = "Durrants"
SLUG = "durrants"
ARCHIVE = "https://durrants.com/property-auctions/auctions-calendar/"
OPERATOR = "GEORGE DURRANT & SONS LIMITED"
COMPANY_NUMBER = "02892242"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(
    r"PROPERTY\s+AUCTION\s*[–-]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(20\d{2})",
    re.I,
)
LOT_RE = re.compile(r"^Lot\s+(\d+[A-Za-z]?)\s*[–-]\s*(.*)$", re.I)
GUIDE_RE = re.compile(
    r"^Guide\s+Price\s+£\s*([\d,]+)(?:\s*-\s*£\s*([\d,]+))?\s*[–-]\s*(.+)$",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+)")
NEXT_TARGET = (
    "Recover Durrants' currently unlinked 2021-2025 property-auction events listed on the "
    "official calendar by inventorying retained WordPress catalogue/result assets for those "
    "exact dates. Batch the surviving PDFs through this reusable runner, preserve each source "
    "object, and reconcile branches as one Durrants operator. Keep national completeness false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized_address(value):
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


def discover_result_pdfs(html, archive_url=ARCHIVE):
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(archive_url, anchor["href"])
        parsed = urlparse(url)
        label = clean(anchor.get_text(" ", strip=True)) or ""
        if parsed.netloc.casefold() not in {"durrants.com", "www.durrants.com"}:
            continue
        if not parsed.path.casefold().endswith(".pdf"):
            continue
        if "result" not in f"{label} {parsed.path}".casefold():
            continue
        found.add(url)
    if not found:
        raise ValueError("official calendar exposes no first-party result PDFs")
    return sorted(found)


def parse_date(text):
    match = DATE_RE.search(clean(text) or "")
    if not match:
        raise ValueError("result sheet has no exact property-auction date")
    day, month, year = match.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()


def outcome_values(value):
    text = clean(value) or ""
    lower = text.casefold()
    money = MONEY_RE.search(text)
    amount = int(money.group(1).replace(",", "")) if money else None
    if "withdrawn" in lower:
        return "withdrawn", None
    if "unsold" in lower:
        return "unsold", None
    if "sold" in lower and "prior" in lower:
        return "sold_prior", amount
    if "sold" in lower and "after" in lower:
        return "sold_after", amount
    if "sold" in lower:
        return "sold", amount
    if "available" in lower:
        return "available", None
    return "unknown", None


def parse_result_text(text, source_url, evidence):
    auction_date = parse_date(text)
    lines = [clean(line) for line in text.replace("\u2014", "–").splitlines()]
    lines = [line for line in lines if line]
    parsed = []
    current = None
    for line in lines:
        lot_match = LOT_RE.match(line)
        if lot_match:
            if current is not None:
                raise ValueError(f"lot {current['lot_number']} has no guide/outcome row")
            lot_number, address = lot_match.groups()
            address = re.sub(rf"^Lot\s+{re.escape(lot_number)}\s*[–-]\s*", "", address, flags=re.I)
            current = {"lot_number": lot_number.upper(), "address_parts": [address]}
            continue
        if current is None:
            continue
        guide_match = GUIDE_RE.match(line)
        if guide_match:
            guide, guide_high, outcome = guide_match.groups()
            address = clean(" ".join(current["address_parts"]))
            if not address:
                raise ValueError(f"lot {current['lot_number']} has no address")
            status, sale_price = outcome_values(outcome)
            parsed.append(
                {
                    "lot_number": current["lot_number"],
                    "address": address,
                    "guide_price": int(guide.replace(",", "")),
                    "guide_price_high": int(guide_high.replace(",", "")) if guide_high else None,
                    "status": status,
                    "sale_price": sale_price,
                    "source_guide_text": line.split("–", 1)[0] if "–" in line else line,
                    "source_outcome_text": outcome,
                }
            )
            current = None
        elif not re.match(r"^(?:WE ARE|NEXT COLLECTIVE|PLEASE CONTACT|BECCLES|DISS|HARLESTON|SOUTHWOLD|HALESWORTH|MAYFAIR|AUCTION ROOMS|Registered Office|WWW\.)", line, re.I):
            current["address_parts"].append(line)
    if current is not None:
        raise ValueError(f"lot {current['lot_number']} has no guide/outcome row")
    if not parsed:
        raise ValueError("result sheet contains no numbered property rows")

    event_key = auction_date
    auction_id = f"{SLUG}:{event_key}"
    rows = []
    for position, item in enumerate(parsed, 1):
        source_id = hashlib.sha256(
            f"{auction_date}|{item['lot_number']}|{normalized_address(item['address'])}".encode()
        ).hexdigest()[:24]
        row = corpus.base_row(SOURCE, auction_id, auction_date, item["lot_number"], source_id, source_url)
        postcode = corpus.PC.search(item["address"])
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|lot:{item['lot_number']}",
            address=item["address"],
            postcode=postcode.group().upper() if postcode else None,
            locality=item["address"],
            property_type=None,
            sector=corpus.sector(item["address"]),
            status=item["status"],
            guide_price=item["guide_price"],
            guide_price_high=item["guide_price_high"],
            sale_price=item["sale_price"],
            annual_rent=None,
            property_id=None,
            identity_method="first_party_exact_event_date_lot_number_and_address",
            record_quality="address_record",
            source_position=position,
            source_guide_text=item["source_guide_text"],
            source_outcome_text=item["source_outcome_text"],
            source_event_url=source_url,
            source_property_url=None,
            auction_date_precision="day",
            auction_date_basis="exact date printed on first-party result sheet",
            source_platform="Durrants first-party property auction calendar and result PDF",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name=SOURCE,
            source_evidence=evidence,
        )
        rows.append(row)
    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": auction_id,
        "auction_date": auction_date,
        "auction_date_precision": "day",
        "source_url": source_url,
        "lots_captured": len(rows),
        "catalogue_complete": True,
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "published_lot_denominator": len(rows),
        "completion_scope": "all numbered rows on retained first-party result sheet",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def parse_result_pdf(raw, source_url, evidence):
    if not raw.startswith(b"%PDF-"):
        raise ValueError("result link did not return a PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)
    return parse_result_text(text, source_url, evidence)


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append(
                    {"appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")}
                )
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
    payload["city_rural_catalogue_followup"] = {
        "checked_at": summary["checked_at"],
        "outcome": "zero_new_appearances",
        "route": "indexed March 2023 first-party catalogue PDF",
        "evidence": "all eight catalogue lots already banked from the exact-dated event page; direct catalogue host timed out",
        "revisit_only_when": "a different retained catalogue or accessible recovery route is identified",
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    archive_url, archive_raw = get(ARCHIVE)
    archive_sha, retrieved_at = corpus.digest(archive_raw), corpus.now()
    archive_snapshot = corpus.DATA / "sources" / SLUG / f"auction-calendar-{archive_sha[:16]}.html.gz"
    if not archive_snapshot.exists():
        corpus.atomic(archive_snapshot, gzip.compress(archive_raw, mtime=0))
    archive_evidence = {
        "source_url": archive_url,
        "retrieved_at": retrieved_at,
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party property-auction calendar with retained result-sheet links",
    }
    pdf_urls = discover_result_pdfs(archive_raw.decode("utf-8", "replace"), archive_url)
    states, run_rows, failures = {}, [], []
    for position, url in enumerate(pdf_urls, 1):
        try:
            resolved, raw = get(url)
            sha, captured_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources" / SLUG / f"result-{sha[:20]}.pdf.gz"
            if not snapshot.exists():
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": resolved,
                "retrieved_at": captured_at,
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "retained first-party exact-dated property-auction result PDF",
            }
            state, rows = parse_result_pdf(raw, resolved, evidence)
            states[state["auction_date"]] = state
            corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)
            run_rows.extend(rows)
            print("DURRANTS", position, "/", len(pdf_urls), "sheets", len(run_rows), "lots", flush=True)
        except Exception as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    overlaps, admissible = [], []
    global_exact = global_exact_appearances()
    for row in run_rows:
        matches = global_exact.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlaps.append({"auction_date": row["auction_date"], "lot_number": row["lot_number"], "address": row["address"], "existing": matches})
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
        "operator": {"canonical_name": SOURCE, "company_name": OPERATOR, "company_number": COMPANY_NUMBER, "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "result_sheets_discovered": len(pdf_urls),
        "result_sheets_captured": len(states),
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
    corpus.save_json(corpus.DATA / "durrants_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(pdf_urls):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    harvest()
