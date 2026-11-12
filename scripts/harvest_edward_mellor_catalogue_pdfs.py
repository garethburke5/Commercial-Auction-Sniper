"""Bank retained first-party Edward Mellor catalogue PDFs in reusable batches.

The result-sheet collector deliberately ignores catalogues.  This companion
runner admits only explicit property rows from retained catalogues, keeps the
immutable PDFs, and reconciles each configured file inventory before writing.
A catalogue is allowed to be a surviving fragment of an event; its file
inventory can be complete without claiming that the whole auction is.
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
PARSER_VERSION = 5
MAX_SNAPSHOT_PART_BYTES = 700_000
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
        "format": "split_2014",
        "residential_url": RESIDENTIAL_URL,
        "additional_url": ADDITIONAL_URL,
        "expected_residential": EXPECTED_RESIDENTIAL,
        "expected_additional": EXPECTED_ADDITIONAL,
    },
    {
        "date": "2018-03-13",
        "event_id": "edward-mellor-catalogue:2018-03-13",
        "format": "combined_2018",
        "url": (
            "https://edwardmellor.co.uk/pdf/archive/"
            "20180301_March_Auction_Catalogue_2018.pdf"
        ),
        "printed_date": "TUESDAY 13 MARCH 2018",
        "expected_lots": tuple(
            [str(number) for number in range(1, 41)]
            + ["40A"]
            + [str(number) for number in range(41, 61)]
            + ["60A"]
            + [str(number) for number in range(61, 64)]
        ),
    },
    {
        "date": "2018-04-24",
        "event_id": "edward-mellor-catalogue:2018-04-24",
        "format": "combined_2018",
        "url": (
            "https://edwardmellor.co.uk/pdf/archive/"
            "20180401_April_Auction_Catalogue_2018.pdf"
        ),
        "printed_date": "TUESDAY 24 APRIL 2018",
        "expected_lots": tuple(
            [str(number) for number in range(1, 17)]
            + ["16A"]
            + [str(number) for number in range(17, 21)]
            + ["20A"]
            + [str(number) for number in range(21, 29)]
            + ["28A", "29", "30", "30A", "31", "32", "32A"]
            + [str(number) for number in range(33, 46)]
            + ["45A", "46", "47", "47A"]
            + [str(number) for number in range(48, 72)]
        ),
    },
    {
        "date": "2018-06-05",
        "event_id": "edward-mellor-catalogue:2018-06-05",
        "format": "unnumbered_combined_2018",
        "url": "https://edwardmellor.co.uk/pdf/June_Auction_Catalogue_2018.pdf",
        "printed_date": "TUESDAY 5 JUNE 2018",
        "expected_rows": 69,
    },
    {
        "date": "2018-07-17",
        "event_id": "edward-mellor-catalogue:2018-07-17",
        "format": "numbered_order_2018",
        "url": "https://edwardmellor.co.uk/pdf/July_Auction_Catalogue_2018.pdf?v=4",
        "printed_date": "Lots for July 17th 2018",
        "expected_lots": tuple(str(number) for number in range(1, 59)),
    },
)

LOT_HEADER_RE = re.compile(
    r"^\s*Lot\s+(\d+[A-Za-z]?)\s+Guide Price\s+£\s*([\d,]+)"
    r"(?:\s+to\s+£\s*([\d,]+))?\s*(\+)?\s*$",
    re.I,
)
ORDER_ROW_RE = re.compile(r"^\s*(\d+[A-Za-z]?)\s{2,}(.+)$")
MONEY_RE = re.compile(r"£\s*([\d,]+)")
COMBINED_GUIDE_RE = re.compile(
    r"GUIDE PRICE:\s*£\s*([\d,]+)(?:\s*[-\u00ad]\s*£\s*([\d,]+))?\s*(\+)?",
    re.I,
)
GUIDE_TEXT_RE = re.compile(r"GUIDE PRICE:\s*([^\n\r]+)", re.I)

# Lot 109 uses an embedded private-use font without a usable ToUnicode map.
# The value is a reviewed transcription of the visible address in this exact
# immutable first-party PDF; it is not inferred from any other property.
ADDRESS_TRANSCRIPTIONS = {
    "109": "15a Currier Lane, Ashton-under-Lyne OL6 6TW",
}
DESCRIPTION_TRANSCRIPTIONS = {
    "109": "Jacobean era cottage with roots from early 17th century",
}
COMBINED_TRANSCRIPTIONS = {
    # Reviewed directly against the immutable first-party order-of-sale table.
    # These are the few cells whose tight column layout crosses pdftotext's
    # inferred boundary; the catalogue remains the sole evidence source.
    ("2018-03-13", "19"): {
        "address": "129, 131, 133 Stamford Street Central, Ashton-under-Lyne",
        "locality": "Ashton-under-Lyne",
        "description": (
            "Three retail units with hi-spec offices over, basements, "
            "suitable for development STP."
        ),
    },
    ("2018-03-13", "20"): {
        "description": "Four bedroom house of multiple occupancy generating £11,652 p/a.",
    },
    ("2018-04-24", "12"): {
        "address": "The Spear Building, Manchester City Centre",
        "locality": "Manchester City Centre",
    },
    ("2018-04-24", "68"): {
        "address": "GO9 Hacienda Apartments, Manchester City Centre",
        "locality": "Manchester City Centre",
    },
}


def clean(value) -> str | None:
    value = str(value or "").replace("\x02", "-")
    value = re.sub(r"\s+", " ", value).strip(" ,\xa0")
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


def snapshot_pdf(raw: bytes) -> tuple[list[Path], str]:
    sha = hashlib.sha256(raw).hexdigest()
    path = corpus.DATA / "sources" / SLUG / f"{sha[:16]}.pdf.gz"
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) <= MAX_SNAPSHOT_PART_BYTES:
        paths = [path]
    else:
        paths = [
            Path(f"{path}.part-{index // MAX_SNAPSHOT_PART_BYTES + 1:03d}")
            for index in range(0, len(compressed), MAX_SNAPSHOT_PART_BYTES)
        ]
    if all(item.exists() for item in paths):
        saved = b"".join(item.read_bytes() for item in paths)
        if hashlib.sha256(gzip.decompress(saved)).hexdigest() != sha:
            raise ValueError(f"immutable snapshot collision at {paths}")
    elif any(item.exists() for item in paths):
        raise ValueError(f"incomplete immutable snapshot parts at {paths}")
    else:
        for index, item in enumerate(paths):
            start = index * MAX_SNAPSHOT_PART_BYTES
            corpus.atomic(item, compressed[start:start + MAX_SNAPSHOT_PART_BYTES])
    return paths, sha


def snapshot_fields(paths: list[Path]) -> dict:
    relative = [str(path.relative_to(corpus.ROOT)) for path in paths]
    if len(relative) == 1:
        return {"snapshot_path": relative[0]}
    return {"snapshot_parts": relative}


def retained_or_fetched_pdf(url: str, saved_summary: dict) -> tuple[bytes, str, list[Path], str, str]:
    """Reuse verified immutable evidence before making a source request."""
    requested = url.split("?", 1)[0]
    for evidence in saved_summary.get("source_files") or []:
        source_url = evidence.get("source_url")
        if not source_url or source_url.split("?", 1)[0] != requested:
            continue
        relative_paths = evidence.get("snapshot_parts") or [evidence.get("snapshot_path")]
        if not all(relative_paths):
            continue
        paths = [corpus.ROOT / path for path in relative_paths]
        try:
            raw = gzip.decompress(b"".join(path.read_bytes() for path in paths))
        except (OSError, gzip.BadGzipFile):
            continue
        sha = hashlib.sha256(raw).hexdigest()
        if sha != evidence.get("sha256"):
            raise ValueError(f"saved immutable snapshot hash mismatch for {source_url}")
        return raw, source_url, paths, sha, evidence.get("retrieved_at") or corpus.now()
    raw, resolved = fetch_pdf(url)
    paths, sha = snapshot_pdf(raw)
    return raw, resolved, paths, sha, corpus.now()


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


def parse_combined_guides(text: str) -> dict[str, tuple[int, int | None, bool]]:
    """Read the alternating left/right lot headers used by 2018 catalogues."""
    guides = {}
    for page in text.split("\f"):
        guide = COMBINED_GUIDE_RE.search(page)
        if not guide:
            continue
        labels = []
        for line in page.splitlines()[:8]:
            match = re.fullmatch(r"\s*(\d+[A-Za-z]?)\s*", line)
            if match:
                labels.append(normalize_label(match.group(1)))
        if len(set(labels)) != 1:
            raise ValueError("2018 detail page does not expose one unambiguous lot number")
        label = labels[0]
        value = (money(guide.group(1)), money(guide.group(2)), bool(guide.group(3)))
        if label in guides and guides[label] != value:
            raise ValueError(f"conflicting 2018 guide headers for lot {label}")
        guides[label] = value
    return guides


def parse_guide_text(value: str | None) -> dict:
    """Preserve a published guide phrase while structuring numeric evidence."""
    guide_text = clean(value)
    if not guide_text:
        return {
            "guide_price": None,
            "guide_price_high": None,
            "guide_plus": False,
            "guide_text": None,
        }
    match = re.fullmatch(
        r"£\s*([\d,]+)(?:\s*[-\u00ad]\s*£\s*([\d,]+))?\s*(\+)?",
        guide_text,
        re.I,
    )
    return {
        "guide_price": money(match.group(1)) if match else None,
        "guide_price_high": money(match.group(2)) if match and match.group(2) else None,
        "guide_plus": bool(match and match.group(3)),
        "guide_text": guide_text,
        "guide_observation": True,
    }


def parse_unnumbered_guides(text: str, expected_rows: int) -> list[dict]:
    """Read ordered guide headers when the catalogue publishes no lot labels."""
    guides = []
    for page in text.split("\f"):
        match = GUIDE_TEXT_RE.search(page)
        if match:
            guides.append(parse_guide_text(match.group(1)))
    if len(guides) != expected_rows:
        raise ValueError(
            f"unnumbered guide inventory mismatch: expected={expected_rows} actual={len(guides)}"
        )
    return guides


def _order_segments(line: str, address_start: int, description_start: int) -> tuple[str, str, str]:
    padded = line.ljust(description_start)
    return (
        clean(padded[:address_start]) or "",
        clean(padded[address_start:description_start]) or "",
        clean(padded[description_start:]) or "",
    )


def _repair_order_boundary(address_part: str | None, description_part: str | None) -> tuple[str | None, str | None]:
    """Move a word split by pdftotext's one-column table-boundary drift."""
    address_part = clean(address_part)
    description_part = clean(description_part)
    if address_part and description_part and description_part[:1].islower():
        leading = re.fullmatch(r"([A-Za-z]{1,3})\s+(.+)", address_part)
        first_word = re.match(r"[A-Za-z]+", description_part)
        joined_word = (
            (leading.group(1) + first_word.group()).casefold()
            if leading and first_word
            else None
        )
        if leading and joined_word in {"first", "ground", "redevelopment"}:
            description_part = clean(leading.group(1) + description_part)
            address_part = clean(leading.group(2))
        match = re.search(r"\s([A-Za-z]{1,3})$", address_part)
        if not match and re.fullmatch(r"[A-Za-z]{1,3}", address_part):
            description_part = clean(address_part + description_part)
            return None, description_part
        if match:
            fragment = match.group(1)
            address_part = clean(address_part[:match.start()])
            description_part = clean(fragment + description_part)
    return address_part, description_part


