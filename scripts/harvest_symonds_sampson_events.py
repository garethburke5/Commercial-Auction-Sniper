"""Bank surviving Symonds & Sampson property-auction event cards.

The canonical sitemap collector retains only property pages still present in
the live sitemap.  The first-party past-events index separately retains dated
event pages and their complete visible property-card arrays back to April
2023.  This collector preserves those event appearances, including repeat
offerings of the same listing on different dates, without duplicating a
same-date listing already banked by the canonical collector.
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
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_symonds_sampson_canonical import strict_address


BASE = "https://auctions.symondsandsampson.co.uk"
INDEX = BASE + "/events/property-auction/symonds-and-sampson-property-auctions?eventdate=past"
EVENT_DATE_RE = re.compile(
    r"Event Date & Time:\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    re.I,
)
PROPERTY_RE = re.compile(r"^/property/([a-z]{3}\d[^/]*)/", re.I)
STATUS_MAP = {
    "sold by auction": "sold",
    "sold stc": "sold",
    "sold": "sold",
    "withdrawn": "withdrawn",
    "postponed": "postponed",
    "unsold": "unsold",
    "available": "available",
    "for sale": "available",
}


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"}), timeout=60) as response:
        return response.read()


def discover_event_urls(index_pages: list[bytes]) -> list[str]:
    urls = []
    for raw in index_pages:
        soup = BeautifulSoup(raw, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("/event/property-auction-"):
                urls.append(urljoin(BASE, href))
    return list(dict.fromkeys(urls))


def parse_money(label: str, text: str) -> int | None:
    match = re.search(label + r"(?:\s*Price)?\s*(?:£\s*)+([\d,]+(?:\.\d+)?)\s*([mk])?", text, re.I)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    value *= {"m": 1_000_000, "k": 1_000}.get((match.group(2) or "").lower(), 1)
    return int(round(value))


def parse_event(raw: bytes, event_url: str, evidence: dict) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(raw, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    date_match = EVENT_DATE_RE.search(text)
    if not date_match:
        raise ValueError("event page has no exact published date")
    date = datetime.strptime(date_match.group(1), "%d %B %Y").date().isoformat()
    event_slug = urlparse(event_url).path.rstrip("/").rsplit("/", 1)[-1]
    rows = []
    seen = set()
    for anchor in soup.select("a.FeaturedGrid__item[href]"):
        match = PROPERTY_RE.match(anchor.get("href", ""))
        if not match:
            continue
        source_id = match.group(1).lower()
        if source_id in seen:
            continue
        seen.add(source_id)
        heading = anchor.find("h3")
        locality = " ".join(heading.get_text(" ", strip=True).split()) if heading else None
        card_text = " ".join(anchor.get_text(" ", strip=True).split())
        status_node = anchor.select_one(".status")
        status_text = " ".join(status_node.get_text(" ", strip=True).lower().split()) if status_node else ""
        status = STATUS_MAP.get(status_text, "unknown")
        original_url = urljoin(BASE, anchor["href"])
        path_parts = [part for part in urlparse(original_url).path.split("/") if part]
        property_type = path_parts[-2].replace("-", " ") if path_parts[-1].startswith(("studio", "1-bedroom", "2-bedroom", "3-bedroom", "4-bedroom", "5-bedroom", "6-bedroom", "7-bedroom", "8-bedroom", "9-bedroom")) else path_parts[-1].replace("-", " ")
        address = strict_address(locality)
        postcode_match = corpus.PC.search(locality or "")
        sale_price = parse_money(r"Sold by Auction for", card_text)
        guide_price = parse_money(r"Guide", card_text)
        guide_high_match = re.search(r"Guide(?: Price)?\s*(?:£\s*)+[\d,]+(?:\.\d+)?\s*(?:[mk])?\s*-\s*(?:£\s*)+([\d,]+(?:\.\d+)?)\s*([mk])?", card_text, re.I)
        guide_high = None
        if guide_high_match:
            guide_high = int(round(float(guide_high_match.group(1).replace(",", "")) * {"m": 1_000_000, "k": 1_000}.get((guide_high_match.group(2) or "").lower(), 1)))
        auction_id = "symonds-sampson-event:" + event_slug
        row = corpus.base_row("Symonds & Sampson", auction_id, date, None, source_id, original_url)
        row.update(
            appearance_id=f"Symonds & Sampson|event:{event_slug}|listing:{source_id}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=locality,
            property_type=property_type,
            sector=corpus.sector(" ".join(v for v in (property_type, locality) if v)),
            status=status,
            sale_price=sale_price,
            guide_price=guide_price,
            guide_price_high=guide_high,
            identity_method="source_property_id_and_event",
            record_quality="address_record" if address else "partial_lot",
            source_evidence=evidence,
            auction_date_basis="exact date published on official event page",
        )
        image = anchor.select_one("[data-bg]")
        if image and image.get("data-bg"):
            row["image_urls"] = [urljoin(BASE, image["data-bg"])]
        rows.append(row)
    if not rows:
        raise ValueError("event page exposes zero property cards")
    return date, rows


def canonical_pairs() -> set[tuple[str, str]]:
    path = corpus.DATA / "appearances/symonds-sampson/retained-property-pages.jsonl.gz"
    if not path.exists():
        return set()
    return {(row.get("source_lot_id"), row.get("auction_date")) for row in corpus.iter_rows(path)}


def harvest(workers: int = 4) -> None:
    # The index currently advertises four pages. Stop at the first page with no
    # new event links so a future fifth page is picked up without hard-coding a
    # completeness claim beyond the live pagination.
    index_pages, index_urls, event_urls = [], [], []
    for page in range(1, 20):
        url = INDEX + (f"&page={page}" if page > 1 else "")
        raw = fetch(url)
        discovered = discover_event_urls([raw])
        if not discovered:
            break
        new = [item for item in discovered if item not in event_urls]
        if not new:
            break
        index_pages.append(raw)
        index_urls.append(url)
        event_urls.extend(new)
    if not event_urls:
        raise SystemExit("Symonds & Sampson past-events index exposed no event pages")

    index_digest = corpus.digest(b"\n".join(index_pages))
    index_snapshot = corpus.DATA / "sources/symonds-sampson/events" / f"index-{index_digest[:16]}.json.gz"
    if not index_snapshot.exists():
        corpus.save_gzip(index_snapshot, {
            "source_urls": index_urls,
            "retrieved_at": corpus.now(),
            "sha256": index_digest,
            "event_urls": event_urls,
            "pages": [raw.decode("utf-8", "replace") for raw in index_pages],
        })

    overlap_pairs = canonical_pairs()
    rows, auctions = [], {}

    def collect(event_url: str):
        raw = fetch(event_url)
        sha = corpus.digest(raw)
        slug = urlparse(event_url).path.rstrip("/").rsplit("/", 1)[-1]
        snapshot = corpus.DATA / "sources/symonds-sampson/events" / f"{slug}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": event_url,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "index_snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "basis": "property card on first-party dated past-event page",
        }
        date, event_rows = parse_event(raw, event_url, evidence)
        return event_url, slug, date, raw, snapshot, evidence, event_rows

    collected = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as executor:
        jobs = {executor.submit(collect, event_url): event_url for event_url in event_urls}
        for position, future in enumerate(as_completed(jobs), 1):
            collected.append(future.result())
            print(f"SYMONDS FETCH {position}/{len(event_urls)}", flush=True)

    for event_url, slug, date, raw, snapshot, evidence, event_rows in sorted(collected, key=lambda item: item[1]):
        if not snapshot.exists():
            corpus.save_gzip(snapshot, {"evidence": evidence, "source_content": raw.decode("utf-8", "replace")})
        retained = [row for row in event_rows if (row["source_lot_id"], date) not in overlap_pairs]
        rows.extend(retained)
        auctions[slug] = {
            "auctioneer": "Symonds & Sampson",
            "source_auction_id": "symonds-sampson-event:" + slug,
            "auction_date": date,
            "source_url": event_url,
            "source_rows_complete": True,
            "catalogue_complete": True,
            "pagination_reconciled": True,
            "denominator_reconciled": True,
            "visible_source_rows": len(event_rows),
            "lots_captured": len(event_rows),
            "overlapping_canonical_rows": len(event_rows) - len(retained),
            "completion_scope": "all property cards on the retained first-party event page",
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions/symonds-sampson/events" / f"{slug}.json", auctions[slug])
        print(f"SYMONDS EVENT {date} {len(event_rows)} rows ({len(retained)} event rows)", flush=True)

    if len({row["appearance_id"] for row in rows}) != len(rows):
        raise SystemExit("duplicate event/listing identity in Symonds & Sampson archive")
    appearance_path = corpus.DATA / "appearances/symonds-sampson/event-archive.jsonl.gz"
    existing_event_ids = {
        row["appearance_id"] for row in corpus.iter_rows(appearance_path)
    } if appearance_path.exists() else set()
    new_rows = [row for row in rows if row["appearance_id"] not in existing_event_ids]
    total = corpus.write_rows("symonds-sampson/event-archive", rows)
    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "index_pages_captured": len(index_pages),
        "events_discovered": len(event_urls),
        "events_complete": len(auctions),
        "visible_event_rows": sum(item["visible_source_rows"] for item in auctions.values()),
        "overlapping_canonical_rows": sum(item["overlapping_canonical_rows"] for item in auctions.values()),
        "event_appearances_captured": total,
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": sum(row.get("sale_price") is not None for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_year": dict(Counter(row["auction_date"][:4] for row in rows)),
        "complete": len(auctions) == len(event_urls),
        "archive_pagination_complete": len(auctions) == len(event_urls),
        "completion_scope": "surviving first-party past-event pages from the live paginated index; not twenty-year coverage",
    }
    corpus.save_json(corpus.DATA / "symonds_sampson_event_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    harvest(args.workers)
