"""Bank Seel & Co's retained first-party auction catalogue PDFs.

The former Seel Auctions WordPress media library still exposes complete
catalogues from December 2019 to April 2022.  Printed order-of-sale tables, or
the complete contiguous sequence of numbered detail pages where no table is
present, provide finite denominators.  This collector keeps the raw PDF,
rejects any non-contiguous source, and never refetches a reconciled catalogue.
"""
from __future__ import annotations

from collections import Counter
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
BASE = "https://www.seelauctions.co.uk/wp-content/uploads"
CATALOGUES = [
    ("2019-12-10", 28, f"{BASE}/2019/12/Seel-Co-Auction-Catalogue-for-10.12.19.pdf"),
    ("2020-02-11", 30, f"{BASE}/2020/02/February-Auction-Catalogue-Late-Entries.pdf"),
    ("2020-03-31", 27, f"{BASE}/2020/03/March-Auction-Catalogue-web.pdf"),
    ("2020-05-19", 22, f"{BASE}/2020/05/May-Online-Auction-Catalogue-Amended.pdf"),
    ("2020-07-08", 21, f"{BASE}/2020/06/Seel-Co-July-Auction-Catalogue.pdf"),
    ("2020-09-08", 21, f"{BASE}/2020/09/Seel-Co-September-Online-Auction-Catalogue.pdf"),
    ("2020-10-20", 25, f"{BASE}/2020/10/Seel-and-Co-October-Online-Auction-Catalogue.pdf"),
    ("2020-12-08", 34, f"{BASE}/2020/12/Seel-Co-December-Auction-Catalogue.pdf"),
    ("2021-02-16", 24, f"{BASE}/2021/01/auction_catalogue.pdf"),
    ("2021-03-30", 24, f"{BASE}/2021/03/Seel-Co-Auction-Catalogue-March-2021.pdf"),
    ("2021-05-18", 23, f"{BASE}/2021/05/Auction-Catalogue-May-2021.pdf"),
    ("2021-07-06", 29, f"{BASE}/2021/07/Auction-Catalogue-July-2021-4.pdf"),
    ("2021-09-14", 30, f"{BASE}/2021/08/Seel-Co-September-Auction-Catalogue-V3.pdf"),
    ("2021-12-07", 26, f"{BASE}/2021/11/December-2021-Auction-Catalogue-2.pdf"),
    ("2022-02-22", 29, f"{BASE}/2022/02/February-2022-Auction-Catalogue-3.pdf"),
    ("2022-04-05", 31, f"{BASE}/2022/04/April-2022-Auction-Catalogue.pdf"),
]
DETAIL_CATALOGUES = [
    ("2021-10-26", 36, f"{BASE}/2021/10/Seel-Co-October-Auction-Catalogue-7.pdf"),
]
ALL_CATALOGUES = sorted(CATALOGUES + DETAIL_CATALOGUES)
DEFERRED = []
MAX_SNAPSHOT_BLOB = 12_000_000
SNAPSHOT_PART_BYTES = 8_000_000
MARKER_RE = re.compile(r"(?m)^(\d{1,3})(?:\x03)?\s+")
MONEY_RE = re.compile(r"£\s*([\d,]+)")
TAIL_RE = re.compile(
    r"\b(?:SOLD\s*PRIOR|WITHDRAWN|POSTPONED|NIL\s+RESERVE|GUIDE|AVAILABLE|SOLD)\b",
    re.I,
)
NOISE_RE = re.compile(
    r"^(?:Lot Numbers?|Order of Sale|seelandco\.com|/|029|2037|0117|DR|\d{1,2})$",
    re.I,
)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def extract_pdf_text(raw: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for Seel catalogue reconciliation")
    with tempfile.TemporaryDirectory(prefix="seel-catalogue-") as directory:
        source = Path(directory) / "catalogue.pdf"
        output = Path(directory) / "catalogue.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-raw", str(source), str(output)],
            check=True, capture_output=True, timeout=120,
        )
        text = output.read_text(errors="replace")
    if len(text.strip()) < 100:
        raise ValueError("catalogue PDF contains no usable text")
    return text