def _rent_fields(description: str | None) -> tuple[int | None, str | None]:
    normalized_text = clean(description) or ""
    annual_rent = None
    rent_match = re.search(
        r"£\s*([\d,]+)\s*(?:net\s+)?(?:p\s*[/\.\s]?\s*a\.?|pa\b|per annum)",
        normalized_text,
        re.I,
    )
    if not rent_match:
        rent_match = re.search(
            r"(?:annualised rent|annual rent)\s*(?:circa|of|is)?\s*£\s*([\d,]+)",
            normalized_text,
            re.I,
        )
    if rent_match:
        annual_rent = money(rent_match.group(1))
    monthly = re.search(r"£\s*([\d,]+)\s*(?:pcm|monthly)", normalized_text, re.I)
    if monthly and annual_rent is None:
        annual_rent = money(monthly.group(1)) * 12
    return annual_rent, clean(normalized_text if annual_rent is not None else None)


def _description_needs_continuation(description: str, fragment: str) -> bool:
    if fragment[:1].islower() or len(fragment) <= 25:
        return True
    return bool(
        re.search(
            r"\b(?:a|an|and|as|for|from|in|of|on|or|the|to|with)\s*$",
            description,
            re.I,
        )
    )


def parse_unnumbered_combined_order(text: str, expected_rows: int) -> list[dict]:
    """Parse a complete ordered catalogue table that omits printed lot labels."""
    rows = []
    carry_area = []
    carry_address = []
    carry_description = []
    for page in text.split("\f"):
        lines = page.splitlines()
        header_index = next(
            (
                index for index, line in enumerate(lines)
                if re.search(r"\bAREA\b", line)
                and re.search(r"\bADDRESS\b", line)
                and re.search(r"\bDESCRIPTION\b", line)
                and not re.search(r"\bLOT\b", line)
            ),
            None,
        )
        if header_index is None:
            continue
        header = lines[header_index]
        address_start = header.index("ADDRESS")
        description_start = header.index("DESCRIPTION")
        body = lines[header_index + 1:]
        starts = []
        for index, line in enumerate(body):
            area, _, _ = _order_segments(line, address_start, description_start)
            if area:
                starts.append(index)

        carry_area = []
        carry_address = []
        carry_description = []
        for position, index in enumerate(starts):
            next_index = starts[position + 1] if position + 1 < len(starts) else len(body)
            area, address, description = _order_segments(
                body[index], address_start, description_start
            )
            address, description = _repair_order_boundary(address, description)
            area = clean(" ".join(carry_area + ([area] if area else [])))
            prefix_address = list(carry_address)
            prefix_description = list(carry_description)
            carry_area = []
            carry_address = []
            carry_description = []
            post_area = []
            post_address = []
            post_description = []
            for continuation in body[index + 1:next_index]:
                area_part, address_part, description_part = _order_segments(
                    continuation, address_start, description_start
                )
                address_part, description_part = _repair_order_boundary(
                    address_part, description_part
                )
                if area_part:
                    post_area.append(area_part)
                if address_part:
                    post_address.append(address_part)
                if description_part:
                    post_description.append(description_part)

            if not address and post_address:
                address = post_address.pop(0)
            address = clean(" ".join(prefix_address + ([address] if address else [])))
            if not description and post_description:
                description = post_description.pop(0)
            while (
                description
                and post_description
                and _description_needs_continuation(description, post_description[0])
            ):
                description = clean(f"{description} {post_description.pop(0)}")
            description = clean(
                " ".join(prefix_description + ([description] if description else []))
            )
            carry_area = post_area
            carry_address = post_address
            carry_description = post_description
            if not area or not address or not description:
                raise ValueError(
                    f"unnumbered 2018 order row {len(rows) + 1} is incomplete"
                )
            annual_rent, rent_text = _rent_fields(description)
            order_position = len(rows) + 1
            rows.append({
                "identity_key": f"order-{order_position:03d}",
                "lot_number": None,
                "catalogue_order_position": order_position,
                "address": clean(f"{address}, {area}"),
                "locality": area,
                "property_type": description,
                "description": description,
                "annual_rent": annual_rent,
                "rent_text": rent_text,
                "status": "unknown",
            })
        carry_area = []
        carry_address = []
        carry_description = []
    if len(rows) != expected_rows:
        raise ValueError(
            f"unnumbered order inventory mismatch: expected={expected_rows} actual={len(rows)}"
        )
    return rows


