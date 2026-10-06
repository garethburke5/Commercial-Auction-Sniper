"""Bank Sharpes Auctions' retained first-party traditional-auction results."""
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
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.sharpesauctions.co.uk"
ARCHIVE_URL = BASE + "/previous-auctions.php?type=traditional"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def exact_date(value: str | None) -> str | None:
    match = DATE_RE.search(value or "")
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 5000:
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
    for link in soup.select('a[href*="previous-auction-properties.php?date="]'):
        match = re.search(r"[?&]date=(\d{4}-\d{2}-\d{2})", link.get("href") or "")
        if not match:
            continue
        date = match.group(1)
        if exact_date(link.get_text(" ", strip=True)) != date:
            raise ValueError(f"archive link date text disagrees with {date}")
        item = {"source_id": date, "auction_date": date, "source_url": urljoin(BASE, link.get("href") or "")}
        prior = catalogues.setdefault(date, item)
        if prior != item:
            raise ValueError(f"auction {date} has conflicting archive metadata")
    if not catalogues:
        raise ValueError("Sharpes archive contains no dated catalogues")
    return sorted(catalogues.values(), key=lambda item: item["auction_date"])


def status_value(value: str | None) -> str:
    text = (clean(value) or "").upper()
    if "WITHDRAWN" in text:
        return "withdrawn"
    if "POSTPONED" in text:
        return "postponed"
    if "SOLD PRIOR" in text:
        return "sold_prior"
    if "SOLD POST" in text or "SOLD AFTER" in text:
        return "sold_after"
    if "UNSOLD" in text or "REFER" in text:
        return "unsold"
    if "SOLD" in text:
        return "sold"
    return "unknown"


