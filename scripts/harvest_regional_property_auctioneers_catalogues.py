"""Bank Regional Property Auctioneers' retained first-party catalogues.

The official catalogue page retains a large multi-year PDF archive.  The PDFs
were produced by repeatedly editing a shared template, so native extraction can
surface hidden stale property text from older editions.  Admission is therefore
anchored only to the printed, contiguous order-of-sale table in each catalogue.
Matching detail panels may enrich guides and rents, but can never create rows.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from difflib import SequenceMatcher
import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Regional Property Auctioneers"
SLUG = "regional-property-auctioneers"
OPERATOR = "BARNSDALES LIMITED"
COMPANY_NUMBER = "05521957"
ARCHIVE = "https://www.regionalpropertyauctioneers.co.uk/catalogue"
MANIFEST = corpus.ROOT / "config" / "regional_property_auctioneers_catalogues.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
ORDER_HEADING = re.compile(r"(?:Order\s+of\s+sale|Lot\s+Order\s+and\s+Guide\s+Prices)", re.I)
GUIDE_ORDER_HEADING = re.compile(r"Lot\s+Order\s+and\s+Guide\s+Prices", re.I)
ORDER_ROW = re.compile(r"^\s*Lot\s+(\d{1,3}[A-Za-z]?)\s+(\S.*?)\s{2,}(.+?)\s*$", re.I)
FALLBACK_ORDER_ROW = re.compile(r"^\s*Lot\s+(\d{1,3}[A-Za-z]?)\s+(.+)$", re.I)
RANGE_ORDER_ROW = re.compile(
    r"^\s*Lots?\s+(\d{1,3}(?:[–-]\d{1,3}[A-Za-z]?))\s+(\S.*?)\s{2,}(.+?)\s*$",
    re.I,
)
LEGACY_GUIDE_ROW = re.compile(
    r"^\s*LOT\s+(\d{1,3}[A-Za-z]?)\s+(.+?)\s{2,}((?:£\s*[\d,]+(?:\.\d+)?(?:\s*[-–]\s*£?\s*[\d,]+(?:\.\d+)?)?\+?)|SOLD\s+PRIOR)\s*$",
    re.I,
)
NUMBERED_ORDER_ROW = re.compile(r"^\s*(\d{1,3}[A-Za-z]?)\s+(\S.*)$")
ORDER_TYPE_START = re.compile(
    r"\s+(?=(?:VACANT|RESIDENTIAL|COMMERCIAL|MIXED|DEVELOPMENT|INDUSTRIAL|TAKEAWAY|"
    r"RESTAURANT|RENOVATION|LAND)\b)",
    re.I,
)
# Keep immutable binary evidence parts below connector transport limits as well as
# GitHub's blob limit. Reassembly is byte-for-byte and the original PDF digest is
# checked before a retained snapshot is reused.
MAX_SNAPSHOT_PART_BYTES = 700_000
SECTOR_SUFFIX = re.compile(
    r"\s+((?:(?:VACANT|RESIDENTIAL|COMMERCIAL|COMM|RESI|MIXED|LAND|GROUND|GARAGE|LOCK|LOCKUP|"
    r"FORMER|BUILDING|INDUSTRIAL|CHURCH|AMENITY|DEVELOPMENT|INVESTMENT|PLOT|PREMISES|PUB|"
    r"MOBILE|HOME|LODGE|CONVERSION|OPPORTUNITY|WITH|PLANNING|SITE|SCHOOL|COMMUNITY|BUNKER|UP|"
    r"AGRICULTURAL|PROPERTY|&|/|-)(?:\s+|$))+)$"
)
DETAIL_START = re.compile(r"(?im)^\s*lot\b")
GUIDE_LABEL = re.compile(r"(?i)\*?\s*guide\s+price\s*:?")
MONEY = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
RENT = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?\s*a\.?)\b", re.I
)
NEXT_TARGET = (
    "Batch Halls' retained 2022 Collective Property & Land catalogues and result sheets through the "
    "existing multi-event runner, preserving complete numbered inventories and leaving any unnamed "
    "denominator gaps explicit. Do not refresh the exhausted Regional Property Auctioneers archive. "
    "National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def fetch(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=120)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def load_manifest(path=MANIFEST):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    events = payload.get("events") or []
    expected_catalogues = int(payload["expected_catalogues"])
    expected_lots = int(payload["expected_lots"])
    if len(events) != expected_catalogues:
        raise ValueError(f"expected {expected_catalogues} catalogue PDFs, found {len(events)}")
    if sum(int(event["expected_lots"]) for event in events) != expected_lots:
        raise ValueError(f"manifest must retain the literal {expected_lots}-lot denominator")
    if len({event["source_url"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate catalogue URLs")
    if len({event["auction_date"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate auction dates")
    return payload


def discover_catalogue_pdfs(html, archive_url=ARCHIVE):
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(archive_url, anchor["href"])
        if url.lower().endswith(".pdf") and "addendum" not in url.lower():
            found.add(url)
    if len(found) < 50:
        raise ValueError(f"official catalogue page exposes only {len(found)} catalogue PDFs")
    return found


def pdf_text(raw):
    if not raw.startswith(b"%PDF-"):
        raise ValueError("catalogue link did not return a PDF")
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for layout-preserving catalogue extraction")
    with tempfile.TemporaryDirectory(prefix="regional-catalogue-") as directory:
        source = Path(directory) / "catalogue.pdf"
        output = Path(directory) / "catalogue.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(output)],
            check=True, capture_output=True, timeout=180,
        )
        text = output.read_text(errors="replace").replace("\x03", "")
    if len(text.strip()) < 500:
        raise ValueError("catalogue PDF contains no usable layout text")
    return text


def parse_fallback_order_row(line):
    match = FALLBACK_ORDER_ROW.match(line)
    if not match:
        return None
    lot_number, remainder = match.groups()
    postcode_matches = list(corpus.PC.finditer(remainder))
    if postcode_matches:
        postcode = postcode_matches[-1]
        address = clean(remainder[:postcode.end()])
        property_type = clean(remainder[postcode.end():])
    else:
        sector = SECTOR_SUFFIX.search(remainder)
        if not sector:
            return None
        address = clean(remainder[:sector.start()])
        property_type = clean(sector.group(1))
    if not address or not property_type:
        return None
    return lot_number, address, property_type


def parse_legacy_guide_rows(page):
    rows = []
    for line in page.splitlines():
        match = LEGACY_GUIDE_ROW.match(line)
        if not match:
            continue
        lot_number, address, order_value = match.groups()
        status = "sold_prior" if re.search(r"sold\s+prior", order_value, re.I) else "unknown"
        low, high = parse_guide(order_value)
        rows.append({
            "lot_number": clean(lot_number),
            "printed_lot_label": clean(lot_number),
            "address": clean(address),
            "property_type": None,
            "status": status,
            "source_order_outcome": clean(order_value) if status != "unknown" else None,
            "source_guide_text": clean(order_value) if low is not None else None,
            "guide_price": low,
            "guide_price_high": high,
        })
    return rows


def parse_numbered_order_rows(page):
    lines = page.splitlines()
    heading = next(index for index, line in enumerate(lines) if ORDER_HEADING.search(line))
    chunks, current = [], None
    for line in lines[heading + 1:]:
        if "regionalpropertyauctioneers.co.uk" in line.casefold() or "how to find our auction venue" in line.casefold():
            break
        match = NUMBERED_ORDER_ROW.match(line)
        if match:
            if current:
                chunks.append(current)
            current = [match.group(1), match.group(2), []]
        elif current and clean(line) and clean(line) != "2":
            current[2].append(line)
    if current:
        chunks.append(current)

    rows = []
    for lot_number, first, continuation in chunks:
        status, source_outcome = "unknown", None
        address_parts, type_parts = [], []
        for index, source_line in enumerate([first, *continuation]):
            raw_line = source_line.replace("\x07", " ").rstrip()
            status_match = re.search(r"\b(postponed\s+to\s+september|sold\s+prior)\b", raw_line, re.I)
            if status_match:
                source_outcome = clean(status_match.group())
                status = "postponed" if source_outcome.casefold().startswith("postponed") else "sold_prior"
                raw_line = raw_line[:status_match.start()] + " " + raw_line[status_match.end():]
            leading = len(raw_line) - len(raw_line.lstrip())
            content = raw_line.strip()
            if not content:
                continue
            split = re.split(r"\t+|\s{2,}", content, maxsplit=1)
            if len(split) == 2:
                address_part, type_part = split
            elif index > 0 and (leading >= 45 or (content.startswith("(") and type_parts)):
                address_part, type_part = None, content
            else:
                boundary = ORDER_TYPE_START.search(content)
                address_part = clean(content[:boundary.start()]) if boundary else content
                type_part = clean(content[boundary.start():]) if boundary else None
            if address_part:
                address_parts.append(address_part)
            if type_part:
                type_parts.append(type_part)
        address = clean(" ".join(address_parts))
        property_type = clean(" ".join(type_parts))
        if not address:
            raise ValueError(f"numbered order row {lot_number} has no address")
        rows.append({
            "lot_number": clean(lot_number),
            "printed_lot_label": clean(lot_number),
            "address": address,
            "property_type": property_type,
            "status": status,
            "source_order_outcome": source_outcome,
        })
    return rows


def parse_order_rows(text, expected):
    pages = [page for page in text.split("\f") if ORDER_HEADING.search(page)]
    if not pages:
        raise ValueError("catalogue has no printed order-of-sale table")
    page = max(
        pages,
        key=lambda value: len(re.findall(r"(?im)^\s*(?:lots?\s+)?\d+[A-Za-z]?\s+", value)),
    )
    if GUIDE_ORDER_HEADING.search(page):
        rows = parse_legacy_guide_rows(page)
    elif re.search(r"(?m)^\s*\d+[A-Za-z]?\s+\S", page):
        rows = parse_numbered_order_rows(page)
    else:
        rows = []
    if rows:
        return validate_order_rows(rows, expected)
    lines = page.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"(?i)^\s*lots?\s+\d+\b", line):
            continue
        range_match = RANGE_ORDER_ROW.match(line)
        match = ORDER_ROW.match(line)
        parsed = range_match.groups() if range_match else match.groups() if match else parse_fallback_order_row(line)
        if not parsed and index + 1 < len(lines):
            combined = line.rstrip() + "    " + clean(lines[index + 1])
            match = ORDER_ROW.match(combined)
            parsed = match.groups() if match else parse_fallback_order_row(combined)
        if not parsed:
            # Introductory prose in some older PDFs starts with “LOT 1,”.  It
            # is not an order row and is excluded; the literal denominator
            # assertion below still prevents a silent omission.
            continue
        lot_number, address, property_type = parsed
        labels = [clean(lot_number)]
        if range_match:
            start, end = re.split(r"[–-]", lot_number)
            end_number = int(re.match(r"\d+", end).group())
            labels = [str(value) for value in range(int(start), end_number + 1)]
            if end[-1:].isalpha():
                if int(start) == end_number:
                    labels.append(end)
                else:
                    labels[-1] = end
        for label in labels:
            rows.append({
                "lot_number": label,
                "printed_lot_label": clean(lot_number),
                "address": clean(address),
                "property_type": clean(property_type),
            })
    return validate_order_rows(rows, expected)


def validate_order_rows(rows, expected):
    if len(rows) != expected:
        raise ValueError(f"order-of-sale table yielded {len(rows)} lots; expected {expected}")
    labels = [row["lot_number"].casefold() for row in rows]
    if len(labels) != len(set(labels)):
        raise ValueError(f"order-of-sale labels are not unique: {labels}")
    numeric = [int(label) for label in labels if label.isdigit()]
    if numeric != list(range(1, max(numeric) + 1)):
        raise ValueError(f"numeric order-of-sale labels are not contiguous: {labels}")
    # Two lot numbers can intentionally describe separate legal interests at
    # the same printed address (for example two land parcels).  Lot identity,
    # not address uniqueness, is the catalogue denominator.
    return rows


def parse_guide(raw):
    values = [corpus.money(value) for value in MONEY.findall(raw or "")]
    values = [value for value in values if value is not None]
    return (
        values[0] if values else None,
        values[1] if len(values) > 1 else None,
    )


def detail_blocks(text):
    blocks = []
    for page_number, page in enumerate(text.split("\f"), 1):
        starts = list(DETAIL_START.finditer(page))
        for index, marker in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(page)
            block = page[marker.start():end]
            guide = GUIDE_LABEL.search(block)
            if not guide or guide.start() > 700:
                continue
            prefix = block[marker.end() - marker.start():guide.start()]
            lines = [clean(line) for line in prefix.splitlines() if clean(line)]
            address = clean(" ".join(lines))
            suffix = block[guide.end():]
            guide_raw = next((clean(line) for line in suffix.splitlines() if clean(line)), None)
            if (
                not address or len(address) > 280 or len(lines) > 4
                or not guide_raw or not ("£" in guide_raw or "NIL" in guide_raw.upper())
                or "FULL PAGE FILLER" in address.upper()
            ):
                continue
            description_lines = [clean(line) for line in suffix.splitlines()[1:8] if clean(line)]
            description = clean(" ".join(description_lines))
            rent_matches = [corpus.money(value) for value in RENT.findall(block)]
            annual_rent = next((value for value in rent_matches if value is not None), None)
            blocks.append({
                "page_number": page_number,
                "address": address,
                "postcode": (corpus.PC.search(address).group().upper() if corpus.PC.search(address) else None),
                "guide_raw": guide_raw,
                "guide_price": parse_guide(guide_raw)[0],
                "guide_price_high": parse_guide(guide_raw)[1],
                "annual_rent": annual_rent,
                "rent_text": (f"£{int(annual_rent):,} per annum" if annual_rent else None),
                "description": description,
            })
    return blocks


def match_score(order_row, block):
    left, right = normalized(order_row["address"]), normalized(block["address"])
    left_postcode = corpus.PC.search(order_row["address"])
    right_postcode = block.get("postcode")
    postcode_bonus = 0.35 if left_postcode and right_postcode and left_postcode.group().upper() == right_postcode else 0
    left_tokens, right_tokens = set(left.split()), set(right.split())
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return min(1.0, 0.6 * SequenceMatcher(None, left, right).ratio() + 0.4 * token_score + postcode_bonus)


def enrich_order_rows(order_rows, blocks):
    used = set()
    enriched = []
    for row in order_rows:
        candidates = sorted(
            ((match_score(row, block), index, block) for index, block in enumerate(blocks) if index not in used),
            reverse=True, key=lambda item: item[0],
        )
        best = candidates[0] if candidates else None
        item = dict(row)
        if best and best[0] >= 0.57:
            score, index, block = best
            used.add(index)
            item.update({
                "guide_price": item.get("guide_price") if item.get("guide_price") is not None else block["guide_price"],
                "guide_price_high": item.get("guide_price_high") if item.get("guide_price_high") is not None else block["guide_price_high"],
                "source_guide_text": item.get("source_guide_text") or block["guide_raw"],
                "annual_rent": block["annual_rent"],
                "rent_text": block["rent_text"],
                "detail_match_score": round(score, 6),
                "detail_page_number": block["page_number"],
            })
            if not item.get("property_type"):
                item["property_type"] = block.get("description")
        else:
            item.update({
                "guide_price": item.get("guide_price"),
                "guide_price_high": item.get("guide_price_high"),
                "source_guide_text": item.get("source_guide_text"), "annual_rent": None,
                "rent_text": None, "detail_match_score": None,
                "detail_page_number": None,
            })
        enriched.append(item)
    return enriched


def validate_date(text, auction_date):
    year, month, day = auction_date.split("-")
    month_name = date(int(year), int(month), int(day)).strftime("%B")
    pattern = re.compile(
        rf"\b0?{int(day)}(?:st|nd|rd|th)?\s+{month_name}\s+{year}\b", re.I
    )
    if not pattern.search(text[:20000]):
        raise ValueError(f"exact auction date {auction_date} is absent from the catalogue front matter")


def materialize_event(config, resolved_url, evidence, text):
    validate_date(text, config["auction_date"])
    order_rows = parse_order_rows(text, int(config["expected_lots"]))
    rows = enrich_order_rows(order_rows, detail_blocks(text))
    auction_id = f"{SLUG}:{config['auction_date']}"
    materialized = []
    for position, item in enumerate(rows, 1):
        source_lot_id = f"lot:{item['lot_number']}"
        row = corpus.base_row(
            SOURCE, auction_id, config["auction_date"], item["lot_number"],
            source_lot_id, resolved_url,
        )
        postcode = corpus.PC.search(item["address"])
        property_evidence = f"{item.get('property_type') or ''} {item['address']}"
        residential = bool(re.search(r"\b(?:bedroom|terrace(?:d)?|cottage|bungalow|hmo)\b", property_evidence, re.I))
        commercial = bool(re.search(r"\b(?:commercial|shop|retail|office|industrial|warehouse|restaurant|takeaway|workshop)\b", property_evidence, re.I))
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
            address=item["address"],
            postcode=postcode.group().upper() if postcode else None,
            locality=item["address"],
            sector=corpus.sector(property_evidence, residential=residential, commercial=commercial),
            property_type=item["property_type"],
            status=item.get("status") or "unknown",
            guide_price=item["guide_price"],
            guide_price_high=item["guide_price_high"],
            annual_rent=item["annual_rent"],
            rent_text=item["rent_text"],
            description=item["property_type"],
            identity_method="first_party_exact_event_date_order_of_sale_lot_number_and_address",
            record_quality="address_record",
            source_position=position,
            source_guide_text=item["source_guide_text"],
            source_order_outcome=item.get("source_order_outcome"),
            detail_match_score=item["detail_match_score"],
            detail_page_number=item["detail_page_number"],
            source_event_url=resolved_url,
            auction_date_precision="day",
            auction_date_basis="exact date printed in first-party catalogue and linked from exact-year archive section",
            source_platform="Regional Property Auctioneers first-party catalogue archive",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name=SOURCE,
            source_evidence=evidence,
        )
        materialized.append(row)
    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "trading_name": SOURCE,
        "source_auction_id": auction_id,
        "auction_date": config["auction_date"],
        "auction_date_precision": "day",
        "source_url": resolved_url,
        "published_lots": len(materialized),
        "lots_captured": len(materialized),
        "guides_captured": sum(row["guide_price"] is not None for row in materialized),
        "rents_captured": sum(row["annual_rent"] is not None for row in materialized),
        "published_outcomes_captured": sum(row["status"] != "unknown" for row in materialized),
        "catalogue_complete": True,
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "denominator_basis": "contiguous numbered order-of-sale table in complete first-party catalogue PDF",
        "completion_scope": "every numbered property row in the printed order-of-sale table; hidden stale template text excluded",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, materialized


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer"),
                })
    return values


def reusable_states(events, existing, refresh_existing=False):
    if refresh_existing:
        return {}
    by_auction = defaultdict(list)
    for row in existing:
        by_auction[row.get("source_auction_id")].append(row)
    reusable = {}
    configured = {unquote(event["source_url"]): event["source_url"] for event in events}
    for path in (corpus.DATA / "auctions" / SLUG).glob("*.json"):
        state = json.loads(path.read_text(encoding="utf-8"))
        rows = by_auction.get(state.get("source_auction_id"), [])
        if (
            unquote(state.get("source_url") or "") in configured
            and state.get("source_rows_complete") is True
            and len(rows) == state.get("lots_captured")
        ):
            reusable[configured[unquote(state["source_url"])]] = (state, rows)
    return reusable


def retained_catalogue(auction_date):
    directory = corpus.DATA / "sources" / SLUG
    complete = sorted(directory.glob(f"catalogue-{auction_date}-*.pdf.gz"))
    if complete:
        path = complete[-1]
        return gzip.decompress(path.read_bytes()), {"snapshot_path": str(path.relative_to(corpus.ROOT))}
    parts = sorted(directory.glob(f"catalogue-{auction_date}-*.pdf.gz.part-*"))
    if not parts:
        return None
    prefixes = sorted({str(path).rsplit(".part-", 1)[0] for path in parts})
    selected = [Path(path) for path in parts if str(path).startswith(prefixes[-1] + ".part-")]
    return gzip.decompress(b"".join(path.read_bytes() for path in selected)), {
        "snapshot_parts": [str(path.relative_to(corpus.ROOT)) for path in selected],
        "snapshot_encoding": "concatenate parts, then gzip-decompress to recover the source PDF",
    }


def save_catalogue_snapshot(auction_date, raw, sha):
    path = corpus.DATA / "sources" / SLUG / f"catalogue-{auction_date}-{sha[:20]}.pdf.gz"
    compressed = gzip.compress(raw, mtime=0)
    paths = (
        [path]
        if len(compressed) <= MAX_SNAPSHOT_PART_BYTES
        else [
            Path(f"{path}.part-{index // MAX_SNAPSHOT_PART_BYTES + 1:03d}")
            for index in range(0, len(compressed), MAX_SNAPSHOT_PART_BYTES)
        ]
    )
    if all(item.exists() for item in paths):
        if corpus.digest(gzip.decompress(b"".join(item.read_bytes() for item in paths))) != sha:
            raise ValueError(f"immutable snapshot collision at {paths}")
    elif any(item.exists() for item in paths):
        raise ValueError(f"incomplete immutable snapshot parts at {paths}")
    else:
        for index, item in enumerate(paths):
            start = index * MAX_SNAPSHOT_PART_BYTES
            corpus.atomic(item, compressed[start:start + MAX_SNAPSHOT_PART_BYTES])
    if len(paths) == 1:
        return {"snapshot_path": str(paths[0].relative_to(corpus.ROOT))}
    return {
        "snapshot_parts": [str(item.relative_to(corpus.ROOT)) for item in paths],
        "snapshot_encoding": "concatenate parts, then gzip-decompress to recover the source PDF",
        "snapshot_compressed_bytes": len(compressed),
    }


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed" if not summary.get("failures") else "partial",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "halls-2022-retained-catalogues",
        "auctioneer": "Halls",
        "source_format": "retained first-party catalogue PDFs and result sheets",
        "opportunity": "batch Halls' surviving 2022 Collective Property & Land catalogues through the existing multi-event runner",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(refresh_existing=False):
    manifest = load_manifest()
    events = manifest["events"]
    archive_url, archive_raw = fetch(manifest.get("archive_url") or ARCHIVE)
    archive_sha, captured_at = corpus.digest(archive_raw), corpus.now()
    archive_snapshot = corpus.DATA / "sources" / SLUG / f"catalogue-index-{archive_sha[:20]}.html.gz"
    if not archive_snapshot.exists():
        corpus.atomic(archive_snapshot, gzip.compress(archive_raw, mtime=0))
    archive_evidence = {
        "source_url": archive_url, "retrieved_at": captured_at, "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party multi-year property-auction catalogue archive",
    }
    discovered = discover_catalogue_pdfs(archive_raw.decode("utf-8", "replace"), archive_url)
    configured = {event["source_url"] for event in events}
    if not configured <= discovered:
        raise ValueError(f"configured catalogue URLs absent from live archive: {sorted(configured - discovered)}")

    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    summary_path = corpus.DATA / "regional_property_auctioneers_collection.json"
    previous_summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists() else None
    )
    if previous_summary and previous_summary.get("failures"):
        baseline_ids = set(previous_summary.get("batch_baseline_appearance_ids", []))
    else:
        baseline_ids = {row["appearance_id"] for row in existing}
    reusable = reusable_states(events, existing, refresh_existing)
    states, run_rows, failures = {}, [], []
    for position, config in enumerate(events, 1):
        if config["source_url"] in reusable:
            state, rows = reusable[config["source_url"]]
            states[state["auction_date"]] = state
            run_rows.extend(rows)
            continue
        try:
            retained = retained_catalogue(config["auction_date"])
            if retained:
                raw, snapshot_fields = retained
                resolved = config["source_url"]
                retrieved_at = corpus.now()
            else:
                resolved, raw = fetch(config["source_url"])
                retrieved_at = corpus.now()
            sha = corpus.digest(raw)
            if not retained:
                snapshot_fields = save_catalogue_snapshot(config["auction_date"], raw, sha)
            evidence = {
                "source_url": resolved, "retrieved_at": retrieved_at, "sha256": sha,
                "basis": "complete first-party exact-dated property-auction catalogue PDF",
                "archive_evidence": archive_evidence,
                **snapshot_fields,
            }
            state, rows = materialize_event(config, resolved, evidence, pdf_text(raw))
            states[state["auction_date"]] = state
            corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)
            run_rows.extend(rows)
            print("REGIONAL", position, "/", len(events), "catalogues", len(run_rows), "lots", flush=True)
        except Exception as exc:
            failures.append({"url": config["source_url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    global_exact = global_exact_appearances()
    overlaps, admissible = [], []
    existing_ids = {row["appearance_id"] for row in existing}
    for row in run_rows:
        if row["appearance_id"] in existing_ids:
            admissible.append(row)
            continue
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({
                "auction_date": row["auction_date"], "lot_number": row["lot_number"],
                "address": row["address"], "existing": matches,
            })
        else:
            admissible.append(row)

    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in baseline_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    # A multi-attempt batch may already have banked some events in ``existing``.
    # Compare years with the preserved pre-batch appearance baseline so partial
    # retries do not suppress genuinely new source-years in the final report.
    years_before = {
        row["auction_date"][:4]
        for row in existing
        if row["appearance_id"] in baseline_ids and row.get("auction_date")
    }
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "source_url": ARCHIVE,
        "operator": {
            "canonical_trading_name": SOURCE, "legal_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "archive_catalogue_pdfs_discovered": len(discovered),
        "catalogue_pdfs_in_batch": len(events),
        "catalogue_pdfs_captured": len(states),
        "published_property_rows_reconciled": len(run_rows),
        "appearances_captured": total,
        "batch_baseline_appearance_ids": sorted(baseline_ids),
        "run_new_appearances": total - len(baseline_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use": sum(row.get("sector") in {"mixed", "mixed-use"} for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "archive_evidence": archive_evidence,
        "auctions": states,
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "excluded_non_catalogue_archive_assets": [
            {"year": 2023, "label": "May", "reason": "linked PNG is not a property catalogue"},
            {"year": 2023, "label": "September", "reason": "linked PDF is a catalogue-not-ready placeholder with zero property rows"},
        ],
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(summary_path, summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(events) or len(run_rows) != int(manifest["expected_lots"]):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-existing", action="store_true")
    args = parser.parse_args()
    harvest(refresh_existing=args.refresh_existing)