def parse_numbered_order_sheet(text: str, expected_labels) -> dict[str, dict]:
    """Parse a numbered fixed-column order sheet including guide/status cells."""
    expected = {normalize_label(label) for label in expected_labels}
    rows = {}
    carry_locality = []
    for page in text.split("\f"):
        lines = page.splitlines()
        header_index = next(
            (
                index for index, line in enumerate(lines)
                if re.search(r"\bLOT\b", line)
                and re.search(r"\bAREA\b", line)
                and re.search(r"\bADDRESS\b", line)
                and re.search(r"\bDESCRIPTION\b", line)
                and re.search(r"\bGUIDE PRICE\b", line)
            ),
            None,
        )
        if header_index is None:
            continue
        header = lines[header_index]
        area_start = header.index("AREA")
        address_start = header.index("ADDRESS")
        description_start = header.index("DESCRIPTION")
        guide_start = header.index("GUIDE PRICE")
        body = lines[header_index + 1:]
        starts = []
        for index, line in enumerate(body):
            match = re.match(r"^\s*(\d+[A-Za-z]?)\s+", line)
            if match and match.start(1) < area_start:
                starts.append((index, match))

        carry_locality = []
        for position, (index, match) in enumerate(starts):
            next_index = starts[position + 1][0] if position + 1 < len(starts) else len(body)
            label = normalize_label(match.group(1))
            if label not in expected or label in rows:
                raise ValueError(f"unexpected or duplicate order-sheet lot {label}")
            line = body[index]
            locality = clean(
                " ".join(carry_locality + [clean(line[match.end():address_start]) or ""])
            )
            carry_locality = []
            address = clean(line[address_start:description_start])
            tail = clean(line[description_start:]) or ""
            guide_match = re.search(
                r"(£\s*[\d,]+(?:\s*[-\u00ad]\s*£\s*[\d,]+)?\s*\+?"
                r"|No Reserve|SOLD PRIOR|POSTPONED)\s*$",
                tail,
                re.I,
            )
            if not guide_match:
                raise ValueError(f"order-sheet lot {label} has no terminal guide/status cell")
            description = clean(tail[:guide_match.start()])
            guide_text = clean(guide_match.group(1))
            after_notes = False
            for continuation in body[index + 1:next_index]:
                if continuation.strip().upper().startswith("NOTES:"):
                    after_notes = True
                    continue
                locality_part = clean(continuation[area_start:address_start])
                address_part = clean(continuation[address_start:description_start])
                description_part = clean(continuation[description_start:guide_start])
                guide_part = clean(continuation[guide_start:])
                if after_notes:
                    if locality_part and not address_part and not description_part and not guide_part:
                        carry_locality.append(locality_part)
                    continue
                address = clean(" ".join(filter(None, [address, address_part])))
                description = clean(" ".join(filter(None, [description, description_part])))
                guide_text = clean(" ".join(filter(None, [guide_text, guide_part])))
            if not locality or not address or not description or not guide_text:
                raise ValueError(f"order-sheet lot {label} has an incomplete published row")
            parsed_guide = parse_guide_text(guide_text)
            status = "unknown"
            if guide_text.casefold() == "sold prior":
                status = "sold prior"
            elif guide_text.casefold() == "postponed":
                status = "postponed"
            if status != "unknown":
                parsed_guide["guide_observation"] = False
            annual_rent, rent_text = _rent_fields(description)
            rows[label] = {
                "identity_key": label,
                "lot_number": label,
                "address": clean(f"{address}, {locality}"),
                "locality": locality,
                "property_type": description,
                "description": description,
                "annual_rent": annual_rent,
                "rent_text": rent_text,
                "status": status,
                **parsed_guide,
            }
        carry_locality = []
    validate_labels(rows, expected, "2018 numbered order sheet")
    return rows


