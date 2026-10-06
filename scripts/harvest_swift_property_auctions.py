"""Bank Swift Property Auctions' retained first-party results archive.

The archive exposes a stable auction ID, exact auction date and published lot
count for each sale.  Result pages are unpaginated and expose stable property
IDs, lot numbers, addresses, descriptions, guides and outcomes.  A catalogue is
complete only when its heading date and every distinct property card reconcile
to the archive denominator.
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
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.swiftpropertyauctions.co.uk"
ARCHIVE_URL = BASE + "/previous-auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def date_value(value: str | None) -> str | None:
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
    for link in soup.select('a[href^="/previous-auctions/"]'):
        source_id = urlsplit(link.get("href") or "").path.rstrip("/").rsplit("/", 1)[-1]
        if not source_id.isdigit():
            continue
        date = date_value(link.get("aria-label"))
        container = link.find_parent("article", class_="date-card")
        text = clean(container.get_text(" ", strip=True)) if container else None
        count_match = re.search(r"\b(\d+)\s+lots?\b", text or "", re.I)
        if not count_match:
            section = link.find_parent("section")
            section_text = clean(section.get_text(" ", strip=True)) if section else None
            count_match = re.search(r"\bLots sold\s+\d+\s+of\s+(\d+)\b", section_text or "", re.I)
        if not date or not count_match:
            raise ValueError(f"archive entry {source_id} lacks exact date or lot denominator")
        item = {
            "source_id": source_id,
            "auction_date": date,
            "expected_lots": int(count_match.group(1)),
            "source_url": urljoin(BASE, link.get("href") or ""),
        }
        prior = catalogues.setdefault(source_id, item)
        if prior != item:
            raise ValueError(f"auction {source_id} has conflicting archive metadata")
    if not catalogues:
        raise ValueError("Swift archive contains no dated catalogues")
    return sorted(catalogues.values(), key=lambda item: (item["auction_date"], int(item["source_id"])))


def result_fields(card) -> tuple[str, int | None, str | None]:
    raw = clean((card.select_one(".sr-only") or card).get_text(" ", strip=True))
    source_status = clean(card.get("data-result"))
    status_map = {
        "sold": "sold", "sold-prior": "sold_prior", "sold-after": "sold_after",
        "unsold": "unsold", "withdrawn": "withdrawn", "postponed": "postponed",
        "available": "available",
    }
    status = status_map.get((source_status or "").lower(), "unknown")
    price_block = card.select_one(".auction-guide.x-result-price")
    match = MONEY_RE.search(price_block.get_text(" ", strip=True) if price_block else (raw or ""))
    price = corpus.money((match.group(1) + (match.group(2) or "")) if match else None)
    return status, int(price) if price and status in {"sold", "sold_prior", "sold_after"} else None, raw


def parse_catalogue(html: str, item: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(lambda tag: tag.name in {"h1", "h2"} and date_value(tag.get_text(" ", strip=True)))
    heading_date = date_value(heading.get_text(" ", strip=True) if heading else None)
    rows, malformed, seen_source_ids = [], [], set()
    cards = soup.select("article.auction-lot.x-result-lot")
    for position, card in enumerate(cards, 1):
        detail = card.select_one('h3 a[href^="/lots/"]')
        lot_badge = clean((card.select_one(".auction-lot-badge") or card).get_text(" ", strip=True))
        source_lot_id = urlsplit(detail.get("href") if detail else "").path.rstrip("/").rsplit("/", 1)[-1]
        lot_match = re.fullmatch(r"Lot\s+(.+)", lot_badge or "", re.I)
        if not detail or not source_lot_id.isdigit() or not lot_match or source_lot_id in seen_source_ids:
            malformed.append({"position": position, "source_lot_id": source_lot_id or None, "lot_badge": lot_badge})
            continue
        seen_source_ids.add(source_lot_id)
        title = clean(detail.get_text(" ", strip=True))
        locality = clean((card.select_one(".auction-lot-location") or card).get_text(" ", strip=True))
        address = clean(", ".join(part for part in (title, locality) if part))
        description = clean((card.select_one(".auction-lot-summary") or card).get_text(" ", strip=True))
        guide_block = card.select_one(".auction-guide:not(.x-result-price)")
        guide_match = MONEY_RE.search(guide_block.get_text(" ", strip=True) if guide_block else "")
        guide = corpus.money((guide_match.group(1) + (guide_match.group(2) or "")) if guide_match else None)
        status, sale_price, result_text = result_fields(card)
        postcode_match = corpus.PC.search(address or "")
        legal = card.select_one('a[href*="legaldocuments.eigroup.co.uk"]')
        image = card.select_one(".auction-lot-photo img[src]")
        detail_url = urljoin(BASE, detail.get("href") or "")
        row = corpus.base_row(
            "Swift Property Auctions", f"swift:{item['source_id']}", item["auction_date"],
            lot_match.group(1), source_lot_id, detail_url,
        )
        row.update(
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=locality,
            sector=corpus.sector(" ".join(part for part in (title, description) if part)),
            guide_price=int(guide) if guide else None,
            sale_price=sale_price,
            status=status,
            description=description,
            legal_pack_url=legal.get("href") if legal else None,
            image_urls=[image.get("src")] if image else [],
            property_id=source_lot_id,
            identity_method="first_party_stable_property_id_scoped_to_auction",
            record_quality="address_record" if address else "partial_lot",
            source_position=position,
            source_result_text=result_text,
            source_result_code=clean(card.get("data-result")),
            auction_date_basis="exact date in first-party archive and result-page heading",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    complete = bool(
        not malformed
        and heading_date == item["auction_date"]
        and len(cards) == len(rows) == len(set(identities)) == item["expected_lots"]
    )
    return rows, {
        "published_lot_denominator": item["expected_lots"],
        "visible_source_rows": len(cards),
        "distinct_appearance_identities": len(set(identities)),
        "heading_auction_date": heading_date,
        "heading_date_matches_archive": heading_date == item["auction_date"],
        "malformed_source_rows": malformed,
        "catalogue_complete": complete,
    }


def state_path(source_id: str) -> Path:
    return corpus.DATA / "auctions/swift-property-auctions" / f"{source_id}.json"


def harvest(workers: int = 8, refresh: bool = False) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    catalogues = discover(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/swift-property-auctions" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved, "retrieved_at": corpus.now(), "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained results archive with exact dates and lot denominators",
        "catalogues_discovered": len(catalogues),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    pending = []
    for item in catalogues:
        path = state_path(item["source_id"])
        state = json.loads(path.read_text()) if path.exists() else {}
        if refresh or not state.get("catalogue_complete") or state.get("published_lot_denominator") != item["expected_lots"]:
            pending.append(item)
    before_ids = {
        row["appearance_id"]
        for path in (corpus.DATA / "appearances/swift-property-auctions").glob("*.jsonl.gz")
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
                snapshot = corpus.DATA / "sources/swift-property-auctions" / f"auction-{item['source_id']}-{sha[:16]}.json.gz"
                evidence = {
                    "source_url": resolved, "retrieved_at": corpus.now(), "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party unpaginated auction result page",
                    "archive_evidence": archive_evidence,
                }
                corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
                rows, reconciliation = parse_catalogue(html, item, evidence)
                if not reconciliation["catalogue_complete"]:
                    raise ValueError(f"catalogue reconciliation failed: {reconciliation}")
                total = corpus.write_rows(f"swift-property-auctions/{item['source_id']}", rows)
                state = {
                    "auctioneer": "Swift Property Auctions",
                    "source_auction_id": f"swift:{item['source_id']}",
                    "auction_date": item["auction_date"], "source_url": resolved,
                    "lots_captured": total, "source_rows_complete": True,
                    "pagination_reconciled": True, "denominator_reconciled": True,
                    "completion_scope": "every property card in the first-party unpaginated result page",
                    **reconciliation, "source_evidence": evidence, "errors": [], "checked_at": corpus.now(),
                }
                corpus.save_json(state_path(item["source_id"]), state)
                print(f"Swift {item['auction_date']} ({item['source_id']}): {total} rows complete", flush=True)
            except Exception as exc:
                failures.append({"source_id": item["source_id"], "auction_date": item["auction_date"], "error": str(exc)})
                print(f"Swift {item['source_id']}: FAILED {exc}", flush=True)

    states, all_rows = [], []
    for item in catalogues:
        state_file = state_path(item["source_id"])
        if state_file.exists():
            states.append(json.loads(state_file.read_text()))
        shard = corpus.DATA / "appearances/swift-property-auctions" / f"{item['source_id']}.jsonl.gz"
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
    corpus.save_json(corpus.DATA / "swift_property_auctions_collection.json", summary)
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
