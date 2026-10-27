"""Bank Butters John Bee's retained first-party catalogue/result archive.

The first-party archive pairs a full catalogue with a compact result sheet for
each event.  Result-sheet tables are the authoritative individual appearance
inventory: every row has a printed lot number, address, guide and outcome.
Catalogues independently evidence the exact event date and can enrich the same
lot with property type, tenure and rent without creating another appearance.

The collector snapshots the archive HTML and every result PDF byte-for-byte.
Catalogue PDFs are large, so their SHA-256 and an immutable extracted-text
snapshot are retained alongside the original URL.  Every result table must be
sequential from lot 1 through its terminal lot before any row is admitted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import gzip
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import pdfplumber
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Butters John Bee"
SLUG = "butters-john-bee"
ARCHIVE_URL = "https://buttersjohnbee.com/auction-catalogues"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PARSER_VERSION = 1
DATE_RE = re.compile(
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(20\d{2})",
    re.I,
)
MONEY_RE = re.compile(r"£?\s*([\d,]+(?:\.\d+)?)")
MONEY_FULL_RE = re.compile(r"£?\s*[\d,]+(?:\.\d+)?")
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*"
    r"(per\s+annum|p\.?\s*/?\s*a\.?|pa\b|per\s+calendar\s+month|"
    r"per\s+month|monthly|p\.?\s*c\.?\s*m\.?)",
    re.I,
)


def clean(value: object | None) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def amount(value: str | None) -> int | None:
    match = MONEY_RE.search(clean(value) or "")
    if not match:
        return None
    parsed = corpus.money(match.group(1))
    return int(parsed) if parsed else None


def exact_date(text: str | None) -> str | None:
    match = DATE_RE.search(clean(text) or "")
    if not match:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def status_and_price(result: str | None) -> tuple[str, int | None]:
    value = clean(result) or ""
    lower = value.casefold()
    price = amount(value) if MONEY_FULL_RE.fullmatch(value) else None
    if price is not None:
        return "sold", price
    if "sold prior" in lower:
        return "sold_prior", None
    if "sold post" in lower or "sold after" in lower:
        return "sold_after", None
    if "withdrawn" in lower:
        return "withdrawn", None
    if "postponed" in lower:
        return "postponed", None
    if "unsold" in lower:
        return "unsold", None
    return "unknown", None


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=180)
            response.raise_for_status()
            if len(response.content) < 800:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def html_snapshot(raw: bytes, resolved: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"archive-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "first-party catalogue and result PDF index",
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def result_snapshot(raw: bytes, resolved: str, auction_date: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"result-{auction_date}-{sha[:16]}.pdf.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": "first-party complete auction result sheet PDF",
        "auction_date": auction_date,
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return evidence


def catalogue_snapshot(text: str, raw: bytes, resolved: str, auction_date: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"catalogue-{auction_date}-{sha[:16]}.txt.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "source_size_bytes": len(raw),
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "snapshot_format": "pdftotext-layout UTF-8 text from immutable first-party PDF",
        "basis": "first-party complete auction catalogue PDF",
        "auction_date": auction_date,
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(text.encode("utf-8"), mtime=0))
    return evidence


def parse_archive(html: str, base_url: str = ARCHIVE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for link in soup.select("a[href]"):
        label = clean(link.get_text(" ", strip=True))
        if label not in {"View Catalogue", "Results"}:
            continue
        url = urljoin(base_url, link.get("href") or "")
        if not url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        heading = link.find_previous(["h2", "h3", "h4", "h5", "h6"])
        links.append({
            "label": label,
            "url": url,
            "archive_date_text": clean(heading.get_text(" ", strip=True)) if heading else None,
        })
    if not links or len(links) % 2:
        raise ValueError("archive does not expose complete catalogue/result pairs")
    events = []
    for position in range(0, len(links), 2):
        catalogue, result = links[position : position + 2]
        if catalogue["label"] != "View Catalogue" or result["label"] != "Results":
            raise ValueError(f"archive link sequence is not catalogue/result at position {position + 1}")
        if catalogue["archive_date_text"] != result["archive_date_text"]:
            raise ValueError("catalogue and result links have different archive headings")
        events.append({
            "source_position": position // 2 + 1,
            "archive_date_text": catalogue["archive_date_text"],
            "catalogue_url": catalogue["url"],
            "result_url": result["url"],
        })
    if len({event["catalogue_url"] for event in events}) != len(events):
        raise ValueError("archive contains duplicate catalogue URLs")
    if len({event["result_url"] for event in events}) != len(events):
        raise ValueError("archive contains duplicate result URLs")
    return events


def extract_catalogue_text(raw: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for Butters John Bee catalogue reconciliation")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "catalogue.pdf"
        output = Path(directory) / "catalogue.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(output)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return output.read_text(errors="replace")


def catalogue_lot_pages(text: str) -> dict[str, list[dict]]:
    lots: dict[str, list[dict]] = defaultdict(list)
    for page_number, page in enumerate(text.split("\f"), 1):
        head = "\n".join(page.splitlines()[:20])
        if not (re.search(r"\bLOT\b", head, re.I) and re.search(r"Guide\s+price", head, re.I)):
            continue
        numbers = []
        for line in head.splitlines():
            match = re.match(r"^\s*0*(\d{1,3})(?:\s{2,}|$)", line)
            if match:
                number = int(match.group(1))
                if number:
                    numbers.append(number)
        if not numbers:
            continue
        lot = str(numbers[0])
        lots[lot].append({"page_number": page_number, "text": page})
    return dict(lots)


def catalogue_enrichment(pages: list[dict], address: str) -> tuple[dict, str | None]:
    postcode = corpus.PC.search(address or "")
    selected = []
    if postcode:
        expected = re.sub(r"\s+", "", postcode.group()).casefold()
        for page in pages:
            observed = {
                re.sub(r"\s+", "", match.group()).casefold()
                for match in corpus.PC.finditer(page["text"])
            }
            if expected in observed:
                selected.append(page)
    if not selected:
        return {}, "catalogue lot page does not reconcile to result address postcode"
    text = "\n".join(page["text"] for page in selected)
    bullets = []
    for line in text.splitlines():
        if "•" not in line:
            continue
        value = line.split("•", 1)[1]
        value = re.split(r"\s{3,}", value, maxsplit=1)[0]
        value = clean(value)
        if value and not value.casefold().startswith("guide/reserve"):
            bullets.append(value)
    bullets = list(dict.fromkeys(bullets))
    rent_matches = []
    for match in RENT_RE.finditer(text):
        value = amount(match.group(1))
        unit = match.group(2)
        if value is not None and re.search(r"month|p\.?\s*c\.?\s*m", unit, re.I):
            value *= 12
        if value is not None:
            rent_matches.append((value, clean(match.group(0))))
    distinct_rents = sorted({value for value, _ in rent_matches})
    tenure_values = [value for value in bullets if re.search(r"\b(?:freehold|leasehold)\b", value, re.I)]
    return {
        "property_type": bullets[0] if bullets else None,
        "description": "; ".join(bullets) if bullets else None,
        "tenure": "; ".join(tenure_values) if tenure_values else None,
        "annual_rent": distinct_rents[0] if len(distinct_rents) == 1 else None,
        "rent_text": "; ".join(dict.fromkeys(value for _, value in rent_matches)) or None,
        "catalogue_page_numbers": [page["page_number"] for page in selected],
    }, None


def parse_result_tables(raw: bytes, event: dict, evidence: dict) -> list[dict]:
    rows = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for raw_row in table:
                    if not raw_row or not (clean(raw_row[0]) or "").isdigit():
                        continue
                    lot = str(int(clean(raw_row[0]) or "0"))
                    address = clean(raw_row[1] if len(raw_row) > 1 else None)
                    tail = [clean(value) for value in raw_row[2:]]
                    guide_index = next(
                        (index for index, value in enumerate(tail)
                         if value and MONEY_FULL_RE.fullmatch(value)),
                        None,
                    )
                    guide_text = tail[guide_index] if guide_index is not None else None
                    after = [value for value in (tail[guide_index + 1 :] if guide_index is not None else tail) if value]
                    result_text = after[-1] if after else None
                    if not address or not result_text:
                        raise ValueError(
                            f"result row {event['auction_date']} lot {lot} lacks address or outcome: {raw_row!r}"
                        )
                    status, sale_price = status_and_price(result_text)
                    if status == "unknown":
                        raise ValueError(
                            f"result row {event['auction_date']} lot {lot} has unknown outcome {result_text!r}"
                        )
                    source_id = f"{event['auction_date']}:{lot}"
                    auction_id = f"{SLUG}:{event['auction_date']}"
                    row = corpus.base_row(SOURCE, auction_id, event["auction_date"], lot, source_id, event["result_url"])
                    postcode = corpus.PC.search(address)
                    row.update(
                        appearance_id=f"{SOURCE}|{auction_id}|{lot}",
                        address=address,
                        postcode=postcode.group().upper() if postcode else None,
                        locality=address,
                        sector=corpus.sector(address),
                        guide_price=amount(guide_text),
                        sale_price=sale_price,
                        status=status,
                        property_id=source_id,
                        identity_method="first_party_exact_auction_date_and_printed_lot_number",
                        record_quality="address_record",
                        source_position=len(rows) + 1,
                        result_pdf_page=page_number,
                        guide_price_text=guide_text,
                        source_result_text=result_text,
                        source_platform="Butters John Bee first-party catalogue/result archive",
                        operator_legal_name="Butters John Bee Limited",
                        operator_company_number="05289439",
                        source_evidence=evidence,
                    )
                    rows.append(row)
    lots = [int(row["lot_number"]) for row in rows]
    if not lots or lots != list(range(1, max(lots) + 1)):
        raise ValueError(
            f"result sheet {event['auction_date']} is not a complete sequential lot inventory: {lots[:5]}...{lots[-5:]}"
        )
    if len({row["appearance_id"] for row in rows}) != len(rows):
        raise ValueError(f"result sheet {event['auction_date']} contains duplicate identities")
    return rows


def global_exact_appearances(exclude_slug: str) -> dict[tuple[str, str], list[dict]]:
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                    "original_url": row.get("original_url"),
                })
    return values


def harvest(workers: int = 10, cache_dir: Path | None = None) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_evidence = html_snapshot(archive_raw, archive_resolved)
    events = parse_archive(archive_raw.decode("utf-8", "replace"), archive_resolved)

    fetched, failures = {}, []
    tasks = [(event, kind, event[f"{kind}_url"]) for event in events for kind in ("catalogue", "result")]

    def fetch_task(event: dict, kind: str, url: str) -> tuple[bytes, str]:
        if cache_dir:
            index = event["source_position"] * 2 - (1 if kind == "catalogue" else 0)
            path = cache_dir / f"{index:02d}.pdf"
            if path.exists():
                return path.read_bytes(), url
        return get(url)

    with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
        futures = {pool.submit(fetch_task, *task): task for task in tasks}
        for future in as_completed(futures):
            event, kind, url = futures[future]
            key = (event["source_position"], kind)
            try:
                fetched[key] = future.result()
            except Exception as exc:
                failures.append({"url": url, "kind": kind, "error": f"{type(exc).__name__}: {exc}"})
    if failures:
        raise RuntimeError(f"PDF downloads failed before admission: {failures}")

    all_rows, event_states, catalogue_mismatches = [], [], []
    for event in events:
        catalogue_raw, catalogue_resolved = fetched[(event["source_position"], "catalogue")]
        result_raw, result_resolved = fetched[(event["source_position"], "result")]
        catalogue_text = extract_catalogue_text(catalogue_raw)
        auction_date = exact_date(catalogue_text.split("\f", 1)[0])
        if not auction_date:
            raise ValueError(f"catalogue {catalogue_resolved} has no exact auction date")
        published_heading_date = exact_date(event["archive_date_text"])
        if published_heading_date and published_heading_date != auction_date:
            raise ValueError("archive heading and catalogue auction date disagree")
        event.update(auction_date=auction_date, catalogue_url=catalogue_resolved, result_url=result_resolved)
        result_evidence = result_snapshot(result_raw, result_resolved, auction_date)
        catalogue_evidence = catalogue_snapshot(catalogue_text, catalogue_raw, catalogue_resolved, auction_date)
        rows = parse_result_tables(result_raw, event, result_evidence)
        pages_by_lot = catalogue_lot_pages(catalogue_text)
        matched = 0
        for row in rows:
            pages = pages_by_lot.get(row["lot_number"], [])
            enrichment, mismatch = catalogue_enrichment(pages, row["address"])
            if enrichment:
                row.update(enrichment)
                row["sector"] = corpus.sector(" ".join(filter(None, [row["address"], row.get("description")])) )
                row["catalogue_source_evidence"] = catalogue_evidence
                matched += 1
            elif mismatch:
                catalogue_mismatches.append({
                    "auction_date": auction_date,
                    "lot_number": row["lot_number"],
                    "address": row["address"],
                    "reason": mismatch,
                })
        all_rows.extend(rows)
        event_states.append({
            "auctioneer": SOURCE,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "source_url": result_resolved,
            "catalogue_url": catalogue_resolved,
            "visible_source_rows": len(rows),
            "lots_captured": len(rows),
            "catalogue_lots_enriched": matched,
            "source_rows_complete": True,
            "catalogue_complete": True,
            "completion_scope": "every sequential row in the first-party result sheet; catalogue text retained for enrichment",
            "source_evidence": [archive_evidence, result_evidence, catalogue_evidence],
            "errors": [],
            "checked_at": corpus.now(),
        })

    event_dates = [event["auction_date"] for event in events]
    if len(event_dates) != len(set(event_dates)):
        raise ValueError("archive contains duplicate auction dates")
    exact_global = global_exact_appearances(SLUG)
    overlap_exclusions, admissible = [], []
    for row in all_rows:
        matches = exact_global.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlap_exclusions.append({
                "auction_date": row["auction_date"],
                "address": row["address"],
                "butters_john_bee_appearance_id": row["appearance_id"],
                "existing": matches,
            })
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    existing_by_id = {row["appearance_id"]: row for row in existing}
    merged = dict(existing_by_id)
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    persisted = list(corpus.iter_rows(path))
    if len(persisted) != len(merged) or {row["appearance_id"] for row in persisted} != set(merged):
        raise RuntimeError("Butters John Bee canonical rows did not persist exactly")
    new_rows = [row for key, row in merged.items() if key not in existing_by_id]

    for state in event_states:
        state["exact_global_overlaps_excluded"] = sum(
            item["butters_john_bee_appearance_id"].startswith(
                f"{SOURCE}|{state['source_auction_id']}|"
            )
            for item in overlap_exclusions
        )
        corpus.save_json(
            corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json",
            state,
        )

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    historical_new = [row for row in new_rows if cutoff <= (row.get("auction_date") or "") <= today]
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "operator_legal_name": "Butters John Bee Limited",
        "operator_company_number": "05289439",
        "trading_name_not_counted_as_separate_operator": "butters john bee",
        "branches_not_counted_as_separate_auctioneers": True,
        "related_group_brands_not_counted_as_butters_john_bee_operators": ["Darlows", "Haybrook", "haart"],
        "parser_version": PARSER_VERSION,
        "source_url": archive_resolved,
        "paired_auction_events": len(events),
        "visible_source_rows": len(all_rows),
        "distinct_source_identities": len({row["appearance_id"] for row in all_rows}),
        "appearances_captured": len(merged),
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical_new),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_new_undated": sum(not row.get("auction_date") for row in new_rows),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(overlap_exclusions),
        "exact_global_overlap_exclusions": overlap_exclusions,
        "new_source_years": sorted(years_after - years_before),
        "source_years_visible": sorted({int(row["auction_date"][:4]) for row in all_rows}),
        "date_range": [min(event_dates), max(event_dates)],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "catalogue_lots_enriched": sum(bool(row.get("catalogue_source_evidence")) for row in all_rows),
        "catalogue_enrichment_mismatches": len(catalogue_mismatches),
        "catalogue_enrichment_mismatch_examples": catalogue_mismatches[:100],
        "completion_scope": "all sequential rows in 23 retained first-party result sheets paired to exact-dated catalogues; archive before 2024 is not published on the current page",
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "butters_john_bee_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    harvest(args.workers, args.cache_dir)


if __name__ == "__main__":
    main()