def parse_combined_order(text: str, expected_labels, auction_date: str | None = None) -> dict[str, dict]:
    """Parse every explicit order-of-sale row in the retained 2018 layout.

    The table sometimes prints a wrapped address immediately above its numbered
    row.  The address and description columns are therefore taken from the
    publisher's fixed layout, with narrowly bounded continuation handling.
    """
    expected = {normalize_label(label) for label in expected_labels}
    rows = {}
    carry_address = []
    carry_description = []
    for page in text.split("\f"):
        lines = page.splitlines()
        header_index = next(
            (
                index for index, line in enumerate(lines)
                if re.search(r"\bLOT\b", line)
                and re.search(r"\bAREA\b", line)
                and re.search(r"\bADDRESS\b", line)
                and re.search(r"\bDESCRIPTION\b", line)
            ),
            None,
        )
        if header_index is None:
            continue
        header = lines[header_index]
        address_start = header.index("ADDRESS")
        # The body column begins one cell left of the printed heading in both
        # retained 2018 table variants.
        description_start = header.index("DESCRIPTION") - 1
        body = lines[header_index + 1:]
        starts = []
        for index, line in enumerate(body):
            match = re.match(r"^\s*(\d+[A-Za-z]?)\s+", line)
            if (
                match
                and match.start(1) < address_start
                and normalize_label(match.group(1)) in expected
            ):
                starts.append((index, match))

        carry_address = []
        carry_description = []
        if starts:
            for prelude in body[:starts[0][0]]:
                _, address_part, description_part = _order_segments(
                    prelude, address_start, description_start
                )
                address_part, description_part = _repair_order_boundary(
                    address_part, description_part
                )
                if address_part:
                    carry_address.append(address_part)
                if description_part:
                    carry_description.append(description_part)

        for position, (index, match) in enumerate(starts):
            label = normalize_label(match.group(1))
            if label in rows:
                raise ValueError(f"duplicate 2018 order row for lot {label}")
            next_index = starts[position + 1][0] if position + 1 < len(starts) else len(body)
            line = body[index]
            locality = clean(line[match.end():address_start])
            address, description = _repair_order_boundary(
                line[address_start:description_start], line[description_start:]
            )

            prefix_address = list(carry_address)
            prefix_description = list(carry_description)
            carry_address = []
            carry_description = []
            post_address = []
            post_description = []
            for continuation in body[index + 1:next_index]:
                left, address_part, description_part = _order_segments(
                    continuation, address_start, description_start
                )
                address_part, description_part = _repair_order_boundary(
                    address_part, description_part
                )
                if address_part and address_part.startswith("£"):
                    description_part = clean(f"{address_part}{description_part or ''}")
                    address_part = None
                # Text left of ADDRESS is a wrapped locality only when both
                # property columns are empty; retain it without guessing.
                if left and not address_part and not description_part:
                    locality = clean(f"{locality or ''} {left}")
                if address_part:
                    post_address.append(address_part)
                if description_part:
                    post_description.append(description_part)

            # A blank address row takes the first following address fragment.
            # A short street suffix completes a prefix printed above the row.
            if not address and post_address:
                address = post_address.pop(0)
            if prefix_address and post_address and len(post_address[0]) <= 24:
                prefix_address.append(post_address.pop(0))
            address = clean(" ".join(prefix_address + ([address] if address else [])))

            # A row with no inline description owns the first following
            # description fragment. Remaining fragments are the next row's
            # vertically centred prefix.
            if not description and post_description:
                description = post_description.pop(0)
            while description and post_description and not re.search(r"[.!?]$", description):
                description = clean(f"{description} {post_description.pop(0)}")
            description = clean(
                " ".join(prefix_description + ([description] if description else []))
            )
            carry_address = post_address
            carry_description = post_description
            if not address:
                raise ValueError(f"2018 order row {label} has no published address")
            annual_rent, rent_text = _rent_fields(description)
            row = {
                "lot_number": label,
                "address": clean(f"{address}, {locality}") if locality else address,
                "locality": locality,
                "property_type": description,
                "description": description,
                "annual_rent": annual_rent,
                "rent_text": rent_text,
            }
            transcription = COMBINED_TRANSCRIPTIONS.get((auction_date, label), {})
            row.update(transcription)
            if "description" in transcription:
                row["property_type"] = transcription["description"]
                description = transcription["description"]
                annual = re.search(r"£\s*([\d,]+)\s*p\s*[/\.\s]?\s*a\.?,?", description, re.I)
                if annual:
                    row["annual_rent"] = money(annual.group(1))
                    row["rent_text"] = description
            rows[label] = row
        carry_address = []
        carry_description = []
    validate_labels(rows, expected, "2018 combined order")
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