def extract_detail_pages(raw: bytes, ocr_pages=(21, 26, 39, 40)) -> list[dict]:
    """Extract every PDF page, OCRing image-only property detail pages."""
    for command in ("pdftotext", "pdftoppm", "tesseract"):
        if not shutil.which(command):
            raise RuntimeError(f"{command} is required for Seel detail-page reconciliation")
    with tempfile.TemporaryDirectory(prefix="seel-detail-catalogue-") as directory:
        directory = Path(directory)
        source = directory / "catalogue.pdf"
        output = directory / "catalogue.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-raw", str(source), str(output)],
            check=True, capture_output=True, timeout=120,
        )
        native_pages = output.read_text(errors="replace").split("\f")
        pages = [
            {"page_number": number, "text": text, "extraction": "native_pdf_text"}
            for number, text in enumerate(native_pages, 1)
        ]
        for page_number in ocr_pages:
            if page_number > len(pages):
                raise ValueError(f"catalogue has no page {page_number} required for OCR")
            prefix = directory / f"page-{page_number}"
            subprocess.run(
                ["pdftoppm", "-f", str(page_number), "-l", str(page_number),
                 "-r", "200", "-png", "-singlefile", str(source), str(prefix)],
                check=True, capture_output=True, timeout=120,
            )
            result = subprocess.run(
                ["tesseract", str(prefix) + ".png", "stdout"],
                check=True, capture_output=True, timeout=120,
            )
            pages[page_number - 1] = {
                "page_number": page_number,
                "text": result.stdout.decode("utf-8", "replace"),
                "extraction": "ocr_first_party_pdf_page",
            }
    return pages


def order_page(text: str, expected_rows: int) -> str:
    candidates = []
    for page in text.split("\f"):
        if re.search(r"Order\s+of\s+Sale", page, re.I):
            candidates.append(page)
    if not candidates:
        raise ValueError("catalogue has no order-of-sale page")
    return max(candidates, key=lambda page: len(sequential_markers(page, expected_rows)))


def sequential_markers(page: str, expected_rows: int) -> list[re.Match]:
    """Return the exact 1..N marker run, ignoring phone/address numbers."""
    accepted = []
    wanted = 1
    for marker in MARKER_RE.finditer(page):
        number = int(marker.group(1))
        if number == wanted:
            accepted.append(marker)
            wanted += 1
            if wanted > expected_rows:
                break
    return accepted


def status_semantics(text: str | None) -> str:
    value = (clean(text) or "").upper()
    compact = re.sub(r"[^A-Z]", "", value)
    if "SOLDPRIOR" in compact:
        return "sold_prior"
    if "WITHDRAWN" in value:
        return "withdrawn"
    if "POSTPONED" in value:
        return "postponed"
    if re.search(r"\bSOLD\b", value):
        return "sold"
    return "unknown"


