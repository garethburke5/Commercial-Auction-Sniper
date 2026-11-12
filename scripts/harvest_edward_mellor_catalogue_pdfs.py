"""Bank retained first-party Edward Mellor catalogue PDFs in reusable batches.

The result-sheet collector deliberately ignores catalogues.  This companion
runner admits only explicit numbered property rows from retained catalogues,
keeps the immutable PDFs, and reconciles each configured file inventory before
writing.  A catalogue is allowed to be a surviving fragment of an event; its
file inventory can be complete without claiming that the whole auction is.
"""
from __future__ import annotations

from datetime import date
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Edward Mellor"
SLUG = "edward-mellor-catalogues"
PARSER_VERSION = 1
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
EVENT_DATE = "2014-06-11"
EVENT_ID = f"edward-mellor-catalogue:{EVENT_DATE}"
RESIDENTIAL_URL = (
    "https://edwardmellor.co.uk/pdf/archive/"
    "20140601_June_Auction_Residential_Catalogue_2014.pdf"
)
ADDITIONAL_URL = (
    "https://edwardmellor.co.uk/pdf/archive/"
    "20140601_June_Auction_Additional_Lots.pdf"
)
EXPECTED_RESIDENTIAL = tuple(
    [str(number) for number in range(40, 49)]
    + ["48A"]
    + [str(number) for number in range(49, 109)]
)
EXPECTED_ADDITIONAL = ("31A",) + tuple(str(number) for number in range(32, 40)) + ("109", "110")
CATALOGUES = (
    {
        "date": EVENT_DATE,
        "event_id": EVENT_ID,
        "residential_url": RESIDENTIAL_URL,
        "additional_url": ADDITIONAL_URL,
        "expected_residential": EXPECTED_RESIDENTIAL,
        "expected_additional": EXPECTED_ADDITIONAL,
    },
)

LOT_HEADER_RE = re.compile(
    r"^\s*Lot\s+(\d+[A-Za-z]?)\s+Guide Price\s+£\s*([\d,]+)"
    r"(?:\s+to\s+£\s*([\d,]+))?\s*(\+)?\s*$",
    re.I,
)
ORDER_ROW_RE = re.compile(r"^\s*(\d+[A-Za-z]?)\s{2,}(.+)$")
MONEY_RE = re.compile(r"£\s*([\d,]+)")

# Lot 109 uses an embedded private-use font without a usable ToUnicode map.
# The value is a reviewed transcription of the visible address in this exact
# immutable first-party PDF; it is not inferred from any other property.
ADDRESS_TRANSCRIPTIONS = {
    "109": "15a Currier Lane, Ashton-under-Lyne OL6 6TW",
}
DESCRIPTION_TRANSCRIPTIONS = {
    "109": "Jacobean era cottage with roots from early 17th century",
}


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def money(value: str | None) -> int | None:
    return int(value.replace(",", "")) if value else None


def normalize_label(value: str) -> str:
    return clean(value).upper()