def make_row(source_row: dict, source_url: str, evidence: dict, catalogue: dict) -> dict:
    label = source_row.get("lot_number")
    identity_key = source_row.get("identity_key") or label
    if not identity_key:
        raise ValueError("catalogue row has no stable source identity")
    address = source_row["address"]
    description = source_row.get("description")
    property_type = source_row.get("property_type")
    event_id = catalogue["event_id"]
    event_date = catalogue["date"]
    row = corpus.base_row(SOURCE, event_id, event_date, label, identity_key, source_url)
    postcode = compact_postcode(address)
    if postcode and postcode.replace(" ", "") in address and postcode not in address:
        address = address.replace(postcode.replace(" ", ""), postcode)
    row.update(
        appearance_id=(
            f"{SOURCE}|{event_id}|entry:{identity_key}"
            if label is None
            else f"{SOURCE}|{event_id}|lot:{label}"
        ),
        address=address,
        postcode=postcode,
        locality=source_row.get("locality"),
        sector=corpus.sector(f"{property_type or ''} {description or ''}"),
        property_type=property_type,
        description=description,
        guide_price=source_row.get("guide_price"),
        guide_price_high=source_row.get("guide_price_high"),
        guide_plus=source_row.get("guide_plus", False),
        guide_text=source_row.get("guide_text"),
        guide_observation=source_row.get("guide_observation"),
        annual_rent=source_row.get("annual_rent"),
        rent_text=source_row.get("rent_text"),
        status=source_row.get("status") or "unknown",
        property_id=None,
        identity_method=(
            "exact_auction_date_catalogue_and_published_order_position"
            if catalogue["format"] == "unnumbered_combined_2018"
            else "exact_auction_date_catalogue_and_published_lot_number"
        ),
        catalogue_order_position=source_row.get("catalogue_order_position"),
        record_quality="address_record",
        auction_date_basis=(
            "exact date printed on the cover of the retained first-party catalogue; "
            "additional-lot evidence, where present, is linked to that event in the first-party archive"
        ),
        source_evidence=evidence,
    )
    if catalogue["format"] == "split_2014":
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


