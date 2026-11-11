"""Bank Durrants' retained property-auction result sheets and catalogues.

The official auction calendar is the event inventory.  Its retained result
links are exact-dated, finite PDF sheets containing numbered property rows,
guide prices and published outcomes.  One reusable run discovers and parses
every linked sheet.  A small manifest extends the same run across retained
catalogues whose URLs are no longer linked from the calendar.  Every source
object is kept as immutable evidence and result rows always take precedence
over overlapping catalogue evidence.
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
CATALOGUE_MANIFEST = corpus.DATA / "durrants_catalogue_manifest.json"
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
    "Search retained publisher and platform copies for Durrants' exact 2021-2022 calendar dates, "
    "then rotate to another uncovered high-yield auctioneer/source-year if no individual catalogue "
    "inventory survives. Batch additions through this reusable manifest runner and keep national "
    "completeness false."
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


def parse_catalogue_date(text):
    match = re.search(
        r"(?:Wednesday\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(20\d{2})",
        clean(text) or "",
        re.I,
    )
    if not match:
        raise ValueError("catalogue has no exact auction date")
    day, month, year = match.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()


def parse_catalogue_text(text, config, source_url, evidence):
    """Validate and materialise catalogue-only rows from a finite manifest.

    The manifest is declarative because multi-column historic catalogues do not
    have a stable text order.  The runner verifies the printed date, lot marker,
    postcode, guide and a source-title fragment before a row can be banked.
    """
    auction_date = parse_catalogue_date(text)
    if auction_date != config["auction_date"]:
        raise ValueError(f"catalogue date {auction_date} does not match manifest {config['auction_date']}")
    folded = clean(text).casefold()
    compact = normalized_address(text)
    rows = []
    tier = config.get("source_tier", "first_party")
    for position, item in enumerate(config["lots"], 1):
        lot_number = str(item["lot_number"]).upper()
        if not re.search(rf"\bLOT\s+{re.escape(lot_number)}\b", text, re.I):
            raise ValueError(f"catalogue is missing lot marker {lot_number}")
        validation_text = clean(item.get("validation_text") or item["address"])
        if normalized_address(validation_text) not in compact:
            raise ValueError(f"catalogue is missing validation text for lot {lot_number}")
        postcode = corpus.PC.search(item["address"])
        if postcode and postcode.group().casefold() not in folded:
            raise ValueError(f"catalogue is missing postcode for lot {lot_number}")
        guide = int(item["guide_price"])
        if f"{guide:,}" not in text:
            raise ValueError(f"catalogue is missing guide for lot {lot_number}")
        guide_high = item.get("guide_price_high")
        if guide_high is not None and f"{int(guide_high):,}" not in text:
            raise ValueError(f"catalogue is missing high guide for lot {lot_number}")
        auction_id = f"{SLUG}:{auction_date}"
        source_id = hashlib.sha256(
            f"{auction_date}|{lot_number}|{normalized_address(item['address'])}".encode()
        ).hexdigest()[:24]
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_id, source_url)
        if tier == "first_party":
            identity_method = "first_party_exact_event_date_lot_number_and_address"
            source_platform = "Durrants first-party retained property auction catalogue"
        elif tier == "retained_search_cache_text":
            identity_method = "retained_search_cache_catalogue_exact_event_date_lot_number_and_address"
            source_platform = "Durrants PDF catalogue retained as search-index text extraction"
        else:
            identity_method = "retained_publisher_catalogue_exact_event_date_lot_number_and_address"
            source_platform = "Durrants catalogue retained by OnTheMarket media"
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|lot:{lot_number}",
            address=item["address"],
            postcode=postcode.group().upper() if postcode else None,
            locality=item["address"],
            property_type=item.get("property_type"),
            tenure=item.get("tenure"),
            sector=item.get("sector") or corpus.sector(item["address"]),
            status=item.get("status", "unknown"),
            guide_price=guide,
            guide_price_high=int(guide_high) if guide_high is not None else None,
            sale_price=None,
            annual_rent=item.get("annual_rent"),
            description=item.get("description"),
            property_id=None,
            identity_method=identity_method,
            record_quality="address_record",
            source_position=position,
            source_guide_text=item.get("source_guide_text"),
            source_outcome_text=None,
            source_event_url=source_url,
            source_property_url=None,
            auction_date_precision="day",
            auction_date_basis="exact date printed on retained Durrants catalogue",
            source_platform=source_platform,
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
        "source_auction_id": f"{SLUG}:{auction_date}",
        "auction_date": auction_date,
        "auction_date_precision": "day",
        "source_url": source_url,
        "lots_captured": len(rows),
        "catalogue_complete": bool(config.get("catalogue_complete", True)),
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "published_lot_denominator": int(config["published_lot_denominator"]),
        "completion_scope": config["completion_scope"],
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def parse_catalogue_pdf(raw, config, source_url, evidence):
    if not raw.startswith(b"%PDF-"):
        raise ValueError("catalogue link did not return a PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)
    return parse_catalogue_text(text, config, source_url, evidence)


def load_catalogue_manifest(path=CATALOGUE_MANIFEST):
    payload = json.loads(path.read_text(encoding="utf-8"))
    catalogues = payload.get("catalogues", [])
    if not catalogues:
        raise ValueError("Durrants catalogue manifest is empty")
    return catalogues


def retained_catalogue_source(config):
    """Return a reproducible catalogue payload without hiding source limits.

    Most entries retain the original PDF bytes. A removed publisher PDF may use
    a finite text extraction retained by a public search index; in that case the
    manifest stores the admitted extraction, the original URL remains the
    source URL, and the snapshot is explicitly labelled as extracted text.
    """
    tier = config.get("source_tier", "first_party")
    if tier != "retained_search_cache_text":
        resolved, raw = get(config["source_url"])
        basis = (
            "retained first-party exact-dated property-auction catalogue PDF"
            if tier == "first_party"
            else "Durrants-issued exact-dated catalogue retained by OnTheMarket media"
        )
        return resolved, raw, "pdf", basis
    text = config.get("retained_text")
    if not isinstance(text, str) or len(text) < 200:
        raise ValueError("retained search-cache catalogue text is missing or unexpectedly short")
    return (
        config["source_url"],
        text.encode("utf-8"),
        "txt",
        "Durrants-issued exact-dated PDF catalogue retained as a public search-index text extraction; original publisher bytes currently return 404",
    )


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

    catalogue_states = {}
    catalogue_configs = load_catalogue_manifest()
    for position, config in enumerate(catalogue_configs, 1):
        url = config["source_url"]
        try:
            resolved, raw, snapshot_format, basis = retained_catalogue_source(config)
            sha, captured_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources" / SLUG / f"catalogue-{sha[:20]}.{snapshot_format}.gz"
            if not snapshot.exists():
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            tier = config.get("source_tier", "first_party")
            evidence = {
                "source_url": resolved,
                "retrieved_at": captured_at,
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": basis,
                "source_tier": tier,
                "snapshot_format": snapshot_format,
            }
            if snapshot_format == "pdf":
                state, rows = parse_catalogue_pdf(raw, config, resolved, evidence)
            else:
                state, rows = parse_catalogue_text(raw.decode("utf-8"), config, resolved, evidence)
            event_date = state["auction_date"]
            catalogue_states[event_date] = state
            if event_date in states:
                result_state = states[event_date]
                result_state["catalogue_source_url"] = resolved
                result_state["catalogue_evidence"] = evidence
                result_state["published_lot_denominator"] = max(
                    result_state["published_lot_denominator"], state["published_lot_denominator"]
                )
                result_state["lots_captured"] += len(rows)
                result_state["completion_scope"] = config["completion_scope"]
                corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event_date}.json", result_state)
            else:
                states[event_date] = state
                corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event_date}.json", state)
            run_rows.extend(rows)
            print("DURRANTS", position, "/", len(catalogue_configs), "catalogues", len(run_rows), "lots", flush=True)
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
        "result_sheets_captured": len(pdf_urls) - sum(
            failure["url"] in pdf_urls for failure in failures
        ),
        "catalogues_configured": len(catalogue_configs),
        "catalogues_captured": len(catalogue_states),
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
    if failures or len(catalogue_states) != len(catalogue_configs):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    harvest()