def extract_pdf_text(raw: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for the catalogue layout parser")
    with tempfile.TemporaryDirectory(prefix="edward-mellor-catalogue-") as directory:
        source = Path(directory) / "source.pdf"
        output = Path(directory) / "source.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(output)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        text = output.read_text(errors="replace")
    if len(text.strip()) < 100:
        raise ValueError("catalogue PDF contains no usable layout text")
    return text


def fetch_pdf(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000 or not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
        raise ValueError(f"first-party PDF is truncated or malformed ({len(raw)} bytes)")
    return raw, response.url


def snapshot_pdf(raw: bytes) -> tuple[Path, str]:
    sha = hashlib.sha256(raw).hexdigest()
    path = corpus.DATA / "sources" / SLUG / f"{sha[:16]}.pdf.gz"
    if path.exists():
        if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != sha:
            raise ValueError(f"immutable snapshot collision at {path}")
    else:
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return path, sha


def parse_guides(text: str) -> dict[str, tuple[int, int | None, bool]]:
    guides = {}
    for line in text.splitlines():
        match = LOT_HEADER_RE.match(line)
        if not match:
            continue
        label, low, high, plus = match.groups()
        label = normalize_label(label)
        value = (money(low), money(high), bool(plus))
        if label in guides and guides[label] != value:
            raise ValueError(f"conflicting guide headers for lot {label}")
        guides[label] = value
    return guides


def parse_residential_order(text: str) -> dict[str, dict]:
    rows = {}
    in_order = False
    for line in text.splitlines():
        if line.lstrip().startswith("Order of sale"):
            in_order = True
            continue
        if not in_order:
            continue
        match = ORDER_ROW_RE.match(line)
        if not match:
            if line.strip() and not line.lstrip().startswith("Order of sale"):
                in_order = False
            continue
        label, remainder = match.groups()
        label = normalize_label(label)
        if not re.fullmatch(r"(?:4[0-9]|[5-9][0-9]|10[0-8])A?", label):
            in_order = False
            continue
        columns = re.split(r"\s{2,}", remainder.strip())
        if len(columns) != 3:
            raise ValueError(f"lot {label} order row has {len(columns)} columns")
        locality, street, property_type = map(clean, columns)
        address = clean(f"{street}, {locality}")
        row = {
            "lot_number": label,
            "address": address,
            "locality": locality,
            "property_type": property_type,
            "description": property_type,
        }
        if label in rows and rows[label] != row:
            raise ValueError(f"conflicting order rows for lot {label}")
        rows[label] = row
    return rows


def split_lot_pages(text: str) -> dict[str, str]:
    pages = {}
    for page in text.split("\f"):
        label = None
        for line in page.splitlines():
            match = LOT_HEADER_RE.match(line)
            if match:
                label = normalize_label(match.group(1))
                break
        if not label:
            continue
        if label in pages and clean(pages[label]) != clean(page):
            # Some brochures repeat an identical lot page in the extracted
            # stream. Only byte-for-text equivalent repeats are collapsible.
            raise ValueError(f"conflicting detail pages for lot {label}")
        pages[label] = page
    return pages


def _first_detail_lines(page: str) -> list[str]:
    lines = page.splitlines()
    header_index = next(index for index, line in enumerate(lines) if LOT_HEADER_RE.match(line))
    return [clean(line) for line in lines[header_index + 1:] if clean(line)]


def compact_postcode(value: str) -> str | None:
    match = corpus.PC.search(value or "")
    if match:
        raw = re.sub(r"\s+", "", match.group()).upper()
        return f"{raw[:-3]} {raw[-3:]}"
    compact = re.search(
        r"\b(GIR0AA|[A-PR-UWYZ](?:\d[\dA-HJKPSTUW]?|[A-HK-Y]\d[\dABEHMNPRV-Y]?)\d[ABD-HJLNP-UW-Z]{2})\b",
        re.sub(r"\s+", "", value or ""),
        re.I,
    )
    if not compact:
        return None
    raw = compact.group().upper()
    return f"{raw[:-3]} {raw[-3:]}"


def parse_additional_rows(text: str) -> dict[str, dict]:
    rows = {}
    guides = parse_guides(text)
    for label, page in split_lot_pages(text).items():
        detail = _first_detail_lines(page)
        address = ADDRESS_TRANSCRIPTIONS.get(label)
        description = DESCRIPTION_TRANSCRIPTIONS.get(label)
        if not address:
            if not detail:
                raise ValueError(f"lot {label} has no detail lines")
            address = detail[0]
        if not description and len(detail) > 1:
            description = detail[1]
        low, high, plus = guides[label]
        joined_detail = clean(" ".join(detail)) or ""
        rent_fragments = re.findall(
            r"(?:[^.]*\b(?:rent|rental income)\b[^.]*\.?)",
            joined_detail,
            re.I,
        )
        rent_text = clean(" ".join(rent_fragments))
        annual_rent = None
        income = re.search(
            r"rental income(?:\s+of|\s+is)?\s*£\s*([\d,]+)\s*per annum",
            joined_detail,
            re.I,
        )
        if income:
            annual_rent = money(income.group(1))
        rows[label] = {
            "lot_number": label,
            "address": clean(address),
            "locality": None,
            "property_type": clean(description),
            "description": clean(description),
            "guide_price": low,
            "guide_price_high": high,
            "guide_plus": plus,
            "annual_rent": annual_rent,
            "rent_text": rent_text,
        }
    return rows


def validate_labels(actual, expected, name: str) -> None:
    actual_set = set(actual)
    expected_set = set(expected)
    if actual_set != expected_set:
        raise ValueError(
            f"{name} inventory mismatch: missing={sorted(expected_set-actual_set)} "
            f"unexpected={sorted(actual_set-expected_set)}"
        )


def _existing_exact_signatures(target_path: Path) -> set[tuple[str, str]]:
    signatures = set()
    appearances = corpus.DATA / "appearances"
    for path in appearances.rglob("*.jsonl.gz"):
        if path == target_path:
            continue
        for row in corpus.iter_rows(path):
            address = clean(row.get("address"))
            auction_date = clean(row.get("auction_date"))
            if not address or not auction_date:
                continue
            normalized = re.sub(r"[^a-z0-9]+", "", address.casefold())
            signatures.add((auction_date, normalized))
    return signatures


def make_row(source_row: dict, source_url: str, evidence: dict) -> dict:
    label = source_row["lot_number"]
    address = source_row["address"]
    description = source_row.get("description")
    property_type = source_row.get("property_type")
    row = corpus.base_row(SOURCE, EVENT_ID, EVENT_DATE, label, label, source_url)
    postcode = compact_postcode(address)
    if postcode and postcode.replace(" ", "") in address and postcode not in address:
        address = address.replace(postcode.replace(" ", ""), postcode)
    row.update(
        appearance_id=f"{SOURCE}|{EVENT_ID}|lot:{label}",
        address=address,
        postcode=postcode,
        locality=source_row.get("locality"),
        sector=corpus.sector(f"{property_type or ''} {description or ''}"),
        property_type=property_type,
        description=description,
        guide_price=source_row.get("guide_price"),
        guide_price_high=source_row.get("guide_price_high"),
        guide_plus=source_row.get("guide_plus", False),
        annual_rent=source_row.get("annual_rent"),
        rent_text=source_row.get("rent_text"),
        status="unknown",
        property_id=None,
        identity_method="exact_auction_date_catalogue_and_published_lot_number",
        record_quality="address_record",
        auction_date_basis=(
            "exact date printed in first-party June 2014 residential catalogue; "
            "additional-lot PDF linked to the same June 2014 event in the first-party archive"
        ),
        source_evidence=evidence,
    )
    if label == "31A":
        row["sector"] = "mixed-use"
    elif label in {str(number) for number in range(32, 40)}:
        row["sector"] = "commercial"
    else:
        # These rows are published in the first-party residential catalogue or
        # its residential additional-lot continuation. This source label is
        # stronger evidence than relying on a keyword such as "house" in each
        # abbreviated order-of-sale description.
        row["sector"] = "residential"
    return row


def collection_is_current(summary: dict, rows: list[dict], root: Path) -> bool:
    """Prove a configured batch is already banked without refreshing sources."""
    expected = sum(
        len(catalogue["expected_residential"]) + len(catalogue["expected_additional"])
        for catalogue in CATALOGUES
    )
    if (
        summary.get("parser_version") != PARSER_VERSION
        or summary.get("catalogues_configured") != len(CATALOGUES)
        or summary.get("catalogues_banked") != len(CATALOGUES)
        or summary.get("appearances_banked") != expected
        or len(rows) != expected
        or len({row.get("appearance_id") for row in rows}) != expected
    ):
        return False
    for catalogue in CATALOGUES:
        state_path = (
            root / "data/auction_history/auctions" / SLUG /
            f"{catalogue['date']}.json"
        )
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        if (
            state.get("parser_version") != PARSER_VERSION
            or not state.get("source_files_reconciled")
            or not state.get("surviving_file_inventory_complete")
            or state.get("lots_captured") != expected
        ):
            return False
    source_files = summary.get("source_files") or []
    if len(source_files) != len(CATALOGUES) * 2:
        return False
    for evidence in source_files:
        try:
            snapshot = root / evidence["snapshot_path"]
            raw = gzip.decompress(snapshot.read_bytes())
        except (KeyError, OSError, gzip.BadGzipFile):
            return False
        if hashlib.sha256(raw).hexdigest() != evidence.get("sha256"):
            return False
    return True


def harvest() -> dict:
    target_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    summary_path = corpus.DATA / "edward_mellor_catalogue_collection.json"
    if target_path.exists() and summary_path.exists():
        try:
            saved_summary = json.loads(summary_path.read_text())
            saved_rows = list(corpus.iter_rows(target_path))
        except (OSError, json.JSONDecodeError, gzip.BadGzipFile):
            saved_summary, saved_rows = {}, []
        if collection_is_current(saved_summary, saved_rows, corpus.ROOT):
            report = dict(saved_summary)
            report.update(
                run_skipped_already_current=True,
                run_new_appearances=0,
                run_new_address_records=0,
                run_new_guides=0,
                run_new_sale_prices=0,
                run_new_rents=0,
                run_new_commercial=0,
                run_new_mixed_use=0,
            )
            print(json.dumps(report, indent=2))
            return report
    existing_ids = set()
    if target_path.exists():
        existing_ids = {row["appearance_id"] for row in corpus.iter_rows(target_path)}
    exact_signatures = _existing_exact_signatures(target_path)
    all_rows = []
    event_states = []
    source_files = []
    duplicate_evidence = []

    for catalogue in CATALOGUES:
        if catalogue["date"] != EVENT_DATE or catalogue["event_id"] != EVENT_ID:
            raise ValueError("configured event constants do not agree")
        residential_raw, residential_resolved = fetch_pdf(catalogue["residential_url"])
        additional_raw, additional_resolved = fetch_pdf(catalogue["additional_url"])
        residential_snapshot, residential_sha = snapshot_pdf(residential_raw)
        additional_snapshot, additional_sha = snapshot_pdf(additional_raw)
        residential_text = extract_pdf_text(residential_raw)
        additional_text = extract_pdf_text(additional_raw)

        if "11th June 2014" not in residential_text[:2500]:
            raise ValueError("residential catalogue does not print the configured exact event date")
        date(2014, 6, 11)  # fail loudly if the configured exact date becomes invalid

        residential = parse_residential_order(residential_text)
        residential_guides = parse_guides(residential_text)
        validate_labels(residential, catalogue["expected_residential"], "residential order")
        unexpected_guide_labels = set(residential_guides) - set(residential)
        if unexpected_guide_labels:
            raise ValueError(f"residential detail guides outside order: {sorted(unexpected_guide_labels)}")
        for label, row in residential.items():
            if label in residential_guides:
                low, high, plus = residential_guides[label]
                row.update(guide_price=low, guide_price_high=high, guide_plus=plus)

        additional = parse_additional_rows(additional_text)
        validate_labels(additional, catalogue["expected_additional"], "additional details")

        retrieved_at = corpus.now()
        residential_evidence = {
            "source_url": residential_resolved,
            "retrieved_at": retrieved_at,
            "sha256": residential_sha,
            "snapshot_path": str(residential_snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party residential auction catalogue PDF",
        }
        additional_evidence = {
            "source_url": additional_resolved,
            "retrieved_at": retrieved_at,
            "sha256": additional_sha,
            "snapshot_path": str(additional_snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party additional-lot catalogue PDF",
        }
        source_files.extend([residential_evidence, additional_evidence])
        candidates = [
            make_row(row, residential_resolved, residential_evidence)
            for row in residential.values()
        ] + [
            make_row(row, additional_resolved, additional_evidence)
            for row in additional.values()
        ]
        if len({row["appearance_id"] for row in candidates}) != len(candidates):
            raise ValueError("event contains duplicate appearance IDs")
        for row in candidates:
            signature = (
                row["auction_date"],
                re.sub(r"[^a-z0-9]+", "", row["address"].casefold()),
            )
            if signature in exact_signatures:
                duplicate_evidence.append({
                    "lot_number": row["lot_number"],
                    "address": row["address"],
                    "source_url": row["original_url"],
                })
                continue
            all_rows.append(row)

        event_state = {
            "auctioneer": SOURCE,
            "source_auction_id": EVENT_ID,
            "auction_date": EVENT_DATE,
            "parser_version": PARSER_VERSION,
            "catalogue_complete": False,
            "source_files_reconciled": True,
            "surviving_file_inventory_complete": True,
            "event_inventory_complete": False,
            "lots_captured": len(candidates) - len(duplicate_evidence),
            "published_lots_in_surviving_files": len(candidates),
            "residential_order_rows": len(residential),
            "additional_detail_rows": len(additional),
            "guide_prices_captured": sum(row.get("guide_price") is not None for row in candidates),
            "sale_prices_captured": 0,
            "rents_captured": sum(row.get("annual_rent") is not None for row in candidates),
            "duplicate_exact_date_address_evidence": len(duplicate_evidence),
            "missing_detail_guides": sorted(set(residential) - set(residential_guides)),
            "completion_scope": (
                "every explicit numbered property in the retained June 2014 residential "
                "and additional-lot PDFs; the absent main commercial catalogue is not inferred"
            ),
            "errors": [],
            "checked_at": corpus.now(),
        }
        event_states.append(event_state)
        state_path = corpus.DATA / "auctions" / SLUG / f"{EVENT_DATE}.json"
        corpus.save_json(state_path, event_state)

    total = corpus.write_rows(f"{SLUG}/canonical", all_rows, preserve_existing=True)
    current_ids = {row["appearance_id"] for row in all_rows}
    added_ids = current_ids - existing_ids
    added = [row for row in all_rows if row["appearance_id"] in added_ids]
    summary = {
        "checked_at": corpus.now(),
        "parser_version": PARSER_VERSION,
        "catalogues_configured": len(CATALOGUES),
        "catalogues_banked": len(event_states),
        "appearances_banked": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(row.get("address") is not None for row in added),
        "run_new_guides": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use": sum(row.get("sector") == "mixed-use" for row in added),
        "run_duplicate_evidence": len(duplicate_evidence),
        "duplicate_evidence": duplicate_evidence,
        "source_files": source_files,
        "events": event_states,
        "national_coverage_complete": False,
        "next_growth_target": (
            "Batch another accessible missing Edward Mellor catalogue year from the first-party "
            "archive, beginning with a retained event absent from the result-PDF corpus; keep "
            "catalogue evidence separate from published outcomes."
        ),
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    harvest()


if __name__ == "__main__":
    main()
