"""Bank Cheffins' retained first-party property-auction result cards.

The result archive publishes one stable catalogue URL and a lot denominator for
each sale. Catalogue pages are unpaginated and expose exact auction dates plus
one property card per retained lot. Every surviving card is banked. A catalogue
is only complete when its unique cards reconcile to the published denominator;
older denominator-short catalogues remain explicit partial catalogues.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import gzip
from io import BytesIO
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.cheffins.co.uk"
INDEX = BASE + "/property-auctions/results.htm"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
CATALOGUE_RE = re.compile(r"catalogue-view,[^?#]+_(\d+)\.htm", re.I)
LOT_RE = re.compile(r"lot-view,[^?#]+_(\d+)\.htm", re.I)
COUNT_RE = re.compile(r"Number\s+of\s+lots:\s*(\d+)", re.I)
LOT_NUMBER_RE = re.compile(r"\bLot\s+number:\s*([^\s]+)", re.I)
DATE_RE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)\d{2})\s*\|", re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)
ADDENDUM_RE = re.compile(r"https://cdn\.eigpropertyauctions\.co\.uk/[^\"']+/addendum\.pdf", re.I)
ADDENDUM_LOT_RE = re.compile(
    r"(?ims)^\s*LOT\s+0*([0-9]+[A-Z]?)\s*(?:[-\u2013\u2014]\s*)?(.+?)\s*$"
    r"(.*?)(?=^\s*LOT\s+0*[0-9]+[A-Z]?\b|^\s*ENTRIES\b|\Z)"
)
ADDENDUM_RECOVERY_VERSION = 2
CATALOGUE_PDF_RECOVERY_VERSION = 1
DATE_RECOVERY = {
    "549": {
        "auction_date": "2019-06-19",
        "url": BASE + "/about/news/view,eastern-counties-auction-gives-property-investors-array-of-opportunities_364.htm",
        "required": re.compile(r"21\s+lots.*Wednesday\s+19\s+June\s+2019", re.I | re.S),
    },
}
CATALOGUE_PDF_RECOVERY = {
    "549": BASE + "/ugc-1/1/2/0/property_auction_catalogue_june_2019.pdf",
}

PDF_ADDRESS_RE = re.compile(
    r"\bLOT\s+0*([0-9]+[A-Z]?)\s+(.+?)\s+"
    r"(?=Not\s+to\s+scale|Approved\s+plans|Image\s+supplied|TENURE:)",
    re.I,
)
PDF_GUIDE_RE = re.compile(
    r"Guide\s+Price\*?\s*£\s*([\d,]+)\s*"
    r"(?:(?:----|[-–—])\s*£?\s*([\d,]+))?",
    re.I,
)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def discover_catalogues(html: str, source_url: str = INDEX) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, dict] = {}
    for anchor in soup.find_all("a", href=True):
        text = clean(anchor.get_text(" ", strip=True)) or ""
        count_match = COUNT_RE.search(text)
        href = urljoin(source_url, anchor["href"])
        catalogue_match = CATALOGUE_RE.search(href)
        if not count_match or not catalogue_match:
            continue
        catalogue_id = catalogue_match.group(1)
        item = {"catalogue_id": catalogue_id, "label": clean(COUNT_RE.sub("", text)),
                "published_lots": int(count_match.group(1)), "url": href}
        old = found.get(catalogue_id)
        if old and old != item:
            raise ValueError(f"conflicting archive entries for catalogue {catalogue_id}")
        found[catalogue_id] = item
    if not found:
        raise ValueError("Cheffins result archive contains no catalogue denominators")
    return sorted(found.values(), key=lambda item: int(item["catalogue_id"]))


def parse_money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def status_and_price(status_text: str | None, price_text: str | None) -> tuple[str, int | None]:
    combined = " ".join(filter(None, [clean(status_text), clean(price_text)]))
    lower = combined.casefold()
    if "sold prior" in lower:
        return "sold_prior", parse_money(combined)
    if "withdrawn" in lower:
        return "withdrawn", None
    if "unsold" in lower or "available" in lower:
        return "unsold", None
    if "sold" in lower or (status_text or "").strip().casefold() == "sold":
        return "sold", parse_money(combined)
    return "unknown", None


def parse_addendum(text: str, missing_lots: set[str]) -> list[dict]:
    """Return evidenced missing lot headings from a first-party linked addendum."""
    recovered = []
    for match in ADDENDUM_LOT_RE.finditer(text.replace("\r", "")):
        lot_number = match.group(1).upper()
        if lot_number not in missing_lots:
            continue
        address = clean(match.group(2))
        body = clean(match.group(3)) or ""
        if not address:
            continue
        lower = body.casefold()
        if "sold prior" in lower:
            status = "sold_prior"
        elif "sold after" in lower:
            status = "sold_after"
        elif "withdrawn" in lower:
            status = "withdrawn"
        elif re.search(r"\bsold\b", lower):
            status = "sold"
        else:
            status = "unknown"
        recovered.append({
            "lot_number": lot_number,
            "address": address,
            "status": status,
            "guide_price": parse_money(body) if "guide" in lower else None,
            "source_text": clean(" ".join(filter(None, [address, body]))),
        })
    return recovered


def addendum_rows(text: str, catalogue: dict, auction_date: str, evidence: dict,
                   existing_rows: list[dict]) -> list[dict]:
    existing_lots = {str(row.get("lot_number") or "").upper() for row in existing_rows}
    expected_lots = {str(number) for number in range(1, catalogue["published_lots"] + 1)}
    missing_lots = expected_lots - existing_lots
    rows = []
    for position, item in enumerate(parse_addendum(text, missing_lots), len(existing_rows) + 1):
        lot_number, address = item["lot_number"], item["address"]
        source_id = f"addendum-lot-{lot_number.casefold()}"
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row("Cheffins", f"cheffins:{catalogue['catalogue_id']}", auction_date,
                              lot_number, source_id, evidence["source_url"])
        row.update(
            appearance_id=(f"Cheffins|catalogue:{catalogue['catalogue_id']}|"
                           f"addendum-lot:{lot_number}"),
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            property_type=None,
            description=None,
            sector=corpus.sector(address),
            status=item["status"],
            guide_price=item["guide_price"],
            sale_price=None,
            property_id=None,
            identity_method="source_catalogue_and_addendum_lot_number",
            record_quality="address_record",
            source_position=position,
            source_status_text=item["source_text"],
            source_result_text=None,
            source_evidence=evidence,
        )
        rows.append(row)
    return rows


def _published_rent(text: str) -> tuple[int | None, str | None]:
    """Return the current total rent and its exact published sentence fragment."""
    patterns = (
        r"Rental\s+income\s+(?:of\s+)?£\s*([\d,]+)\s+per\s+annum",
        r"current\s+rent\s+of\s+£\s*([\d,]+)\s+per\s+annum",
        r"tenant\s+paying\s+£[\d,]+\s+per\s+week\s*\(£\s*([\d,]+)\s+per\s+year\)",
        r"at\s+a\s+rent\s+of\s+£\s*([\d,]+)\s+per\s+annum",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        start = max(0, text.rfind(".", 0, match.start()) + 1)
        end = text.find(".", match.end())
        fragment = clean(text[start:end if end >= 0 else match.end()])
        return int(match.group(1).replace(",", "")), fragment
    return None, None


def _property_type(address: str, summary: str | None, sector: str) -> str | None:
    if sector == "mixed-use":
        return "Mixed-use investment/development"
    if sector == "commercial":
        return "Commercial investment"
    text = " ".join(filter(None, [address, summary])).casefold()
    for pattern, label in (
        (r"\bwoodland\b", "Woodland"), (r"\bland\b", "Land"),
        (r"\bbarns?\b", "Barns"), (r"\bbungalow\b", "Bungalow"),
        (r"\bcottages?\b", "Cottage"), (r"\bflats?\b", "Flat"),
        (r"\bhouses?\b", "House"),
    ):
        if re.search(pattern, text):
            return label
    if sector == "residential":
        return "Residential"
    return None


def _catalogue_sector(text: str) -> str:
    """Classify the advertised lot, excluding solicitor/contact boilerplate."""
    value = text.casefold()
    commercial = bool(re.search(
        r"\b(?:commercial|retail|shop|office|industrial|warehouse|restaurant|"
        r"hotel|workshop)\b", value
    ))
    residential = bool(re.search(
        r"\b(?:residential|dwelling|house|cottage|bungalow|flat|apartment|"
        r"maisonette|bedroom|terraced)\b", value
    ))
    if commercial and residential:
        return "mixed-use"
    if commercial:
        return "commercial"
    if residential:
        return "residential"
    if re.search(r"\b(?:land|woodland|site|plot|barns?)\b", value):
        return "land"
    return "unknown"


def catalogue_pdf_rows_from_pages(pages: list[str], catalogue: dict, auction_date: str,
                                  evidence: dict) -> list[dict]:
    """Parse complete Cheffins lot pages from a first-party catalogue PDF.

    The parser is catalogue-generic: it scans detail pages rather than relying
    on fixed page numbers, and refuses duplicate or incomplete lot inventories.
    """
    rows = []
    seen = set()
    for page_number, raw_text in enumerate(pages, 1):
        text = clean(raw_text) or ""
        if not PDF_GUIDE_RE.search(text):
            continue
        address_matches = list(PDF_ADDRESS_RE.finditer(text))
        if not address_matches:
            continue
        address_match = address_matches[-1]
        lot_number = address_match.group(1).upper()
        if lot_number in seen:
            raise ValueError(f"duplicate catalogue PDF lot {lot_number}")
        guide_match = PDF_GUIDE_RE.search(text)
        address = clean(address_match.group(2))
        if not address or not guide_match:
            raise ValueError(f"catalogue PDF lot {lot_number} lacks address or guide")
        seen.add(lot_number)
        description_match = re.search(
            r"\bDescription\s+(.+?)(?=\s+(?:Location|Planning|Tenancies|"
            r"Auctioneers?\s+Note|Accommodation|LOT)\b)", text,
        )
        description = clean(description_match.group(1)) if description_match else None
        guide_low = int(guide_match.group(1).replace(",", ""))
        guide_high = (int(guide_match.group(2).replace(",", ""))
                      if guide_match.group(2) else None)
        postcode_match = corpus.PC.search(address)
        annual_rent, rent_text = _published_rent(text)
        before_address = text[:address_match.start()]
        bullet_parts = before_address.split("•")
        summary = (" ".join(bullet_parts[-4:]) if len(bullet_parts) > 1
                   else (description or ""))
        sector = _catalogue_sector(" ".join(filter(None, [address, summary])))
        source_id = f"catalogue-pdf-lot-{lot_number.casefold()}"
        row = corpus.base_row("Cheffins", f"cheffins:{catalogue['catalogue_id']}",
                              auction_date, lot_number, source_id, evidence["source_url"])
        row.update(
            appearance_id=(f"Cheffins|catalogue:{catalogue['catalogue_id']}|"
                           f"catalogue-pdf-lot:{lot_number}"),
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            property_type=_property_type(address, summary, sector),
            description=description,
            sector=sector,
            status="unknown",
            guide_price=guide_low,
            guide_price_high=guide_high,
            sale_price=None,
            annual_rent=annual_rent,
            rent_text=rent_text,
            property_id=None,
            identity_method="source_catalogue_pdf_and_lot_number",
            record_quality="address_record",
            source_position=page_number,
            source_status_text=clean(guide_match.group(0)),
            source_result_text=None,
            source_evidence=evidence,
        )
        rows.append(row)
    rows.sort(key=lambda row: (int(re.match(r"\d+", row["lot_number"]).group()),
                               row["lot_number"]))
    expected = catalogue["published_lots"]
    if len(rows) != expected:
        raise ValueError(
            f"catalogue PDF yielded {len(rows)} unique lots; expected {expected}"
        )
    return rows


def catalogue_pdf_rows(raw: bytes, catalogue: dict, auction_date: str,
                       evidence: dict) -> list[dict]:
    reader = PdfReader(BytesIO(raw))
    pages = [page.extract_text() or "" for page in reader.pages]
    return catalogue_pdf_rows_from_pages(pages, catalogue, auction_date, evidence)


def denominator_gap_rows(catalogue: dict, auction_date: str, evidence: dict,
                         existing_rows: list[dict]) -> list[dict]:
    """Bank identity-only rows for unambiguous holes in a numbered catalogue.

    Cheffins' archive supplies an exact published denominator, while some old
    catalogue pages have dropped individual detail cards (usually withdrawn
    lots).  When every retained identity is a unique integer in the published
    1..N range, a hole is an evidenced auction appearance even though its
    address and outcome are no longer public.  Zero-card and lettered-number
    catalogues deliberately remain untouched.
    """
    lot_numbers = [str(row.get("lot_number") or "").strip() for row in existing_rows]
    if not lot_numbers or any(not number.isdigit() for number in lot_numbers):
        return []
    retained = [int(number) for number in lot_numbers]
    published = catalogue["published_lots"]
    if len(set(retained)) != len(retained) or any(number < 1 or number > published
                                                  for number in retained):
        return []
    missing = sorted(set(range(1, published + 1)) - set(retained))
    if len(existing_rows) + len(missing) != published:
        return []
    rows = []
    for position, number in enumerate(missing, len(existing_rows) + 1):
        lot_number = str(number)
        source_id = f"published-gap-{lot_number}"
        row_evidence = dict(evidence)
        row_evidence["basis"] = (
            "first-party published lot denominator and missing integer identity "
            "within the retained catalogue sequence"
        )
        row = corpus.base_row("Cheffins", f"cheffins:{catalogue['catalogue_id']}",
                              auction_date, lot_number, source_id, catalogue["url"])
        row.update(
            appearance_id=(f"Cheffins|catalogue:{catalogue['catalogue_id']}|"
                           f"published-gap:{lot_number}"),
            address=None,
            postcode=None,
            locality=None,
            property_type=None,
            description=None,
            sector="unknown",
            status="unknown",
            property_id=None,
            identity_method="published_denominator_and_retained_numeric_gap",
            record_quality="partial_lot",
            source_position=position,
            source_status_text=None,
            source_result_text=None,
            source_evidence=row_evidence,
        )
        rows.append(row)
    return rows


def node_text(node, selector: str) -> str | None:
    match = node.select_one(selector)
    return clean(match.get_text(" ", strip=True)) if match else None


def parse_catalogue(html: str, catalogue: dict, evidence: dict,
                    auction_date_override: str | None = None,
                    recovered_rows: list[dict] | None = None) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    page_text = clean(soup.get_text(" ", strip=True)) or ""
    date_match = DATE_RE.search(page_text)
    if not date_match and not auction_date_override:
        raise ValueError("catalogue has no exact published auction date")
    auction_date = (datetime.strptime(date_match.group(1), "%d %B %Y").date().isoformat()
                    if date_match else auction_date_override)
    cards, rows = soup.select("div.property-card"), []
    for position, card in enumerate(cards, 1):
        detail = card.find("a", href=LOT_RE)
        if not detail:
            raise ValueError(f"source property identity missing at card {position}")
        detail_url = urljoin(catalogue["url"], detail["href"])
        source_match = LOT_RE.search(detail_url)
        source_id = source_match.group(1) if source_match else None
        content = card.select_one(".pc-content")
        if not content or not source_id:
            raise ValueError(f"source property content missing at card {position}")
        lot_match = LOT_NUMBER_RE.search(node_text(content, ".pc-tag") or "")
        if not lot_match:
            raise ValueError(f"lot number missing at card {position}")
        lot_number = lot_match.group(1).upper()
        price_text, status_text = node_text(content, ".pc-price"), node_text(card, ".pc-extraInfo")
        status, sale_price = status_and_price(status_text, price_text)
        address, description = node_text(content, ".pc-add"), node_text(content, ".pc-summ")
        tags = [clean(node.get_text(" ", strip=True)) for node in content.select(".pc-tag")]
        property_type = next((value for value in tags[1:] if value), None)
        postcode_match = corpus.PC.search(address or "")
        postcode = postcode_match.group().upper() if postcode_match else None
        source_auction_id = f"cheffins:{catalogue['catalogue_id']}"
        row = corpus.base_row("Cheffins", source_auction_id, auction_date,
                              lot_number, source_id, detail_url)
        row.update(address=address, postcode=postcode, locality=address,
                   property_type=property_type, description=description,
                   sector=corpus.sector(" ".join(filter(None, [property_type, description, address]))),
                   status=status, sale_price=sale_price, property_id=None,
                   identity_method="source_catalogue_and_property_id",
                   record_quality="address_record" if address else "partial_lot",
                   source_position=position, source_status_text=status_text,
                   source_result_text=price_text, source_evidence=evidence)
        row["appearance_id"] = f"Cheffins|catalogue:{catalogue['catalogue_id']}|property:{source_id}"
        rows.append(row)

    rows.extend(recovered_rows or [])
    identities = [row["source_lot_id"] for row in rows]
    unique = len(set(identities)) == len(identities)
    expected = catalogue["published_lots"]
    complete = unique and len(rows) == expected
    state = {"auctioneer": "Cheffins",
             "source_auction_id": f"cheffins:{catalogue['catalogue_id']}",
             "auction_date": auction_date, "catalogue_complete": complete,
             "source_rows_complete": True, "published_lots_offered": expected,
             "visible_source_rows": len(rows), "lots_captured": len(rows),
             "source_url": catalogue["url"], "pagination_reconciled": True,
             "denominator_reconciled": complete,
             "denominator_basis": "published Number of lots on first-party result archive",
             "completion_scope": "all retained cards on the first-party unpaginated catalogue page",
             "partial_reason": None if complete else
                 f"published denominator {expected} exceeds {len(rows)} retained source cards",
             "auction_date_basis": ("exact date on catalogue page" if date_match else
                                      "exact date and lot count on first-party sale preview"),
             "addendum_recovery_version": ADDENDUM_RECOVERY_VERSION,
             "addendum_lots_recovered": len(recovered_rows or []),
             "source_sha256": evidence["sha256"],
             "errors": [] if unique else ["duplicate source property identities"],
             "checked_at": corpus.now()}
    return state, rows


def get(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    return raw, response.url


def reparse_saved_catalogue_pdf(catalogue_id: str) -> None:
    """Bank a complete already-snapshotted catalogue without a live refresh."""
    pdf_url = CATALOGUE_PDF_RECOVERY.get(catalogue_id)
    if not pdf_url:
        raise ValueError(f"no saved catalogue PDF recovery configured for {catalogue_id}")
    snapshots = sorted((corpus.DATA / "sources/cheffins").glob(
        f"catalogue-{catalogue_id}-original-catalogue-*.pdf.gz"
    ))
    if len(snapshots) != 1:
        raise ValueError(
            f"expected one immutable saved PDF for catalogue {catalogue_id}; found {len(snapshots)}"
        )
    snapshot = snapshots[0]
    with gzip.open(snapshot, "rb") as handle:
        raw = handle.read()
    sha = corpus.digest(raw)
    if sha[:16] not in snapshot.name:
        raise ValueError("saved catalogue PDF filename does not match content digest")
    state_path = corpus.DATA / f"auctions/cheffins/catalogue-{catalogue_id}.json"
    old_state = json.loads(state_path.read_text())
    auction_date = old_state.get("auction_date")
    published_lots = old_state.get("published_lots_offered")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(auction_date)):
        raise ValueError("saved event state lacks an exact auction date")
    if not isinstance(published_lots, int) or published_lots < 1:
        raise ValueError("saved event state lacks a published lot denominator")
    catalogue = {
        "catalogue_id": catalogue_id,
        "published_lots": published_lots,
        "url": old_state["source_url"],
    }
    evidence = {
        "source_url": pdf_url,
        "catalogue_url": old_state["source_url"],
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party complete property-auction catalogue PDF",
    }
    recovered = catalogue_pdf_rows(raw, catalogue, auction_date, evidence)
    canonical_path = corpus.DATA / "appearances/cheffins/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(canonical_path))
    existing_event = [row for row in existing
                      if row.get("source_auction_id") == f"cheffins:{catalogue_id}"]
    if existing_event:
        raise ValueError(
            f"catalogue {catalogue_id} already has {len(existing_event)} rows; "
            "refusing an overlapping saved-PDF recovery"
        )
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in recovered:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("cheffins/canonical", list(merged.values()))
    state = dict(old_state)
    state.update(
        checked_at=corpus.now(),
        catalogue_complete=True,
        source_rows_complete=True,
        visible_source_rows=len(recovered),
        lots_captured=len(recovered),
        pagination_reconciled=True,
        denominator_reconciled=True,
        completion_scope="all numbered lots in the first-party complete catalogue PDF",
        partial_reason=None,
        catalogue_pdf_recovery_version=CATALOGUE_PDF_RECOVERY_VERSION,
        catalogue_pdf_lots_recovered=len(recovered),
        catalogue_pdf_source_evidence=evidence,
        errors=[],
    )
    corpus.save_json(state_path, state)
    summary_path = corpus.DATA / "cheffins_collection.json"
    summary = json.loads(summary_path.read_text())
    auctions = summary.setdefault("auctions", {})
    auctions[catalogue_id] = state
    added = [row for row in recovered if row["appearance_id"] not in before_ids]
    summary.update(
        checked_at=corpus.now(),
        appearances_captured=total,
        run_new_appearances=len(added),
        run_new_address_records=sum(bool(row.get("address")) for row in added),
        run_new_partial_lots=sum(not row.get("address") for row in added),
        run_new_guide_prices=sum(row.get("guide_price") is not None for row in added),
        run_new_sale_prices=sum(row.get("sale_price") is not None for row in added),
        run_new_rents=sum(row.get("annual_rent") is not None for row in added),
        by_sector=dict(Counter(row.get("sector") for row in merged.values())),
    )
    summary["catalogues_complete"] = sum(
        bool(item.get("catalogue_complete")) for item in auctions.values()
    )
    summary["catalogues_partial"] = sum(
        not item.get("catalogue_complete") for item in auctions.values()
    )
    corpus.save_json(summary_path, summary)
    print(json.dumps({
        "catalogue_id": catalogue_id,
        "new_appearances": len(added),
        "new_address_records": sum(bool(row.get("address")) for row in added),
        "new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "new_rents": sum(row.get("annual_rent") is not None for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
    }, indent=2))


def harvest(workers: int = 6) -> None:
    index_raw, resolved_index = get(INDEX)
    index_sha, checked_at = corpus.digest(index_raw), corpus.now()
    index_snapshot = corpus.DATA / "sources/cheffins" / f"results-{index_sha[:16]}.json.gz"
    index_evidence = {"source_url": resolved_index, "retrieved_at": checked_at,
                      "sha256": index_sha,
                      "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
                      "basis": "first-party result archive with published lot denominators"}
    corpus.save_gzip(index_snapshot, {"evidence": index_evidence,
        "html": index_raw.decode("utf-8", "replace")})
    catalogues = discover_catalogues(index_raw.decode("utf-8", "replace"), resolved_index)
    path = corpus.DATA / "appearances/cheffins/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)
    states, run_rows, pending, failures, reused = {}, [], [], [], 0
    for catalogue in catalogues:
        state_path = corpus.DATA / f"auctions/cheffins/catalogue-{catalogue['catalogue_id']}.json"
        old_state = None
        if state_path.exists():
            try:
                old_state = json.loads(state_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        old_rows = existing_by_auction.get(f"cheffins:{catalogue['catalogue_id']}", [])
        pdf_recovery_current = (
            catalogue["catalogue_id"] not in CATALOGUE_PDF_RECOVERY or
            (old_state and old_state.get("catalogue_pdf_recovery_version") ==
             CATALOGUE_PDF_RECOVERY_VERSION)
        )
        if (old_state and pdf_recovery_current and
                (old_rows or old_state.get("lots_captured") == 0) and
                old_state.get("source_rows_complete") and
                old_state.get("published_lots_offered") == catalogue["published_lots"] and
                old_state.get("lots_captured") == len(old_rows) and
                (old_state.get("catalogue_complete") or
                 old_state.get("addendum_recovery_version") == ADDENDUM_RECOVERY_VERSION)):
            states[catalogue["catalogue_id"]] = old_state
            run_rows.extend(old_rows)
            reused += 1
        else:
            pending.append(catalogue)

    def capture(catalogue: dict):
        raw, resolved = get(catalogue["url"])
        sha, retrieved_at = corpus.digest(raw), corpus.now()
        snapshot = corpus.DATA / "sources/cheffins" / f"catalogue-{catalogue['catalogue_id']}-{sha[:16]}.json.gz"
        evidence = {"source_url": resolved, "index_url": resolved_index,
                    "retrieved_at": retrieved_at, "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "index_snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party unpaginated historical property-auction catalogue"}
        corpus.save_gzip(snapshot, {"evidence": evidence,
            "html": raw.decode("utf-8", "replace")})
        html = raw.decode("utf-8", "replace")
        date_override = None
        if not DATE_RE.search(clean(BeautifulSoup(html, "lxml").get_text(" ", strip=True)) or ""):
            recovery = DATE_RECOVERY.get(catalogue["catalogue_id"])
            if not recovery:
                raise ValueError("catalogue has no exact date and no recovery evidence")
            recovery_raw, recovery_url = get(recovery["url"])
            recovery_html = recovery_raw.decode("utf-8", "replace")
            recovery_text = clean(BeautifulSoup(recovery_html, "lxml").get_text(" ", strip=True)) or ""
            if not recovery["required"].search(recovery_text):
                raise ValueError("date recovery page lacks required auction/date evidence")
            recovery_sha = corpus.digest(recovery_raw)
            recovery_snapshot = corpus.DATA / "sources/cheffins" / (
                f"catalogue-{catalogue['catalogue_id']}-date-{recovery_sha[:16]}.json.gz"
            )
            corpus.save_gzip(recovery_snapshot, {"source_url": recovery_url,
                "retrieved_at": corpus.now(), "sha256": recovery_sha, "html": recovery_html})
            evidence["auction_date_evidence_url"] = recovery_url
            evidence["auction_date_snapshot_path"] = str(recovery_snapshot.relative_to(corpus.ROOT))
            evidence["auction_date_sha256"] = recovery_sha
            date_override = recovery["auction_date"]
        state, rows = parse_catalogue(html, catalogue, evidence, date_override)
        pdf_url = CATALOGUE_PDF_RECOVERY.get(catalogue["catalogue_id"])
        if pdf_url and not state["catalogue_complete"]:
            pdf_raw, resolved_pdf = get(pdf_url)
            pdf_sha = corpus.digest(pdf_raw)
            pdf_snapshot = corpus.DATA / "sources/cheffins" / (
                f"catalogue-{catalogue['catalogue_id']}-original-catalogue-"
                f"{pdf_sha[:16]}.pdf.gz"
            )
            pdf_snapshot.parent.mkdir(parents=True, exist_ok=True)
            with gzip.GzipFile(filename=str(pdf_snapshot), mode="wb", mtime=0) as handle:
                handle.write(pdf_raw)
            pdf_evidence = {
                "source_url": resolved_pdf,
                "catalogue_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": pdf_sha,
                "snapshot_path": str(pdf_snapshot.relative_to(corpus.ROOT)),
                "catalogue_snapshot_path": evidence["snapshot_path"],
                "basis": "first-party complete property-auction catalogue PDF",
            }
            recovered = catalogue_pdf_rows(
                pdf_raw, catalogue, state["auction_date"], pdf_evidence
            )
            state, rows = parse_catalogue(
                html, catalogue, evidence, date_override, recovered
            )
            state["catalogue_pdf_recovery_version"] = CATALOGUE_PDF_RECOVERY_VERSION
            state["catalogue_pdf_lots_recovered"] = len(recovered)
            state["catalogue_pdf_source_evidence"] = pdf_evidence
            state["completion_scope"] = (
                "all numbered lots in the first-party complete catalogue PDF"
            )
        addendum_match = ADDENDUM_RE.search(html)
        if addendum_match and not state["catalogue_complete"]:
            addendum_raw, addendum_url = get(addendum_match.group(0))
            addendum_sha = corpus.digest(addendum_raw)
            addendum_snapshot = corpus.DATA / "sources/cheffins" / (
                f"catalogue-{catalogue['catalogue_id']}-addendum-{addendum_sha[:16]}.pdf.gz"
            )
            addendum_snapshot.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(addendum_snapshot, "wb") as handle:
                handle.write(addendum_raw)
            addendum_evidence = {
                "source_url": addendum_url,
                "catalogue_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": addendum_sha,
                "snapshot_path": str(addendum_snapshot.relative_to(corpus.ROOT)),
                "catalogue_snapshot_path": evidence["snapshot_path"],
                "basis": "first-party catalogue-linked published auction addendum",
            }
            addendum_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(addendum_raw)).pages)
            recovered = addendum_rows(addendum_text, catalogue, state["auction_date"],
                                      addendum_evidence, rows)
            state, rows = parse_catalogue(html, catalogue, evidence, date_override, recovered)
            state["addendum_source_evidence"] = addendum_evidence
        if not state["catalogue_complete"]:
            visible_rows = len(rows)
            gaps = denominator_gap_rows(catalogue, state["auction_date"], evidence, rows)
            if gaps:
                rows.extend(gaps)
                state["visible_source_rows"] = visible_rows
                state["lots_captured"] = len(rows)
                state["inferred_gap_lots_banked"] = len(gaps)
                state["partial_reason"] = (
                    f"{len(gaps)} published lot identities survive only as gaps in the "
                    "retained first-party numeric sequence; address and result remain null"
                )
            else:
                state["inferred_gap_lots_banked"] = 0
        return catalogue["catalogue_id"], state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        jobs = {pool.submit(capture, catalogue): catalogue for catalogue in pending}
        for future in as_completed(jobs):
            catalogue = jobs[future]
            try:
                catalogue_id, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/cheffins/catalogue-{catalogue_id}.json", state)
                states[catalogue_id] = state
                run_rows.extend(rows)
                print("CHEFFINS", len(states), "/", len(catalogues), "catalogues",
                      len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"catalogue_id": catalogue["catalogue_id"],
                    "url": catalogue["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})
    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("cheffins/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {"checked_at": corpus.now(), "source_url": INDEX,
        "catalogues_discovered": len(catalogues), "catalogues_captured": len(states),
        "catalogues_complete": sum(bool(s.get("catalogue_complete")) for s in states.values()),
        "catalogues_partial": sum(not s.get("catalogue_complete") for s in states.values()),
        "catalogues_reused": reused,
        "published_lots": sum(item["published_lots"] for item in catalogues),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "index_evidence": index_evidence, "auctions": states, "failures": failures}
    corpus.save_json(corpus.DATA / "cheffins_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reparse-saved-pdf":
        reparse_saved_catalogue_pdf(sys.argv[2])
    else:
        harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
