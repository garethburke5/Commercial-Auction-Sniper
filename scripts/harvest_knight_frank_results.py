"""Bank Knight Frank Auctions' retained first-party recently-sold archive.

The archive is a complete unpaginated presentation of its stated result count,
but describes itself as a selection rather than a complete set of original
catalogues.  We therefore reconcile and preserve every retained card without
claiming original-catalogue completeness.  Stable source property IDs define
appearances; detail pages add exact auction dates, lot numbers and rich fields.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.knightfrankauctions.com"
ARCHIVE_URL = BASE + "/recently-sold/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
COUNT_RE = re.compile(r"Showing\s+([\d,]+)\s+results", re.I)
DETAIL_RE = re.compile(r"/property/([^/]+)/", re.I)
AUCTION_RE = re.compile(r"/auction/(\d+)/", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}\s+[A-Za-z]+\s+20\d{2})\b")
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
IMAGE_RE = re.compile(r"background-image:\s*url\(['\"]?([^)'\"]+)", re.I)
CHUNK_SIZE = 20


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def published_total(html: str) -> int:
    match = COUNT_RE.search(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
    if not match:
        raise ValueError("recently-sold archive denominator is absent")
    return int(match.group(1).replace(",", ""))


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").casefold()
    if "prior" in text:
        status = "sold_prior"
    elif "after" in text or "post" in text:
        status = "sold_after"
    else:
        # Every archive card is explicitly ribboned Sold; a bare price and the
        # one blank retained label therefore remain sold, not unknown.
        status = "sold"
    return status, pounds(value)


def parse_archive(html: str) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div[data-id][data-page]")
    expected = published_total(html)
    if len(cards) != expected:
        raise ValueError(f"archive exposes {len(cards)} cards of {expected} stated results")
    rows, duplicates, seen = [], [], set()
    for position, card in enumerate(cards, 1):
        source_id = clean(card.get("data-id"))
        link = card.select_one('a[href*="/property/"]')
        address_node = card.select_one("p.mt-2")
        if not source_id or not link or not address_node:
            raise ValueError(f"archive card {position} lacks source identity, link or address")
        detail_url = urljoin(BASE, link.get("href") or "")
        match = DETAIL_RE.search(detail_url)
        address = clean(address_node.get_text(" ", strip=True))
        if not match or match.group(1) != source_id or not address:
            raise ValueError(f"archive card {position} has conflicting or empty identity fields")
        result_node = card.select_one("div.font-bold.text-red-700")
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        style = link.get("style") or ""
        image_match = IMAGE_RE.search(style)
        item = {
            "source_id": source_id,
            "detail_url": detail_url,
            "address": address,
            "result_text": result_text,
            "image_url": urljoin(BASE, image_match.group(1)) if image_match else None,
            "source_position": position,
        }
        if source_id in seen:
            duplicates.append(item)
        else:
            seen.add(source_id)
            rows.append(item)
    return rows, duplicates


def labelled_value(soup: BeautifulSoup, label: str) -> str | None:
    for node in soup.select("ul.flex.mt-2.text-sm p"):
        text = clean(node.get_text(" ", strip=True))
        if text and text.casefold().startswith(label.casefold()):
            return clean(text.split(":", 1)[1] if ":" in text else None)
    return None


def section_value(soup: BeautifulSoup, label: str) -> str | None:
    for node in soup.select("p.font-bold"):
        if clean(node.get_text(" ", strip=True)).casefold() == label.casefold():
            sibling = node.find_next_sibling("p")
            return clean(sibling.get_text(" ", strip=True)) if sibling else None
    return None


def detail_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    address_node = soup.select_one("h6.mt-2.font-bold")
    headline_node = soup.select_one("h2.text-2xl")
    result_node = soup.select_one("div.font-bold.text-red-700")
    auction_link = soup.select_one('a[href*="/auction/"]')
    auction_match = AUCTION_RE.search(auction_link.get("href") or "") if auction_link else None
    auction_panel = None
    for heading in soup.find_all("h3"):
        if clean(heading.get_text(" ", strip=True)) == "Auction Information":
            auction_panel = heading.parent
            break
    date_match = DATE_RE.search(auction_panel.get_text(" ", strip=True)) if auction_panel else None
    auction_date = None
    if date_match:
        auction_date = datetime.strptime(date_match.group(1), "%d %B %Y").date().isoformat()
    description = section_value(soup, "Property Description")
    images = [urljoin(BASE, image.get("src")) for image in soup.select("div.slider img[src]")]
    legal_node = soup.select_one('a[href*="legaldocuments.eigroup.co.uk"]')
    return {
        "address": clean(address_node.get_text(" ", strip=True)) if address_node else None,
        "headline": clean(headline_node.get_text(" ", strip=True)) if headline_node else None,
        "result_text": clean(result_node.get_text(" ", strip=True)) if result_node else None,
        "auction_id": auction_match.group(1) if auction_match else None,
        "auction_date": auction_date,
        "lot_number": labelled_value(soup, "Lot No"),
        "property_type": labelled_value(soup, "Property Type"),
        "contract_type": labelled_value(soup, "Contract Type"),
        "description": description,
        "occupancy": section_value(soup, "Occupancy"),
        "tenure": section_value(soup, "Tenure"),
        "image_urls": list(dict.fromkeys(filter(None, images))),
        "legal_pack_url": urljoin(BASE, legal_node.get("href")) if legal_node else None,
    }


def fetch(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"response from {url} is unexpectedly short")
    return response.content, response.url


def row_from(card: dict, details: dict | None, evidence: dict) -> dict:
    details = details or {}
    address = details.get("address") or card["address"]
    result_text = details.get("result_text") or card.get("result_text")
    status, sale_price = status_and_price(result_text)
    auction_id = details.get("auction_id")
    auction_date = details.get("auction_date")
    row = corpus.base_row(
        "Knight Frank Auctions",
        f"knight-frank:{auction_id}" if auction_id else "knight-frank:recently-sold-undated",
        auction_date,
        details.get("lot_number"),
        card["source_id"],
        card["detail_url"],
    )
    postcode_match = corpus.PC.search(address)
    description = details.get("description") or details.get("headline")
    images = details.get("image_urls") or ([card["image_url"]] if card.get("image_url") else [])
    row.update(
        appearance_id=f"Knight Frank Auctions|eig-property:{card['source_id']}",
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector=corpus.sector(" ".join(filter(None, [address, details.get("property_type"), description]))),
        property_type=details.get("property_type"),
        sale_price=sale_price,
        status=status,
        description=description,
        image_urls=images,
        tenure=details.get("tenure"),
        occupancy=details.get("occupancy"),
        legal_pack_url=details.get("legal_pack_url"),
        property_id=card["source_id"],
        identity_method="first_party_published_eig_property_id",
        record_quality="address_record",
        source_position=card["source_position"],
        source_result_text=result_text,
        source_contract_type=details.get("contract_type"),
        auction_date_basis="published Auction Information panel" if auction_date else None,
        detail_fetch_status="ok" if details else "failed",
        source_evidence=evidence,
    )
    return row


def harvest(workers: int = 12) -> None:
    archive_raw, archive_resolved = fetch(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    expected = published_total(archive_html)
    cards, duplicates = parse_archive(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/knight-frank" / f"recently-sold-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained recently-sold grid",
        "published_source_rows": expected,
        "distinct_source_identities": len(cards),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})

    appearance_path = corpus.DATA / "appearances/knight-frank/canonical.jsonl.gz"
    state_path = corpus.DATA / "auctions/knight-frank/retained-recently-sold.json"
    cached_state = json.loads(state_path.read_text()) if state_path.exists() else {}
    existing = {row["property_id"]: row for row in corpus.iter_rows(appearance_path)} if appearance_path.exists() else {}
    to_fetch = [card for card in cards if card["source_id"] not in existing or existing[card["source_id"]].get("detail_fetch_status") != "ok"]
    fetched, failures = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, card["detail_url"]): card for card in to_fetch}
        for future in as_completed(futures):
            card = futures[future]
            try:
                raw, resolved = future.result()
                fetched[card["source_id"]] = (raw, resolved)
            except Exception as exc:
                failures.append({"property_id": card["source_id"], "source_url": card["detail_url"], "error": f"{type(exc).__name__}: {exc}"})

    detail_evidence = {}
    fetched_items = sorted(fetched.items())
    for offset in range(0, len(fetched_items), CHUNK_SIZE):
        chunk = fetched_items[offset:offset + CHUNK_SIZE]
        chunk_bytes = b"\n".join(raw for _, (raw, _) in chunk)
        sha = corpus.digest(chunk_bytes)
        snapshot = corpus.DATA / "sources/knight-frank" / f"detail-pages-{offset // CHUNK_SIZE + 1:03d}-{sha[:16]}.json.gz"
        evidence = {
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party property detail pages",
            "members": [source_id for source_id, _ in chunk],
        }
        pages = []
        for source_id, (raw, resolved) in chunk:
            pages.append({"property_id": source_id, "source_url": resolved, "html": raw.decode("utf-8", "replace")})
            detail_evidence[source_id] = {**evidence, "source_url": resolved, "snapshot_member": source_id}
        corpus.save_gzip(snapshot, {"evidence": evidence, "pages": pages})

    observed = []
    for card in cards:
        source_id = card["source_id"]
        if source_id in fetched:
            raw, _ = fetched[source_id]
            details = detail_fields(raw.decode("utf-8", "replace"))
            if details.get("address") and clean(details["address"]).casefold() != clean(card["address"]).casefold():
                raise ValueError(f"detail address conflict for property {source_id}")
            evidence = {"archive": archive_evidence, "detail": detail_evidence[source_id]}
            observed.append(row_from(card, details, evidence))
        elif source_id in existing and existing[source_id].get("detail_fetch_status") == "ok":
            row = existing[source_id]
            current_status, current_price = status_and_price(card.get("result_text"))
            row.update(status=current_status, sale_price=current_price, source_result_text=card.get("result_text"), source_position=card["source_position"])
            observed.append(row)
        else:
            observed.append(row_from(card, None, {"archive": archive_evidence}))

    identities = [row["appearance_id"] for row in observed]
    if len(observed) != len(cards) or len(identities) != len(set(identities)):
        raise ValueError("recently-sold distinct identity reconciliation failed")
    before_ids = {row["appearance_id"] for row in existing.values()}
    total = corpus.write_rows("knight-frank/canonical", observed)
    added = [row for row in observed if row["appearance_id"] not in before_ids]

    saved_detail_evidence = {
        evidence.get("snapshot_path"): evidence
        for evidence in cached_state.get("source_evidence") or []
        if evidence.get("basis") == "first-party property detail pages" and evidence.get("snapshot_path")
    }
    saved_detail_evidence.update({
        evidence["snapshot_path"]: evidence
        for evidence in detail_evidence.values()
        if evidence.get("snapshot_path")
    })
    state = {
        "auctioneer": "Knight Frank Auctions",
        "source_auction_id": "knight-frank:retained-recently-sold",
        "auction_date": None,
        "catalogue_complete": False,
        "source_rows_complete": True,
        "published_source_rows": expected,
        "visible_source_rows": expected,
        "duplicate_source_presentations": len(duplicates),
        "distinct_source_identities": len(cards),
        "lots_captured": len(observed),
        "detail_pages_enriched": sum(row.get("detail_fetch_status") == "ok" for row in observed),
        "source_url": archive_resolved,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "completion_scope": "every retained card in the first-party recently-sold selection; not the original auction catalogues",
        "source_evidence": [archive_evidence, *saved_detail_evidence.values()],
        "errors": failures,
        "checked_at": corpus.now(),
    }
    corpus.save_json(state_path, state)
    dates = [row["auction_date"] for row in observed if row.get("auction_date")]
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive_resolved,
        "published_source_rows": expected,
        "distinct_source_identities": len(cards),
        "duplicate_source_presentations": len(duplicates),
        "appearances_captured": total,
        "detail_pages_enriched": state["detail_pages_enriched"],
        "dated_appearances": len(dates),
        "undated_appearances": len(observed) - len(dates),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(dates), max(dates)] if dates else [None, None],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in observed)),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in observed)),
        "catalogue_completion_claimed": False,
        "completion_scope": state["completion_scope"],
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "knight_frank_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    harvest(workers)
