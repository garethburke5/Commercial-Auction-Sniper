"""Bank Shonki Brothers' retained first-party catalogue lot inventories.

Each admitted appearance comes from an individual catalogue lot page carrying
an exact event date, printed lot identifier, address and guide price.  The
collector reconciles those pages to each catalogue's printed order of sale.
Extracted text plus the original PDF SHA-256 and URL is retained as immutable
source evidence; the PDF containers themselves are never counted as lots.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import gzip
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Kal Sangra Shonki Brothers"
SLUG = "shonki-brothers"
OPERATOR = "Shonki Brothers Limited"
COMPANY_NUMBER = "05393795"
INDEX_URL = "https://www.shonkibrothers.com/catalogues"
DEFAULT_SEED = (
    Path(__file__).resolve().parents[1]
    / "data/historical_source_corpus/shonki-brothers/catalogue-text.json.gz"
)
DEFAULT_FLIPHTML_SEED = (
    Path(__file__).resolve().parents[1]
    / "data/historical_source_corpus/shonki-brothers/fliphtml5-search-text.json.gz"
)
DATE_RE = re.compile(
    r"\bAuction:\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b",
    re.I,
)
LOT_RE = re.compile(r"^_?([A-Z]|\d{1,3})\s+GUIDE\s+PRICE:\s*(.+)$", re.I)
FLIPHTML_LOT_RE = re.compile(
    r"(?:^|\r?\n)LOT\s*\r?\n\s*([A-Z]|\d{1,3})\s*\r?\n"
    r"([\s\S]*?)\r?\nGUIDE\s+PRICE\s*[:;]\s*([^\r\n]+)",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
CURRENT_RENT_RE = re.compile(
    r"\b(?:current\s+(?:gross\s+|net\s+)?rental\s+income|total\s+gross\s+rental\s+income)"
    r"\s*[:\-]?\s*£?\s*([\d,]+(?:\.\d+)?)\b",
    re.I,
)
PASSING_RENT_RE = re.compile(
    r"\b(?:current\s+passing\s+rent|passing\s+rent|currently\s+pays\s+a\s+rent)\s+of\s+"
    r"£\s*([\d,]+(?:\.\d+)?)\s*(?:pa|pax|per\s+annum)\b",
    re.I,
)


def clean(value: object | None) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def amount(value: str | None) -> int | None:
    if value is None:
        return None
    parsed = corpus.money(value)
    return int(round(parsed)) if parsed else None


def exact_auction_date(text: str) -> str:
    # The cover is authoritative.  One 2025 introduction contains a weekday/
    # day typo while the cover and source filename agree on 13 February.
    cover = text.split("\f", 1)[0]
    match = DATE_RE.search(cover) or DATE_RE.search(text)
    if not match:
        raise ValueError("catalogue has no exact auction date")
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid catalogue auction date: {match.group(0)!r}") from exc


def first_column(value: str) -> str:
    return re.split(r"\s{3,}", value.strip(), maxsplit=1)[0].strip()


def parse_order_of_sale(text: str) -> list[str]:
    lots: list[str] = []
    for page in text.split("\f"):
        if "Order of Sale" not in page or "PROPERTY ADDRESS" not in page:
            continue
        body = page.split("PROPERTY ADDRESS", 1)[1]
        for raw_line in body.splitlines():
            line = raw_line.rstrip()
            if re.search(r"IMPORTANT NOTICE|NEXT AUCTION DATE|BUYERS FEE", line, re.I):
                break
            match = re.match(
                r"^\s*(?:Late\s+Entry\s*-\s*)?([A-Z]|\d{1,3})\s{2,}\S",
                line,
                re.I,
            )
            if match:
                lots.append(match.group(1).upper())
    if not lots:
        raise ValueError("catalogue has no printed order-of-sale inventory")
    if len(lots) != len(set(lots)):
        raise ValueError(f"order of sale contains duplicate lot identifiers: {lots}")
    return lots


def guide_values(text: str) -> tuple[int, int | None, str]:
    values = [amount(value) for value in MONEY_RE.findall(text)]
    values = [value for value in values if value is not None]
    if not values:
        raise ValueError(f"guide contains no monetary value: {text!r}")
    return values[0], values[1] if len(values) > 1 else None, clean(text) or text


def property_type_from_page(lines: list[str], guide_index: int) -> str | None:
    for raw in lines[guide_index + 1 : guide_index + 8]:
        value = first_column(raw)
        if not value or value.casefold().startswith(("location:", "description:", "tenure:")):
            continue
        if re.fullmatch(r"[A-Z][A-Z &/\-]{2,}", value) and not re.search(
            r"IMPORTANT NOTICE|NEXT AUCTION|SHONKI BROTHERS|PHOTOGRAPH", value
        ):
            return clean(value)
    return None


def rent_from_page(page: str) -> tuple[int | None, str | None]:
    matches = []
    for pattern in (CURRENT_RENT_RE, PASSING_RENT_RE):
        for match in pattern.finditer(page):
            value = amount(match.group(1))
            if value is not None:
                matches.append((value, clean(match.group(0))))
    distinct = sorted({value for value, _ in matches})
    if len(distinct) != 1:
        return None, None
    return distinct[0], "; ".join(dict.fromkeys(text for _, text in matches if text)) or None


def parse_lot_pages(text: str, auction_date: str, source_url: str, evidence: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for page_number, page in enumerate(text.split("\f"), 1):
        raw_lines = [line.rstrip() for line in page.splitlines() if line.strip()]
        if not raw_lines or not re.match(r"^\s*LOT\b", raw_lines[0], re.I):
            continue
        guide_index = next(
            (index for index, line in enumerate(raw_lines[:8]) if "GUIDE PRICE" in line.upper()),
            None,
        )
        if guide_index is None:
            continue
        guide_line = raw_lines[guide_index].strip()
        match = LOT_RE.match(guide_line)
        if not match:
            raise ValueError(f"unrecognised lot/guide heading on page {page_number}: {guide_line!r}")
        lot_number = match.group(1).upper()
        if lot_number in seen:
            raise ValueError(f"duplicate lot page {lot_number} on {auction_date}")
        seen.add(lot_number)

        address_parts = [re.sub(r"^\s*LOT\s+", "", raw_lines[0], flags=re.I).strip()]
        address_parts.extend(first_column(line) for line in raw_lines[1:guide_index])
        address = clean(" ".join(part for part in address_parts if part))
        if not address or not corpus.PC.search(address):
            raise ValueError(f"lot {lot_number} on {auction_date} has no exact postcode address")
        guide, guide_high, guide_text = guide_values(match.group(2))
        property_type = property_type_from_page(raw_lines, guide_index)
        annual_rent, rent_text = rent_from_page(page)
        auction_id = f"{SLUG}:{auction_date}"
        source_id = f"{auction_date}:{lot_number}"
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_id, source_url)
        postcode = corpus.PC.search(address)
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{lot_number}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            property_type=property_type,
            sector=corpus.sector(" ".join(filter(None, [address, property_type]))),
            guide_price=guide,
            guide_price_high=guide_high,
            status="unknown",
            annual_rent=annual_rent,
            rent_text=rent_text,
            property_id=source_id,
            identity_method="first_party_exact_auction_date_and_printed_lot_number",
            record_quality="address_record",
            source_position=len(rows) + 1,
            catalogue_page_number=page_number,
            guide_price_text=guide_text,
            auction_date_precision="day",
            auction_date_basis="first-party catalogue cover",
            source_platform="Shonki Brothers first-party retained catalogues",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name="Kal Sangra Shonki Brothers",
            source_evidence=evidence,
        )
        rows.append(row)
    if not rows:
        raise ValueError(f"catalogue {auction_date} has no individual lot pages")
    return rows


def load_seed(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        seed = json.load(handle)
    if seed.get("schema_version") != 1 or not seed.get("catalogues"):
        raise ValueError("Shonki seed has no recognised catalogue inventory")
    return seed


def load_fliphtml_seed(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        seed = json.load(handle)
    if seed.get("schema_version") != 1 or not seed.get("catalogues"):
        raise ValueError("Shonki FlipHTML5 seed has no recognised catalogue inventory")
    return seed


def fliphtml_pages(item: dict) -> list[str]:
    raw = item["search_config_js"]
    match = re.fullmatch(r"\s*var\s+textForPages\s*=\s*(\[[\s\S]*\])\s*;?\s*", raw)
    if not match:
        raise ValueError(f"unrecognised FlipHTML5 search inventory: {item['source_url']}")
    pages = json.loads(match.group(1))
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"empty FlipHTML5 search inventory: {item['source_url']}")
    return pages


def parse_fliphtml_order_of_sale(pages: list[str]) -> tuple[list[str], dict[str, str]]:
    order: list[str] = []
    addresses: dict[str, str] = {}
    for page in pages:
        if "LOT PROPERTY ADDRESS" not in page or "Order of Sale" not in page:
            continue
        body = page.split("LOT PROPERTY ADDRESS", 1)[1].split("Order of Sale", 1)[0]
        current: str | None = None
        late_entry = False
        for raw_line in body.splitlines():
            line = clean(raw_line)
            if not line:
                continue
            if line.upper() == "LATE ENTRY":
                late_entry = True
                continue
            match = re.match(r"^([A-Z]|\d{1,3})(?:\s+(.+))?$", line, re.I)
            if match and (match.group(2) or late_entry):
                current = match.group(1).upper()
                if current in addresses:
                    raise ValueError(f"duplicate FlipHTML5 order-of-sale lot {current}")
                order.append(current)
                addresses[current] = clean(match.group(2)) or ""
                late_entry = False
            elif current:
                addresses[current] = clean(f"{addresses[current]} {line}") or ""
    if not order:
        raise ValueError("FlipHTML5 catalogue has no printed order-of-sale inventory")
    missing_addresses = [lot for lot in order if not corpus.PC.search(addresses[lot])]
    if missing_addresses:
        raise ValueError(f"FlipHTML5 order lots have no postcode: {missing_addresses}")
    return order, addresses


def fliphtml_property_type(page: str, lot_match: re.Match[str]) -> str | None:
    candidates = page[: lot_match.start()] + "\n" + page[lot_match.end() :]
    keywords = re.compile(
        r"\b(?:COMMERCIAL|RESIDENTIAL|RETAIL|LAND|DEVELOPMENT|GROUND RENT|OPEN MARKET|INVESTMENT)\b"
    )
    for raw_line in candidates.splitlines():
        value = clean(raw_line)
        if (
            value
            and re.fullmatch(r"[A-Z][A-Z &/\-]{2,}", value)
            and keywords.search(value)
            and "AUCTION" not in value
        ):
            return value
    return None


def snapshot_fliphtml_catalogue(item: dict, auction_date: str) -> dict:
    search_raw = item["search_config_js"].encode("utf-8")
    config_raw = item["config_js"].encode("utf-8")
    search_sha = corpus.digest(search_raw)
    config_sha = corpus.digest(config_raw)
    if search_sha != item["search_config_sha256"] or len(search_raw) != item["search_config_size_bytes"]:
        raise ValueError("FlipHTML5 search source checksum/size mismatch")
    if config_sha != item["config_sha256"] or len(config_raw) != item["config_size_bytes"]:
        raise ValueError("FlipHTML5 config source checksum/size mismatch")
    prefix = corpus.DATA / "sources" / SLUG
    search_path = prefix / f"fliphtml5-{item['book_slug']}-{auction_date}-{search_sha[:16]}.js.gz"
    config_path = prefix / f"fliphtml5-{item['book_slug']}-config-{config_sha[:16]}.js.gz"
    if not search_path.exists():
        corpus.atomic(search_path, gzip.compress(search_raw, mtime=0))
    if not config_path.exists():
        corpus.atomic(config_path, gzip.compress(config_raw, mtime=0))
    return {
        "source_url": item["search_config_url"],
        "catalogue_url": item["source_url"],
        "retrieved_at": item["retrieved_at"],
        "sha256": search_sha,
        "source_size_bytes": len(search_raw),
        "snapshot_path": str(search_path.relative_to(corpus.ROOT)),
        "snapshot_format": "verbatim FlipHTML5 search_config.js UTF-8 source",
        "config_source_url": item["config_url"],
        "config_sha256": config_sha,
        "config_size_bytes": len(config_raw),
        "config_snapshot_path": str(config_path.relative_to(corpus.ROOT)),
        "basis": "first-party retained catalogue page-text inventory and book configuration",
        "auction_date": auction_date,
    }


def parse_fliphtml_lot_pages(
    pages: list[str], auction_date: str, source_url: str, evidence: dict
) -> tuple[list[dict], list[str]]:
    order, order_addresses = parse_fliphtml_order_of_sale(pages)
    rows: list[dict] = []
    seen: set[str] = set()
    for page_number, page in enumerate(pages, 1):
        for match in FLIPHTML_LOT_RE.finditer(page):
            lot_number = match.group(1).upper()
            if lot_number in seen:
                raise ValueError(f"duplicate FlipHTML5 lot page {lot_number} on {auction_date}")
            seen.add(lot_number)
            if lot_number not in order_addresses:
                raise ValueError(f"FlipHTML5 lot page {lot_number} is absent from printed order")
            page_address = clean(match.group(2))
            postcodes = list(corpus.PC.finditer(page_address or ""))
            if not postcodes:
                raise ValueError(f"FlipHTML5 lot {lot_number} has no exact postcode address")
            page_address = clean((page_address or "")[: postcodes[-1].end()])
            address = order_addresses[lot_number]
            page_postcodes = {
                value.group().replace(" ", "").casefold() for value in corpus.PC.finditer(page_address or "")
            }
            order_postcodes = {
                value.group().replace(" ", "").casefold() for value in corpus.PC.finditer(address)
            }
            if page_postcodes != order_postcodes:
                raise ValueError(
                    f"FlipHTML5 lot {lot_number} postcode mismatch: {page_address!r} vs {address!r}"
                )
            guide, guide_high, guide_text = guide_values(match.group(3))
            property_type = fliphtml_property_type(page, match)
            annual_rent, rent_text = rent_from_page(page)
            auction_id = f"{SLUG}:{auction_date}"
            source_id = f"{auction_date}:{lot_number}"
            row = corpus.base_row(
                SOURCE, auction_id, auction_date, lot_number, source_id, source_url
            )
            postcode = corpus.PC.search(address)
            row.update(
                appearance_id=f"{SOURCE}|{auction_id}|{lot_number}",
                address=address,
                postcode=postcode.group().upper() if postcode else None,
                locality=address,
                property_type=property_type,
                sector=corpus.sector(" ".join(filter(None, [address, property_type]))),
                guide_price=guide,
                guide_price_high=guide_high,
                status="unknown",
                annual_rent=annual_rent,
                rent_text=rent_text,
                property_id=source_id,
                identity_method="first_party_exact_auction_date_and_printed_lot_number",
                record_quality="address_record",
                source_position=len(rows) + 1,
                catalogue_page_number=page_number,
                guide_price_text=guide_text,
                auction_date_precision="day",
                auction_date_basis="first-party catalogue cover and order of sale",
                source_platform="Shonki Brothers retained FlipHTML5 catalogues",
                operator_legal_name=OPERATOR,
                operator_company_number=COMPANY_NUMBER,
                trading_name="Kal Sangra Shonki Brothers",
                source_evidence=evidence,
            )
            rows.append(row)
    if not rows:
        raise ValueError(f"FlipHTML5 catalogue {auction_date} has no individual lot pages")
    return rows, order


def snapshot_catalogue(item: dict, auction_date: str) -> dict:
    text = item["extracted_text"]
    pdf_sha = item["pdf_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", pdf_sha):
        raise ValueError("catalogue seed has invalid PDF SHA-256")
    path = corpus.DATA / "sources" / SLUG / f"catalogue-{auction_date}-{pdf_sha[:16]}.txt.gz"
    evidence = {
        "source_url": item["source_url"],
        "retrieved_at": item["retrieved_at"],
        "sha256": pdf_sha,
        "source_size_bytes": item["source_size_bytes"],
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "snapshot_format": "pdftotext-layout UTF-8 text from immutable first-party PDF",
        "basis": "first-party complete auction catalogue PDF",
        "auction_date": auction_date,
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(text.encode("utf-8"), mtime=0))
    return evidence


def snapshot_outcomes(seed: dict) -> dict | None:
    snapshot = seed.get("outcome_page_snapshot")
    if not snapshot:
        return None
    raw = snapshot["rendered_text"].encode("utf-8")
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"unsold-outcomes-{sha[:16]}.txt.gz"
    evidence = {
        "source_url": snapshot["source_url"],
        "retrieved_at": snapshot["retrieved_at"],
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "snapshot_format": "rendered UTF-8 text from first-party dynamic result grid",
        "basis": "first-party retained unsold and available property rows",
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return evidence


def apply_outcomes(rows: list[dict], seed: dict) -> int:
    evidence = snapshot_outcomes(seed)
    by_key = {(row["auction_date"], str(row["lot_number"]).lstrip("0") or "0"): row for row in rows}
    applied = 0
    for outcome in seed.get("outcomes", []):
        key = (outcome["auction_date"], str(outcome["lot_number"]).lstrip("0") or "0")
        row = by_key.get(key)
        if row is None:
            raise ValueError(f"published outcome has no matching catalogue lot: {key}")
        expected = corpus.PC.search(outcome["address"])
        observed = corpus.PC.search(row["address"])
        if not expected or not observed or expected.group().replace(" ", "").casefold() != observed.group().replace(" ", "").casefold():
            raise ValueError(f"published outcome postcode does not reconcile to catalogue lot: {key}")
        result_text = clean(outcome["result_text"])
        available_values = [amount(value) for value in MONEY_RE.findall(result_text or "")]
        row.update(
            status="unsold",
            available_price=available_values[0] if available_values else None,
            source_result_text=result_text,
            source_result_url=outcome["detail_url"],
            result_source_evidence=evidence,
        )
        applied += 1
    return applied


def global_exact_appearances() -> dict[tuple[str, str], list[dict]]:
    values: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append(
                    {
                        "appearance_id": row.get("appearance_id"),
                        "auctioneer": row.get("auctioneer"),
                        "original_url": row.get("original_url"),
                    }
                )
    return values


def harvest(
    seed_path: Path = DEFAULT_SEED, fliphtml_seed_path: Path = DEFAULT_FLIPHTML_SEED
) -> dict:
    seed = load_seed(seed_path)
    fliphtml_seed = load_fliphtml_seed(fliphtml_seed_path)
    today = date.today().isoformat()
    all_rows, states = [], []
    excluded_future = list(seed.get("excluded_future_catalogues", []))
    for item in seed["catalogues"]:
        text = item["extracted_text"]
        auction_date = exact_auction_date(text)
        if item.get("auction_date") != auction_date:
            raise ValueError(f"seed/cover date mismatch for {item.get('source_url')}")
        if auction_date > today:
            excluded_future.append({"auction_date": auction_date, "source_url": item["source_url"]})
            continue
        evidence = snapshot_catalogue(item, auction_date)
        rows = parse_lot_pages(text, auction_date, item["source_url"], evidence)
        order = parse_order_of_sale(text)
        visible = [row["lot_number"] for row in rows]
        reconciled = order == visible
        errors = [] if reconciled else ["printed order of sale does not match individual lot pages"]
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "auction_date_precision": "day",
            "source_url": item["source_url"],
            "visible_order_of_sale_lots": len(order),
            "individual_lot_pages": len(rows),
            "lots_captured": len(rows),
            "catalogue_complete": reconciled,
            "source_rows_complete": True,
            "denominator_reconciled": reconciled,
            "completion_scope": "every printed individual lot page reconciled to the catalogue order of sale",
            "source_evidence": evidence,
            "errors": errors,
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{auction_date}.json", state)
        states.append(state)
        all_rows.extend(rows)

    for item in fliphtml_seed["catalogues"]:
        pages = fliphtml_pages(item)
        text = "\f".join(pages)
        auction_date = exact_auction_date(text)
        expected_date = datetime.strptime(item["expected_auction_date"], "%d %B %Y").date().isoformat()
        if auction_date != expected_date:
            raise ValueError(f"FlipHTML5 seed/cover date mismatch for {item['source_url']}")
        if auction_date > today:
            excluded_future.append(
                {"auction_date": auction_date, "source_url": item["source_url"]}
            )
            continue
        evidence = snapshot_fliphtml_catalogue(item, auction_date)
        rows, order = parse_fliphtml_lot_pages(
            pages, auction_date, item["source_url"], evidence
        )
        visible = [row["lot_number"] for row in rows]
        reconciled = order == visible
        missing_pages = [lot for lot in order if lot not in visible]
        unexpected_pages = [lot for lot in visible if lot not in order]
        errors = []
        if missing_pages:
            errors.append(f"printed order lots without individual lot page: {missing_pages}")
        if unexpected_pages:
            errors.append(f"individual lot pages absent from printed order: {unexpected_pages}")
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "auction_date_precision": "day",
            "source_url": item["source_url"],
            "visible_order_of_sale_lots": len(order),
            "individual_lot_pages": len(rows),
            "lots_captured": len(rows),
            "catalogue_complete": reconciled,
            "source_rows_complete": True,
            "denominator_reconciled": reconciled,
            "missing_individual_lot_pages": missing_pages,
            "unexpected_individual_lot_pages": unexpected_pages,
            "completion_scope": (
                "every retained individual lot page reconciled to the printed order of sale; "
                "missing order entries remain explicit"
            ),
            "source_evidence": evidence,
            "errors": errors,
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{auction_date}.json", state)
        states.append(state)
        all_rows.extend(rows)

    if not all_rows:
        raise ValueError("no historical Shonki lots admitted")
    outcomes_applied = apply_outcomes(all_rows, seed)
    global_exact = global_exact_appearances()
    overlap_exclusions, admissible = [], []
    for row in all_rows:
        matches = global_exact.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlap_exclusions.append(
                {
                    "auction_date": row["auction_date"],
                    "lot_number": row["lot_number"],
                    "address": row["address"],
                    "shonki_appearance_id": row["appearance_id"],
                    "existing": matches,
                }
            )
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before = {row["appearance_id"]: row for row in existing}
    merged = dict(before)
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    added = [row for key, row in merged.items() if key not in before]
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    historical_added = [row for row in added if cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "source_url": seed.get("source_page", INDEX_URL),
        "operator": {
            "canonical_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "trading_name": "Kal Sangra Shonki Brothers",
            "trading_name_not_counted_as_separate_auctioneer": True,
            "branches_not_counted_as_separate_auctioneers": True,
        },
        "catalogues_in_seed": len(seed["catalogues"]) + len(fliphtml_seed["catalogues"]),
        "pdf_catalogues_in_seed": len(seed["catalogues"]),
        "fliphtml5_catalogues_in_seed": len(fliphtml_seed["catalogues"]),
        "historical_catalogues_captured": len(states),
        "historical_catalogues_complete": sum(state["catalogue_complete"] for state in states),
        "visible_individual_lot_pages": len(all_rows),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical_added),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_available_prices": sum(row.get("available_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_duplicate_source_evidence_excluded": len(overlap_exclusions),
        "duplicate_source_evidence_exclusions": overlap_exclusions,
        "future_catalogues_excluded": excluded_future,
        "published_outcomes_enriched": outcomes_applied,
        "new_source_years": sorted(years_after - years_before),
        "source_years_visible": sorted({row["auction_date"][:4] for row in all_rows}),
        "source_date_range": [min(row["auction_date"] for row in all_rows), max(row["auction_date"] for row in all_rows)],
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "auctions": {state["auction_date"]: state for state in states},
        "completion_scope": (
            "20 retained first-party catalogues from July 2023 through September 2026; "
            "every printed lot is reconciled to an individual retained lot page; "
            "catalogues before July 2023 are not yet evidenced"
        ),
        "national_completeness": False,
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "shonki_brothers_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--fliphtml-seed", type=Path, default=DEFAULT_FLIPHTML_SEED)
    args = parser.parse_args()
    harvest(args.seed, args.fliphtml_seed)


if __name__ == "__main__":
    main()
