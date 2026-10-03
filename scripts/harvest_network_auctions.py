"""Bank Network Auctions' retained 2020-2023 first-party result catalogues.

The archive still links legacy ``auction_id`` catalogues containing one
unpaginated card per lot.  Newer ``online_auction_id`` shells do not expose lot
rows and are deliberately excluded until their underlying data source can be
reconciled.  Every visible legacy card is preserved, including residential,
commercial, unsold, postponed and withdrawn lots.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.networkauctions.co.uk"
ARCHIVE = BASE + "/auctions/previous-auctions/"
CATALOGUE = BASE + "/auctions/next-auction/?auction_id={}"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(
    r"Auction Date:\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def parse_archive_date(value: str) -> str:
    match = DATE_RE.search(value or "")
    if not match:
        raise ValueError(f"missing archive date in {value!r}")
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def discover_auctions(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    cards = soup.select("div.next-auction-content, div.future-auction-single")
    for card in cards:
        date = None
        try:
            date = parse_archive_date(card.get_text(" ", strip=True))
        except ValueError:
            continue
        for anchor in card.select("a[href]"):
            url = urljoin(BASE, anchor.get("href"))
            query = parse_qs(urlsplit(url).query)
            # Do not confuse the newer empty online-auction shells with the
            # retained legacy catalogues that actually publish source rows.
            if "auction_id" not in query or "online_auction_id" in query:
                continue
            auction_id = clean(query["auction_id"][0])
            if auction_id:
                found[auction_id] = {
                    "auction_id": auction_id, "auction_date": date,
                    "url": CATALOGUE.format(auction_id),
                }
                break
    if not found:
        raise ValueError("archive contains no legacy auction_id catalogues")
    return sorted(found.values(), key=lambda item: item["auction_date"])


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def status_and_prices(status_text: str | None, price_text: str | None) -> tuple[str, int | None, int | None]:
    status = (clean(status_text) or "").casefold()
    result = (clean(price_text) or "").casefold()
    text = f"{status} {result}".strip()
    amount = money(price_text)
    if "sold prior" in text:
        return "sold_prior", amount, None
    if "sold after" in text or "sold post" in text:
        return "sold_after", amount, None
    if "withdrawn" in text:
        return "withdrawn", None, None
    if "postponed" in text:
        return "postponed", None, None
    if "no bids" in text:
        return "no_bids", None, amount
    if "unsold" in text:
        return "unsold", None, amount
    if status == "sold" or result.startswith("sold"):
        return "sold", amount, None
    if amount is not None:
        return "unknown", None, amount
    return "unknown", None, None


def parse_catalogue(html: str, expected: dict, evidence: dict) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    heading = clean((soup.select_one("h1") or soup.select_one("h2") or soup).get_text(" ", strip=True))
    heading_date = None
    match = re.search(r"LOTS FOR AUCTION\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", heading or "", re.I)
    if match:
        heading_date = datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
    if heading_date and heading_date != expected["auction_date"]:
        raise ValueError(f"catalogue date mismatch: expected {expected['auction_date']}, saw {heading_date}")

    cards = soup.select("div.current-lots-single")
    if not cards:
        raise ValueError("legacy catalogue contains no lot cards")
    rows = []
    for position, card in enumerate(cards, 1):
        lot_nodes = card.select("span.lot-number")
        lot_text = clean(lot_nodes[0].get_text(" ", strip=True)) if lot_nodes else None
        lot_match = re.match(r"Lot\s+(.+)$", lot_text or "", re.I)
        lot_number = clean(lot_match.group(1)) if lot_match else None
        status_text = clean(lot_nodes[1].get_text(" ", strip=True)) if len(lot_nodes) > 1 else None
        anchor = card.select_one('a[href*="lot_id="]')
        detail_url = urljoin(BASE, anchor.get("href")) if anchor else None
        query = parse_qs(urlsplit(detail_url or "").query)
        source_id = clean(query.get("lot_id", [None])[0])
        # Seven retained rows publish the literal label "Lot" without a
        # printed number.  The first-party lot_id is still a stable property
        # identity, so preserve the row with a null lot_number.
        if not source_id or not detail_url:
            raise ValueError(f"lot identity missing at source position {position}")

        address_node = card.select_one("div.lot-info p")
        address_text = clean(address_node.get_text(" ", strip=True) if address_node else None)
        postcode_match = corpus.PC.search(address_text or "")
        postcode = postcode_match.group().upper() if postcode_match else None
        address = address_text if postcode else None
        price_node = card.select_one("p.guide-price")
        price_text = clean(price_node.get_text(" ", strip=True) if price_node else None)
        status, sale_price, guide_price = status_and_prices(status_text, price_text)
        source_auction_id = f"network-auctions:{expected['auction_id']}"
        row = corpus.base_row(
            "Network Auctions", source_auction_id, expected["auction_date"],
            lot_number, source_id, detail_url,
        )
        row.update(
            address=address, postcode=postcode, locality=address_text,
            sector=corpus.sector(address_text or ""), status=status,
            sale_price=sale_price, guide_price=guide_price,
            property_id=None,
            identity_method="source_auction_and_first_party_lot_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_status_text=status_text,
            source_price_text=price_text, source_result_url=expected["url"],
            source_evidence=evidence,
        )
        row["appearance_id"] = (
            f"Network Auctions|auction:{expected['auction_id']}|property:{source_id}"
        )
        rows.append(row)

    identities = [row["source_lot_id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate first-party lot IDs within catalogue")
    state = {
        "auctioneer": "Network Auctions",
        "source_auction_id": f"network-auctions:{expected['auction_id']}",
        "auction_date": expected["auction_date"], "catalogue_complete": True,
        "source_rows_complete": True, "published_lots_offered": None,
        "visible_source_rows": len(rows), "lots_captured": len(rows),
        "source_url": expected["url"], "pagination_reconciled": True,
        "denominator_reconciled": True,
        "denominator_basis": "all current-lots-single cards in the first-party unpaginated legacy catalogue",
        "completion_scope": "all visible property cards in the retained first-party legacy catalogue",
        "errors": [], "checked_at": corpus.now(),
    }
    return state, rows


def get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response


def harvest(workers: int = 6) -> None:
    archive_response = get(ARCHIVE)
    archive_html = archive_response.content.decode("utf-8", "replace")
    archive_sha, retrieved_at = corpus.digest(archive_response.content), corpus.now()
    archive_snapshot = corpus.DATA / "sources/network-auctions" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_response.url, "retrieved_at": retrieved_at,
        "sha256": archive_sha, "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party previous-auctions index",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    auctions = discover_auctions(archive_html)

    path = corpus.DATA / "appearances/network-auctions/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)

    states, run_rows, pending, failures, reused = {}, [], [], [], 0
    for item in auctions:
        state_path = corpus.DATA / f"auctions/network-auctions/auction-{item['auction_id']}.json"
        try:
            old_state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            old_state = None
        old_rows = existing_by_auction.get(f"network-auctions:{item['auction_id']}", [])
        if (old_state and old_state.get("catalogue_complete") and old_rows and
                old_state.get("lots_captured") == len(old_rows) and
                old_state.get("auction_date") == item["auction_date"]):
            states[item["auction_id"]] = old_state
            run_rows.extend(old_rows)
            reused += 1
        else:
            pending.append(item)

    def capture(item: dict):
        response = get(item["url"])
        raw = response.content
        sha, captured_at = corpus.digest(raw), corpus.now()
        snapshot = corpus.DATA / "sources/network-auctions" / f"auction-{item['auction_id']}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": response.url, "retrieved_at": captured_at,
            "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated legacy result catalogue",
        }
        page_html = raw.decode("utf-8", "replace")
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        state, rows = parse_catalogue(page_html, item, evidence)
        return state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        jobs = {pool.submit(capture, item): item for item in pending}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                state, rows = future.result()
                corpus.save_json(
                    corpus.DATA / f"auctions/network-auctions/auction-{item['auction_id']}.json", state,
                )
                states[item["auction_id"]] = state
                run_rows.extend(rows)
                print("NETWORK", len(states), "/", len(auctions), "auctions", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({
                    "auction_id": item["auction_id"], "auction_date": item["auction_date"],
                    "url": item["url"], "error": f"{type(exc).__name__}: {exc}"[:500],
                })

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("network-auctions/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "legacy_auctions_discovered": len(auctions), "auctions_captured": len(states),
        "auctions_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "auctions_reused": reused, "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
        "deferred_scope": "online_auction_id shells expose no visible source lot rows",
    }
    corpus.save_json(corpus.DATA / "network_auctions_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    harvest(workers)