def parse_detail_catalogue(pages: list[dict], item: tuple[str, int, str], evidence: dict) -> tuple[dict, list[dict]]:
    """Parse a catalogue whose complete denominator is its numbered detail pages."""
    auction_date, expected_rows, source_url = item
    numbered = {}
    for page in pages:
        matches = re.findall(r"(?im)^\s*Lot\s+(\d{1,3})\s*$", page["text"])
        for label in matches:
            number = int(label)
            if number in numbered:
                raise ValueError(f"duplicate detail page for lot {number}")
            numbered[number] = page
    labels = sorted(numbered)
    if labels != list(range(1, expected_rows + 1)):
        raise ValueError(
            f"detail pages do not reconcile: expected 1..{expected_rows}, got {labels}"
        )

    rows = []
    for number in labels:
        page = numbered[number]
        raw_text = page["text"].replace("\x03", "")
        lines = [clean(line) for line in raw_text.splitlines()]
        lines = [line for line in lines if line]
        heading_index = next(
            index for index, line in enumerate(lines)
            if re.fullmatch(rf"Lot\s+{number}", line, re.I)
        )
        guide_index = next(
            (index for index in range(heading_index + 1, len(lines))
             if re.search(r"Auction\s+Guide", lines[index], re.I)),
            None,
        )
        if guide_index is not None:
            title = clean(" ".join(lines[heading_index + 1:guide_index]))
            guide_text = lines[guide_index]
            address_start = guide_index + 1
            address_lines = []
            for line in lines[address_start:address_start + 6]:
                address_lines.append(line)
                if corpus.PC.search(line):
                    break
            address_candidate = clean(" ".join(address_lines))
            address = address_candidate if corpus.PC.search(address_candidate or "") else None
        else:
            guide_text = None
            title = None
            address = None
            for paragraph in re.split(r"\n\s*\n", raw_text):
                value = clean(paragraph)
                if value and corpus.PC.search(value):
                    address = value
                    break
            if address:
                before_address = raw_text[:raw_text.find(address.split()[0])]
                title = clean(re.sub(rf"(?i)^.*?Lot\s+{number}\s*", "", before_address, flags=re.S))

        guide_amounts = [int(value.replace(",", "")) for value in MONEY_RE.findall(guide_text or "")]
        postcode_match = corpus.PC.search(address or "")
        lot_number = str(number)
        auction_id = f"seel-catalogue:{auction_date}"
        row = corpus.base_row(
            "Seel & Co", auction_id, auction_date, lot_number, lot_number, source_url,
        )
        row.update(
            appearance_id=f"Seel & Co|{auction_id}|lot:{lot_number}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address or title,
            sector=corpus.sector(" ".join(value for value in (title, address) if value)),
            guide_price=guide_amounts[0] if guide_amounts else None,
            guide_price_high=guide_amounts[1] if len(guide_amounts) > 1 else None,
            status=status_semantics(raw_text),
            description=title,
            property_id=None,
            identity_method="exact_first_party_catalogue_date_and_printed_detail_lot_number",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis="exact date printed on first-party catalogue cover",
            source_position=number,
            source_page_number=page["page_number"],
            source_page_extraction=page["extraction"],
            source_price_text=guide_text,
            source_evidence=evidence,
        )
        rows.append(row)

    state = {
        "auctioneer": "Seel & Co",
        "source_auction_id": f"seel-catalogue:{auction_date}",
        "auction_date": auction_date,
        "catalogue_complete": True,
        "source_rows_complete": True,
        "published_lots": expected_rows,
        "visible_detail_lot_pages": len(rows),
        "lots_captured": len(rows),
        "missing_lot_numbers": [],
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "denominator_basis": "complete contiguous 1..N numbered property detail-page sequence in first-party catalogue PDF",
        "completion_scope": "every numbered property detail page in the retained first-party catalogue",
        "ocr_page_numbers": sorted(
            page["page_number"] for page in numbered.values()
            if page["extraction"] == "ocr_first_party_pdf_page"
        ),
        "source_url": source_url,
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def parse_segment(segment: str) -> tuple[str | None, str | None, int | None, str]:
    lines = [clean(line) for line in segment.replace("\x03", "").splitlines()]
    lines = [line for line in lines if line and not NOISE_RE.fullmatch(line)]
    combined = " ".join(lines)
    status_value = status_semantics(combined)
    guide_match = MONEY_RE.search(combined)
    guide = int(guide_match.group(1).replace(",", "")) if guide_match else None
    # Some tables put an outcome before the address, some after it, and one
    # says "Postponed until October auction - <address>". Remove only the
    # small vocabulary of printed outcome/price annotations; the remainder is
    # the source address, regardless of table column reading order.
    address = re.sub(r"^Postponed\s+until\s+.+?\s+auction\s*-\s*", "", combined, flags=re.I)
    address = re.sub(r"\s*-?\s*\b(?:SOLD\s*PRIOR|WITHDRAWN|POSTPONED|SOLD)\b\s*", " ", address, flags=re.I)
    address = re.sub(r"\s*£\s*[\d,]+\s*(?:[-–]\s*£?\s*[\d,]+)?\s*\+?\s*", " ", address)
    address = re.sub(r"\s*\b(?:NIL\s+RESERVE|TBC)\b\s*", " ", address, flags=re.I)
    address = clean(address)
    annotations = []
    annotations.extend(match.group(0) for match in TAIL_RE.finditer(combined))
    annotations.extend(match.group(0) for match in MONEY_RE.finditer(combined))
    if re.search(r"\bNIL\s+RESERVE\b", combined, re.I):
        annotations.append("Nil Reserve")
    if re.search(r"\bTBC\b", combined, re.I):
        annotations.append("TBC")
    tail = clean("; ".join(dict.fromkeys(annotations)))
    return address, tail, guide, status_value


def parse_catalogue(text: str, item: tuple[str, int, str], evidence: dict) -> tuple[dict, list[dict]]:
    auction_date, expected_rows, source_url = item
    page = order_page(text, expected_rows)
    markers = sequential_markers(page, expected_rows)
    labels = [int(marker.group(1)) for marker in markers]
    if labels != list(range(1, expected_rows + 1)):
        raise ValueError(
            f"order-of-sale rows do not reconcile: expected 1..{expected_rows}, got {labels}"
        )
    rows = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(page)
        address, price_text, guide, status = parse_segment(page[marker.end():end])
        if not address:
            raise ValueError(f"lot {index + 1} has no printed address")
        postcode_match = corpus.PC.search(address)
        lot_number = str(index + 1)
        auction_id = f"seel-catalogue:{auction_date}"
        row = corpus.base_row(
            "Seel & Co", auction_id, auction_date, lot_number, lot_number, source_url,
        )
        row.update(
            appearance_id=f"Seel & Co|{auction_id}|lot:{lot_number}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address),
            guide_price=guide,
            status=status,
            property_id=None,
            identity_method="exact_first_party_catalogue_date_and_printed_lot_number",
            record_quality="address_record",
            auction_date_basis="exact date printed by Seel in first-party catalogue material",
            source_position=index + 1,
            source_price_text=price_text,
            source_evidence=evidence,
        )
        rows.append(row)
    state = {
        "auctioneer": "Seel & Co",
        "source_auction_id": f"seel-catalogue:{auction_date}",
        "auction_date": auction_date,
        "catalogue_complete": True,
        "source_rows_complete": True,
        "published_lots": expected_rows,
        "visible_order_rows": len(rows),
        "lots_captured": len(rows),
        "missing_lot_numbers": [],
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "denominator_basis": "complete numbered order-of-sale table in first-party catalogue PDF",
        "completion_scope": "every printed row in the catalogue order-of-sale table",
        "source_url": source_url,
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def get_pdf(url: str, cache_file: Path | None = None) -> tuple[str, bytes]:
    if cache_file and cache_file.exists():
        raw = cache_file.read_bytes()
        if len(raw) < 10_000 or not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
            raise ValueError(f"malformed cached PDF ({len(raw)} bytes)")
        return url, raw
    last_error = None
    for _ in range(4):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            raw = response.content
            if len(raw) < 10_000 or not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
                raise ValueError(f"malformed PDF response ({len(raw)} bytes)")
            return response.url, raw
        except Exception as exc:
            last_error = exc
    raise last_error


def save_pdf_snapshot(auction_date: str, sha: str, raw: bytes) -> dict:
    """Persist one PDF gzip, splitting only when an API-safe blob is required."""
    packed = gzip.compress(raw, mtime=0)
    directory = corpus.DATA / "sources/seel/catalogues"
    stem = f"{auction_date}-{sha[:16]}.pdf.gz"
    if len(packed) <= MAX_SNAPSHOT_BLOB:
        snapshot = directory / stem
        corpus.atomic(snapshot, packed)
        return {"snapshot_path": str(snapshot.relative_to(corpus.ROOT))}
    paths = []
    for number, offset in enumerate(range(0, len(packed), SNAPSHOT_PART_BYTES), 1):
        part = directory / f"{stem}.part-{number:03d}"
        corpus.atomic(part, packed[offset:offset + SNAPSHOT_PART_BYTES])
        paths.append(str(part.relative_to(corpus.ROOT)))
    return {
        "snapshot_parts": paths,
        "snapshot_encoding": "concatenate parts, then gzip-decompress to recover the source PDF",
        "snapshot_compressed_bytes": len(packed),
    }


def harvest() -> None:
    summary_path = corpus.DATA / "seel_collection.json"
    existing = []
    for auction_date, _, _ in ALL_CATALOGUES:
        shard = corpus.DATA / "appearances/seel" / f"{auction_date}.jsonl.gz"
        if shard.exists():
            existing.extend(corpus.iter_rows(shard))
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    failures = []
    states = []
    cache_dir = Path(os.environ["SEEL_PDF_CACHE"]) if os.environ.get("SEEL_PDF_CACHE") else None
    for item in ALL_CATALOGUES:
        auction_date, expected_rows, source_url = item
        state_path = corpus.DATA / "auctions/seel" / f"{auction_date}.json"
        shard_path = corpus.DATA / "appearances/seel" / f"{auction_date}.jsonl.gz"
        if state_path.exists() and shard_path.exists():
            state = json.loads(state_path.read_text())
            rows = list(corpus.iter_rows(shard_path))
            if state.get("catalogue_complete") and len(rows) == expected_rows:
                states.append(state)
                for row in rows:
                    merged[row["appearance_id"]] = row
                continue
        try:
            cache_file = cache_dir / f"{auction_date}.pdf" if cache_dir else None
            resolved_url, raw = get_pdf(source_url, cache_file)
            sha = corpus.digest(raw)
            evidence = {
                "source_url": resolved_url,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "basis": (
                    "first-party complete auction catalogue PDF and contiguous numbered detail pages"
                    if item in DETAIL_CATALOGUES else
                    "first-party complete auction catalogue PDF and printed order-of-sale table"
                ),
            }
            evidence.update(save_pdf_snapshot(auction_date, sha, raw))
            if item in DETAIL_CATALOGUES:
                state, rows = parse_detail_catalogue(extract_detail_pages(raw), item, evidence)
            else:
                state, rows = parse_catalogue(extract_pdf_text(raw), item, evidence)
            corpus.save_json(state_path, state)
            corpus.write_rows(f"seel/{auction_date}", rows)
            states.append(state)
            for row in rows:
                merged[row["appearance_id"]] = row
            print("SEEL", auction_date, len(rows), "lots complete", flush=True)
        except Exception as exc:
            failures.append({
                "auction_date": auction_date,
                "source_url": source_url,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

    total = len(merged)
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(),
        "source": "Seel & Co first-party retained catalogue PDFs",
        "catalogues_discovered": len(ALL_CATALOGUES) + len(DEFERRED),
        "catalogues_banked": len(states),
        "catalogues_complete": sum(bool(state.get("catalogue_complete")) for state in states),
        "catalogues_deferred": len(DEFERRED),
        "appearances_captured": total,
        "address_records": sum(bool(row.get("address")) for row in merged.values()),
        "partial_lots": sum(not row.get("address") for row in merged.values()),
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(state["auction_date"] for state in states),
                       max(state["auction_date"] for state in states)] if states else [],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "deferred_catalogues": DEFERRED,
        "failures": failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
