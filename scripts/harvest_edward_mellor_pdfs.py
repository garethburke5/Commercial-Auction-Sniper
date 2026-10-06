"""Bank Edward Mellor's retained first-party legacy auction result PDFs.

The archive still exposes complete result sheets from 2010 onward.  Each sheet
is finite and publishes an exact auction date, numbered rows, address text and
an outcome.  Collection is bounded, oldest-first and resumable; a reconciled
saved sheet is never fetched again.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from io import BytesIO
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://edwardmellor.co.uk"
ARCHIVE = BASE + "/auctions/catalogue-and-results-archive/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
ROW_RE = re.compile(r"^LOT\s+(\d+[A-Za-z]?)\s+(.+)$", re.I)
DATE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:ST|ND|RD|TH)?\s+"
    r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
    r"\s+(20\d{2})\b",
    re.I,
)
RESULT_RE = re.compile(
    r"\b(?:SOLD(?:\s+(?:AT\s+£[\d,]+|PRIOR|POST|AFTER))?|"
    r"AVAILABLE(?:\s+(?:AT\s+£[\d,]+|IN\s+[A-Z]+))?|"
    r"MAKE\s+(?:US\s+AN\s+OFFER|A\s+BID)!*|"
    r"NOT\s+OFFERED|UNDER\s+OFFER|WTHDRAWN|WITHDRAWN|POSTPONED|UNSOLD|"
    r"REFER\s+TO\s+AUCTIONEER)\b.*$",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+)")
MONTHS = {name.upper(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"), 1
)}


class SourceObjectUnavailable(ValueError):
    """The first-party object exists as a link but is not a usable file."""


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def discover_result_pdfs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for anchor in soup.find_all("a", href=True):
        label = clean(anchor.get_text(" ", strip=True)) or ""
        url = urljoin(ARCHIVE, anchor["href"])
        if not url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        if "result" not in f"{label} {url}".casefold():
            continue
        match = re.search(r"/(20\d{2})\d{4}[_-]", url)
        year = int(match.group(1)) if match else 9999
        found[url] = {"url": url, "label": label, "year": year}
    if not found:
        raise ValueError("archive contains no legacy result PDF links")
    return sorted(found.values(), key=lambda item: (item["year"], item["url"]))


def parse_auction_date(text: str) -> str:
    heading = clean(text[:2000]) or ""
    match = DATE_RE.search(heading)
    if not match:
        raise ValueError("result sheet has no exact auction date")
    day, month, year = match.groups()
    return date(int(year), MONTHS[month.upper()], int(day)).isoformat()


def result_semantics(value: str) -> tuple[str, int | None, int | None]:
    text = (clean(value) or "").upper()
    money = MONEY_RE.search(text)
    amount = int(money.group(1).replace(",", "")) if money else None
    if "NOT OFFERED" in text:
        return "not_offered", None, None
    if "UNDER OFFER" in text:
        return "under_offer", None, None
    if "WITHDRAWN" in text or "WTHDRAWN" in text:
        return "withdrawn", None, None
    if "POSTPONED" in text:
        return "postponed", None, None
    if "UNSOLD" in text:
        return "unsold", None, None
    if "AVAILABLE" in text:
        return "available", None, amount
    if "MAKE US AN OFFER" in text or "MAKE A BID" in text:
        return "available", None, None
    if "SOLD PRIOR" in text:
        return "sold_prior", amount, None
    if "SOLD POST" in text or "SOLD AFTER" in text:
        return "sold_after", amount, None
    if "SOLD" in text:
        return "sold", amount, None
    return "unknown", None, None


def parse_result_text(text: str, source_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    auction_date = parse_auction_date(text)
    raw_rows = []
    current_lot = None
    current_parts = []
    for original in text.replace("\u00a0", " ").splitlines():
        line = clean(original)
        if not line:
            continue
        match = ROW_RE.match(line)
        if match:
            if current_lot is not None:
                raw_rows.append((current_lot, " ".join(current_parts)))
            current_lot, body = match.groups()
            current_parts = [body]
        elif current_lot is not None and not re.match(r"^(?:RESULTS|TEL:|WWW\.)", line, re.I):
            current_parts.append(line)
    if current_lot is not None:
        raw_rows.append((current_lot, " ".join(current_parts)))
    if not raw_rows:
        raise ValueError("result sheet contains no numbered lot rows")

    source_row_count = len(raw_rows)
    deduplicated_rows = []
    first_body_by_label = {}
    duplicate_source_rows = []
    for lot, body in raw_rows:
        label = lot.upper()
        if label in first_body_by_label:
            current_body = clean(body) or ""
            first_body = clean(first_body_by_label[label]) or ""
            if not (
                current_body == first_body
                or current_body.startswith(first_body)
                or first_body.startswith(current_body)
            ):
                raise ValueError(f"conflicting duplicate lot label {label} in result sheet")
            duplicate_source_rows.append(label)
            continue
        first_body_by_label[label] = body
        deduplicated_rows.append((lot, body))
    raw_rows = deduplicated_rows
    labels = [lot.upper() for lot, _ in raw_rows]
    base_numbers = {int(re.match(r"\d+", label).group()) for label in labels}
    max_lot = max(base_numbers)
    missing = sorted(set(range(1, max_lot + 1)) - base_numbers)
    source_key = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    source_auction_id = f"edward-mellor-pdf:{auction_date}:{source_key}"
    rows = []
    for position, (lot_number, body) in enumerate(raw_rows, 1):
        result_match = RESULT_RE.search(body)
        address = clean(body[:result_match.start()] if result_match else body)
        result_text = clean(result_match.group()) if result_match else None
        status, sale_price, available_price = result_semantics(result_text or "")
        postcode_match = corpus.PC.search(address or "")
        row = corpus.base_row(
            "Edward Mellor", source_auction_id, auction_date,
            lot_number.upper(), lot_number.upper(), source_url,
        )
        row.update(
            appearance_id=f"Edward Mellor|{source_auction_id}|lot:{lot_number.upper()}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address or ""),
            sale_price=sale_price,
            available_price=available_price,
            status=status,
            property_id=None,
            identity_method="exact_auction_date_result_sheet_and_published_lot_number",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis="exact date printed on first-party complete result sheet",
            source_position=position,
            source_result_text=result_text,
            source_evidence=evidence,
        )
        rows.append(row)

    complete = not missing and not duplicate_source_rows
    errors = []
    if missing:
        errors.append({"error": "non-contiguous result lot sequence", "missing": missing})
    if duplicate_source_rows:
        errors.append({
            "error": "identical duplicate source rows were collapsed conservatively",
            "lot_numbers": duplicate_source_rows,
        })
    state = {
        "auctioneer": "Edward Mellor",
        "source_auction_id": source_auction_id,
        "auction_date": auction_date,
        "catalogue_complete": complete,
        "source_rows_complete": complete,
        "visible_result_rows": source_row_count,
        "lots_captured": len(rows),
        "published_lots_offered": max_lot,
        "lettered_additional_rows": len(rows) - len(base_numbers),
        "identical_duplicate_source_rows": len(duplicate_source_rows),
        "duplicate_source_lot_numbers": duplicate_source_rows,
        "missing_base_lot_numbers": missing,
        "pagination_reconciled": True,
        "denominator_reconciled": complete,
        "denominator_basis": "continuous published base lot sequence in complete first-party result sheet",
        "completion_scope": "every numbered row in the retained first-party result PDF",
        "source_url": source_url,
        "errors": errors,
        "checked_at": corpus.now(),
    }
    return state, rows


def extract_pdf_text(raw: bytes) -> str:
    if shutil.which("pdftotext"):
        with tempfile.TemporaryDirectory(prefix="edward-mellor-pdf-") as directory:
            source = Path(directory) / "result.pdf"
            output = Path(directory) / "result.txt"
            source.write_bytes(raw)
            subprocess.run(
                ["pdftotext", "-layout", str(source), str(output)],
                check=True, capture_output=True, timeout=90,
            )
            text = output.read_text(errors="replace")
    else:
        # GitHub's base runner does not provide Poppler until the later
        # Cottons OCR step. pypdf is already a project dependency and retains
        # the line boundaries in these text-native result sheets.
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < 100:
        raise ValueError("result PDF contains no usable text")
    return text


def get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 100:
        raise ValueError("source response is unexpectedly short")
    if url.lower().split("?", 1)[0].endswith(".pdf"):
        raw = response.content
        if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
            raise SourceObjectUnavailable(
                f"first-party PDF response is truncated or malformed ({len(raw)} bytes)"
            )
    return response


def terminal_source_failure(exc: Exception) -> bool:
    """Return true only for a definitive missing first-party object.

    A removed PDF must remain visibly incomplete, but it should not consume one
    of the bounded harvest slots on every run while later result sheets remain
    available. Transient transport and parser failures are deliberately not
    classified here.
    """
    return (
        isinstance(exc, SourceObjectUnavailable)
        or (
            isinstance(exc, requests.HTTPError)
            and exc.response is not None
            and exc.response.status_code in {404, 410}
        )
    )


def harvest(limit: int = 8) -> None:
    archive_response = get(ARCHIVE)
    archive_raw = archive_response.content
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/edward-mellor-pdfs" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_response.url,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party catalogue and results archive",
    }
    corpus.save_gzip(archive_snapshot, {
        "evidence": archive_evidence,
        "html": archive_raw.decode("utf-8", "replace"),
    })
    discovered = discover_result_pdfs(archive_raw.decode("utf-8", "replace"))

    summary_path = corpus.DATA / "edward_mellor_pdf_collection.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    completed_urls = set(previous.get("completed_source_urls") or [])
    terminal_failures = {
        failure["url"]: failure
        for failure in previous.get("terminal_source_failures") or []
        if failure.get("url")
    }
    # Migrate a definitive 404/410 recorded by the older summary format.
    for failure in previous.get("failures") or []:
        if failure.get("url") and re.search(r"\b(?:404|410) Client Error\b", failure.get("error", "")):
            terminal_failures[failure["url"]] = failure
    appearances_path = corpus.DATA / "appearances/edward-mellor-pdfs/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearances_path)) if appearances_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    processed_urls = set(previous.get("processed_source_urls") or []) | completed_urls
    # Older summaries recorded only complete URLs. Recover the exact successful
    # fetches from the URL-derived suffix already embedded in every appearance
    # ID, including banked sheets whose published numbering has gaps.
    existing_source_keys = {
        str(row.get("source_auction_id") or "").rsplit(":", 1)[-1]
        for row in existing
    }
    for item in discovered:
        prepared_url = requests.utils.requote_uri(item["url"])
        if hashlib.sha256(prepared_url.encode()).hexdigest()[:12] in existing_source_keys:
            processed_urls.add(item["url"])
    pending = [
        item for item in discovered
        if item["url"] not in processed_urls and item["url"] not in terminal_failures
    ]
    failures = []
    completed_this_run = []
    states = []

    # A failed runner may already have persisted the immutable PDF before its
    # extractor proved unavailable. Reuse those snapshots instead of probing
    # the same source URL again. Result sheets are monthly and the archive URL
    # embeds YYYYMM, while the PDF heading independently supplies the exact day.
    used_snapshots = {
        row.get("source_evidence", {}).get("snapshot_path") for row in existing
    }
    cached_by_month = {}
    results_dir = corpus.DATA / "sources/edward-mellor-pdfs/results"
    for snapshot in sorted(results_dir.glob("*.pdf.gz")) if results_dir.exists() else []:
        relative = str(snapshot.relative_to(corpus.ROOT))
        if relative in used_snapshots:
            continue
        try:
            raw = gzip.decompress(snapshot.read_bytes())
            text = extract_pdf_text(raw)
            cached_by_month[parse_auction_date(text)[:7]] = (snapshot, raw, text)
        except Exception:
            continue

    for item in pending[:max(0, limit)]:
        try:
            url_month_match = re.search(r"/(20\d{2})(\d{2})\d{2}[_-]", item["url"])
            url_month = (f"{url_month_match.group(1)}-{url_month_match.group(2)}"
                         if url_month_match else None)
            cached = cached_by_month.pop(url_month, None)
            if cached:
                snapshot, raw, pdf_text = cached
                resolved_url = item["url"]
                basis = "cached first-party complete auction result PDF from prior failed extractor run"
            else:
                response = get(item["url"])
                raw = response.content
                resolved_url = response.url
                sha = corpus.digest(raw)
                snapshot = results_dir / f"{sha[:16]}.pdf.gz"
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
                pdf_text = extract_pdf_text(raw)
                basis = "first-party complete auction result PDF"
            sha = corpus.digest(raw)
            evidence = {
                "source_url": resolved_url,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": basis,
            }
            state, rows = parse_result_text(pdf_text, resolved_url, evidence)
            state_name = state["source_auction_id"].replace(":", "-") + ".json"
            corpus.save_json(corpus.DATA / "auctions/edward-mellor-pdfs" / state_name, state)
            for row in rows:
                merged[row["appearance_id"]] = row
            states.append(state)
            processed_urls.add(item["url"])
            if state["catalogue_complete"]:
                completed_urls.add(item["url"])
                completed_this_run.append(item["url"])
            print("EDWARD MELLOR PDF", state["auction_date"], len(rows), "lots", state["catalogue_complete"], flush=True)
        except Exception as exc:
            failure = {
                "url": item["url"], "label": item["label"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
            if terminal_source_failure(exc):
                failure["terminal"] = True
                terminal_failures[item["url"]] = failure
            else:
                failures.append(failure)

    total = corpus.write_rows("edward-mellor-pdfs/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(),
        "source_url": ARCHIVE,
        "result_pdfs_discovered": len(discovered),
        "result_pdfs_complete": len(completed_urls),
        "result_pdfs_banked": len(processed_urls),
        "result_pdfs_incomplete_banked": len(processed_urls - completed_urls),
        "result_pdfs_completed_this_run": len(completed_this_run),
        "result_pdfs_pending": max(0, len(discovered) - len(completed_urls)),
        "result_pdfs_unbanked": sum(
            item["url"] not in processed_urls for item in discovered
        ),
        "result_pdfs_usable_pending": sum(
            item["url"] not in processed_urls and item["url"] not in terminal_failures
            for item in discovered
        ),
        "result_pdfs_terminal_source_failures": len(terminal_failures),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "completed_source_urls": sorted(completed_urls),
        "processed_source_urls": sorted(processed_urls),
        "archive_evidence": archive_evidence,
        "terminal_source_failures": sorted(terminal_failures.values(), key=lambda item: item["url"]),
        "failures": failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
