"""Bank Lextons' complete first-party auction-property search inventory.

The auction branch search exposes individual property detail pages across a
paginated archive.  Each page is an evidenced property appearance even when
the surviving page no longer publishes its auction date.  Dates are admitted
only from explicit auction-date labels; guide prices are never treated as
achieved prices.  Result-sheet matching remains a separate enrichment task.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Lextons Auctions Ltd"
SLUG = "lextons-auctions"
OPERATOR = "Lextons Auctions Ltd"
TRADING_NAME = "Lextons Auctions"
SEARCH_URL = (
    "https://www.lextons.co.uk/search/1.html?showsold=on&showstc=on&bid=4"
    "&orderby=availability+asc%2Cdate_sold+desc"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}
NEXT_TARGET = (
    "Parse and match all 20 official Lextons result sheets from September 2021 "
    "through April 2026, using native text and free OCR where required. Enrich "
    "only the exact property appearances matched by event, property and source "
    "evidence with achieved prices and published outcomes; preserve unmatched "
    "result rows separately. Then move to another uncovered source-year register "
    "target. Keep national completeness false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 20000:
        raise ValueError(f"source response is unexpectedly short: {url}")
    return response.url, response.content


def snapshot(raw, name, source_url, basis):
    sha = hashlib.sha256(raw).hexdigest()
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.html.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


def search_inventory(html, base_url=SEARCH_URL):
    soup = BeautifulSoup(html, "lxml")
    pages = [1]
    for link in soup.select("ul.pagination a[href]"):
        match = re.search(r"/search/(\d+)\.html", link.get("href", ""))
        if match:
            pages.append(int(match.group(1)))
    urls = []
    for link in soup.select('a[href*="/property-details/"]'):
        absolute = urljoin(base_url, link["href"])
        if re.search(r"/property-details/\d+/", absolute):
            urls.append(absolute.split("?", 1)[0])
    return max(pages), sorted(set(urls))


def parse_date_label(text):
    if not text:
        return None
    match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(20\d{2})\b",
        text,
        re.I,
    )
    if not match:
        return None
    return datetime.strptime(
        f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y"
    ).date().isoformat()


def explicit_auction_date(soup):
    details = soup.select_one(".property-full-details")
    if not details:
        return None, "explicit auction date absent from surviving detail page"
    text = clean(details.get_text(" ", strip=True)) or ""
    # A dedicated field is authoritative and appears before later narrative
    # references.  It also prevents lease, planning and tenancy dates from
    # being mistaken for the auction event.
    dedicated = re.search(
        r"\b(?:Online\s+)?Auction Date\s*:?[ \t]*"
        r"(TBA|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        text,
        re.I,
    )
    if dedicated:
        value = parse_date_label(dedicated.group(1))
        if value:
            return value, "exact date in first-party Auction Date field"
        return None, "first-party Auction Date field is TBA or has no exact date"
    advertised = re.search(
        r"\bFor Sale By Auction(?:\s+On)?\s+"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})\b",
        text,
        re.I,
    )
    if advertised:
        return parse_date_label(advertised.group(1)), "exact date in first-party For Sale By Auction label"
    onsite = re.search(
        r"\bBidding to Take Place on\s+"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})\b",
        text,
        re.I,
    )
    if onsite:
        return parse_date_label(onsite.group(1)), "exact date in first-party Bidding to Take Place label"
    return None, "explicit auction date absent from surviving detail page"


def money_text(value):
    if not value:
        return None
    match = re.search(r"£\s*([\d,]+)", value)
    return int(match.group(1).replace(",", "")) if match else None


def exact_annual_rent(text):
    if not text:
        return None, None
    patterns = (
        r"(?:rent(?:al)?(?: income)?(?: of| is| at)?\s*)"
        r"(£\s*[\d,]+(?:\.\d{1,2})?\s*(?:per annum|p\.?a\.?))",
        r"(£\s*[\d,]+(?:\.\d{1,2})?\s*(?:per annum|p\.?a\.?))",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            rent_text = clean(match.group(1))
            return money_text(rent_text), rent_text
    return None, None


def property_id_from_url(url):
    match = re.search(r"/property-details/(\d+)/", url)
    if not match:
        raise ValueError(f"missing stable property ID: {url}")
    return match.group(1)


def parse_detail(html, url, evidence=None):
    soup = BeautifulSoup(html, "lxml")
    property_id = property_id_from_url(url)
    title_node = soup.select_one(".property-headings [itemprop=name]")
    title = clean(title_node.get_text(" ", strip=True) if title_node else None)
    if not title:
        raise ValueError(f"missing first-party property title: {url}")
    price_node = soup.select_one("[itemprop=price]")
    guide = None
    if price_node:
        content = clean(price_node.get("content"))
        if content and re.fullmatch(r"\d+", content):
            guide = int(content)
        else:
            guide = money_text(price_node.get_text(" ", strip=True))
    description_node = soup.select_one("span[itemprop=description]")
    description = clean(description_node.get_text(" ", strip=True) if description_node else None)
    details_node = soup.select_one(".property-full-details")
    details_text = clean(details_node.get_text(" ", strip=True) if details_node else None)
    guide_high = None
    guide_range = re.search(
        r"Auction Guide\s*£\s*[\d,]+\s*(?:to|[-–])\s*£\s*([\d,]+)",
        details_text or "",
        re.I,
    )
    if guide_range:
        guide_high = int(guide_range.group(1).replace(",", ""))
    heading = soup.select_one(".property-headings")
    heading_text = clean(heading.get_text(" ", strip=True) if heading else None) or ""
    auction_date, date_basis = explicit_auction_date(soup)
    tenure = next((word for word in ("Freehold", "Leasehold", "Share of Freehold") if re.search(rf"\b{re.escape(word)}\b", heading_text, re.I)), None)
    property_type = None
    og = soup.select_one('meta[property="og:title"]')
    if og:
        og_title = clean(og.get("content"))
        if og_title and og_title.casefold().startswith(title.casefold()):
            remainder = clean(og_title[len(title):].lstrip(" ,"))
            parts = [clean(part) for part in (remainder or "").split(",") if clean(part)]
            if parts and not re.fullmatch(r"\d+\s+bedrooms?", parts[-1], re.I):
                property_type = parts[-1]
    status_text = clean((soup.select_one(".sale-auction") or soup.select_one(".sale-auction-thumb")).get_text(" ", strip=True) if (soup.select_one(".sale-auction") or soup.select_one(".sale-auction-thumb")) else None)
    combined = " ".join(filter(None, [status_text, details_text, description]))
    if re.search(r"\bsold prior\b", combined, re.I):
        status = "sold prior"
    elif re.search(r"\bwithdrawn\b", combined, re.I):
        status = "withdrawn"
    elif re.search(r"\bunsold\b|\bnot sold\b", combined, re.I):
        status = "unsold"
    elif re.search(r"\bsold at auction\b|\bsold\b", status_text or "", re.I):
        status = "sold"
    elif auction_date and auction_date > date.today().isoformat():
        status = "available"
    else:
        status = "unknown"
    annual_rent, rent_text = exact_annual_rent(" ".join(filter(None, [details_text, description])))
    row = corpus.base_row(SOURCE, f"{SLUG}:{auction_date or 'undated'}", auction_date, None, property_id, url)
    postcode = corpus.PC.search(title)
    row.update(
        appearance_id=f"{SOURCE}|property:{property_id}",
        address=title,
        postcode=postcode.group().upper() if postcode else None,
        locality=title,
        description=description,
        property_type=property_type,
        tenure=tenure,
        sector=corpus.sector(" ".join(filter(None, [title, property_type, details_text, description]))),
        guide_price=guide,
        guide_price_high=guide_high,
        sale_price=None,
        status=status,
        annual_rent=annual_rent,
        rent_text=rent_text,
        property_id=property_id,
        identity_method="first_party_stable_property_id_and_verbatim_property_title",
        record_quality="address_record",
        address_basis="verbatim individual property title on first-party detail page",
        auction_date_precision="day" if auction_date else "unknown",
        auction_date_basis=date_basis,
        source_guide_text=clean(price_node.get_text(" ", strip=True) if price_node else None),
        source_outcome_text=status_text,
        source_platform="Lextons first-party auction branch search and detail archive",
        operator_legal_name=OPERATOR,
        trading_name=TRADING_NAME,
        source_evidence=evidence,
    )
    return row


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append(
                    {"appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")}
                )
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
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
        "source_key_candidate": "lextons-result-sheets-2021-2026",
        "auctioneer": SOURCE,
        "source_format": "20 linked official result sheets; mixed native PDF and image-only PDF",
        "opportunity": "achieved-price and outcome enrichment plus any unmatched result properties",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(workers=8):
    resolved, first_raw = get(SEARCH_URL)
    max_page, first_urls = search_inventory(first_raw, resolved)
    if max_page < 2:
        raise ValueError("pagination denominator was not exposed")
    search_pages = {1: (resolved, first_raw)}
    all_urls = set(first_urls)
    for page in range(2, max_page + 1):
        page_url = re.sub(r"/search/1\.html", f"/search/{page}.html", SEARCH_URL)
        page_resolved, raw = get(page_url)
        _, urls = search_inventory(raw, page_resolved)
        search_pages[page] = (page_resolved, raw)
        all_urls.update(urls)
    if len(all_urls) < max_page:
        raise ValueError("property denominator is smaller than page count")

    search_evidence = []
    for page, (page_url, raw) in search_pages.items():
        search_evidence.append(snapshot(raw, f"search-page-{page:02d}", page_url, "first-party paginated auction-property inventory"))

    downloads = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(get, url): url for url in sorted(all_urls)}
        for future in as_completed(futures):
            original = futures[future]
            downloads[original] = future.result()

    run_rows = []
    for original in sorted(downloads):
        detail_url, raw = downloads[original]
        property_id = property_id_from_url(detail_url)
        evidence = snapshot(raw, f"property-{property_id}", detail_url, "first-party individual auction-property detail page")
        run_rows.append(parse_detail(raw, detail_url, evidence))

    if len(run_rows) != len(all_urls) or len({row["property_id"] for row in run_rows}) != len(run_rows):
        raise ValueError("detail-page inventory did not reconcile to unique property IDs")

    exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in run_rows:
        matches = exact.get((row.get("auction_date"), normalized(row.get("address"))), []) if row.get("auction_date") else []
        if matches:
            overlaps.append({"appearance_id": row["appearance_id"], "address": row["address"], "auction_date": row["auction_date"], "existing": matches})
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    dated = [row for row in added if row.get("address") and row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}

    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "source_auction_id": f"{SLUG}:search-inventory",
        "source_url": SEARCH_URL,
        "search_pages_captured": max_page,
        "published_property_denominator": len(all_urls),
        "properties_captured": len(run_rows),
        "properties_admitted": len(admissible),
        "catalogue_complete": False,
        "source_inventory_complete": True,
        "denominator_reconciled": len(run_rows) == len(all_urls),
        "completion_scope": "all unique individual property detail URLs in the current first-party auction search inventory",
        "result_sheets_pending": 20,
        "source_evidence": search_evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "search-inventory.json", state)
    summary = {
        "checked_at": corpus.now(),
        "operator": {"canonical_name": SOURCE, "company_name": OPERATOR, "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "search_pages_captured": max_page,
        "detail_pages_captured": len(run_rows),
        "appearances_captured": total,
        "run_new_appearances": total - len(before),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(dated),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_lots": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_lots": sum(bool(row.get("auction_date") and row["auction_date"] > today) for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "run_new_twenty_year_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in dated),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "source_state": state,
        "result_sheet_price_enrichment_pending": 20,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "lextons_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)
