"""Bank John Francis's retained first-party auction lot lists.

The archive publishes an exact auction date and one unpaginated lot list per
sale.  Each visible row exposes a stable EIG lot ID, lot number, address and
result.  Catalogues are complete only after all visible IDs and the heading
date reconcile with the archive.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.johnfrancis.co.uk"
ARCHIVE_URL = BASE + "/pages/past_auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(
    r"\bon\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 1000:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def discover(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    catalogues = {}
    for row in soup.select("table.auctions__table tbody tr"):
        date_link = row.select_one('a[href*="lotlist?aid="]')
        if not date_link:
            continue
        query = parse_qs(urlsplit(date_link.get("href") or "").query)
        source_id = (query.get("aid") or [None])[0]
        date_text = clean(date_link.get_text(" ", strip=True))
        if not source_id or not date_text or not re.fullmatch(r"\d{2}/\d{2}/\d{2}", date_text):
            continue
        date = datetime.strptime(date_text, "%d/%m/%y").date().isoformat()
        cells = row.find_all("td", recursive=False)
        venue = clean(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else None
        item = {
            "source_id": source_id,
            "auction_date": date,
            "venue": venue,
            "source_url": urljoin(BASE, date_link.get("href") or ""),
        }
        prior = catalogues.setdefault(source_id, item)
        if prior["auction_date"] != date:
            raise ValueError(f"auction {source_id} has conflicting archive dates")
    if not catalogues:
        raise ValueError("John Francis archive contains no dated catalogues")
    return sorted(catalogues.values(), key=lambda item: (item["auction_date"], int(item["source_id"])))


def result_fields(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").upper()
    if "WITHDRAWN" in text:
        status = "withdrawn"
    elif "POSTPONED" in text:
        status = "postponed"
    elif "UNSOLD" in text:
        status = "unsold"
    elif "SOLD PRIOR" in text:
        status = "sold_prior"
    elif "SOLD POST" in text or "SOLD AFTER" in text:
        status = "sold_after"
    elif "SOLD" in text:
        status = "sold"
    elif "AVAILABLE" in text:
        status = "available"
    else:
        status = "unknown"
    match = MONEY_RE.search(text)
    price = corpus.money((match.group(1) + (match.group(2) or "")) if match else None)
    return status, int(price) if price and status in {"sold", "sold_prior", "sold_after"} else None


def heading_date(soup: BeautifulSoup) -> str | None:
    heading = soup.find(lambda tag: tag.name in {"h3", "h4"} and "List of properties" in tag.get_text(" ", strip=True))
    match = DATE_RE.search(heading.get_text(" ", strip=True) if heading else "")
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def parse_catalogue(html: str, item: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    groups = {}
    for link in soup.select('table.auctions__table a[href*="auction_property?lid="]'):
        query = parse_qs(urlsplit(link.get("href") or "").query)
        source_lot_id = (query.get("lid") or [None])[0]
        if source_lot_id:
            groups.setdefault(source_lot_id, []).append(link)

    rows, malformed = [], []
    for position, (source_lot_id, links) in enumerate(groups.items(), 1):
        if len(links) != 3:
            malformed.append({"source_lot_id": source_lot_id, "link_count": len(links)})
            continue
        lot_number = clean(links[0].get_text(" ", strip=True))
        address = clean(links[1].get_text(" ", strip=True))
        result_cell = links[1].find_parent("td").find_next_sibling("td")
        result_text = clean(result_cell.get_text(" ", strip=True)) if result_cell else None
        detail_url = urljoin(BASE, links[1].get("href") or "")
        status, sale_price = result_fields(result_text)
        postcode_match = corpus.PC.search(address or "")
        row = corpus.base_row(
            "John Francis", f"john-francis:{item['source_id']}", item["auction_date"],
            lot_number, source_lot_id, detail_url,
        )
        row.update(
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address or ""),
            sale_price=sale_price,
            status=status,
            property_id=source_lot_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=position,
            source_result_text=result_text,
            source_venue=item.get("venue"),
            auction_date_basis="exact date in first-party retained auction archive and lot-list heading",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    exact_heading_date = heading_date(soup)
    complete = bool(
        not malformed
        and len(rows) == len(groups) == len(set(identities))
        and exact_heading_date == item["auction_date"]
    )
    return rows, {
        "visible_source_rows": len(groups),
        "distinct_appearance_identities": len(set(identities)),
        "heading_auction_date": exact_heading_date,
        "heading_date_matches_archive": exact_heading_date == item["auction_date"],
        "malformed_source_rows": malformed,
        "catalogue_complete": complete,
    }


def state_path(source_id: str) -> Path:
    return corpus.DATA / "auctions/john-francis" / f"{source_id}.json"


def fetch_catalogue(item: dict) -> tuple[dict, bytes, str]:
    raw, resolved = get(item["source_url"])
    return item, raw, resolved


def harvest(limit: int | None = None, workers: int = 8, refresh: bool = False) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    catalogues = discover(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/john-francis" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained past-auctions table",
        "catalogues_discovered": len(catalogues),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})

    pending = []
    for item in catalogues:
        path = state_path(item["source_id"])
        state = json.loads(path.read_text()) if path.exists() else {}
        if refresh or not state.get("catalogue_complete") or state.get("auction_date") != item["auction_date"]:
            pending.append(item)
    if limit is not None:
        pending = pending[:limit]

    before_ids = set()
    for path in (corpus.DATA / "appearances/john-francis").glob("*.jsonl.gz"):
        before_ids.update(row["appearance_id"] for row in corpus.iter_rows(path))
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {pool.submit(fetch_catalogue, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item, raw, resolved = future.result()
                html = raw.decode("utf-8", "replace")
                sha = corpus.digest(raw)
                snapshot = corpus.DATA / "sources/john-francis" / f"auction-{item['source_id']}-{sha[:16]}.json.gz"
                evidence = {
                    "source_url": resolved,
                    "retrieved_at": corpus.now(),
                    "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party retained unpaginated auction lot list",
                    "archive_evidence": archive_evidence,
                }
                corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
                rows, reconciliation = parse_catalogue(html, item, evidence)
                if not reconciliation["catalogue_complete"]:
                    raise ValueError(f"catalogue reconciliation failed: {reconciliation}")
                total = corpus.write_rows(f"john-francis/{item['source_id']}", rows)
                state = {
                    "auctioneer": "John Francis",
                    "source_auction_id": f"john-francis:{item['source_id']}",
                    "auction_date": item["auction_date"],
                    "source_url": resolved,
                    "lots_captured": total,
                    "source_rows_complete": True,
                    "pagination_reconciled": True,
                    "denominator_reconciled": True,
                    "completion_scope": "every distinct lot ID in the first-party unpaginated lot list",
                    **reconciliation,
                    "source_evidence": evidence,
                    "errors": [],
                    "checked_at": corpus.now(),
                }
                corpus.save_json(state_path(item["source_id"]), state)
                print(f"John Francis {item['auction_date']} ({item['source_id']}): {total} rows complete", flush=True)
            except Exception as exc:
                failures.append({"source_id": item["source_id"], "auction_date": item["auction_date"], "error": str(exc)})
                print(f"John Francis {item['source_id']}: FAILED {exc}", flush=True)

    states, all_rows = [], []
    for item in catalogues:
        state_file = state_path(item["source_id"])
        if state_file.exists():
            states.append(json.loads(state_file.read_text()))
        shard = corpus.DATA / "appearances/john-francis" / f"{item['source_id']}.jsonl.gz"
        if shard.exists():
            all_rows.extend(corpus.iter_rows(shard))
    all_ids = {row["appearance_id"] for row in all_rows}
    added = [row for row in all_rows if row["appearance_id"] not in before_ids]
    complete_states = [state for state in states if state.get("catalogue_complete")]
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive_resolved,
        "catalogues_discovered": len(catalogues),
        "catalogues_captured": len(states),
        "catalogues_complete": len(complete_states),
        "appearances_captured": len(all_ids),
        "address_records": sum(bool(row.get("address")) for row in all_rows),
        "partial_lots": sum(not row.get("address") for row in all_rows),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [catalogues[0]["auction_date"], catalogues[-1]["auction_date"]],
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in all_rows)),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "failures": failures,
        "complete": len(complete_states) == len(catalogues) and not failures,
    }
    corpus.save_json(corpus.DATA / "john_francis_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    summary = harvest(args.limit, args.workers, args.refresh)
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