def expected_catalogue_rows(catalogue: dict) -> int:
    if catalogue["format"] == "split_2014":
        return len(catalogue["expected_residential"]) + len(catalogue["expected_additional"])
    if catalogue["format"] == "unnumbered_combined_2018":
        return catalogue["expected_rows"]
    return len(catalogue["expected_lots"])


def collection_is_current(summary: dict, rows: list[dict], root: Path) -> bool:
    """Prove a configured batch is already banked without refreshing sources."""
    expected_by_date = {
        catalogue["date"]: expected_catalogue_rows(catalogue)
        for catalogue in CATALOGUES
    }
    expected = sum(expected_by_date.values())
    expected_banked = expected - len(summary.get("duplicate_evidence") or [])
    if (
        summary.get("parser_version") != PARSER_VERSION
        or summary.get("catalogues_configured") != len(CATALOGUES)
        or summary.get("catalogues_banked") != len(CATALOGUES)
        or summary.get("appearances_banked") != expected_banked
        or len(rows) != expected_banked
        or len({row.get("appearance_id") for row in rows}) != expected_banked
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
            or state.get("published_lots_in_surviving_files") != expected_by_date[catalogue["date"]]
            or (
                state.get("lots_captured", 0)
                + state.get("duplicate_exact_date_address_evidence", 0)
                != expected_by_date[catalogue["date"]]
            )
        ):
            return False
    source_files = summary.get("source_files") or []
    expected_files = sum(2 if item["format"] == "split_2014" else 1 for item in CATALOGUES)
    if len(source_files) != expected_files:
        return False
    for evidence in source_files:
        try:
            relative_paths = evidence.get("snapshot_parts") or [evidence["snapshot_path"]]
            compressed = b"".join((root / path).read_bytes() for path in relative_paths)
            raw = gzip.decompress(compressed)
        except (KeyError, OSError, gzip.BadGzipFile):
            return False
        if hashlib.sha256(raw).hexdigest() != evidence.get("sha256"):
            return False
    return True