def parse_catalogue(html: str, item: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(lambda tag: tag.name in {"h1", "h2", "h3"} and "PREVIOUS AUCTION" in tag.get_text(" ", strip=True).upper())
    heading_date = exact_date(heading.get_text(" ", strip=True) if heading else None)
    cards = soup.select(".products_table_items")
    rows, malformed, seen = [], [], set()
    for position, card in enumerate(cards, 1):
        property_link = card.select_one('a[href*="/property/"]')
        detail_link = card.select_one('.products_table_title a[href]')
        route = urlsplit(property_link.get("href") if property_link else "").path.rstrip("/")
        id_match = re.search(r"/(\d+)$", route)
        lot_box = card.select_one(".products_table_items_lotnumber")
        lot_match = re.search(r"\bLot\s+([^*\s]+)", lot_box.get_text(" ", strip=True) if lot_box else "", re.I)
        source_lot_id = id_match.group(1) if id_match else None
        if not source_lot_id or not lot_match or not detail_link or source_lot_id in seen:
            malformed.append({"position": position, "source_lot_id": source_lot_id, "text": clean(card.get_text(" ", strip=True))})
            continue
        seen.add(source_lot_id)
        address = clean(detail_link.get_text(" ", strip=True))
        price_text = clean((card.select_one(".products_table_price") or card).get_text(" ", strip=True))
        result_boxes = card.select(".products_table_items_lotnumber")
        result_text = clean(result_boxes[1].get_text(" ", strip=True)) if len(result_boxes) > 1 else None
        status = status_value(result_text)
        values = MONEY_RE.findall(price_text or "")
        guide = corpus.money("".join(values[0])) if values else None
        sale = corpus.money("".join(values[-1])) if len(values) > 1 else None
        postcode_match = corpus.PC.search(address or "")
        image = card.select_one(".products_table_thumb img[src]")
        original_url = property_link.get("href")
        row = corpus.base_row(
            "Sharpes Auctions", f"sharpes:{item['source_id']}", item["auction_date"],
            lot_match.group(1), source_lot_id, original_url,
        )
        row.update(
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address or ""),
            guide_price=int(guide) if guide else None,
            sale_price=int(sale) if sale and status in {"sold", "sold_prior", "sold_after"} else None,
            status=status,
            image_urls=[urljoin(BASE, image.get("src"))] if image else [],
            property_id=source_lot_id,
            identity_method="first_party_stable_property_route_id_scoped_to_auction",
            record_quality="address_record" if address else "partial_lot",
            source_position=position,
            source_result_text=result_text,
            source_price_text=price_text,
            source_detail_url=urljoin(BASE, detail_link.get("href") or ""),
            auction_date_basis="exact date in first-party archive URL, link text and result heading",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    complete = bool(cards and not malformed and heading_date == item["auction_date"] and len(cards) == len(rows) == len(set(identities)))
    return rows, {
        "visible_source_rows": len(cards),
        "distinct_appearance_identities": len(set(identities)),
        "heading_auction_date": heading_date,
        "heading_date_matches_archive": heading_date == item["auction_date"],
        "malformed_source_rows": malformed,
        "catalogue_complete": complete,
    }


def state_path(source_id: str) -> Path:
    return corpus.DATA / "auctions/sharpes" / f"{source_id}.json"


def harvest(workers: int = 8, refresh: bool = False) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    catalogues = discover(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/sharpes" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved, "retrieved_at": corpus.now(), "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained traditional-auction archive",
        "catalogues_discovered": len(catalogues),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    pending = []
    for item in catalogues:
        path = state_path(item["source_id"])
        state = json.loads(path.read_text()) if path.exists() else {}
        if refresh or not state.get("catalogue_complete") or state.get("auction_date") != item["auction_date"]:
            pending.append(item)
    before_ids = {
        row["appearance_id"]
        for path in (corpus.DATA / "appearances/sharpes").glob("*.jsonl.gz")
        for row in corpus.iter_rows(path)
    }
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {pool.submit(get, item["source_url"]): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            try:
                raw, resolved = future.result()
                html = raw.decode("utf-8", "replace")
                sha = corpus.digest(raw)
                snapshot = corpus.DATA / "sources/sharpes" / f"auction-{item['source_id']}-{sha[:16]}.json.gz"
                evidence = {
                    "source_url": resolved, "retrieved_at": corpus.now(), "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party retained unpaginated traditional-auction results",
                    "archive_evidence": archive_evidence,
                }
                corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
                rows, reconciliation = parse_catalogue(html, item, evidence)
                if not reconciliation["catalogue_complete"]:
                    raise ValueError(f"catalogue reconciliation failed: {reconciliation}")
                total = corpus.write_rows(f"sharpes/{item['source_id']}", rows)
                state = {
                    "auctioneer": "Sharpes Auctions", "source_auction_id": f"sharpes:{item['source_id']}",
                    "auction_date": item["auction_date"], "source_url": resolved, "lots_captured": total,
                    "source_rows_complete": True, "pagination_reconciled": True,
                    "denominator_reconciled": True,
                    "completion_scope": "every property card in the first-party unpaginated result page",
                    **reconciliation, "source_evidence": evidence, "errors": [], "checked_at": corpus.now(),
                }
                corpus.save_json(state_path(item["source_id"]), state)
                print(f"Sharpes {item['auction_date']}: {total} rows complete", flush=True)
            except Exception as exc:
                failures.append({"source_id": item["source_id"], "auction_date": item["auction_date"], "error": str(exc)})
                print(f"Sharpes {item['source_id']}: FAILED {exc}", flush=True)

    states, all_rows = [], []
    for item in catalogues:
        path = state_path(item["source_id"])
        if path.exists():
            states.append(json.loads(path.read_text()))
        shard = corpus.DATA / "appearances/sharpes" / f"{item['source_id']}.jsonl.gz"
        if shard.exists():
            all_rows.extend(corpus.iter_rows(shard))
    all_ids = {row["appearance_id"] for row in all_rows}
    added = [row for row in all_rows if row["appearance_id"] not in before_ids]
    complete_states = [state for state in states if state.get("catalogue_complete")]
    summary = {
        "checked_at": corpus.now(), "source_url": archive_resolved,
        "catalogues_discovered": len(catalogues), "catalogues_captured": len(states),
        "catalogues_complete": len(complete_states), "appearances_captured": len(all_ids),
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
    corpus.save_json(corpus.DATA / "sharpes_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    summary = harvest(args.workers, args.refresh)
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
