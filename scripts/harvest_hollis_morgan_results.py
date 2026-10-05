"""Bank Hollis Morgan's retained first-party 2014-2015 results catalogues.

Those first-party PDF result catalogues expose one stable property URL per
surviving property entry, along with its address, guide and outcome.  We bank
every URL-bearing entry and retain page-text snapshots.  The original lot
denominator is not consistently machine-reconcilable (some entries cover
multiple lot numbers), so the catalogues remain explicitly incomplete even
when every surviving URL-bearing row has been captured.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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


BASE = "https://www.hollismorgan.co.uk"
ARCHIVE_TEMPLATE = BASE + "/auctions/auction-archive/auction-archive-{year}.html"
YEARS = (2014, 2015)
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_RE = re.compile(
    r"https?://www\.hollismorgan\.co\.uk/property/\s*(\d[\d ]{5,})\s*/result_auction",
    re.I,
)
DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday)[, ]+"
    r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",
    re.I,
)
LOT_RE = re.compile(r"\bLOT\s*(\d+[A-Z]?)\b", re.I)
GUIDE_RE = re.compile(r"GUIDE\s+PRICE\s*:?\s*£\s*([\d,.]+)\s*(M|K)?", re.I)
PRICE_RE = re.compile(r"£\s*([\d,.]+)\s*(M(?:ILL?ION)?|K)?", re.I)
STOP_ADDRESS_RE = re.compile(
    r"(?:GUIDE PRICE|VIEW FULL DETAILS|SOLICITOR|VIEWING|PROPERTY AREA|"
    r"HOLLIS\s+MORGAN|\bLOT\b|@|https?://|^\d+$)",
    re.I,
)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def manifest(html: str, year: int, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for link in soup.select('a[href*="archivepdf"]'):
        container = link.find_parent("div", class_=lambda value: value and "green-border-box" in value)
        label = clean(container.get_text(" ", strip=True) if container else link.get_text(" ", strip=True))
        if not label or str(year) not in label:
            continue
        out.append({
            "year": year,
            "label": label,
            "pdf_url": urljoin(page_url, link.get("href") or ""),
        })
    if len(out) != 6 or len({item["pdf_url"] for item in out}) != len(out):
        raise ValueError(f"Hollis Morgan {year} archive exposes {len(out)} distinct result PDFs, expected 6")
    return out


def auction_date(page_texts: list[str]) -> str:
    match = DATE_RE.search("\n".join(page_texts[:4]))
    if not match:
        raise ValueError("exact auction date is absent from result catalogue")
    value = f"{match.group(1)} {match.group(2)} {match.group(3)}"
    return datetime.strptime(value.title(), "%d %B %Y").date().isoformat()


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def money(number: str | None, scale: str | None = None) -> int | None:
    if not number:
        return None
    value = float(number.replace(",", ""))
    scale = (scale or "").upper()
    if scale.startswith("M"):
        value *= 1_000_000
    elif scale == "K":
        value *= 1_000
    return int(round(value)) if value > 0 else None


def address_from_page(text: str, prefer_last: bool = False) -> tuple[str | None, str | None]:
    lines = [clean(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    indexes = range(len(lines) - 1, -1, -1) if prefer_last else range(len(lines))
    for index in indexes:
        line = lines[index]
        match = corpus.PC.search(line)
        if not match:
            continue
        current = line[: match.end()].strip(" ,")
        pieces = [current]
        # A line containing only the postcode/locality needs one or two exact
        # preceding source lines. Stop at catalogue metadata rather than guess.
        while len(pieces) < 3 and index > 0:
            previous = lines[index - 1]
            if "GUIDE PRICE" in previous.upper() and "+++" in previous:
                previous = previous.rsplit("+++", 1)[-1].strip(" ,")
                if not previous:
                    break
            if STOP_ADDRESS_RE.search(previous):
                break
            before_postcode = corpus.PC.sub("", current)
            addressy = bool(re.search(r"\d", before_postcode))
            if addressy:
                break
            pieces.insert(0, previous.strip(" ,"))
            current = ", ".join(pieces)
            index -= 1
        address = clean(", ".join(pieces))
        return address, match.group().upper()
    return None, None


def result_phrases(text: str) -> list[str]:
    lines = [clean(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        upper = line.upper()
        if upper == "SOLD" and i + 1 < len(lines) and lines[i + 1].upper() in {"POST AUCTION", "AFTER AUCTION"}:
            line = f"SOLD {lines[i + 1]}"
            upper = line.upper()
            i += 1
        short = len(line) <= 55
        excluded = any(term in upper for term in (
            "VACANT POSSESSION", "BEING SOLD", "WHY SELL", "LOTS OFFERED", "SELL WITH",
        ))
        if short and not excluded and (
            re.fullmatch(r"(?:LOT\s*\d+\s+)?(?:BOTH |ALL )?SOLD(?:\s+(?:AGREED\s+)?PRIOR|\s+POST AUCTION|\s+AFTER AUCTION)?(?:\s*@?\s*£\s*[\d,./]+\s*(?:K|M(?:ILL?ION)?)?)?", line, re.I)
            or re.fullmatch(r"(?:LOT)?SOLD(?:\s*@?\s*£\s*[\d,./]+\s*(?:K|M(?:ILL?ION)?)?)?", line, re.I)
            or re.fullmatch(r"WITHDRAWN(?:\s+.*)?|POSTPONED(?:\s+.*)?|UNSOLD|AVAILABLE(?:\s*:?\s+.*)?|STILL AVAILABLE(?:\s+.*)?|OFFERS (?:INVITED|RECEIVED POST AUCTION)|SALE AGREED(?:\s+.*)?", line, re.I)
        ):
            out.append(line)
        i += 1
    return out


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").upper()
    if "WITHDRAWN" in text:
        status = "withdrawn"
    elif "POSTPONED" in text:
        status = "postponed"
    elif "UNSOLD" in text:
        status = "unsold"
    elif "AVAILABLE" in text:
        status = "available"
    elif "OFFERS INVITED" in text or "OFFERS RECEIVED" in text:
        status = "available"
    elif "SALE AGREED" in text:
        status = "sale_agreed"
    elif "PRIOR" in text:
        status = "sold_prior"
    elif "POST AUCTION" in text or "AFTER AUCTION" in text:
        status = "sold_after"
    elif "SOLD" in text:
        status = "sold"
    else:
        status = "unknown"
    match = PRICE_RE.search(text) if status in {"sold", "sold_prior", "sold_after"} else None
    return status, money(match.group(1), match.group(2)) if match else None


def parse_pages(page_texts: list[str], pdf_slug: str, pdf_url: str, evidence: dict) -> tuple[list[dict], str]:
    date = auction_date(page_texts)
    rows = []
    for page_number, text in enumerate(page_texts, 1):
        property_matches = list(PROPERTY_RE.finditer(text))
        property_ids = [match.group(1).replace(" ", "") for match in property_matches]
        if not property_ids:
            continue
        lots = ordered_unique(LOT_RE.findall(text))
        guides = [money(number, scale) for number, scale in GUIDE_RE.findall(text)]
        outcomes = result_phrases(text)
        address, postcode = address_from_page(text)
        locality_match = re.search(r"^([A-Za-z][A-Za-z .'-]+)\s+GUIDE PRICE", text, re.M | re.I)
        locality = clean(locality_match.group(1)) if locality_match else None
        for ordinal, property_id in enumerate(property_ids, 1):
            if len(property_ids) == 1:
                prefix = text[max(0, property_matches[0].start() - 600):property_matches[0].start()]
                specific_address, specific_postcode = address_from_page(prefix, prefer_last=True)
                row_address = specific_address or address
                row_postcode = specific_postcode or postcode
                lot = lots[0] if lots else None
                guide = guides[0] if guides else None
                outcome = outcomes[0] if len(outcomes) == 1 else None
            else:
                # PDF hyperlink annotations are sometimes extracted out of
                # visual order on combined-lot pages. Preserve every distinct
                # property ID, but keep row-level address/lot/guide null rather
                # than guessing which printed sub-lot belongs to which URL.
                row_address = None
                row_postcode = None
                lot = None
                guide = None
                outcome = outcomes[0] if len(outcomes) == 1 else None
            result_status, sale_price = status_and_price(outcome)
            if len(property_ids) > 1:
                sale_price = None
            printed_url = f"https://www.hollismorgan.co.uk/property/{property_id}/result_auction"
            source_token = f"{pdf_slug}:page:{page_number}:row:{ordinal}:property:{property_id}"
            row = corpus.base_row(
                "Hollis Morgan", f"hollis-morgan:{date}", date, lot, source_token, printed_url,
            )
            row.update(
                appearance_id=f"Hollis Morgan|{date}|{source_token}",
                address=row_address,
                postcode=row_postcode,
                locality=row_address or locality,
                sector=corpus.sector(text),
                property_type=None,
                guide_price=guide,
                sale_price=sale_price,
                status=result_status,
                description=None,
                image_urls=[],
                property_id=property_id,
                identity_method="first_party_auction_date_plus_pdf_page_row_and_property_id",
                record_quality="address_record" if row_address else "partial_lot",
                source_page=page_number,
                source_row_ordinal=ordinal,
                source_result_text=outcome,
                source_catalogue_url=pdf_url,
                auction_date_basis="exact date printed in first-party result catalogue",
                source_evidence={**evidence, "page": page_number},
            )
            rows.append(row)
    if not rows:
        raise ValueError(f"{pdf_slug} contains no URL-bearing property entries")
    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError(f"{pdf_slug} contains duplicate strict source-position identities")
    return rows, date


def fetch(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=180)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"response from {url} is unexpectedly short")
    return response.content, response.url


def pdf_pages(raw: bytes) -> list[str]:
    return [(page.extract_text() or "") for page in PdfReader(BytesIO(raw)).pages]


def harvest(workers: int = 4) -> None:
    items = []
    archive_evidence = []
    for year in YEARS:
        raw, resolved = fetch(ARCHIVE_TEMPLATE.format(year=year))
        html = raw.decode("utf-8", "replace")
        sha = corpus.digest(raw)
        snapshot = corpus.DATA / "sources/hollis-morgan" / f"archive-{year}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party annual auction-results archive",
        }
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        archive_evidence.append(evidence)
        items.extend(manifest(html, year, resolved))
    if len(items) != 12:
        raise ValueError(f"discovered {len(items)} retained result PDFs, expected 12")

    state_dir = corpus.DATA / "auctions/hollis-morgan"
    cached, pending = {}, []
    for item in items:
        slug = item["pdf_url"].rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        snapshots = sorted((corpus.DATA / "sources/hollis-morgan").glob(f"{slug}-*.json.gz"))
        if snapshots:
            saved = corpus.read_gzip(snapshots[-1])
            cached[item["pdf_url"]] = (saved["pages"], saved["evidence"])
        else:
            pending.append(item)

    fetched = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, item["pdf_url"]): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            fetched[item["pdf_url"]] = future.result()

    all_rows, states = [], []
    for item in items:
        pdf_url = item["pdf_url"]
        slug = pdf_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        if pdf_url in cached:
            pages, evidence = cached[pdf_url]
        else:
            raw, resolved = fetched[pdf_url]
            pages = pdf_pages(raw)
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/hollis-morgan" / f"{slug}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party result-catalogue PDF text extraction",
                "source_media_type": "application/pdf",
                "snapshot_payload": "ordered per-page extracted text",
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "pages": pages})
        rows, date = parse_pages(pages, slug, pdf_url, evidence)
        all_rows.extend(rows)
        state = {
            "auctioneer": "Hollis Morgan",
            "source_auction_id": f"hollis-morgan:{date}",
            "auction_date": date,
            "catalogue_complete": False,
            "source_rows_complete": True,
            "published_url_bearing_rows": len(rows),
            "lots_captured": len(rows),
            "pagination_reconciled": True,
            "denominator_reconciled": False,
            "incomplete_reason": "original lot denominator is not consistently separable where a PDF property entry represents multiple lot numbers",
            "source_url": pdf_url,
            "source_evidence": evidence,
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(state_dir / f"{date}.json", state)
        states.append(state)

    before_path = corpus.DATA / "appearances/hollis-morgan/canonical.jsonl.gz"
    before = {row["appearance_id"] for row in corpus.iter_rows(before_path)} if before_path.exists() else set()
    total = corpus.write_rows("hollis-morgan/canonical", all_rows)
    added = [row for row in all_rows if row["appearance_id"] not in before]
    dates = sorted(state["auction_date"] for state in states)
    summary = {
        "checked_at": corpus.now(),
        "archive_urls": [item["source_url"] for item in archive_evidence],
        "catalogues_discovered": len(items),
        "catalogues_source_rows_complete": len(states),
        "catalogues_original_denominator_reconciled": 0,
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [dates[0], dates[-1]],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in all_rows)),
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "hollis_morgan_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    harvest(workers)