def harvest() -> dict:
    target_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    summary_path = corpus.DATA / "edward_mellor_catalogue_collection.json"
    saved_summary = {}
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
                run_new_guide_observations=0,
                run_new_sale_prices=0,
                run_new_published_outcomes=0,
                run_new_rents=0,
                run_new_commercial=0,
                run_new_mixed_use=0,
                run_new_land=0,
                run_new_residential=0,
                run_new_unknown_sector=0,
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
        parsed_date = date.fromisoformat(catalogue["date"])
        if catalogue["event_id"] != f"edward-mellor-catalogue:{parsed_date.isoformat()}":
            raise ValueError("configured event identity does not agree with its exact date")
        if catalogue["format"] == "split_2014":
            (
                residential_raw,
                residential_resolved,
                residential_snapshots,
                residential_sha,
                residential_retrieved_at,
            ) = retained_or_fetched_pdf(catalogue["residential_url"], saved_summary)
            (
                additional_raw,
                additional_resolved,
                additional_snapshots,
                additional_sha,
                additional_retrieved_at,
            ) = retained_or_fetched_pdf(catalogue["additional_url"], saved_summary)
            residential_text = extract_pdf_text(residential_raw)
            additional_text = extract_pdf_text(additional_raw)
            if "11th June 2014" not in residential_text[:2500]:
                raise ValueError("residential catalogue does not print the configured exact event date")
            residential = parse_residential_order(residential_text)
            residential_guides = parse_guides(residential_text)
            validate_labels(residential, catalogue["expected_residential"], "residential order")
            unexpected = set(residential_guides) - set(residential)
            if unexpected:
                raise ValueError(f"residential detail guides outside order: {sorted(unexpected)}")
            for label, row in residential.items():
                if label in residential_guides:
                    low, high, plus = residential_guides[label]
                    row.update(guide_price=low, guide_price_high=high, guide_plus=plus)
            additional = parse_additional_rows(additional_text)
            validate_labels(additional, catalogue["expected_additional"], "additional details")
            residential_evidence = {
                "source_url": residential_resolved,
                "retrieved_at": residential_retrieved_at,
                "sha256": residential_sha,
                "basis": "first-party residential auction catalogue PDF",
                **snapshot_fields(residential_snapshots),
            }
            additional_evidence = {
                "source_url": additional_resolved,
                "retrieved_at": additional_retrieved_at,
                "sha256": additional_sha,
                "basis": "first-party additional-lot catalogue PDF",
                **snapshot_fields(additional_snapshots),
            }
            source_files.extend([residential_evidence, additional_evidence])
            candidates = [
                make_row(row, residential_resolved, residential_evidence, catalogue)
                for row in residential.values()
            ] + [
                make_row(row, additional_resolved, additional_evidence, catalogue)
                for row in additional.values()
            ]
            order_rows = len(residential) + len(additional)
            missing_guides = sorted(set(residential) - set(residential_guides))
            completion_scope = (
                "every explicit numbered property in the retained June 2014 residential "
                "and additional-lot PDFs; the absent main commercial catalogue is not inferred"
            )
        elif catalogue["format"] == "combined_2018":
            raw, resolved, snapshots, sha, retrieved_at = retained_or_fetched_pdf(
                catalogue["url"], saved_summary
            )
            text = extract_pdf_text(raw)
            if catalogue["printed_date"] not in text[:1000]:
                raise ValueError("combined catalogue does not print the configured exact event date")
            combined = parse_combined_order(
                text, catalogue["expected_lots"], auction_date=catalogue["date"]
            )
            guides = parse_combined_guides(text)
            validate_labels(guides, catalogue["expected_lots"], "2018 combined detail guides")
            for label, row in combined.items():
                low, high, plus = guides[label]
                row.update(guide_price=low, guide_price_high=high, guide_plus=plus)
            evidence = {
                "source_url": resolved,
                "retrieved_at": retrieved_at,
                "sha256": sha,
                "basis": "first-party combined all-sector auction catalogue PDF",
                **snapshot_fields(snapshots),
            }
            source_files.append(evidence)
            candidates = [make_row(row, resolved, evidence, catalogue) for row in combined.values()]
            order_rows = len(combined)
            missing_guides = []
            completion_scope = (
                "every explicit numbered property in the retained combined all-sector catalogue; "
                "no corresponding result sheet survives in the first-party archive, so outcomes remain unknown"
            )
        else:
            raw, resolved, snapshots, sha, retrieved_at = retained_or_fetched_pdf(
                catalogue["url"], saved_summary
            )
            text = extract_pdf_text(raw)
            if catalogue["printed_date"] not in text[:2500]:
                raise ValueError("catalogue does not print the configured exact event date")
            if catalogue["format"] == "unnumbered_combined_2018":
                parsed_rows = parse_unnumbered_combined_order(
                    text, catalogue["expected_rows"]
                )
                guides = parse_unnumbered_guides(text, catalogue["expected_rows"])
                for row, guide in zip(parsed_rows, guides, strict=True):
                    row.update(guide)
                completion_scope = (
                    "every property in the retained ordered all-sector catalogue and its "
                    "same-order detail-page guide; the publisher prints order positions but "
                    "no lot labels, so stable order identities are retained without inventing lot numbers"
                )
            elif catalogue["format"] == "numbered_order_2018":
                numbered = parse_numbered_order_sheet(text, catalogue["expected_lots"])
                parsed_rows = list(numbered.values())
                completion_scope = (
                    "every explicit numbered property in the retained first-party order-of-sale "
                    "catalogue, including published sold-prior and postponed outcomes"
                )
            else:
                raise ValueError(f"unsupported catalogue format {catalogue['format']}")
            evidence = {
                "source_url": resolved,
                "retrieved_at": retrieved_at,
                "sha256": sha,
                "basis": "first-party all-sector auction catalogue PDF",
                **snapshot_fields(snapshots),
            }
            source_files.append(evidence)
            candidates = [make_row(row, resolved, evidence, catalogue) for row in parsed_rows]
            order_rows = len(parsed_rows)
            missing_guides = [
                row.get("lot_number") or row.get("identity_key")
                for row in parsed_rows
                if not row.get("guide_observation")
            ]
        if len({row["appearance_id"] for row in candidates}) != len(candidates):
            raise ValueError("event contains duplicate appearance IDs")
        event_duplicate_count = 0
        for row in candidates:
            signature = (
                row["auction_date"],
                re.sub(r"[^a-z0-9]+", "", row["address"].casefold()),
            )
            if signature in exact_signatures:
                duplicate_evidence.append({
                    "auction_date": row["auction_date"],
                    "lot_number": row["lot_number"],
                    "address": row["address"],
                    "source_url": row["original_url"],
                })
                event_duplicate_count += 1
                continue
            all_rows.append(row)

        event_state = {
            "auctioneer": SOURCE,
            "source_auction_id": catalogue["event_id"],
            "auction_date": catalogue["date"],
            "parser_version": PARSER_VERSION,
            "catalogue_complete": catalogue["format"] != "split_2014",
            "source_files_reconciled": True,
            "surviving_file_inventory_complete": True,
            "event_inventory_complete": catalogue["format"] != "split_2014",
            "lots_captured": len(candidates) - event_duplicate_count,
            "published_lots_in_surviving_files": len(candidates),
            "order_rows_reconciled": order_rows,
            "guide_prices_captured": sum(row.get("guide_price") is not None for row in candidates),
            "published_guide_observations": sum(
                bool(row.get("guide_observation") or row.get("guide_price") is not None)
                for row in candidates
            ),
            "sale_prices_captured": 0,
            "published_outcomes_captured": sum(row.get("status") != "unknown" for row in candidates),
            "rents_captured": sum(row.get("annual_rent") is not None for row in candidates),
            "duplicate_exact_date_address_evidence": event_duplicate_count,
            "missing_detail_guides": missing_guides,
            "completion_scope": completion_scope,
            "errors": [],
            "checked_at": corpus.now(),
        }
        event_states.append(event_state)
        state_path = corpus.DATA / "auctions" / SLUG / f"{catalogue['date']}.json"
        corpus.save_json(state_path, event_state)

    total = corpus.write_rows(f"{SLUG}/canonical", all_rows, preserve_existing=True)
    current_ids = {row["appearance_id"] for row in all_rows}
    added_ids = current_ids - existing_ids
    added = [row for row in all_rows if row["appearance_id"] in added_ids]
    last_material_growth = saved_summary.get("last_material_growth")
    if added:
        last_material_growth = {
            "checked_at": corpus.now(),
            "net_new_appearances": len(added),
            "new_address_records": sum(row.get("address") is not None for row in added),
            "new_guides": sum(row.get("guide_price") is not None for row in added),
            "new_guide_observations": sum(
                bool(row.get("guide_observation", row.get("guide_price") is not None))
                for row in added
            ),
            "new_sale_prices": sum(row.get("sale_price") is not None for row in added),
            "new_published_outcomes": sum(row.get("status") != "unknown" for row in added),
            "new_rents": sum(row.get("annual_rent") is not None for row in added),
            "new_commercial": sum(row.get("sector") == "commercial" for row in added),
            "new_mixed_use": sum(row.get("sector") == "mixed-use" for row in added),
            "new_land": sum(row.get("sector") == "land" for row in added),
            "new_residential": sum(row.get("sector") == "residential" for row in added),
            "new_unknown_sector": sum(row.get("sector") == "unknown" for row in added),
            "new_partial": sum(row.get("record_quality") != "address_record" for row in added),
            "new_undated": sum(not row.get("auction_date") for row in added),
            "new_future_dated": sum(
                bool(row.get("auction_date") and row["auction_date"] > date.today().isoformat())
                for row in added
            ),
        }
    summary = {
        "checked_at": corpus.now(),
        "parser_version": PARSER_VERSION,
        "catalogues_configured": len(CATALOGUES),
        "catalogues_banked": len(event_states),
        "appearances_banked": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(row.get("address") is not None for row in added),
        "run_new_guides": sum(row.get("guide_price") is not None for row in added),
        "run_new_guide_observations": sum(
            bool(row.get("guide_observation", row.get("guide_price") is not None))
            for row in added
        ),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_published_outcomes": sum(row.get("status") != "unknown" for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use": sum(row.get("sector") == "mixed-use" for row in added),
        "run_new_land": sum(row.get("sector") == "land" for row in added),
        "run_new_residential": sum(row.get("sector") == "residential" for row in added),
        "run_new_unknown_sector": sum(row.get("sector") == "unknown" for row in added),
        "run_duplicate_evidence": len(duplicate_evidence),
        "duplicate_evidence": duplicate_evidence,
        "last_material_growth": last_material_growth,
        "source_files": source_files,
        "events": event_states,
        "national_coverage_complete": False,
        "next_growth_target": (
            "Batch the surviving September, October and December 2018 Edward Mellor catalogues "
            "through this runner, reconciling each complete order inventory and preserving "
            "published outcomes separately from guide and achieved-price evidence."
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
