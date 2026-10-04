"""Bank Town & Country Property Auctions' retained first-party result archive.

The public EIG-powered archive exposes one stable UUID and exact closing timestamp
per property.  Every outcome and residential/commercial/land row is retained.
Archive pagination is reconciled separately from unavailable original catalogue
denominators, so these rows are never counted as complete auction catalogues.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.townandcountrypropertyauctions.co.uk"
INDEX = BASE + "/past-auctions?order=RecentlyEnded&lotResultType=All"
DETAIL_RE = re.compile(r"/lot/details/([0-9a-f]{8}-[0-9a-f-]{27})/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def result_details(value: str | None) -> tuple[str, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    if lower.startswith("sold prior"):
        status = "sold_prior"
    elif lower.startswith("sold post") or lower.startswith("sold after"):
        status = "sold_post"
    elif lower.startswith("sold"):
        status = "sold"
    elif lower.startswith("withdrawn"):
        status = "withdrawn"
    elif lower.startswith("postponed"):
        status = "postponed"
    elif lower.startswith("no bids"):
        status = "no_bids"
    elif lower.startswith("unsold"):
        status = "unsold"
    else:
        status = "unknown"
    return status, pounds(text) if status.startswith("sold") else None


def pagination_extent(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for anchor in soup.find_all("a", href=True):
        for value in parse_qs(urlparse(anchor["href"]).query).get("page", []):
            if value.isdigit():
                pages.add(int(value))
    return max(pages)


def parse_page(html: str, source_url: str, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for card in soup.select("div.panel-body.lot-panels"):
        detail_anchor = card.find("a", href=DETAIL_RE)
        if detail_anchor is None:
            detail_anchor = card.select_one('a[href*="/lot/details/"]')
        detail_url = detail_anchor.get("href") if detail_anchor else None
        match = DETAIL_RE.search(urlparse(detail_url or "").path)
        time_node = card.select_one("time[datetime]")
        address_text = clean(
            card.select_one(".lot-address").get_text(" ", strip=True)
            if card.select_one(".lot-address") else None
        )
        if not match or not time_node or not address_text:
            continue
        source_id = match.group(1).lower()
        end_raw = time_node.get("datetime")
        try:
            end_at = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"lot {source_id} has invalid exact end timestamp") from exc
        office = clean(
            card.select_one(".lot-auctioneer-name").get_text(" ", strip=True)
            if card.select_one(".lot-auctioneer-name") else None
        )
        result_node = card.select_one(".grid-guideprice .price")
        result_text = clean(result_node.get_text(" ", strip=True) if result_node else None)
        status, sale_price = result_details(result_text)
        postcode_match = corpus.PC.search(address_text)
        postcode = postcode_match.group().upper() if postcode_match else None
        description = clean(
            card.select_one(".grid-tagline").get_text(" ", strip=True)
            if card.select_one(".grid-tagline") else None
        )
        image = card.select_one("img.grid-img[src]")
        office_slug = re.sub(r"[^a-z0-9]+", "-", (office or "unknown").casefold()).strip("-")
        row = corpus.base_row(
            "Town & Country Property Auctions",
            f"town-country:{office_slug}:online:{end_at.date().isoformat()}",
            end_at.date().isoformat(),
            None,
            source_id,
            detail_url,
        )
        row.update(
            appearance_id=f"Town & Country Property Auctions|online:{source_id}",
            address=address_text if postcode else None,
            postcode=postcode,
            locality=address_text,
            sector=corpus.sector(" ".join(filter(None, (address_text, description)))),
            guide_price=None,
            guide_price_high=None,
            sale_price=sale_price,
            status=status,
            property_id=source_id,
            identity_method="source_lot_uuid",
            record_quality="address_record" if postcode else "partial_lot",
            partial_location=None if postcode else address_text,
            auction_end_time=end_at.isoformat(),
            auction_date_basis="exact individual lot end timestamp published by source",
            source_office=office,
            source_auction_id_basis=(
                "exact published regional office and individual lot end date"
            ),
            result_text=result_text,
            description=description,
            image_urls=[image["src"]] if image else [],
            source_evidence=evidence,
        )
        rows.append(row)
    if not rows:
        raise ValueError("source page contains no evidenced result cards")
    deduped = {}
    for row in rows:
        old = deduped.get(row["source_lot_id"])
        if old and old != row:
            raise ValueError(f"conflicting duplicate lot {row['source_lot_id']}")
        deduped[row["source_lot_id"]] = row
    return list(deduped.values())


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000 or b"/lot/details/" not in response.content:
        raise ValueError("source returned no retained result cards")
    return response


def page_url(page: int) -> str:
    return INDEX + (f"&page={page}" if page > 1 else "")


def harvest(workers: int = 4) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    first = fetch(session, page_url(1))
    first_raw = first.content
    first_html = first_raw.decode("utf-8", "replace")
    last_page = pagination_extent(first_html)

    appearance_path = corpus.DATA / "appearances/town-country/online-results.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    merged = {row["source_lot_id"]: row for row in existing}
    before_ids = set(merged)

    summary_path = corpus.DATA / "town_country_collection.json"
    try:
        prior = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        prior = {}

    first_sha = corpus.digest(first_raw)
    first_snapshot = (
        corpus.DATA / "sources/town-country"
        / f"page-0001-{first_sha[:16]}.json.gz"
    )
    first_evidence = {
        "source_url": first.url,
        "retrieved_at": corpus.now(),
        "sha256": first_sha,
        "snapshot_path": str(first_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party paginated past-auctions result card with stable lot UUID",
    }
    first_rows = parse_page(first_html, first.url, first_evidence)
    first_ids = {row["source_lot_id"] for row in first_rows}
    unchanged_complete = (
        prior.get("archive_pagination_complete") is True
        and prior.get("pages_expected") == last_page
        and first_ids <= before_ids
    )
    pages = [1] if unchanged_complete else list(range(1, last_page + 1))

    page_rows = {1: first_rows}
    page_evidence = {1: (first_raw, first_html, first_evidence)}
    failures = []

    def collect(page: int):
        response = fetch(session, page_url(page))
        raw = response.content
        html = raw.decode("utf-8", "replace")
        sha = corpus.digest(raw)
        snapshot = (
            corpus.DATA / "sources/town-country"
            / f"page-{page:04d}-{sha[:16]}.json.gz"
        )
        evidence = {
            "source_url": response.url,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party paginated past-auctions result card with stable lot UUID",
        }
        return page, raw, html, evidence, parse_page(html, response.url, evidence)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(collect, page): page for page in pages if page != 1}
        for future in as_completed(futures):
            page = futures[future]
            try:
                number, raw, html, evidence, rows = future.result()
                page_rows[number] = rows
                page_evidence[number] = (raw, html, evidence)
            except Exception as exc:
                failures.append({
                    "page": page, "url": page_url(page),
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })

    seen_current = {}
    for page in sorted(page_rows):
        raw, html, evidence = page_evidence[page]
        snapshot = corpus.ROOT / evidence["snapshot_path"]
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        for row in page_rows[page]:
            source_id = row["source_lot_id"]
            if source_id in seen_current:
                raise ValueError(
                    f"source UUID {source_id} repeated on pages "
                    f"{seen_current[source_id]} and {page}"
                )
            seen_current[source_id] = page
            previous = merged.get(source_id)
            if previous and previous.get("address") and row.get("address") and (
                previous["address"] != row["address"]
            ):
                raise ValueError(f"source identity drift for lot {source_id}")
            merged[source_id] = row

    rows = sorted(
        merged.values(),
        key=lambda row: (row.get("auction_end_time") or "", row["source_lot_id"]),
    )
    corpus.write_rows("town-country/online-results", rows)
    full_pass = len(pages) == last_page
    page_counts = {str(page): len(page_rows[page]) for page in sorted(page_rows)}
    archive_complete = (
        full_pass
        and not failures
        and len(page_rows) == last_page
        and len(seen_current) == sum(page_counts.values())
    )
    if unchanged_complete and not failures:
        archive_complete = True
        page_counts = prior.get("page_counts") or page_counts

    added = [row for key, row in merged.items() if key not in before_ids]
    dates = [row["auction_date"] for row in rows if row.get("auction_date")]
    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "pages_expected": last_page,
        "pages_fetched_this_run": len(page_rows),
        "pages_captured": last_page if archive_complete else len(page_rows),
        "current_archive_rows": (
            len(seen_current) if full_pass else prior.get("current_archive_rows")
        ),
        "property_appearances_captured": len(rows),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "earliest_lot_end_date": min(dates) if dates else None,
        "latest_lot_end_date": max(dates) if dates else None,
        "by_status": dict(Counter(row.get("status") or "unknown" for row in rows)),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in rows)),
        "page_counts": page_counts,
        "failures": failures,
        "archive_pagination_complete": archive_complete,
        "scope_warning": (
            "individual timed lots; original catalogue denominators are unavailable "
            "and no auction catalogue is counted complete"
        ),
    }
    corpus.save_json(summary_path, summary)
    corpus.save_json(
        corpus.DATA / "auctions/town-country/online-results.json",
        {
            "auctioneer": "Town & Country Property Auctions",
            "source_auction_id": "town-country:online-results",
            "auction_date": None,
            "catalogue_complete": False,
            "archive_pagination_complete": archive_complete,
            "lots_captured": len(rows),
            "completion_scope": "all retained first-party past-auctions result pages",
            "errors": failures + [{
                "error": (
                    "Rows are individual timed lots; original catalogue "
                    "denominators are not published"
                )
            }],
            "checked_at": corpus.now(),
        },
    )
    print(json.dumps(summary, indent=2), flush=True)
    if failures or not archive_complete:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    harvest(args.workers)
