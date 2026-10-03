"""Bank McHugh & Co's retained first-party auction result catalogues.

Every visible property card is preserved, including residential lots and
withdrawn/postponed/unsold rows.  Published "lots offered" totals are retained
as reconciliation evidence; a catalogue is only marked complete when that
denominator agrees with the visible source rows.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.mchughandco.com"
ARCHIVE = BASE + "/past-auction-results"
AUCTION_RE = re.compile(r"/past-auctions/(\d+)/?$")
DETAIL_RE = re.compile(r"/lot/details/([0-9a-f-]{20,})/?$", re.I)
FULL_DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def parse_auction_dates(value: str) -> tuple[str, str | None]:
    """Return first/last dates, including headings with an abbreviated first date."""
    text = clean(value) or ""
    matches = list(FULL_DATE_RE.finditer(text))
    if not matches:
        raise ValueError("result page has no exact auction date heading")
    dates = [datetime.strptime(" ".join(m.groups()), "%d %B %Y").date() for m in matches]
    prefix = text[:matches[0].start()]
    short = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:&|and)\s*(?:[A-Za-z]+\s*)?$", prefix, re.I)
    if short:
        dates.insert(0, dates[0].replace(day=int(short.group(1))))
    return dates[0].isoformat(), dates[-1].isoformat() if dates[-1] != dates[0] else None


def discover_auctions(html: str, page_url: str = ARCHIVE) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for row in soup.select('tr[data-url*="/past-auctions/"]'):
        anchor = row.find("a", href=True)
        if not anchor:
            continue
        url = urljoin(page_url, anchor["href"]).split("?", 1)[0].rstrip("/")
        match = AUCTION_RE.search(urlparse(url).path)
        cells = row.find_all("td", recursive=False)
        if not match or len(cells) < 3:
            continue
        offered_text = clean(cells[2].get_text(" ", strip=True)) or ""
        found[match.group(1)] = {
            "auction_id": match.group(1), "url": url,
            "date_text": clean(cells[0].get_text(" ", strip=True)),
            "published_lots_offered": int(offered_text) if offered_text.isdigit() else None,
        }
    return sorted(found.values(), key=lambda item: int(item["auction_id"]))


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    match = MONEY_RE.search(text)
    price = int(round(float(match.group(1).replace(",", "")))) if match else None
    if lower.startswith("sold prior"):
        return "sold_prior", price, None
    if lower.startswith("sold post") or lower.startswith("sold after"):
        return "sold_post", price, None
    if lower.startswith("sold"):
        return "sold", price, None
    if lower.startswith("available"):
        return "available", None, price
    for label in ("withdrawn", "postponed", "unsold"):
        if lower.startswith(label):
            return label, None, None
    return "unknown", None, None


def parse_result_page(html: str, result_url: str, published_offered: int | None, evidence: dict) -> tuple[dict, list[dict]]:
    match = AUCTION_RE.search(urlparse(result_url).path)
    if not match:
        raise ValueError("result URL has no auction identifier")
    auction_id = match.group(1)
    soup = BeautifulSoup(html, "lxml")
    heading = clean((soup.find("h1") or soup.title).get_text(" ", strip=True))
    auction_date, auction_date_end = parse_auction_dates(heading or "")
    cards = soup.select("div.panel.grid-panel")
    if not cards:
        raise ValueError("result page contains no source lot cards")

    rows = []
    for position, card in enumerate(cards, 1):
        lot_node = card.select_one("[data-lot-number-searchable]")
        address_node = card.select_one("[data-address-searchable]")
        detail_anchor = card.find("a", href=DETAIL_RE)
        if not detail_anchor:
            detail_anchor = card.select_one('a[href*="/lot/details/"]')
        lot_number = clean(lot_node.get_text(" ", strip=True) if lot_node else None)
        address_text = clean(address_node.get_text(" ", strip=True) if address_node else None)
        detail_url = urljoin(BASE, detail_anchor.get("href")) if detail_anchor else None
        detail_match = DETAIL_RE.search(urlparse(detail_url or "").path)
        if not lot_number or not address_text or not detail_match:
            raise ValueError(f"lot identity missing at source position {position}")
        source_id = detail_match.group(1).lower()
        description = clean((card.select_one(".grid-tagline") or card).get_text(" ", strip=True))
        status_node = card.select_one(".grid-guideprice b")
        status_text = clean(status_node.get_text(" ", strip=True) if status_node else None)
        status, sale_price, available_price = status_and_prices(status_text)
        postcode_match = corpus.PC.search(address_text)
        postcode = postcode_match.group().upper().replace("\u00a0", " ") if postcode_match else None
        address = address_text if postcode else None
        row = corpus.base_row(
            "McHugh & Co", f"mchugh:{auction_id}", auction_date,
            lot_number, source_id, detail_url or result_url,
        )
        row.update(
            address=address, postcode=postcode, locality=address_text,
            description=description, sector=corpus.sector(f"{address_text} {description or ''}"),
            status=status, sale_price=sale_price, available_price=available_price,
            property_id=None, identity_method="source_auction_and_lot_detail_uuid",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_status_text=status_text,
            source_result_url=result_url, source_evidence=evidence,
            auction_date_end=auction_date_end,
        )
        row["appearance_id"] = f"McHugh & Co|auction:{auction_id}|lot:{source_id}"
        rows.append(row)

    identities = [row["source_lot_id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate lot identities within result page")
    complete = published_offered is not None and published_offered == len(rows)
    state = {
        "auctioneer": "McHugh & Co", "source_auction_id": f"mchugh:{auction_id}",
        "auction_date": auction_date, "auction_date_end": auction_date_end,
        "catalogue_complete": complete, "source_rows_complete": True,
        "published_lots_offered": published_offered, "visible_source_rows": len(rows),
        "lots_captured": len(rows), "source_url": result_url,
        "completion_scope": "all visible cards in the first-party unpaginated result catalogue",
        "denominator_reconciled": complete,
        "reconciliation_note": None if complete else {
            "kind": "published_denominator_mismatch",
            "published_lots_offered": published_offered, "visible_source_rows": len(rows),
        },
        "errors": [], "checked_at": corpus.now(),
    }
    return state, rows


def harvest(workers: int = 8) -> None:
    final_url, raw = get(ARCHIVE)
    archive_sha, retrieved_at = corpus.digest(raw), corpus.now()
    archive_snapshot = corpus.DATA / "sources/mchugh" / f"past-auction-results-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": final_url, "retrieved_at": retrieved_at, "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party past-auction-results index",
    }
    html = raw.decode("utf-8", "replace")
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": html})
    auctions = discover_auctions(html, final_url)
    if not auctions:
        raise SystemExit("No retained first-party result pages discovered")

    run_rows, states, failures = [], {}, []

    def capture(item: dict):
        resolved, page_raw = get(item["url"])
        page_sha, captured_at = corpus.digest(page_raw), corpus.now()
        snapshot = corpus.DATA / "sources/mchugh" / f"auction-{item['auction_id']}-{page_sha[:16]}.json.gz"
        evidence = {
            "source_url": resolved, "retrieved_at": captured_at, "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated auction result catalogue",
        }
        page_html = page_raw.decode("utf-8", "replace")
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        state, rows = parse_result_page(page_html, resolved, item["published_lots_offered"], evidence)
        return item["auction_id"], state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
        jobs = {pool.submit(capture, item): item for item in auctions}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                auction_id, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/mchugh/auction-{auction_id}.json", state)
                states[auction_id] = state
                run_rows.extend(rows)
                print("MCHUGH", len(states), "/", len(auctions), "pages", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"url": item["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    path = corpus.DATA / "appearances/mchugh/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("mchugh/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "result_pages_discovered": len(auctions), "result_pages_captured": len(states),
        "result_pages_complete": sum(bool(state["catalogue_complete"]) for state in states.values()),
        "result_pages_denominator_mismatch": sum(not state["catalogue_complete"] for state in states.values()),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "mchugh_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
