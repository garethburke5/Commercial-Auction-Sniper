"""Bank BTG Eddisons' retained first-party auction catalogues.

The results archive exposes live-stream and online catalogues with a published
``results found`` denominator.  Catalogue pages contain 100 cards per page by
default, so every advertised page is traversed and reconciled before a sale is
marked complete.  The archive date range is kept verbatim: online lots use the
published closing day, while two-day live-stream catalogues retain a null
``auction_date`` because the source does not assign an individual lot to one of
the two days.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.btgeddisonspropertyauctions.com"
ARCHIVE = BASE + "/auctions/previous-auction-results"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
CATALOGUE_RE = re.compile(r"/auctions/(online|live-stream)/([a-z]+-20\d{2})/?$", re.I)
PROPERTY_RE = re.compile(r"/properties/([^/?#]+)", re.I)
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/20\d{2})\b")
COUNT_RE = re.compile(r"\b(\d+)\s+results\s+found\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def iso_date(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def get(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    return raw, response.url


def discover_catalogues(html: str, source_url: str = ARCHIVE) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, dict] = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(source_url, anchor["href"]).split("?", 1)[0].rstrip("/")
        match = CATALOGUE_RE.search(urlsplit(url).path)
        if not match:
            continue
        card = anchor.find_parent("div", class_=lambda value: value and "rounded-lg" in value)
        if card is None:
            continue
        dates = [iso_date(value) for value in DATE_RE.findall(card.get_text(" ", strip=True))]
        dates = list(dict.fromkeys(dates))
        if not dates:
            raise ValueError(f"catalogue archive card has no published date: {url}")
        kind, slug = match.group(1).lower(), match.group(2).lower()
        item = {
            "catalogue_id": f"{kind}-{slug}", "kind": kind, "slug": slug,
            "url": url,
            "label": f"{slug.replace('-', ' ').title()} {kind.replace('-', ' ').title()} Auction",
            "auction_date_start": min(dates), "auction_date_end": max(dates),
            "published_date_text": " & ".join(DATE_RE.findall(card.get_text(" ", strip=True))),
        }
        old = found.get(item["catalogue_id"])
        if old and old != item:
            raise ValueError(f"conflicting archive entries for {item['catalogue_id']}")
        found[item["catalogue_id"]] = item
    if not found:
        raise ValueError("BTG Eddisons result archive contains no catalogues")
    return sorted(found.values(), key=lambda item: (item["auction_date_start"], item["catalogue_id"]))


def archive_page_count(html: str, source_url: str = ARCHIVE) -> int:
    pages = [1]
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a", href=True):
        url = urljoin(source_url, anchor["href"])
        page = parse_qs(urlsplit(url).query).get("page", [None])[0]
        if page and str(page).isdigit():
            pages.append(int(page))
    return max(pages)


def result_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    match = COUNT_RE.search(soup.get_text(" ", strip=True))
    if not match:
        raise ValueError("catalogue page has no published results-found denominator")
    return int(match.group(1))


def status_and_prices(text: str) -> tuple[str, int | None, int | None, int | None]:
    normalized = clean(text) or ""
    lower = normalized.casefold()
    sale_price = money(re.search(r"Sold for\s+(£[\d,.]+)", normalized, re.I).group(1)) \
        if re.search(r"Sold for\s+(£[\d,.]+)", normalized, re.I) else None
    guide_match = re.search(r"Guide Price:\s*(£[\d,.]+)(?:\s*-\s*(£[\d,.]+))?", normalized, re.I)
    guide_low = money(guide_match.group(1)) if guide_match else None
    guide_high = money(guide_match.group(2)) if guide_match and guide_match.group(2) else None
    available_match = re.search(r"Available(?:\s+for)?\s+(£[\d,.]+)", normalized, re.I)
    available_price = money(available_match.group(1)) if available_match else None
    if "sold prior to auction" in lower or "sold prior" in lower:
        status = "sold_prior"
    elif "sold post auction" in lower or "sold after auction" in lower:
        status = "sold_after"
    elif "withdrawn" in lower:
        status = "withdrawn"
    elif "postponed" in lower:
        status = "postponed"
    elif "entered into a future auction" in lower:
        status = "entered_future_auction"
    elif "sold at auction" in lower or sale_price is not None:
        status = "sold"
    elif "available" in lower:
        status = "available"
    else:
        status = "unknown"
    return status, sale_price, guide_low, guide_high or available_price


def row_auction_date(catalogue: dict) -> tuple[str | None, str]:
    start, end = catalogue["auction_date_start"], catalogue["auction_date_end"]
    if start == end:
        return start, "single exact date on first-party previous-results archive"
    if catalogue["kind"] == "online":
        return end, "published closing day of first-party online-auction date range"
    return None, "two-day live-stream range; source does not assign individual lots to a day"


def parse_page(html: str, catalogue: dict, page: int, evidence: dict) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    expected = result_count(html)
    cards = soup.select("div.property-card")
    if not cards and expected:
        raise ValueError("catalogue page contains no property cards")
    auction_date, date_basis = row_auction_date(catalogue)
    rows = []
    for position, card in enumerate(cards, 1):
        detail = card.select_one('a[aria-label][href*="/properties/"]')
        detail_url = urljoin(catalogue["url"], detail.get("href")) if detail else None
        identity = PROPERTY_RE.search(urlsplit(detail_url or "").path)
        source_id = identity.group(1) if identity else None
        address = clean(detail.get("aria-label")) if detail else None
        if not source_id or not detail_url or not address:
            raise ValueError(f"property identity or address missing at page {page} card {position}")
        flag = card.select_one("div.absolute.top-0.left-4 p")
        lot_number = clean(flag.get_text(" ", strip=True) if flag else None)
        card_text = clean(card.get_text(" ", strip=True)) or ""
        status, sale_price, guide_price, guide_high_or_available = status_and_prices(card_text)
        guide_high = None
        available_price = None
        guide_match = re.search(r"Guide Price:\s*(£[\d,.]+)(?:\s*-\s*(£[\d,.]+))?", card_text, re.I)
        if guide_match and guide_match.group(2):
            guide_high = money(guide_match.group(2))
        elif status == "available":
            available_price = guide_high_or_available
        end_match = re.search(r"Auction Ends:\s*(\d{2}/\d{2}/20\d{2})", card_text, re.I)
        lot_end_date = iso_date(end_match.group(1)) if end_match else None
        postcode_match = corpus.PC.search(address)
        postcode = postcode_match.group().upper() if postcode_match else None
        source_auction_id = f"btg-eddisons:{catalogue['catalogue_id']}"
        row = corpus.base_row("BTG Eddisons", source_auction_id, auction_date,
                              lot_number, source_id, detail_url)
        row.update(
            address=address, postcode=postcode, locality=address,
            sector=corpus.sector(address), status=status,
            sale_price=sale_price, guide_price=guide_price,
            guide_price_high=guide_high, available_price=available_price,
            property_id=source_id,
            identity_method="source_catalogue_and_first_party_property_id",
            record_quality="address_record", source_page=page,
            source_position=(page - 1) * 100 + position,
            auction_date_start=catalogue["auction_date_start"],
            auction_date_end=catalogue["auction_date_end"],
            auction_date_basis=date_basis, lot_end_date=lot_end_date,
            lot_end_date_basis="card Auction Ends label" if lot_end_date else None,
            source_result_text=card_text, source_evidence=evidence,
        )
        row["appearance_id"] = (
            f"BTG Eddisons|catalogue:{catalogue['catalogue_id']}|property:{source_id}"
        )
        rows.append(row)
    return expected, rows


def reconcile_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """Fold exact source-card duplicates without discarding their presentation.

    BTG Eddisons currently exposes two catalogues with a duplicated card for
    the same property ID and printed lot number.  Those rows count toward the
    site's ``results found`` denominator, but they are not two auction
    appearances.  Keep the alternate URL, source position and changed fields
    on the canonical record instead of inflating the appearance count.
    """
    canonical: dict[tuple[str, str | None], dict] = {}
    duplicate_rows = 0
    for row in rows:
        key = (row["source_lot_id"], row.get("lot_number"))
        old = canonical.get(key)
        if old is None:
            row["source_rows_represented"] = 1
            canonical[key] = row
            continue
        duplicate_rows += 1
        old["source_rows_represented"] = int(old.get("source_rows_represented") or 1) + 1
        old.setdefault("alternate_source_presentations", []).append({
            "original_url": row.get("original_url"),
            "source_page": row.get("source_page"),
            "source_position": row.get("source_position"),
            "status": row.get("status"),
            "guide_price": row.get("guide_price"),
            "guide_price_high": row.get("guide_price_high"),
            "available_price": row.get("available_price"),
            "sale_price": row.get("sale_price"),
            "source_result_text": row.get("source_result_text"),
            "source_evidence": row.get("source_evidence"),
        })
    return list(canonical.values()), duplicate_rows


def harvest(workers: int = 4) -> None:
    archive_evidence, catalogues_by_id, failures = [], {}, []
    raw, final_url = get(ARCHIVE)
    first_html = raw.decode("utf-8", "replace")
    pages = archive_page_count(first_html, final_url)
    for page in range(1, pages + 1):
        url = ARCHIVE if page == 1 else f"{ARCHIVE}?page={page}"
        try:
            if page == 1:
                page_raw, resolved = raw, final_url
            else:
                page_raw, resolved = get(url)
            sha, retrieved_at = corpus.digest(page_raw), corpus.now()
            snapshot = corpus.DATA / "sources/eddisons/catalogues" / f"archive-{page}-{sha[:16]}.json.gz"
            evidence = {"source_url": resolved, "retrieved_at": retrieved_at,
                        "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "basis": "first-party previous-auction results archive"}
            page_html = page_raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
            archive_evidence.append(evidence)
            for item in discover_catalogues(page_html, resolved):
                old = catalogues_by_id.get(item["catalogue_id"])
                if old and old != item:
                    raise ValueError(f"conflicting cross-page catalogue {item['catalogue_id']}")
                catalogues_by_id[item["catalogue_id"]] = item
        except Exception as exc:
            failures.append({"kind": "archive_page", "page": page, "url": url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
    catalogues = sorted(catalogues_by_id.values(), key=lambda x: (x["auction_date_start"], x["catalogue_id"]))

    path = corpus.DATA / "appearances/eddisons/catalogues.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)
    states, run_rows, pending, reused = {}, [], [], 0
    for item in catalogues:
        state_path = corpus.DATA / f"auctions/eddisons/catalogue-{item['catalogue_id']}.json"
        try:
            old_state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            old_state = None
        old_rows = existing_by_auction.get(f"btg-eddisons:{item['catalogue_id']}", [])
        if (old_state and old_state.get("catalogue_complete") and
                old_state.get("lots_captured") == len(old_rows) and old_rows):
            states[item["catalogue_id"]] = old_state
            run_rows.extend(old_rows)
            reused += 1
        else:
            pending.append(item)

    def capture(item: dict):
        page_rows, evidence_pages, expected = [], [], None
        total_pages = None
        for page in range(1, 100):
            url = item["url"] if page == 1 else f"{item['url']}?page={page}"
            page_raw, resolved = get(url)
            sha, retrieved_at = corpus.digest(page_raw), corpus.now()
            snapshot = corpus.DATA / "sources/eddisons/catalogues" / item["catalogue_id"] / (
                f"page-{page}-{sha[:16]}.json.gz"
            )
            evidence = {"source_url": resolved, "retrieved_at": retrieved_at,
                        "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "archive_snapshot_paths": [x["snapshot_path"] for x in archive_evidence],
                        "basis": "first-party retained auction catalogue page"}
            page_html = page_raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
            page_expected, rows = parse_page(page_html, item, page, evidence)
            if expected is not None and expected != page_expected:
                raise ValueError("published result count changed during pagination")
            expected = page_expected
            total_pages = max(1, math.ceil(expected / 100))
            page_rows.extend(rows)
            evidence_pages.append(evidence)
            if page >= total_pages:
                break
        raw_rows = len(page_rows)
        reconciled_rows, duplicate_rows = reconcile_rows(page_rows)
        complete = bool(expected is not None and raw_rows == expected and
                        len(evidence_pages) == total_pages)
        if not complete:
            raise ValueError(
                f"catalogue reconciliation failed: expected {expected}, captured {raw_rows}, "
                f"pages {len(evidence_pages)}/{total_pages}"
            )
        auction_date, date_basis = row_auction_date(item)
        state = {
            "auctioneer": "BTG Eddisons", "source_auction_id": f"btg-eddisons:{item['catalogue_id']}",
            "auction_date": auction_date, "auction_date_start": item["auction_date_start"],
            "auction_date_end": item["auction_date_end"], "auction_date_basis": date_basis,
            "catalogue_complete": True, "source_rows_complete": True,
            "published_results_found": expected, "visible_source_rows": raw_rows,
            "lots_captured": len(reconciled_rows), "source_duplicate_rows": duplicate_rows,
            "source_url": item["url"],
            "pagination_reconciled": True, "pages_expected": total_pages,
            "pages_captured": len(evidence_pages), "denominator_reconciled": True,
            "denominator_basis": "published results found count on first-party catalogue",
            "completion_scope": "all property cards across every retained catalogue page",
            "source_evidence": evidence_pages, "errors": [], "checked_at": corpus.now(),
        }
        return item["catalogue_id"], state, reconciled_rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        jobs = {pool.submit(capture, item): item for item in pending}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                catalogue_id, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/eddisons/catalogue-{catalogue_id}.json", state)
                states[catalogue_id] = state
                run_rows.extend(rows)
                print("BTG EDDISONS", len(states), "/", len(catalogues), "catalogues",
                      len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"kind": "catalogue", "catalogue_id": item["catalogue_id"],
                                 "url": item["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("eddisons/catalogues", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "archive_pages_expected": pages, "archive_pages_captured": len(archive_evidence),
        "catalogues_discovered": len(catalogues), "catalogues_captured": len(states),
        "catalogues_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "catalogues_reused": reused, "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "btg_eddisons_catalogues_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
