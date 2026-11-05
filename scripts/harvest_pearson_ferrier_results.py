"""Bank Pearson Ferrier's complete retained first-party result tables.

The auction sitemap exposes one unpaginated result table per retained sale.
The pages publish the auction month and year, but not an exact auction day.
That source limitation is preserved explicitly: ``auction_date`` remains null
and ``auction_period`` carries the published YYYY-MM value.  No day is
invented.  Every visible property row is retained with its guide range,
published outcome text and any explicit achieved price.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://pearsonferrier.co.uk"
SITEMAP = BASE + "/auctions-sitemap.xml"
EVENT_RE = re.compile(r"/auctions/([a-z]+)-(20\d{2})(?:-auction)?/?$", re.I)
HEADING_RE = re.compile(r"Properties\s+auctioned\s+on\s+([A-Za-z]+)\s+(20\d{2})", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def discover_result_urls(xml: str) -> list[str]:
    soup = BeautifulSoup(xml, "xml")
    urls = set()
    for node in soup.find_all("loc"):
        url = clean(node.get_text())
        if url and EVENT_RE.search(urlparse(url).path):
            urls.add(url.rstrip("/") + "/")

    def order(url: str) -> tuple[int, int, str]:
        match = EVENT_RE.search(urlparse(url).path)
        month, year = match.groups()
        month_number = datetime.strptime(month, "%B").month
        return int(year), month_number, url

    return sorted(urls, key=order)


def published_period(soup: BeautifulSoup) -> tuple[str, str]:
    heading = next(
        (
            clean(node.get_text(" ", strip=True))
            for node in soup.find_all(["h1", "h2", "h3"])
            if HEADING_RE.search(clean(node.get_text(" ", strip=True)) or "")
        ),
        None,
    )
    match = HEADING_RE.search(heading or "")
    if not match:
        raise ValueError("result page has no published auction month heading")
    parsed = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%B %Y")
    return parsed.strftime("%Y-%m"), heading


def money_values(value: str | None) -> list[int]:
    return [int(round(float(item.replace(",", "")))) for item in MONEY_RE.findall(value or "")]


def guide_prices(value: str | None) -> tuple[int | None, int | None]:
    prices = money_values(value)
    if not prices:
        return None, None
    return prices[0], prices[1] if len(prices) > 1 else None


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None, int | None]:
    """Return status, achieved price, available price and non-sale last bid."""
    text = clean(value) or ""
    lower = text.casefold()
    prices = money_values(text)
    price = prices[0] if prices else None
    if lower.startswith("sold prior"):
        return "sold_prior", price, None, None
    if lower.startswith("sold post"):
        return "sold_post", price, None, None
    if lower.startswith("sold at"):
        return "sold", price, None, None
    if lower.startswith("sold in ") or lower.startswith("soldin ") or lower.startswith("sold december"):
        return "sold_later", None, None, None
    if lower.startswith("available last bid"):
        return "available", None, None, price
    if lower.startswith("available at"):
        return "available", None, price, None
    if lower.startswith("available"):
        return "available", None, None, None
    if lower.startswith("enter") or lower.startswith("in december auction"):
        return "reoffered", None, None, None
    if lower.startswith("postponed"):
        return "postponed", None, None, None
    if lower.startswith("withdrawn"):
        return "withdrawn", None, None, None
    return "unknown", None, None, None


def normalized_address(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def parse_result_page(html: str, result_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    period, heading = published_period(soup)
    source_rows = soup.select(
        "section.auction-archives .auction-past-result:not(.auction-past-result-headings)"
    )
    if not source_rows:
        raise ValueError("result page contains no source property rows")
    pagination = soup.select(
        "section.auction-archives .pagination a[href], "
        "section.auction-archives a[rel~='next'][href], "
        "section.auction-archives a[href*='?page='], "
        "section.auction-archives a[href*='&page=']"
    )
    if pagination:
        raise ValueError("unexpected pagination controls on retained result table")

    rows = []
    seen = set()
    for position, source_row in enumerate(source_rows, 1):
        address_node = source_row.select_one(".auction-past-address")
        guide_node = source_row.select_one(".auction-past-guide")
        outcome_node = source_row.select_one(".auction-past-sold")
        address = clean(address_node.get_text(" ", strip=True) if address_node else None)
        guide_text = clean(guide_node.get_text(" ", strip=True) if guide_node else None)
        outcome_text = clean(outcome_node.get_text(" ", strip=True) if outcome_node else None)
        if not address or not guide_text or not outcome_text:
            raise ValueError(f"malformed result row at source position {position}")
        address_key = normalized_address(address)
        if address_key in seen:
            raise ValueError(f"duplicate address within result page at source position {position}")
        seen.add(address_key)

        source_id = hashlib.sha256(f"{period}|{address_key}".encode()).hexdigest()[:24]
        guide_price, guide_price_high = guide_prices(guide_text)
        status, sale_price, available_price, last_bid_price = status_and_prices(outcome_text)
        postcode_match = corpus.PC.search(address)
        postcode = postcode_match.group().upper().replace("\u00a0", " ") if postcode_match else None
        row = corpus.base_row(
            "Pearson Ferrier", f"pearson-ferrier:{period}", None,
            None, source_id, result_url,
        )
        row.update(
            address=address,
            postcode=postcode,
            locality=address,
            sector=corpus.sector(address),
            status=status,
            guide_price=guide_price,
            guide_price_high=guide_price_high,
            sale_price=sale_price,
            available_price=available_price,
            property_id=None,
            identity_method="source_auction_period_and_exact_published_address",
            record_quality="address_record",
            source_position=position,
            source_guide_text=guide_text,
            source_outcome_text=outcome_text,
            last_bid_price=last_bid_price,
            source_result_url=result_url,
            source_evidence=evidence,
            auction_period=period,
            auction_date_precision="month",
            auction_date_basis="first-party result heading; exact day not published",
            operator_company="Pearson Ferrier Estate Agents Limited",
            operator_company_number="09552248",
        )
        row["appearance_id"] = f"Pearson Ferrier|auction:{period}|address:{source_id}"
        rows.append(row)

    state = {
        "auctioneer": "Pearson Ferrier",
        "operator_company": "Pearson Ferrier Estate Agents Limited",
        "operator_company_number": "09552248",
        "source_auction_id": f"pearson-ferrier:{period}",
        "auction_date": None,
        "auction_period": period,
        "auction_date_precision": "month",
        "auction_date_basis": "first-party result heading; exact day not published",
        "published_heading": heading,
        "catalogue_complete": True,
        "source_rows_complete": True,
        "pagination_reconciled": True,
        "published_lot_denominator": None,
        "source_row_denominator": len(rows),
        "visible_source_rows": len(rows),
        "lots_captured": len(rows),
        "source_url": result_url,
        "completion_scope": "all visible rows in the first-party unpaginated retained result table",
        "denominator_reconciled": True,
        "date_limitation": "source publishes month and year only; exact auction day remains null",
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def harvest(workers: int = 8) -> None:
    sitemap_url, raw = get(SITEMAP)
    sitemap_sha, retrieved_at = corpus.digest(raw), corpus.now()
    sitemap_snapshot = (
        corpus.DATA / "sources/pearson-ferrier" / f"auctions-sitemap-{sitemap_sha[:16]}.json.gz"
    )
    sitemap_evidence = {
        "source_url": sitemap_url,
        "retrieved_at": retrieved_at,
        "sha256": sitemap_sha,
        "snapshot_path": str(sitemap_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party auction-result sitemap",
    }
    xml = raw.decode("utf-8", "replace")
    corpus.save_gzip(sitemap_snapshot, {"evidence": sitemap_evidence, "xml": xml})
    result_urls = discover_result_urls(xml)
    if not result_urls:
        raise SystemExit("No retained first-party result pages discovered")

    run_rows, states, failures = [], {}, []

    def capture(url: str):
        resolved, page_raw = get(url)
        page_sha, captured_at = corpus.digest(page_raw), corpus.now()
        page_html = page_raw.decode("utf-8", "replace")
        preview_soup = BeautifulSoup(page_html, "lxml")
        period, _ = published_period(preview_soup)
        snapshot = (
            corpus.DATA / "sources/pearson-ferrier" /
            f"result-{period}-{page_sha[:16]}.json.gz"
        )
        evidence = {
            "source_url": resolved,
            "retrieved_at": captured_at,
            "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated retained result table",
        }
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        state, rows = parse_result_page(page_html, resolved, evidence)
        return period, state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(capture, url): url for url in result_urls}
        for future in as_completed(jobs):
            url = jobs[future]
            try:
                period, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/pearson-ferrier/{period}.json", state)
                states[period] = state
                run_rows.extend(rows)
                print(
                    "PEARSON_FERRIER", len(states), "/", len(result_urls),
                    "pages", len(run_rows), "lots", flush=True,
                )
            except Exception as exc:
                failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    path = corpus.DATA / "appearances/pearson-ferrier/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("pearson-ferrier/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(),
        "source_url": SITEMAP,
        "operator": {
            "canonical_name": "Pearson Ferrier",
            "company_name": "Pearson Ferrier Estate Agents Limited",
            "company_number": "09552248",
            "branches_are_not_counted_as_separate_auctioneers": True,
        },
        "result_pages_discovered": len(result_urls),
        "result_pages_captured": len(states),
        "result_pages_complete": sum(bool(state["catalogue_complete"]) for state in states.values()),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_exact_dated_address_records": 0,
        "run_new_month_precision_address_records": sum(
            bool(row.get("address")) and row.get("auction_date_precision") == "month" for row in added
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_last_bid_prices_not_sale_prices": sum(row.get("last_bid_price") is not None for row in added),
        "source_years": sorted({row["auction_period"][:4] for row in merged.values()}),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "date_limitation": "all retained pages publish month/year only; exact dates remain null",
        "sitemap_evidence": sitemap_evidence,
        "auctions": states,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "pearson_ferrier_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(result_urls):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)
