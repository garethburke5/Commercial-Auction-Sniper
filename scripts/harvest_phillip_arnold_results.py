"""Bank Phillip Arnold Auctions' retained first-party result tables.

The archive links to discrete, unpaginated result tables.  Every visible lot
row is retained, including withdrawn, unavailable, residential and addressless
portfolio rows.  A page is only marked catalogue-complete when the site's
published "Lots Offered" denominator agrees with the visible source rows.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.philliparnoldauctions.co.uk"
ARCHIVE = BASE + "/previous-results"
RESULT_RE = re.compile(r"/auction-results/(-?\d+)/?$")
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
DATE_RE = re.compile(r"Results\s+of\s+our\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\s+Auction", re.I)
OFFERED_RE = re.compile(r"Lots\s+Offered\s*:\s*(\d+)", re.I)
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=75)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def discover_result_urls(html: str, page_url: str = ARCHIVE) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"]).split("?", 1)[0].rstrip("/")
        if RESULT_RE.search(urlparse(url).path):
            urls.add(url)
    return sorted(urls, key=lambda value: int(RESULT_RE.search(urlparse(value).path).group(1)))


def parse_date(soup: BeautifulSoup) -> str:
    heading = next((clean(node.get_text(" ", strip=True)) for node in soup.find_all("h1")
                    if DATE_RE.search(clean(node.get_text(" ", strip=True)) or "")), None)
    match = DATE_RE.search(heading or "")
    if not match:
        raise ValueError("result page has no exact auction date heading")
    return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y").date().isoformat()


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    match = MONEY_RE.search(text)
    price = int(round(float(match.group(1).replace(",", "")))) if match else None
    if lower.startswith("sold prior"):
        return "sold_prior", price, None
    if lower.startswith("sold after"):
        return "sold_after", price, None
    if lower.startswith("sold"):
        return "sold", price, None
    if lower.startswith("withdrawn"):
        return "withdrawn", None, None
    if lower.startswith("unavailable"):
        return "unavailable", None, None
    if lower.startswith("available"):
        return "available", None, price
    if lower.startswith("reoffered"):
        return "reoffered", None, None
    return "unknown", None, None


def detail_identity(row, auction_id: str, lot_number: str) -> tuple[str, str | None]:
    href = None
    onclick = row.get("onclick") or ""
    quoted = re.search(r"['\"]([^'\"]*property_details\.php[^'\"]*)['\"]", onclick, re.I)
    if quoted:
        href = urljoin(BASE, quoted.group(1).replace("&amp;", "&"))
    detail = row.find_next_sibling("tr")
    row_suffix = (row.get("id") or "").removeprefix("lotHeader-")
    if detail and detail.get("id") == f"lotDetail-{row_suffix}":
        anchor = detail.find("a", href=re.compile(r"property_details\.php", re.I))
        if anchor:
            href = urljoin(BASE, anchor.get("href"))
    query = parse_qs(urlparse(href or "").query)
    source_id = (query.get("id") or [None])[0] or f"auction-{auction_id}-lot-{lot_number}"
    return str(source_id), href


def parse_result_page(html: str, result_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    match = RESULT_RE.search(urlparse(result_url).path)
    if not match:
        raise ValueError("result URL has no auction identifier")
    auction_id = match.group(1)
    soup = BeautifulSoup(html, "lxml")
    auction_date = parse_date(soup)
    page_text = clean(soup.get_text(" ", strip=True)) or ""
    offered_match = OFFERED_RE.search(page_text)
    published_offered = int(offered_match.group(1)) if offered_match else None
    source_rows = soup.select('tr[id^="lotHeader-"]')
    if not source_rows:
        raise ValueError("result page contains no source lot rows")

    rows = []
    for position, source_row in enumerate(source_rows, 1):
        cells = source_row.find_all("td", recursive=False)
        if len(cells) < 4:
            raise ValueError(f"malformed lot row at source position {position}")
        lot_number = clean(cells[0].get_text(" ", strip=True))
        address_text = clean((source_row.find("address") or cells[2]).get_text(" ", strip=True))
        status_text = clean(cells[3].get_text(" ", strip=True))
        if not lot_number or not address_text:
            raise ValueError(f"lot identity missing at source position {position}")
        source_id, detail_url = detail_identity(source_row, auction_id, lot_number)
        status, sale_price, available_price = status_and_prices(status_text)
        postcode_match = corpus.PC.search(address_text)
        postcode = postcode_match.group().upper() if postcode_match else None
        address = address_text if postcode else None
        row = corpus.base_row(
            "Phillip Arnold Auctions", f"phillip-arnold:{auction_id}",
            auction_date, lot_number, source_id, detail_url or result_url,
        )
        row.update(
            address=address, postcode=postcode, locality=address_text,
            sector=corpus.sector(address_text), status=status,
            sale_price=sale_price, guide_price=available_price,
            property_id=None,
            identity_method="source_auction_and_property_detail_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_status_text=status_text,
            source_result_url=result_url, source_evidence=evidence,
        )
        row["appearance_id"] = f"Phillip Arnold Auctions|auction:{auction_id}|property:{source_id}"
        rows.append(row)

    identities = [row["source_lot_id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate property identities within result page")
    complete = published_offered is not None and published_offered == len(rows)
    state = {
        "auctioneer": "Phillip Arnold Auctions",
        "source_auction_id": f"phillip-arnold:{auction_id}",
        "auction_date": auction_date,
        "catalogue_complete": complete,
        "source_rows_complete": True,
        "published_lots_offered": published_offered,
        "visible_source_rows": len(rows),
        "lots_captured": len(rows),
        "source_url": result_url,
        "completion_scope": "all visible rows in the first-party unpaginated result table",
        "denominator_reconciled": complete,
        "reconciliation_note": None if complete else {
            "kind": "published_denominator_mismatch",
            "published_lots_offered": published_offered,
            "visible_source_rows": len(rows),
        },
        # Denominator mismatch is an honest incomplete-catalogue state, not a
        # fetch/parse failure; keep the corpus failure metric semantically clean.
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def harvest(workers: int = 8) -> None:
    final_url, raw = get(ARCHIVE)
    archive_sha, retrieved_at = corpus.digest(raw), corpus.now()
    archive_snapshot = corpus.DATA / "sources/phillip-arnold" / f"previous-results-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": final_url, "retrieved_at": retrieved_at, "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party previous-results index",
    }
    html = raw.decode("utf-8", "replace")
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": html})
    result_urls = discover_result_urls(html, final_url)
    if not result_urls:
        raise SystemExit("No retained first-party result pages discovered")

    run_rows, states, failures = [], {}, []

    def capture(url: str):
        resolved, page_raw = get(url)
        page_sha, captured_at = corpus.digest(page_raw), corpus.now()
        auction_id = RESULT_RE.search(urlparse(resolved).path).group(1)
        file_id = auction_id.replace("-", "n", 1)
        snapshot = corpus.DATA / "sources/phillip-arnold" / f"auction-{file_id}-{page_sha[:16]}.json.gz"
        evidence = {
            "source_url": resolved, "retrieved_at": captured_at, "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated auction result table",
        }
        page_html = page_raw.decode("utf-8", "replace")
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        state, rows = parse_result_page(page_html, resolved, evidence)
        return auction_id, state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
        jobs = {pool.submit(capture, url): url for url in result_urls}
        for future in as_completed(jobs):
            url = jobs[future]
            try:
                auction_id, state, rows = future.result()
                file_id = auction_id.replace("-", "n", 1)
                corpus.save_json(corpus.DATA / f"auctions/phillip-arnold/auction-{file_id}.json", state)
                states[auction_id] = state
                run_rows.extend(rows)
                print("PHILLIP_ARNOLD", len(states), "/", len(result_urls), "pages", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    path = corpus.DATA / "appearances/phillip-arnold/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("phillip-arnold/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "result_pages_discovered": len(result_urls), "result_pages_captured": len(states),
        "result_pages_complete": sum(bool(state["catalogue_complete"]) for state in states.values()),
        "result_pages_denominator_mismatch": sum(not state["catalogue_complete"] for state in states.values()),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "phillip_arnold_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    harvest(workers)
