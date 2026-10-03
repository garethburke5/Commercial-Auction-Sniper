"""Bank Pugh's retained first-party property-search archive.

Stable property URLs identify appearances. The first pass reconciles every
result page; later passes stop at a complete page of previously observed IDs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

BASE = "https://www.pugh-auctions.com"
INDEX = BASE + "/property-search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Commercial-Auction-Sniper historical corpus)"}
PROPERTY_RE = re.compile(r"/property/([^/?#]+)", re.I)
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RESULT_COUNT_RE = re.compile(r"Search Results:\s*([\d,]+)\s+properties", re.I)
COMPLETE_STATUSES = {"sold", "sold_prior", "sold_after", "unsold", "withdrawn", "postponed"}
PARAMS = {"filter-date_added": "anytime", "filter-guide_price_from": "",
          "filter-guide_price_to": "", "filter-postcode-town": "",
          "filter-property-type": "all", "filter-radius": "area", "filters": "1",
          "include-sold": "on", "order-results": "date-desc", "style": "list"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def page_url(page: int) -> str:
    return INDEX + "?" + urlencode({**PARAMS, "page": page})


def get(session: requests.Session, url: str, attempts: int = 4) -> tuple[str, bytes]:
    for attempt in range(attempts):
        try:
            response = session.get(url, headers=HEADERS, timeout=60)
            response.raise_for_status()
            return response.url, response.content
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:96] or "auction"


def money_from(pattern: str, value: str | None) -> int | None:
    match = re.search(pattern + r"\s*£\s*([\d,]+(?:\.\d+)?)\s*([mk])?", value or "", re.I)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    number *= {"m": 1_000_000, "k": 1_000}.get((match.group(2) or "").lower(), 1)
    return int(round(number))


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None, int | None]:
    text = clean(value) or ""
    low = text.lower()
    sale = money_from(r"sold\s+for", text)
    guide = money_from(r"guide(?:\s+price)?\s*:?", text)
    guide_high = money_from(r"(?:to\s*:?|[-–])", text) if guide is not None else None
    if "sold prior" in low:
        status = "sold_prior"
    elif "sold post" in low or "sold after" in low or "post auction" in low:
        status = "sold_after"
    elif "sold" in low:
        status = "sold"
    elif "unsold" in low:
        status = "unsold"
    elif "withdrawn" in low:
        status = "withdrawn"
    elif "postponed" in low:
        status = "postponed"
    elif guide is not None:
        status = "available"
    else:
        status = "unknown"
    return status, sale, guide, guide_high


def parse_page(raw: bytes, requested_url: str, evidence: dict) -> tuple[list[dict], int | None, int]:
    soup = BeautifulSoup(raw, "lxml")
    total_match = RESULT_COUNT_RE.search(soup.get_text(" ", strip=True))
    result_count = int(total_match.group(1).replace(",", "")) if total_match else None
    page_numbers = []
    for link in soup.select('a[href*="page="]'):
        try:
            page_numbers.extend(int(v) for v in parse_qs(urlparse(link.get("href") or "").query).get("page", []))
        except ValueError:
            continue
    rows, seen = [], set()
    for tr in soup.select("table tr"):
        cells = tr.find_all("td")
        link = tr.select_one('a[href*="/property/"]')
        if not link or len(cells) < 5:
            continue
        original_url = urljoin(BASE, link.get("href") or "")
        match = PROPERTY_RE.search(urlparse(original_url).path)
        if not match:
            continue
        source_id = match.group(1)
        if source_id in seen:
            raise ValueError(f"Repeated property ID {source_id} on {requested_url}")
        seen.add(source_id)
        values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
        date_text = next((v for v in values if v and DATE_RE.fullmatch(v)), None)
        if not date_text:
            raise ValueError(f"Property {source_id} has no exact auction date")
        auction_date = datetime.strptime(date_text, "%d/%m/%Y").date().isoformat()
        date_index = values.index(date_text)
        venue = values[date_index - 1] if date_index else None
        result_text = " | ".join(v for v in values[date_index + 1:] if v and v.lower() != "view")
        status, sale_price, guide_price, guide_high = status_and_prices(result_text)
        address = clean(link.get_text(" ", strip=True))
        property_text = clean(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else address
        description = clean(property_text[len(address):]) if property_text and address and property_text.startswith(address) else None
        lot = clean(values[0])
        if lot and not re.fullmatch(r"\d+[A-Za-z]?", lot):
            lot = None
        auction_id = f"pugh:{auction_date}:{slug(venue or 'auction')}"
        row = corpus.base_row("Pugh Auctioneers", auction_id, auction_date, lot, source_id, original_url)
        postcode_match = corpus.PC.search(address or "")
        row.update(address=address,
                   postcode=postcode_match.group().upper() if postcode_match else None,
                   sector=corpus.sector(" ".join(filter(None, [address, description]))),
                   status=status, guide_price=guide_price, guide_price_high=guide_high,
                   sale_price=sale_price, description=description, result_text=result_text or None,
                   record_quality="address_record" if address else "partial_lot",
                   identity_method="source_property_id",
                   source_evidence={**evidence, "listing_url": original_url, "published_row": values})
        rows.append(row)
    if not rows:
        raise ValueError(f"Official page exposed zero property rows: {requested_url}")
    return rows, result_count, max(page_numbers, default=1)


def bankable(row: dict, today=None) -> bool:
    today = today or datetime.now().date()
    date = datetime.strptime(row["auction_date"], "%Y-%m-%d").date()
    return date <= today or row.get("status") in COMPLETE_STATUSES


def address_key(value: str | None) -> str | None:
    value = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return value or None


def legacy_pugh_rows() -> dict[tuple[str, str], list[tuple[Path, dict]]]:
    found = defaultdict(list)
    for path in sorted((corpus.DATA / "appearances/source-corpus").glob("*.jsonl.gz")):
        for row in corpus.iter_rows(path):
            if row.get("auctioneer") != "Pugh Auctioneers" or not row.get("address"):
                continue
            key = (address_key(row.get("address")), str(row.get("lot_number") or "").lstrip("0").lower())
            found[key].append((path, row))
    return found


def strict_legacy_match(row: dict, candidates: list[tuple[Path, dict]]) -> tuple[Path, dict] | None:
    current = datetime.strptime(row["auction_date"], "%Y-%m-%d").date()
    matches = []
    for path, old in candidates:
        try:
            previous = datetime.strptime(old.get("auction_date") or "", "%Y-%m-%d").date()
        except ValueError:
            continue
        if abs((current - previous).days) <= 14:
            matches.append((path, old))
    return matches[0] if len(matches) == 1 else None


def harvest() -> None:
    summary_path = corpus.DATA / "pugh_collection.json"
    try:
        previous = json.loads(summary_path.read_text())
    except (OSError, ValueError, TypeError):
        previous = {}
    observed_before = set(previous.get("observed_source_ids") or [])
    full_scan = not (previous.get("archive_pagination_complete") and observed_before)
    existing_path = corpus.DATA / "appearances/pugh-auctions/property-search.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    existing_ids = {str(row.get("source_lot_id")) for row in existing if row.get("source_lot_id")}
    legacy = legacy_pugh_rows()
    enriched_by_path, rows_to_write = defaultdict(list), []
    observed, pages_captured, page_counts = set(observed_before), [], {}
    failures, run_new = [], []
    result_count, last_page, page = None, 1, 1
    session = requests.Session()
    while page <= last_page:
        requested = page_url(page)
        try:
            final_url, raw = get(session, requested)
            sha256, retrieved = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources/pugh" / f"property-search-page-{page:03d}-{sha256[:16]}.json.gz"
            evidence = {"source_url": requested, "final_url": final_url,
                        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "sha256": sha256, "retrieved_at": retrieved,
                        "basis": "visible row in Pugh's retained first-party property-search archive"}
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
            parsed, page_total, page_last = parse_page(raw, requested, evidence)
            if page == 1:
                result_count = page_total
                last_page = page_last or (math.ceil(result_count / len(parsed)) if result_count else 1)
            elif page_total is not None and result_count is not None and page_total != result_count:
                raise ValueError("Published result count changed during traversal")
            current_ids = {row["source_lot_id"] for row in parsed}
            observed.update(current_ids)
            page_counts[str(page)] = len(parsed)
            pages_captured.append(page)
            for row in parsed:
                if not bankable(row):
                    continue
                lot_key = str(row.get("lot_number") or "").lstrip("0").lower()
                match = strict_legacy_match(row, legacy.get((address_key(row.get("address")), lot_key), []))
                if match:
                    path, old = match
                    merged = {**old, **row, "appearance_id": old["appearance_id"],
                              "source_evidence": {**row["source_evidence"],
                                                  "prior_source_evidence": old.get("source_evidence")}}
                    enriched_by_path[path].append(merged)
                    continue
                rows_to_write.append(row)
                if row["source_lot_id"] not in existing_ids:
                    run_new.append(row)
            print(f"PUGH page={page}/{last_page} rows={len(parsed)} new={len(run_new)}", flush=True)
            if not full_scan and current_ids and current_ids.issubset(observed_before):
                break
        except Exception as exc:
            failures.append({"page": page, "url": requested,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
            print("FAILED", failures[-1], flush=True)
            if not full_scan:
                break
        page += 1
        time.sleep(0.05)
    corpus.write_rows("pugh-auctions/property-search", rows_to_write)
    for path, rows in enriched_by_path.items():
        key = str(path.relative_to(corpus.DATA / "appearances")).removesuffix(".jsonl.gz")
        corpus.write_rows(key, rows)
    saved = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    complete = bool(result_count and not failures and len(observed) == result_count and
                    (not full_scan or len(pages_captured) == last_page))
    summary = {"checked_at": corpus.now(), "source_url": INDEX,
               "published_property_rows": result_count, "observed_property_ids": len(observed),
               "observed_source_ids": sorted(observed), "pages_expected": last_page,
               "pages_captured_this_run": pages_captured, "page_counts": page_counts,
               "archive_pagination_complete": complete,
               "property_appearances_captured": len(saved) + sum(len(v) for v in enriched_by_path.values()),
               "canonical_shard_rows": len(saved),
               "legacy_rows_enriched": sum(len(v) for v in enriched_by_path.values()),
               "run_new_appearances": len(run_new),
               "run_new_address_records": sum(bool(row.get("address")) for row in run_new),
               "run_new_partial_lots": sum(not row.get("address") for row in run_new),
               "run_by_sector": dict(Counter(row.get("sector") for row in run_new)),
               "failures": failures}
    corpus.save_json(summary_path, summary)
    corpus.save_json(corpus.DATA / "auctions/pugh-auctions/property-search.json", {
        "auctioneer": "Pugh Auctioneers", "source_auction_id": "pugh:property-search-archive",
        "auction_date": None, "catalogue_complete": False,
        "archive_pagination_complete": complete, "lots_captured": summary["property_appearances_captured"],
        "source_url": INDEX, "pages_expected": last_page,
        "completion_scope": "all retained first-party property-search rows; original auction denominators unavailable",
        "errors": failures, "checked_at": corpus.now()})
    print(json.dumps({k: v for k, v in summary.items() if k != "observed_source_ids"}, indent=2), flush=True)
    if failures or not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
