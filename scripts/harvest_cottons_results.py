"""Bank Cottons' first-party historical property-auction result sheets.

The public archive links result PDFs back to 2001.  Each PDF is a finite result
table with an exact auction date, lot number, address and outcome.  Collection
is deliberately bounded and resumable; complete saved sheets are never fetched
again.  Catalogue PDFs can enrich these appearances later, but are not needed
to establish the result-sheet rows themselves.
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
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.cottons.co.uk"
ARCHIVE = BASE + "/auction-archive/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s*[-/. ]*\s*"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s*[-/. ]*\s*(\d{2}|20\d{2})\b",
    re.I,
)
# Tesseract preserves the source table's vertical rules inconsistently. The
# first row can also be read as a capital I and printed lot numbers may retain
# a trailing full stop. Accept those layout artefacts without relaxing the
# requirement for a numbered row at the beginning of the line.
ROW_RE = re.compile(
    r"^(\d+[A-Za-z]?|I|LI|L1|I1|AQ)[.)}\]]?(?:\s*[_|{}]+\s*|\s+)(.+)$",
    re.I,
)
OCR_VERSION = 3
OCR_DPI = 300
MONEY_RE = re.compile(r"£\s*([\d][\d,.]*)", re.I)
RESULT_SUFFIX_RE = re.compile(
    r"(?:"
    r"SOLD\s+(?:PRIOR|BEFORE|AFTER|POST)|"
    r"SOLD(?:\s+AT)?\s+£\s*[\d,.]+|"
    r"SALE\s+AGREED\s+PRIOR\s+TO\s+AUCTION|"
    r"NOT\s+(?:OFFERED|AVAILABLE)|UNDER\s+OFFER|"
    r"WITHDRAWN(?:\s+AFTER)?|POSTPONED|UNSOLD|SOLD|"
    r"AVAILABLE(?:\s*@|\s+AT)?\s*£?\s*[\d,.]+(?:\s+PLUS\s+VAT)?|"
    r"£\s*[\d,.]+\s*(?:AVAILABLE)?"
    r")\s*$",
    re.I,
)
FOOTER_RE = re.compile(
    r"^(?:entries|our next auction|next auction|auctioneers?|cottons|contact\b|telephone|tel\b|"
    r"important notice|please note|www\.)",
    re.I,
)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def parse_date(value: str) -> str:
    match = DATE_RE.search(value or "")
    if not match:
        raise ValueError(f"missing auction date in {value!r}")
    day, month, year = match.groups()
    month_key = month.casefold()[:3]
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    full_year = int(year) if len(year) == 4 else 2000 + int(year)
    return date(full_year, months[month_key], int(day)).isoformat()


def stable_auction_id(auction_date: str, result_url: str) -> str:
    digest = hashlib.sha256(result_url.encode()).hexdigest()[:12]
    return f"cottons:{auction_date}:{digest}"


def discover_result_sheets(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for anchor in soup.find_all("a", href=True):
        label = clean(anchor.get_text(" ", strip=True)) or ""
        href = urljoin(ARCHIVE, anchor["href"])
        if not (href.lower().split("?", 1)[0].endswith(".pdf") and
                re.search(r"result", f"{label} {href}", re.I)):
            continue
        container = anchor.find_parent("tr") or anchor.parent
        context = clean(container.get_text(" ", strip=True) if container else label) or ""
        auction_date = parse_date(context)
        auction_id = stable_auction_id(auction_date, href)
        found[auction_id] = {
            "auction_id": auction_id,
            "auction_date": auction_date,
            "result_url": href,
            "archive_text": context,
        }
    if not found:
        raise ValueError("archive contains no dated result PDF links")
    return sorted(found.values(), key=lambda item: (item["auction_date"], item["result_url"]), reverse=True)


def result_semantics(value: str) -> tuple[str, int | None, int | None]:
    text = (clean(value) or "").upper()
    money_match = MONEY_RE.search(text)
    amount = None
    if money_match:
        token = money_match.group(1)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
            token = token.replace(".", "")
        else:
            token = token.replace(",", "")
        amount = int(round(float(token)))
    if "NOT OFFERED" in text:
        return "not_offered", None, None
    if "NOT AVAILABLE" in text:
        return "not_available", None, None
    if "UNDER OFFER" in text:
        return "under_offer", None, None
    if "SALE AGREED PRIOR TO AUCTION" in text:
        return "sold_prior", None, None
    if "WITHDRAWN" in text:
        return "withdrawn", None, None
    if "POSTPONED" in text:
        return "postponed", None, None
    if "UNSOLD" in text:
        return "unsold", None, None
    if "AVAILABLE" in text:
        if amount is None:
            available_match = re.search(r"AVAILABLE(?:\s*@|\s+AT)?\s*£?\s*([\d][\d,.]*)", text)
            if available_match:
                token = available_match.group(1)
                if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
                    token = token.replace(".", "")
                else:
                    token = token.replace(",", "")
                amount = int(round(float(token)))
        return "available", None, amount
    if re.search(r"SOLD\s+(?:PRIOR|BEFORE)", text):
        return "sold_prior", amount, None
    if re.search(r"SOLD\s+(?:AFTER|POST)", text):
        return "sold_after", amount, None
    if text.startswith("SOLD") or amount is not None:
        return "sold", amount, None
    return "unknown", None, None


def split_result_row(value: str) -> tuple[str | None, str]:
    match = RESULT_SUFFIX_RE.search(value or "")
    if not match:
        address = clean(value)
        if not address:
            raise ValueError("result row has no address")
        return address, ""
    address = clean(value[:match.start()])
    # A small number of complete result tables publish a lot and outcome while
    # leaving its address cell blank. Preserve that evidenced appearance as a
    # partial lot instead of discarding the row or inventing an address.
    return address, clean(match.group()) or ""


def parse_result_text(text: str, expected: dict, evidence: dict) -> tuple[dict, list[dict]]:
    try:
        heading_date = parse_date(text[:1600])
    except ValueError:
        heading_date = None
    if heading_date and heading_date != expected["auction_date"]:
        raise ValueError(
            f"result PDF date mismatch: expected {expected['auction_date']}, saw {heading_date}"
        )
    url_date = None
    if not heading_date:
        try:
            url_date = parse_date(unquote(expected["result_url"]).replace("-", " "))
        except ValueError:
            source_url = unquote(expected["result_url"])
            numeric = re.search(r"(?:^|\D)(\d{1,2})[-_](\d{1,2})[-_](\d{2}|20\d{2})(?:\D|$)",
                                source_url)
            if numeric:
                day, month, year = map(int, numeric.groups())
                candidate = date(year if year >= 2000 else 2000 + year, month, day).isoformat()
                if candidate == expected["auction_date"]:
                    url_date = candidate
            if url_date is None:
                for compact in re.finditer(r"(?<!\d)(\d{2})(\d{2})(20\d{2}|\d{2})(?!\d)",
                                           source_url):
                    day, month, year = map(int, compact.groups())
                    candidate = date(year if year >= 2000 else 2000 + year, month, day).isoformat()
                    if candidate == expected["auction_date"]:
                        url_date = candidate
                        break
            filename = source_url.rsplit("/", 1)[-1]
            if url_date is None:
                named_compact = re.search(
                    r"(?<!\d)(\d{1,2})"
                    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                    r"June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|"
                    r"Nov(?:ember)?|Dec(?:ember)?)"
                    r"(20\d{2}|\d{2})",
                    filename,
                    re.I,
                )
                if named_compact:
                    candidate = parse_date(" ".join(named_compact.groups()))
                    if candidate == expected["auction_date"]:
                        url_date = candidate
            # A small number of retained filenames publish only the day and
            # month. Use that solely to corroborate the exact dated archive
            # row; never infer a year from the upload directory.
            if url_date is None:
                filename = filename.replace("-", " ").replace("_", " ")
                day_month = re.search(
                    r"\b\d{1,2}\s*(?:st|nd|rd|th)?\s*"
                    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                    r"June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|"
                    r"Nov(?:ember)?|Dec(?:ember)?)",
                    filename,
                    re.I,
                )
                if day_month:
                    candidate = parse_date(
                        f"{day_month.group()} {expected['auction_date'][:4]}"
                    )
                    if candidate == expected["auction_date"]:
                        url_date = candidate
        if url_date != expected["auction_date"]:
            raise ValueError("result PDF has no date corroborating the archive row")
    date_basis = (
        "exact date printed on archive row and corroborated by result PDF heading"
        if heading_date else
        "exact date printed on archive row and corroborated by result PDF filename"
    )

    # Preserve address punctuation at line wraps (notably a trailing comma)
    # while normalising extraction whitespace.
    lines = [re.sub(r"\s+", " ", line).strip()
             for line in text.replace("\u00a0", " ").splitlines()]
    lines = [line for line in lines if line]
    header = next((i for i, line in enumerate(lines)
                   if re.search(r"\bLot\b", line, re.I)
                   and re.search(r"\bAddress\b", line, re.I)
                   and re.search(r"\bResult\b", line, re.I)), None)
    if header is None:
        raise ValueError("result table header is absent")

    raw_rows: list[tuple[str, str]] = []
    current_lot = None
    current_parts: list[str] = []
    for line in lines[header + 1:]:
        if FOOTER_RE.search(line):
            break
        # Multi-page result sheets repeat their title and table heading. They
        # are page furniture, not continuation text for the preceding address.
        if (re.search(r"\bLot\b", line, re.I)
                and re.search(r"\bAddress\b", line, re.I)
                and re.search(r"\bResult\b", line, re.I)):
            continue
        if re.fullmatch(r"(?:Auction\s+)?\d{1,2}\s*(?:st|nd|rd|th)?\s+"
                        r"[A-Za-z]+\s+20\d{2}\s+Results", line, re.I):
            continue
        match = ROW_RE.match(line)
        # The first printed 1 is occasionally recognised as a capital I. It
        # is safe to repair only before any numbered row has been admitted;
        # later prose beginning with I remains continuation text.
        if (match and match.group(1).casefold() == "i"
                and (current_lot is not None or raw_rows)):
            match = None
        if match:
            if current_lot is not None:
                raw_rows.append((current_lot, " ".join(current_parts)))
            current_lot, first = match.groups()
            # At 300 dpi Tesseract consistently renders two particular digit
            # shapes as letters in these tables: 11 as ``LI``/``L1``/``I1``
            # and 40 as ``AQ``. Neither token is a valid printed Cottons lot
            # label, so repair only these exact start-of-row artefacts. The
            # later duplicate and sequence checks still reject ambiguity.
            current_lot = {
                "i": "1",
                "li": "11",
                "l1": "11",
                "i1": "11",
                "aq": "40",
            }.get(current_lot.casefold(), current_lot)
            current_parts = [first]
        elif current_lot is not None:
            current_parts.append(line)
    if current_lot is not None:
        raw_rows.append((current_lot, " ".join(current_parts)))
    if not raw_rows:
        raise ValueError("result table contains no lot rows")

    # A few 2014/15 image scans render the top of a leading ``5`` so faintly
    # that Tesseract reads late-sequence lots 51-59 as 31-39. Repair only when
    # all of the surrounding evidence is deterministic: this is an OCR parse,
    # the observed 3x label duplicates an earlier row, the preceding row is
    # the immediately prior 5x lot, and the expected 5x label is otherwise
    # absent. Genuine duplicate labels and every other discontinuity remain
    # hard failures below.
    if "OCR" in str(evidence.get("basis") or "").upper():
        original_labels = [lot.upper() for lot, _ in raw_rows]
        counts = Counter(original_labels)
        repaired_rows = []
        for lot, body in raw_rows:
            previous = repaired_rows[-1][0] if repaired_rows else None
            if (re.fullmatch(r"3\d", lot)
                    and counts[lot.upper()] > 1
                    and previous and previous.isdigit()):
                expected_number = int(previous) + 1
                expected_label = str(expected_number)
                if (51 <= expected_number <= 59
                        and int(lot) == expected_number - 20
                        and expected_label not in original_labels):
                    lot = expected_label
            repaired_rows.append((lot, body))
        raw_rows = repaired_rows

    labels = [lot.upper() for lot, _ in raw_rows]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate lot labels in result PDF")
    base_numbers = {int(re.match(r"\d+", label).group()) for label in labels}
    max_lot = max(base_numbers)
    missing = sorted(set(range(1, max_lot + 1)) - base_numbers)

    rows = []
    for position, (lot_number, body) in enumerate(raw_rows, 1):
        address, result_text = split_result_row(body)
        status, sale_price, available_price = result_semantics(result_text)
        postcode_match = corpus.PC.search(address or "")
        source_auction_id = expected["auction_id"]
        row = corpus.base_row(
            "Cottons", source_auction_id, expected["auction_date"],
            lot_number, lot_number.upper(), expected["result_url"],
        )
        row.update(
            appearance_id=f"Cottons|{source_auction_id}|lot:{lot_number.upper()}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address or ""),
            sale_price=sale_price,
            available_price=available_price,
            status=status,
            property_id=None,
            identity_method="exact_auction_date_and_published_lot_number",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis=date_basis,
            source_position=position,
            source_result_text=result_text or None,
            source_evidence=evidence,
        )
        rows.append(row)

    complete = not missing
    state = {
        "auctioneer": "Cottons",
        "source_auction_id": expected["auction_id"],
        "auction_date": expected["auction_date"],
        "catalogue_complete": complete,
        "source_rows_complete": complete,
        "visible_result_rows": len(rows),
        "lots_captured": len(rows),
        "published_lots_offered": max_lot,
        "lettered_additional_rows": len(rows) - len(base_numbers),
        "missing_base_lot_numbers": missing,
        "pagination_reconciled": True,
        "denominator_reconciled": complete,
        "denominator_basis": "continuous published base lot sequence in the complete first-party result table",
        "completion_scope": "every row in the retained first-party result PDF; later catalogue enrichment may add property detail",
        "source_url": expected["result_url"],
        "errors": [] if complete else [{"error": "non-contiguous result lot sequence", "missing": missing}],
        "checked_at": corpus.now(),
    }
    return state, rows


def extract_pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < 100:
        raise ValueError("result PDF contains no usable text")
    return text


def extract_pdf_text_ocr(raw: bytes) -> str:
    """OCR a retained image-only result PDF using free runner binaries."""
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        raise RuntimeError("OCR requires pdftoppm and tesseract")
    with tempfile.TemporaryDirectory(prefix="cottons-ocr-") as directory:
        work = Path(directory)
        source = work / "result.pdf"
        source.write_bytes(raw)
        prefix = work / "page"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(OCR_DPI), str(source), str(prefix)],
            check=True,
            capture_output=True,
            timeout=180,
        )
        pages = []
        for image in sorted(work.glob("page-*.png")):
            completed = subprocess.run(
                # PSM 4 preserves the result table's row ordering. PSM 6
                # treated the whole page as one block and dropped most rows
                # from retained 2017 scans.
                ["tesseract", str(image), "stdout", "--psm", "4"],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            pages.append(completed.stdout)
        text = "\n".join(pages)
        if len(text.strip()) < 100:
            raise ValueError("OCR produced no usable result text")
        return text


def get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 100:
        raise ValueError("source response is unexpectedly short")
    return response


def harvest(limit: int = 16, ocr_limit: int = 4) -> None:
    archive_response = get(ARCHIVE)
    archive_raw = archive_response.content
    archive_html = archive_raw.decode("utf-8", "replace")
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/cottons" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_response.url,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party auction archive",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    discovered = discover_result_sheets(archive_html)

    appearances_path = corpus.DATA / "appearances/cottons/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearances_path)) if appearances_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    rows_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        rows_by_auction.setdefault(row["source_auction_id"], []).append(row)

    states, pending, ocr_pending, failures, blockers, reused = {}, [], [], [], [], 0
    for item in discovered:
        state_name = item["auction_id"].replace(":", "-") + ".json"
        state_path = corpus.DATA / "auctions/cottons" / state_name
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            state = None
        saved_rows = rows_by_auction.get(item["auction_id"], [])
        if state and state.get("source_blocked"):
            states[item["auction_id"]] = state
            reason = str(state.get("source_blocker", {}).get("reason") or "")
            snapshots = sorted((corpus.DATA / "sources/cottons/results").glob(
                f"{item['auction_date']}-*.pdf.gz"
            ))
            if ("image-only" in reason
                    and state.get("ocr_version", 0) < OCR_VERSION
                    and snapshots):
                ocr_pending.append((item, state, snapshots[-1]))
            else:
                blockers.append(state["source_blocker"])
            continue
        if (state and state.get("catalogue_complete") and saved_rows and
                state.get("lots_captured") == len(saved_rows)):
            states[item["auction_id"]] = state
            reused += 1
        else:
            pending.append(item)

    ocr_attempted = 0
    ocr_recovered = 0
    for item, blocked_state, snapshot in ocr_pending[:max(0, ocr_limit)]:
        state_name = item["auction_id"].replace(":", "-") + ".json"
        ocr_attempted += 1
        try:
            raw = gzip.decompress(snapshot.read_bytes())
            evidence = {
                "source_url": item["result_url"],
                "retrieved_at": corpus.now(),
                "sha256": corpus.digest(raw),
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": "OCR of retained first-party complete auction result PDF",
                "ocr_engine": f"Tesseract PSM 4 with Poppler {OCR_DPI}dpi lossless rasterisation",
                "ocr_version": OCR_VERSION,
            }
            state, rows = parse_result_text(extract_pdf_text_ocr(raw), item, evidence)
            state["ocr_recovered"] = True
            state["ocr_version"] = OCR_VERSION
            state["source_evidence"] = evidence
            corpus.save_json(corpus.DATA / "auctions/cottons" / state_name, state)
            states[item["auction_id"]] = state
            for row in rows:
                merged[row["appearance_id"]] = row
            ocr_recovered += len(rows)
            print("COTTONS OCR", item["auction_date"], len(rows), "lots",
                  state["catalogue_complete"], flush=True)
        except Exception as exc:
            blocker = {
                **blocked_state["source_blocker"],
                "reason": "retained image-only result PDF failed bounded OCR recovery",
                "ocr_error": f"{type(exc).__name__}: {exc}"[:500],
            }
            blocked_state.update(
                source_blocker=blocker,
                ocr_attempted=True,
                ocr_version=OCR_VERSION,
                ocr_checked_at=corpus.now(),
            )
            corpus.save_json(corpus.DATA / "auctions/cottons" / state_name, blocked_state)
            states[item["auction_id"]] = blocked_state
            blockers.append(blocker)
    for _, state, _ in ocr_pending[max(0, ocr_limit):]:
        blockers.append(state["source_blocker"])

    for item in pending[:max(0, limit)]:
        state_name = item["auction_id"].replace(":", "-") + ".json"
        try:
            response = get(item["result_url"])
            raw = response.content
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/cottons/results" / (
                f"{item['auction_date']}-{sha[:16]}.pdf.gz"
            )
            corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": response.url,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": "first-party complete auction result PDF",
            }
            state, rows = parse_result_text(extract_pdf_text(raw), item, evidence)
            corpus.save_json(corpus.DATA / "auctions/cottons" / state_name, state)
            states[item["auction_id"]] = state
            for row in rows:
                merged[row["appearance_id"]] = row
            print("COTTONS", item["auction_date"], len(rows), "lots", state["catalogue_complete"], flush=True)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            failure = {
                "auction_id": item["auction_id"],
                "auction_date": item["auction_date"],
                "url": item["result_url"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
            if status_code == 404:
                blocker = {**failure, "status_code": 404,
                           "reason": "first-party archive result link returns HTTP 404"}
                state = {
                    "auctioneer": "Cottons", "source_auction_id": item["auction_id"],
                    "auction_date": item["auction_date"], "catalogue_complete": False,
                    "source_rows_complete": False, "lots_captured": 0,
                    "source_url": item["result_url"], "source_blocked": True,
                    "source_blocker": blocker, "errors": [], "checked_at": corpus.now(),
                }
                corpus.save_json(corpus.DATA / "auctions/cottons" / state_name, state)
                states[item["auction_id"]] = state
                blockers.append(blocker)
            else:
                failures.append(failure)
        except Exception as exc:
            failure = {
                "auction_id": item["auction_id"], "auction_date": item["auction_date"],
                "url": item["result_url"], "error": f"{type(exc).__name__}: {exc}"[:500],
            }
            if isinstance(exc, ValueError) and str(exc) == "result PDF contains no usable text":
                blocker = {
                    **failure,
                    "reason": "retained first-party result PDF is image-only and requires OCR enrichment",
                }
                state = {
                    "auctioneer": "Cottons", "source_auction_id": item["auction_id"],
                    "auction_date": item["auction_date"], "catalogue_complete": False,
                    "source_rows_complete": False, "lots_captured": 0,
                    "source_url": item["result_url"], "source_blocked": True,
                    "source_blocker": blocker, "errors": [], "checked_at": corpus.now(),
                }
                corpus.save_json(corpus.DATA / "auctions/cottons" / state_name, state)
                states[item["auction_id"]] = state
                blockers.append(blocker)
            else:
                failures.append(failure)

    total = corpus.write_rows("cottons/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(),
        "source_url": ARCHIVE,
        "result_sheets_discovered": len(discovered),
        "result_sheets_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "result_sheets_blocked": len(blockers),
        "result_sheets_reused": reused,
        "result_sheets_attempted_this_run": min(len(pending), max(0, limit)),
        "result_sheets_pending": max(0, len(pending) - max(0, limit)),
        "ocr_sheets_attempted_this_run": ocr_attempted,
        "ocr_appearances_recovered_this_run": ocr_recovered,
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence,
        "source_blockers": blockers,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "cottons_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(
        int(sys.argv[1]) if len(sys.argv) > 1 else 16,
        int(sys.argv[2]) if len(sys.argv) > 2 else 4,
    )
