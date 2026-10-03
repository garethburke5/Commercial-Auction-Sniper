"""Bank Pugh's retained first-party property-search archive.

The first pass reconciles every result page. Incomplete follow-ups fetch only
missing/failed pages; complete follow-ups stop at a page of known appearances.
A property URL is a property identity, not necessarily one auction appearance,
so a repeated URL is retained when its exact auction date or lot differs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
GRID_PAGE_SIZE = 80


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def page_url(page: int) -> str:
    return INDEX + "?" + urlencode({**PARAMS, "page": page})


def grid_page_url(page: int) -> str:
    """Canonical grid URL; legacy empty filter fields suppress deep grid pages."""
    return INDEX + "?" + urlencode({"order-results": "date-desc", "show-results": GRID_PAGE_SIZE,
                                      "include-sold": "on", "page": page})


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


def parse_page(raw: bytes, requested_url: str, evidence: dict) -> tuple[list[dict], int | None, int, int]:
    soup = BeautifulSoup(raw, "lxml")
    total_match = RESULT_COUNT_RE.search(soup.get_text(" ", strip=True))
    result_count = int(total_match.group(1).replace(",", "")) if total_match else None
    page_numbers = []
    for link in soup.select('a[href*="page="]'):
        try:
            page_numbers.extend(int(v) for v in parse_qs(urlparse(link.get("href") or "").query).get("page", []))
        except ValueError:
            continue
    rows, seen, source_row_count = [], {}, 0
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
        source_row_count += 1
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
        appearance_key = (source_id, auction_date, lot)
        if appearance_key in seen:
            existing = rows[seen[appearance_key]]
            if existing["source_evidence"]["published_row"] == values:
                continue
            alternate = existing["source_evidence"].setdefault("alternate_published_rows", [])
            alternate.append(values)
            existing["source_evidence"]["source_row_occurrences"] = 1 + len(alternate)
            continue
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
        seen[appearance_key] = len(rows)
        rows.append(row)
    if not rows:
        raise ValueError(f"Official page exposed zero property rows: {requested_url}")
    return rows, result_count, max(page_numbers, default=1), source_row_count


def list_source_ids(raw: bytes) -> list[str]:
    """Return every table-row property ID in source order, including duplicates."""
    soup = BeautifulSoup(raw, "lxml")
    found = []
    for tr in soup.select("table tr"):
        link = tr.select_one('a[href*="/property/"]')
        match = PROPERTY_RE.search(urlparse(link.get("href") or "").path) if link else None
        if match:
            found.append(match.group(1))
    return found


def parse_grid_page(raw: bytes, requested_url: str, evidence: dict) -> tuple[list[dict], int | None, int]:
    """Preserve source rows that the site's list template cannot render.

    These cards have a property identity, address and status/price, but no
    published auction date or lot number. They are saved outside appearances
    until another first-party source supplies those fields.
    """
    soup = BeautifulSoup(raw, "lxml")
    total_match = RESULT_COUNT_RE.search(soup.get_text(" ", strip=True))
    result_count = int(total_match.group(1).replace(",", "")) if total_match else None
    page_numbers = []
    for link in soup.select('a[href*="page="]'):
        try:
            page_numbers.extend(int(v) for v in parse_qs(urlparse(link.get("href") or "").query).get("page", []))
        except ValueError:
            continue
    cards = soup.select("div.group.bg-primary.rounded-b-lg.relative.h-full")
    rows = []
    for index, card in enumerate(cards, 1):
        links = card.select('a[href*="/property/"]')
        match = next((PROPERTY_RE.search(urlparse(link.get("href") or "").path) for link in links
                      if PROPERTY_RE.search(urlparse(link.get("href") or "").path)), None)
        if not match:
            continue
        source_id = match.group(1)
        original_url = urljoin(BASE, next(link.get("href") for link in links
                                          if PROPERTY_RE.search(urlparse(link.get("href") or "").path)))
        candidates = [clean(link.get_text(" ", strip=True)) for link in links]
        address = max((value for value in candidates if value and value.lower() != "view property"),
                      key=len, default=None)
        raw_text = clean(card.get_text(" ", strip=True))
        status, sale_price, guide_price, guide_high = status_and_prices(raw_text)
        postcode_match = corpus.PC.search(address or "")
        rows.append({
            "schema_version": 1, "auctioneer": "Pugh Auctioneers",
            "source_lot_id": source_id, "auction_date": None, "lot_number": None,
            "address": address, "postcode": postcode_match.group().upper() if postcode_match else None,
            "status": status, "sale_price": sale_price, "guide_price": guide_price,
            "guide_price_high": guide_high, "original_url": original_url,
            "source_row_index": index, "published_card_text": raw_text,
            "unresolved_reason": "Pugh grid row has no published auction date or lot number; list view returns HTTP 500",
            "source_evidence": evidence,
        })
    if not rows:
        raise ValueError(f"Official grid page exposed zero property rows: {requested_url}")
    return rows, result_count, max(page_numbers, default=1)


def tail_grid_plan(result_count: int, first_failed_page: int, normal_page_size: int,
                   grid_page_size: int = GRID_PAGE_SIZE) -> dict:
    first_failed_position = (first_failed_page - 1) * normal_page_size
    first_grid_page = first_failed_position // grid_page_size + 1
    overlap_rows = first_failed_position - (first_grid_page - 1) * grid_page_size
    normal_overlap_first = ((first_grid_page - 1) * grid_page_size) // normal_page_size + 1
    return {
        "first_grid_page": first_grid_page,
        "last_grid_page": math.ceil(result_count / grid_page_size),
        "overlap_rows": overlap_rows,
        "normal_overlap_pages": list(range(normal_overlap_first, first_failed_page)),
    }


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


def fetch_page(page: int) -> tuple[int, list[dict], int | None, int, int, list[str]]:
    """Fetch, snapshot and parse one archive page in an isolated session."""
    requested = page_url(page)
    final_url, raw = get(requests.Session(), requested)
    sha256, retrieved = corpus.digest(raw), corpus.now()
    snapshot = corpus.DATA / "sources/pugh" / f"property-search-page-{page:03d}-{sha256[:16]}.json.gz"
    evidence = {"source_url": requested, "final_url": final_url,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "sha256": sha256, "retrieved_at": retrieved,
                "basis": "visible row in Pugh's retained first-party property-search archive"}
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    parsed, page_total, page_last, source_rows = parse_page(raw, requested, evidence)
    return page, parsed, page_total, page_last, source_rows, list_source_ids(raw)


def fetch_grid_page(page: int) -> tuple[int, list[dict], int | None, int]:
    requested = grid_page_url(page)
    final_url, raw = get(requests.Session(), requested)
    sha256, retrieved = corpus.digest(raw), corpus.now()
    snapshot = corpus.DATA / "sources/pugh" / f"property-search-grid-080-page-{page:03d}-{sha256[:16]}.json.gz"
    evidence = {"source_url": requested, "final_url": final_url,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "sha256": sha256, "retrieved_at": retrieved,
                "basis": "visible card in Pugh's retained first-party property-search archive"}
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    rows, page_total, page_last = parse_grid_page(raw, requested, evidence)
    return page, rows, page_total, page_last


def harvest() -> None:
    summary_path = corpus.DATA / "pugh_collection.json"
    try:
        previous = json.loads(summary_path.read_text())
    except (OSError, ValueError, TypeError):
        previous = {}
    observed_before = set(previous.get("observed_source_ids") or [])
    repair_mode = bool(observed_before and not previous.get("archive_pagination_complete"))
    full_scan = not observed_before
    known_pages = {
        int(page) for page in (previous.get("pages_captured_this_run") or [])
        if str(page).isdigit()
    } if observed_before else set()
    previous_failures = {
        int(item["page"]) for item in (previous.get("failures") or [])
        if str(item.get("page", "")).isdigit()
    }
    grid_covered_pages = {
        int(page) for page in (previous.get("grid_covered_normal_pages") or [])
        if str(page).isdigit()
    }
    unresolved_rows = int(previous.get("unresolved_source_rows") or 0)
    source_rows_complete = bool(previous.get("source_rows_reconciled_complete"))
    existing_path = corpus.DATA / "appearances/pugh-auctions/property-search.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    existing_appearance_ids = {str(row.get("appearance_id")) for row in existing if row.get("appearance_id")}
    legacy = legacy_pugh_rows()
    enriched_by_path, rows_to_write = defaultdict(list), []
    observed = set(observed_before)
    pages_captured = sorted(known_pages)
    page_counts = dict(previous.get("page_counts") or {}) if observed_before else {}
    failures, run_new = [], []
    result_count, last_page = None, 1

    def process(result: tuple[int, list[dict], int | None, int, int, list[str]]) -> bool:
        current_page, parsed, page_total, _, source_rows, _ = result
        if page_total is not None and result_count is not None and page_total != result_count:
            raise ValueError("Published result count changed during traversal")
        current_ids = {row["source_lot_id"] for row in parsed}
        observed.update(current_ids)
        page_counts[str(current_page)] = source_rows
        if current_page not in pages_captured:
            pages_captured.append(current_page)
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
            if row["appearance_id"] not in existing_appearance_ids:
                run_new.append(row)
                existing_appearance_ids.add(row["appearance_id"])
        print(f"PUGH page={current_page}/{last_page} source_rows={source_rows} "
              f"appearances={len(parsed)} new={len(run_new)}", flush=True)
        return bool(current_ids and current_ids.issubset(observed_before))

    def checkpoint() -> None:
        corpus.write_rows("pugh-auctions/property-search", rows_to_write)
        for path, rows in enriched_by_path.items():
            key = str(path.relative_to(corpus.DATA / "appearances")).removesuffix(".jsonl.gz")
            corpus.write_rows(key, rows)
        corpus.save_json(summary_path, {
            "checked_at": corpus.now(), "source_url": INDEX,
            "published_property_rows": result_count, "observed_property_ids": len(observed),
            "observed_source_ids": sorted(observed), "pages_expected": last_page,
            "pages_captured_this_run": sorted(pages_captured), "page_counts": page_counts,
            "published_rows_reconciled": (sum(page_counts.get(str(page), 0)
                                                for page in range(1, last_page + 1)) + unresolved_rows),
            "source_rows_reconciled_complete": source_rows_complete,
            "grid_covered_normal_pages": sorted(grid_covered_pages),
            "unresolved_source_rows": unresolved_rows,
            "archive_pagination_complete": False, "run_new_appearances": len(run_new),
            "failures": failures,
        })

    try:
        first = fetch_page(1)
        _, first_rows, result_count, first_last, first_source_rows, _ = first
        last_page = first_last or (math.ceil(result_count / first_source_rows) if result_count else 1)
        first_seen_before = process(first) if not full_scan else False
        stop = bool(first_seen_before and not repair_mode)
    except Exception as exc:
        failures.append({"page": 1, "url": page_url(1),
                         "error": f"{type(exc).__name__}: {exc}"[:500]})
        print("FAILED", failures[-1], flush=True)
        stop = True

    if repair_mode:
        expected_counts = {
            page: (result_count - first_source_rows * (last_page - 1)
                   if page == last_page else first_source_rows)
            for page in range(1, last_page + 1)
        }
        anomalous = {
            page for page in pages_captured
            if page_counts.get(str(page)) != expected_counts.get(page)
        }
        targets = sorted(((set(range(1, last_page + 1)) - set(pages_captured)) |
                          previous_failures | anomalous) - {1} - grid_covered_pages)
    else:
        targets = list(range(2, last_page + 1))

    with ThreadPoolExecutor(max_workers=12) as pool:
        for offset in range(0, len(targets), 12):
            if stop:
                break
            batch = targets[offset:offset + 12]
            futures = {pool.submit(fetch_page, page): page for page in batch}
            results = {}
            for future in as_completed(futures):
                current_page = futures[future]
                try:
                    results[current_page] = future.result()
                except Exception as exc:
                    failures.append({"page": current_page, "url": page_url(current_page),
                                     "error": f"{type(exc).__name__}: {exc}"[:500]})
                    print("FAILED", failures[-1], flush=True)
            for current_page in sorted(results):
                try:
                    seen_before = process(results[current_page])
                    if not full_scan and not repair_mode and seen_before:
                        stop = True
                        break
                except Exception as exc:
                    failures.append({"page": current_page, "url": page_url(current_page),
                                     "error": f"{type(exc).__name__}: {exc}"[:500]})
                    print("FAILED", failures[-1], flush=True)
            checkpoint()
            if failures and not full_scan and not repair_mode:
                break

    # Pugh's final all-types list pages return HTTP 500, while the same rows
    # remain visible in the 80-card grid. Reconcile the grid boundary against
    # known list rows and preserve its undated cards separately. This proves
    # source-row pagination without inflating the auction-appearance count.
    failed_pages = sorted(int(item["page"]) for item in failures
                          if str(item.get("page", "")).isdigit())
    if (repair_mode and result_count and failed_pages and
            failed_pages == list(range(failed_pages[0], last_page + 1))):
        try:
            plan = tail_grid_plan(result_count, failed_pages[0], first_source_rows)
            overlap_ids = []
            for page in plan["normal_overlap_pages"]:
                normal = fetch_page(page)
                overlap_ids.extend(normal[5])
            grid_results = [fetch_grid_page(page)
                            for page in range(plan["first_grid_page"], plan["last_grid_page"] + 1)]
            if any(total != result_count for _, _, total, _ in grid_results):
                raise ValueError("Published result count changed in grid fallback")
            if any(last != plan["last_grid_page"] for _, _, _, last in grid_results):
                raise ValueError("Grid fallback page count did not reconcile")
            first_grid_rows = grid_results[0][1]
            first_grid_ids = [row["source_lot_id"] for row in first_grid_rows]
            if first_grid_ids[:plan["overlap_rows"]] != overlap_ids:
                raise ValueError("Grid/list boundary source IDs did not match exactly")
            tail_rows = first_grid_rows[plan["overlap_rows"]:]
            for _, rows, _, _ in grid_results[1:]:
                tail_rows.extend(rows)
            first_position = (failed_pages[0] - 1) * first_source_rows + 1
            for offset, row in enumerate(tail_rows):
                row["source_position"] = first_position + offset
            observed.update(row["source_lot_id"] for row in tail_rows)
            normal_reconciled = sum(page_counts.get(str(page), 0)
                                    for page in range(1, failed_pages[0]))
            if normal_reconciled + len(tail_rows) != result_count:
                raise ValueError("Hybrid list/grid row count did not equal published total")
            unresolved_path = corpus.DATA / "sources/pugh/undated-property-search-tail-records.json.gz"
            corpus.save_gzip(unresolved_path, {
                "checked_at": corpus.now(), "source_url": INDEX,
                "published_property_rows": result_count,
                "source_positions": [first_position, result_count],
                "rows": tail_rows,
            })
            unresolved_rows = len(tail_rows)
            grid_covered_pages.update(failed_pages)
            source_rows_complete = True
            failures = [{
                "kind": "unresolved_source_rows_without_auction_date",
                "source_rows": unresolved_rows,
                "unique_property_ids": len({row["source_lot_id"] for row in tail_rows}),
                "source_positions": [first_position, result_count],
                "record_path": str(unresolved_path.relative_to(corpus.ROOT)),
                "error": "Pugh grid preserves these address-bearing property rows, but publishes no auction date/lot and its list renderer returns HTTP 500; excluded from appearance totals",
            }]
            print(f"PUGH reconciled undated tail source_rows={unresolved_rows} "
                  f"positions={first_position}-{result_count}", flush=True)
        except Exception as exc:
            failures.append({"kind": "grid_tail_recovery", "url": grid_page_url(1),
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
            print("FAILED", failures[-1], flush=True)
    elif source_rows_complete and unresolved_rows:
        failures = [item for item in (previous.get("failures") or [])
                    if item.get("kind") == "unresolved_source_rows_without_auction_date"]
        unresolved_path = corpus.DATA / "sources/pugh/undated-property-search-tail-records.json.gz"
        if not unresolved_path.exists():
            try:
                first_failed_page = min(grid_covered_pages)
                plan = tail_grid_plan(result_count, first_failed_page, first_source_rows)
                restored = []
                for page in range(plan["first_grid_page"], plan["last_grid_page"] + 1):
                    snapshots = sorted((corpus.DATA / "sources/pugh").glob(
                        f"property-search-grid-080-page-{page:03d}-*.json.gz"))
                    if not snapshots:
                        raise ValueError(f"Missing saved grid snapshot for page {page}")
                    payload = corpus.read_gzip(snapshots[-1])
                    rows, page_total, page_last = parse_grid_page(
                        payload["html"].encode(), payload["evidence"]["source_url"], payload["evidence"])
                    if page_total != result_count or page_last != plan["last_grid_page"]:
                        raise ValueError("Saved grid snapshot no longer reconciles to Pugh state")
                    if page == plan["first_grid_page"]:
                        rows = rows[plan["overlap_rows"]:]
                    restored.extend(rows)
                if len(restored) != unresolved_rows:
                    raise ValueError("Saved grid snapshot row count changed")
                first_position = result_count - unresolved_rows + 1
                for offset, row in enumerate(restored):
                    row["source_position"] = first_position + offset
                corpus.save_gzip(unresolved_path, {
                    "checked_at": corpus.now(), "source_url": INDEX,
                    "published_property_rows": result_count,
                    "source_positions": [first_position, result_count],
                    "rows": restored,
                })
                for item in failures:
                    item["record_path"] = str(unresolved_path.relative_to(corpus.ROOT))
                print(f"PUGH restored unresolved tail records from saved snapshots rows={len(restored)}",
                      flush=True)
            except Exception as exc:
                failures.append({"kind": "unresolved_record_restore",
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
    corpus.write_rows("pugh-auctions/property-search", rows_to_write)
    for path, rows in enriched_by_path.items():
        key = str(path.relative_to(corpus.DATA / "appearances")).removesuffix(".jsonl.gz")
        corpus.write_rows(key, rows)
    saved = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    published_rows_reconciled = (sum(page_counts.get(str(page), 0)
                                     for page in range(1, last_page + 1)) + unresolved_rows)
    complete = bool(result_count and not failures and
                    len(set(pages_captured)) == last_page and
                    published_rows_reconciled == result_count)
    summary = {"checked_at": corpus.now(), "source_url": INDEX,
               "published_property_rows": result_count, "observed_property_ids": len(observed),
               "observed_source_ids": sorted(observed), "pages_expected": last_page,
               "pages_captured_this_run": sorted(pages_captured), "page_counts": page_counts,
               "published_rows_reconciled": published_rows_reconciled,
               "source_rows_reconciled_complete": source_rows_complete,
               "grid_covered_normal_pages": sorted(grid_covered_pages),
               "unresolved_source_rows": unresolved_rows,
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
        "published_property_rows": result_count,
        "published_rows_reconciled": published_rows_reconciled,
        "source_rows_reconciled_complete": source_rows_complete,
        "unresolved_source_rows": unresolved_rows,
        "completion_scope": "all retained first-party property-search rows; original auction denominators unavailable",
        "errors": failures, "checked_at": corpus.now()})
    print(json.dumps({k: v for k, v in summary.items() if k != "observed_source_ids"}, indent=2), flush=True)
    if failures or not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
