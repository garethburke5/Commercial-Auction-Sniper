"""Bank Agents Property Auction's retained first-party sold-result tables.

The source exposes one unpaginated table for a venue/month/year selection.
Those tables publish addresses and achieved prices, but not lot numbers, an
exact auction day, or the original catalogue denominator.  Accordingly every
visible result row is retained while catalogue completeness remains false.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.agentspropertyauction.com/auctions/auction-results/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TRANSPORT_VERSION = 3
READER = "https://r.jina.ai/http://www.agentspropertyauction.com"
HEADING_RE = re.compile(
    r"Results\s+from\s+our(?:\s+latest)?\s+auction\s+at\s+(.+?)\s+in\s+([A-Za-z]+)\s+(20\d{2})",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def fetch(url: str, params=None) -> tuple[str, bytes]:
    # The legacy filter route returns HTTP 500 to stateless/non-browser
    # requests.  Reuse the archive-index session and issue requests serially.
    response = SESSION.get(url, params=params, timeout=60)
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def discover_filters(html: str) -> tuple[list[str], list[int]]:
    soup = BeautifulSoup(html, "lxml")
    venues = [clean(option.get("value")) for option in soup.select('select[name="a_venue"] option[value]')]
    years = [clean(option.get("value")) for option in soup.select('select[name="a_year"] option[value]')]
    venues = sorted({value for value in venues if value})
    parsed_years = sorted({int(value) for value in years if value and re.fullmatch(r"20\d{2}", value)})
    if not venues or not parsed_years:
        raise ValueError("result archive filters expose no venues or years")
    return venues, parsed_years


def normalize_exact_address(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def parse_price(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def result_pairs(document: str, document_format: str) -> tuple[re.Match, list[tuple[str, str | None]]]:
    if document_format == "markdown":
        heading = HEADING_RE.search(document)
        if not heading:
            raise ValueError("reader snapshot has no venue/month/year heading")
        pairs = []
        for line in document.splitlines():
            if "|" not in line:
                continue
            cells = [clean(re.sub(r"[*_`]", "", value)) for value in line.strip().strip("|").split("|")]
            if len(cells) != 2 or not cells[0] or cells[0].casefold() == "address":
                continue
            if re.fullmatch(r"[-: ]+", cells[0]) or re.fullmatch(r"[-: ]+", cells[1] or ""):
                continue
            if MONEY_RE.search(cells[1] or "") or (cells[1] or "").casefold() == "undisclosed":
                pairs.append((cells[0], cells[1]))
        if not pairs:
            raise ValueError("reader snapshot contains no sold-result rows")
        return heading, pairs

    soup = BeautifulSoup(document, "lxml")
    headings = [clean(node.get_text(" ", strip=True)) for node in soup.select("h1, h2")]
    heading = next((HEADING_RE.search(value or "") for value in headings if HEADING_RE.search(value or "")), None)
    if not heading:
        raise ValueError("result page has no venue/month/year heading")
    source_rows = soup.select("table.table--results tbody tr") or soup.select("table.table--results tr")
    pairs = []
    for position, source_row in enumerate(source_rows, 1):
        cells = source_row.find_all("td", recursive=False)
        if not cells:
            continue
        if len(cells) != 2:
            raise ValueError(f"malformed sold-result row at source position {position}")
        address = clean(cells[0].get_text(" ", strip=True))
        result_text = clean(cells[1].get_text(" ", strip=True))
        if not address:
            raise ValueError(f"sold-result row has no address at source position {position}")
        pairs.append((address, result_text))
    return heading, pairs


def parse_result_page(
    html: str,
    source_url: str,
    venue: str,
    year: int,
    month: int,
    evidence: dict,
) -> tuple[dict | None, list[dict]]:
    match, source_pairs = result_pairs(html, evidence.get("document_format", "html"))
    expected_month = datetime(year, month, 1).strftime("%B")
    if (
        clean(match.group(1)).casefold() != venue.casefold()
        or match.group(2).casefold() != expected_month.casefold()
        or int(match.group(3)) != year
    ):
        raise ValueError(
            f"result page resolved to {match.group(1)} {match.group(2)} {match.group(3)}, "
            f"not {venue} {expected_month} {year}"
        )

    parsed = []
    occurrences: defaultdict[str, int] = defaultdict(int)
    for position, (address, result_text) in enumerate(source_pairs, 1):
        normalized = normalize_exact_address(address)
        occurrences[normalized] += 1
        digest = hashlib.sha256(normalized.encode()).hexdigest()[:24]
        source_id = digest if occurrences[normalized] == 1 else f"{digest}-{occurrences[normalized]}"
        auction_id = f"agents-property-auction:{venue.casefold().replace(' ', '-')}:{year:04d}-{month:02d}"
        row = corpus.base_row("Agents Property Auction", auction_id, None, None, source_id, source_url)
        postcode_match = corpus.PC.search(address)
        postcode = postcode_match.group().upper() if postcode_match else None
        row.update(
            address=address,
            postcode=postcode,
            locality=venue,
            sector=corpus.sector(address),
            status="sold",
            sale_price=parse_price(result_text),
            property_id="agents-property-auction|exact-address:" + hashlib.sha256(normalized.encode()).hexdigest(),
            identity_method="exact_normalized_first_party_address",
            record_quality="address_record",
            date_basis="month_only_unresolved",
            published_auction_month=f"{year:04d}-{month:02d}",
            source_position=position,
            source_result_text=result_text,
            source_evidence=evidence,
        )
        row["appearance_id"] = f"Agents Property Auction|{auction_id}|result:{source_id}"
        parsed.append(row)

    if not parsed:
        return None, []
    identities = [row["source_lot_id"] for row in parsed]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate derived result identities")
    auction_id = parsed[0]["source_auction_id"]
    state = {
        "auctioneer": "Agents Property Auction",
        "source_auction_id": auction_id,
        "auction_date": None,
        "published_auction_month": f"{year:04d}-{month:02d}",
        "date_basis": "month_only_unresolved",
        "venue": venue,
        "catalogue_complete": False,
        "result_rows_complete": True,
        "pagination_reconciled": True,
        "visible_source_rows": len(parsed),
        "lots_captured": len(parsed),
        "source_url": source_url,
        "completion_scope": "all visible rows in the first-party unpaginated sold-result table; original catalogue denominator unavailable",
        "denominator_reconciled": False,
        "reconciliation_note": {
            "kind": "sold_results_only_no_original_catalogue_denominator",
            "visible_sold_result_rows": len(parsed),
        },
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, parsed


def harvest(years_per_run: int = 2, workers: int = 1) -> dict:
    collection_path = corpus.DATA / "agents_property_auction_collection.json"
    previous = json.loads(collection_path.read_text()) if collection_path.exists() else {}
    if (
        previous.get("transport_version") == TRANSPORT_VERSION
        and previous.get("month_filters_checked") == 0
        and len(previous.get("failures", [])) >= 96
    ):
        previous["source_blocker"] = {
            "kind": "filtered_archive_blocked_from_free_collector_infrastructure",
            "direct_route": "HTTP 500 for every attempted filter",
            "free_reader_route": "response contained no requested auction heading or result rows",
            "scope": "2010-2013, both advertised venues and all months",
            "retry_policy": "terminal until a materially different free retrieval route is available",
            "note": "the browser-verifiable February 2012 table is not treated as empty or captured",
        }
        previous["checked_at"] = corpus.now()
        corpus.save_json(collection_path, previous)
        print(json.dumps(previous, indent=2), flush=True)
        return previous

    resolved, archive_raw = fetch(BASE)
    archive_html = archive_raw.decode("utf-8", "replace")
    venues, years = discover_filters(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/agents-property-auction" / f"result-filter-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party result archive filter",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})

    checked = set(previous.get("checked_month_keys", []))
    # Do not hammer combinations which the source itself rejected on the
    # preceding pass.  Retain them as unresolved and advance to usable years;
    # they can be explicitly retried after the surviving archive is banked.
    previous_failures = {
        item.get("key"): item for item in previous.get("failures", []) if item.get("key")
    }
    if previous.get("transport_version") == TRANSPORT_VERSION:
        prior_failed = set(previous_failures)
    else:
        # The v1 transport failed every filtered request.  Avoid repeating the
        # already exhausted 2010-11 probe, but retry 2012+ once with the fixed
        # browser session (February 2012 is independently known to be live).
        prior_failed = {
            key for key in previous_failures
            if int(key.rsplit("-", 1)[0].rsplit("|", 1)[1]) < 2012
        }
    attempted = checked | prior_failed
    now = datetime.now(timezone.utc)
    candidates = []
    for year in years:
        for venue in venues:
            final_month = now.month if year == now.year else 12
            for month in range(1, final_month + 1):
                key = f"{venue}|{year:04d}-{month:02d}"
                if key not in attempted:
                    candidates.append((key, venue, year, month))
    limit = max(1, years_per_run) * max(1, len(venues)) * 12
    selected = candidates[:limit]
    states, rows, run_failures = {}, [], []

    def capture(item):
        key, venue, year, month = item
        # Match the first-party form/search URL ordering.  Some legacy result
        # routes return HTTP 500 for unsupported combinations.
        params = [("a_month", f"{month:02d}"), ("a_sub", "1"), ("a_venue", venue), ("a_year", str(year))]
        page_url = BASE + "?" + urlencode(params)
        document_format = "html"
        retrieval_url = page_url
        try:
            page_url, raw = fetch(BASE, params)
        except requests.HTTPError as direct_error:
            target = urlsplit(page_url)
            retrieval_url = READER + target.path + ("?" + target.query if target.query else "")
            response = requests.get(retrieval_url, headers=HEADERS, timeout=75)
            response.raise_for_status()
            raw = response.content
            if len(raw) < 500:
                raise ValueError("reader response is unexpectedly short") from direct_error
            document_format = "markdown"
        sha = corpus.digest(raw)
        snapshot = corpus.DATA / "sources/agents-property-auction" / f"{venue.casefold().replace(' ', '-')}-{year:04d}-{month:02d}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": page_url,
            "retrieval_url": retrieval_url,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party venue/month sold-result table" if document_format == "html" else "public text rendering of first-party venue/month sold-result table",
            "document_format": document_format,
        }
        page_html = raw.decode("utf-8", "replace")
        state, page_rows = parse_result_page(page_html, page_url, venue, year, month, evidence)
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        return key, state, page_rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        jobs = {pool.submit(capture, item): item for item in selected}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                key, state, page_rows = future.result()
                checked.add(key)
                previous_failures.pop(key, None)
                if state:
                    states[state["source_auction_id"]] = state
                    rows.extend(page_rows)
                    venue_slug = state["venue"].casefold().replace(" ", "-")
                    month = state["published_auction_month"]
                    corpus.save_json(corpus.DATA / f"auctions/agents-property-auction/{venue_slug}-{month}.json", state)
            except Exception as exc:
                failure = {
                    "key": item[0],
                    "url": BASE + "?" + urlencode({"a_venue": item[1], "a_year": item[2], "a_month": f"{item[3]:02d}", "a_sub": 1}),
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
                previous_failures[item[0]] = failure
                run_failures.append(failure)

    shard = corpus.DATA / "appearances/agents-property-auction/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in rows})
    total = corpus.write_rows("agents-property-auction/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    all_possible = sum((now.month if year == now.year else 12) * len(venues) for year in years)
    summary = {
        "checked_at": corpus.now(),
        "transport_version": TRANSPORT_VERSION,
        "source_url": BASE,
        "archive_evidence": archive_evidence,
        "venues": venues,
        "years_exposed": years,
        "checked_month_keys": sorted(checked),
        "attempted_month_keys": sorted(attempted | {item[0] for item in selected}),
        "month_filters_checked": len(checked),
        "month_filters_expected_through_current_month": all_possible,
        "filter_inventory_complete_through_current_month": len(checked) == all_possible and not previous_failures,
        "result_tables_captured_this_run": len(states),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_records": sum(not row.get("auction_date") for row in added),
        "with_sale_price": sum(row.get("sale_price") is not None for row in merged.values()),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "catalogue_completion_claimed": False,
        "completion_limit": "sold-result tables do not expose the original catalogue denominator or exact auction day",
        "failures": [previous_failures[key] for key in sorted(previous_failures)],
        "run_failures": run_failures,
    }
    corpus.save_json(collection_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if run_failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("years_per_run", nargs="?", type=int, default=2)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    harvest(args.years_per_run, args.workers)
