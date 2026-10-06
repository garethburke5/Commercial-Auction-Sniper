"""Bank every retained Dedman Gray first-party/EIG result catalogue.

The public archive exposes one unpaginated result table per auction, a stable
EIG lot identifier, and an exact archive date.  A catalogue is complete only
when every visible table produces one distinct appearance and its heading
agrees with the archive's day and month.
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


TENANT = "4a7995f2-9c5d-4ca4-a92d-84f05a99af25"
ARCHIVE_URL = f"https://ams-webtemplates.eigroup.co.uk/embed/script/auction/{TENANT}/3993/119"
CATALOGUE_URL = f"https://ams-webtemplates.eigroup.co.uk/embed/script/auction/{TENANT}/{{}}/105"
PUBLIC_ARCHIVE = "https://www.dedmangray.co.uk/auction/?q=1&tid=119"
HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)",
    "Referer": PUBLIC_ARCHIVE,
}
WRITE_RE = re.compile(r'document\.write\(("(?:\\.|[^"\\])*")\);', re.S)
LOT_RE = re.compile(r"LOT:\s*([0-9A-Za-z]+)?", re.I)
PRICE_RE = re.compile(r"£\s*([\d,.]+)\s*([MK])?", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if b"document.write" not in response.content:
                raise ValueError("EIG response contains no document.write payload")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def expand_script(script: str) -> str:
    values = [corpus.js_string(match.group(1)[1:-1]) for match in WRITE_RE.finditer(script)]
    if not values:
        raise ValueError("EIG script contains no decodable HTML fragments")
    return "".join(values)


def discover(script: str) -> list[dict]:
    soup = BeautifulSoup(expand_script(script), "lxml")
    catalogues = {}
    for link in soup.select('a[href*="aid="][href*="tid=105"]'):
        query = parse_qs(urlsplit(link.get("href") or "").query)
        source_id = (query.get("aid") or [None])[0]
        date_text = clean(link.get_text(" ", strip=True))
        if not source_id or not date_text or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", date_text):
            continue
        date = datetime.strptime(date_text, "%d/%m/%Y").date().isoformat()
        prior = catalogues.setdefault(source_id, date)
        if prior != date:
            raise ValueError(f"auction {source_id} has conflicting archive dates")
    if not catalogues:
        raise ValueError("Dedman Gray archive contains no dated result catalogues")
    return [
        {"source_id": source_id, "auction_date": date}
        for source_id, date in sorted(catalogues.items(), key=lambda item: (item[1], int(item[0])))
    ]


def labelled_value(table, label: str) -> str | None:
    for node in table.select("span.lotheader"):
        if clean(node.get_text(" ", strip=True)) == label:
            parent = node.parent
            text = parent.get_text(" ", strip=True)
            return clean(re.sub(rf"^\s*{re.escape(label)}\s*", "", text, flags=re.I))
    return None


def result_fields(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").upper()
    if "SOLD PRIOR" in text:
        status = "sold_prior"
    elif "SOLD POST" in text or "SOLD AFTER" in text:
        status = "sold_after"
    elif "SOLD" in text:
        status = "sold"
    elif "WITHDRAWN" in text:
        status = "withdrawn"
    elif "POSTPONED" in text:
        status = "postponed"
    elif "UNSOLD" in text:
        status = "unsold"
    elif "AVAILABLE" in text:
        status = "available"
    else:
        status = "unknown"
    match = PRICE_RE.search(text)
    price = corpus.money((match.group(1) + (match.group(2) or "")) if match else None)
    return status, int(price) if price and status in {"sold", "sold_prior", "sold_after"} else None


def parse_catalogue(script: str, item: dict, evidence: dict) -> tuple[list[dict], dict]:
    html = expand_script(script)
    soup = BeautifulSoup(html, "lxml")
    date = datetime.fromisoformat(item["auction_date"]).date()
    heading = clean(soup.get_text(" ", strip=True)) or ""
    heading_match = re.search(r"Results for property auction held on\s+(\d{1,2})\s+([A-Za-z]+)", heading, re.I)
    heading_day_month = None
    if heading_match:
        heading_day_month = datetime.strptime(
            f"{heading_match.group(1)} {heading_match.group(2)} {date.year}", "%d %B %Y"
        ).date()
    date_matches = bool(heading_day_month and (heading_day_month.day, heading_day_month.month) == (date.day, date.month))

    tables = soup.select("table.lotdetails")
    rows, missing_identity = [], []
    for position, table in enumerate(tables, 1):
        number_node = table.select_one("td.lotnum")
        number_match = LOT_RE.search(number_node.get_text(" ", strip=True) if number_node else "")
        if not number_match:
            raise ValueError(f"auction {item['source_id']} row {position} has no lot marker")
        lot_number = number_match.group(1).upper() if number_match.group(1) else None
        detail = table.select_one('a[href*="lid="]')
        detail_url = urljoin(PUBLIC_ARCHIVE, detail.get("href") or "") if detail else None
        query = parse_qs(urlsplit(detail_url or "").query)
        source_lot_id = (query.get("lid") or [None])[0]
        if not source_lot_id:
            source_lot_id = f"archive-row:{lot_number or 'unlabelled'}:{position}"
            missing_identity.append(position)
        address = labelled_value(table, "Address:")
        result_text = labelled_value(table, "Result:")
        status, sale_price = result_fields(result_text)
        description_node = table.select_one("td[style*='padding:5px']")
        description = clean(description_node.get_text(" ", strip=True)) if description_node else None
        image = table.select_one("img[src]")
        image_url = urljoin(PUBLIC_ARCHIVE, image.get("src") or "") if image else None
        postcode_match = corpus.PC.search(address or "")
        row = corpus.base_row(
            "Dedman Gray", f"dedman-gray:{item['source_id']}", item["auction_date"],
            lot_number, source_lot_id, detail_url or PUBLIC_ARCHIVE,
        )
        row.update(
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, description]))),
            sale_price=sale_price,
            status=status,
            description=description,
            image_urls=[image_url] if image_url else [],
            property_id=source_lot_id if not source_lot_id.startswith("archive-row:") else None,
            identity_method=(
                "first_party_published_eig_lot_id" if not source_lot_id.startswith("archive-row:")
                else "exact_auction_lot_and_source_position"
            ),
            record_quality="address_record" if address else "partial_lot",
            source_position=position,
            source_result_text=result_text,
            auction_date_basis="exact date in first-party retained results archive",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    complete = bool(len(rows) == len(tables) == len(set(identities)) and date_matches)
    return rows, {
        "visible_source_rows": len(tables),
        "distinct_appearance_identities": len(set(identities)),
        "heading_date_matches_archive": date_matches,
        "fallback_identity_positions": missing_identity,
        "catalogue_complete": complete,
    }


def state_path(source_id: str) -> Path:
    return corpus.DATA / "auctions/dedman-gray" / f"{source_id}.json"


def fetch_catalogue(item: dict) -> tuple[dict, bytes, str]:
    raw, resolved = get(CATALOGUE_URL.format(item["source_id"]))
    return item, raw, resolved


def harvest(limit: int | None = None, workers: int = 8, refresh: bool = False) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_script = archive_raw.decode("utf-8", "replace")
    catalogues = discover(archive_script)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/dedman-gray" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved,
        "public_archive_url": PUBLIC_ARCHIVE,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained EIG results archive",
        "catalogues_discovered": len(catalogues),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "script": archive_script})

    pending = []
    for item in catalogues:
        path = state_path(item["source_id"])
        state = json.loads(path.read_text()) if path.exists() else {}
        if refresh or not state.get("catalogue_complete") or state.get("auction_date") != item["auction_date"]:
            pending.append(item)
    if limit is not None:
        pending = pending[:limit]

    before_ids = set()
    for path in (corpus.DATA / "appearances/dedman-gray").glob("*.jsonl.gz"):
        before_ids.update(row["appearance_id"] for row in corpus.iter_rows(path))
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {pool.submit(fetch_catalogue, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item, raw, resolved = future.result()
                script = raw.decode("utf-8", "replace")
                sha = corpus.digest(raw)
                snapshot = corpus.DATA / "sources/dedman-gray" / f"auction-{item['source_id']}-{sha[:16]}.json.gz"
                evidence = {
                    "source_url": resolved,
                    "public_archive_url": PUBLIC_ARCHIVE,
                    "retrieved_at": corpus.now(),
                    "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party retained unpaginated EIG result catalogue",
                    "archive_evidence": archive_evidence,
                }
                corpus.save_gzip(snapshot, {"evidence": evidence, "script": script})
                rows, reconciliation = parse_catalogue(script, item, evidence)
                if not reconciliation["catalogue_complete"]:
                    raise ValueError(f"catalogue reconciliation failed: {reconciliation}")
                total = corpus.write_rows(f"dedman-gray/{item['source_id']}", rows)
                state = {
                    "auctioneer": "Dedman Gray",
                    "source_auction_id": f"dedman-gray:{item['source_id']}",
                    "auction_date": item["auction_date"],
                    "source_url": resolved,
                    "lots_captured": total,
                    "source_rows_complete": True,
                    "pagination_reconciled": True,
                    "denominator_reconciled": True,
                    "completion_scope": "every visible row in the first-party unpaginated result catalogue",
                    **reconciliation,
                    "source_evidence": evidence,
                    "errors": [],
                    "checked_at": corpus.now(),
                }
                corpus.save_json(state_path(item["source_id"]), state)
                print(f"Dedman Gray {item['auction_date']} ({item['source_id']}): {total} rows complete", flush=True)
            except Exception as exc:  # preserve completed catalogues and report retryable failures
                failures.append({"source_id": item["source_id"], "auction_date": item["auction_date"], "error": str(exc)})
                print(f"Dedman Gray {item['source_id']}: FAILED {exc}", flush=True)

    all_rows = []
    states = []
    for item in catalogues:
        path = state_path(item["source_id"])
        if path.exists():
            states.append(json.loads(path.read_text()))
        shard = corpus.DATA / "appearances/dedman-gray" / f"{item['source_id']}.jsonl.gz"
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
    corpus.save_json(corpus.DATA / "dedman_gray_collection.json", summary)
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
