"""Bank Smith & Sons' retained first-party property-auction result pages.

The past-auctions page publishes an explicit property denominator for each
retained sale. Each linked result page is unpaginated and exposes one card per
lot, so completeness requires exact card, lot and denominator reconciliation.
"""
from __future__ import annotations

from collections import Counter
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


BASE = "https://www.smithandsons.net"
ARCHIVE_URL = BASE + "/pages/services/auctions/past-auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})", re.I)
COUNT_RE = re.compile(r"This auction had\s+(\d[\d,]*)\s+properties", re.I)
RESULT_COUNT_RE = re.compile(r"Results:\s*(\d[\d,]*)\s+Properties", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,.\xa0")
    return value or None


def pounds(value: str) -> int:
    return int(round(float(value.replace(",", ""))))


def parse_date(value: str) -> str:
    match = DATE_RE.search(value)
    if not match:
        raise ValueError(f"auction date is absent: {value!r}")
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def parse_archive(html: str, source_url: str = ARCHIVE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    if not heading or clean(heading.get_text(" ", strip=True)) != "Past Auctions":
        raise ValueError("past-auctions heading is absent")
    rows = []
    for item in soup.select(".auctions-list-past .auction-list-item"):
        link = item.select_one(".auction-list-date a[href]")
        count_match = COUNT_RE.search(item.get_text(" ", strip=True))
        if not link or not count_match:
            raise ValueError("retained auction lacks a result link or denominator")
        url = urljoin(source_url, link["href"])
        auction_id = urlparse(url).path.rstrip("/").split("/")[-1]
        if not auction_id.isdigit():
            raise ValueError(f"invalid auction identity: {auction_id!r}")
        rows.append({
            "auction_id": auction_id,
            "auction_date": parse_date(link.get_text(" ", strip=True)),
            "published_lots": int(count_match.group(1).replace(",", "")),
            "source_url": url,
        })
    if not rows:
        raise ValueError("past-auctions page contains no retained auctions")
    if len({row["auction_id"] for row in rows}) != len(rows):
        raise ValueError("past-auctions page contains duplicate auction identities")
    return rows


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    if "sold prior" in lower:
        status = "sold_prior"
    elif "sold after" in lower:
        status = "sold_after"
    elif lower.startswith("sold"):
        status = "sold"
    elif "withdrawn" in lower:
        status = "withdrawn"
    elif "postponed" in lower:
        status = "postponed"
    elif "available" in lower:
        status = "available"
    elif "unsold" in lower:
        status = "unsold"
    else:
        status = "unknown"
    prices = MONEY_RE.findall(text)
    sold = {"sold", "sold_prior", "sold_after"}
    return status, pounds(prices[-1]) if prices and status in sold else None


def parse_catalogue(html: str, auction: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    if not heading or parse_date(heading.get_text(" ", strip=True)) != auction["auction_date"]:
        raise ValueError("catalogue heading does not match archive date")
    count_match = RESULT_COUNT_RE.search(soup.get_text(" ", strip=True))
    if not count_match:
        raise ValueError("catalogue result denominator is absent")
    page_count = int(count_match.group(1).replace(",", ""))
    if page_count != auction["published_lots"]:
        raise ValueError("archive and catalogue denominators disagree")

    rows = []
    for position, card in enumerate(soup.select("article.property-item"), 1):
        lot_node = card.select_one(".lot-number-number")
        lot = clean(lot_node.get_text(" ", strip=True)) if lot_node else None
        address_link = card.select_one(".property-address-list a[href]")
        address = clean(address_link.get_text(" ", strip=True)) if address_link else None
        detail_url = urljoin(auction["source_url"], address_link["href"]) if address_link else None
        if not lot or not address or not detail_url:
            raise ValueError(f"catalogue card {position} lacks lot identity or address")
        source_id = urlparse(detail_url).path.rstrip("/").split("/")[-1]
        if not source_id:
            raise ValueError(f"catalogue card {position} lacks a stable detail slug")
        guide_text = clean(card.find("h2").get_text(" ", strip=True)) if card.find("h2") else None
        guide_values = MONEY_RE.findall(guide_text or "")
        status_node = card.select_one(".property-status")
        status_text = clean(status_node.get_text(" ", strip=True)) if status_node else None
        status, sale_price = status_and_price(status_text)
        type_node = card.select_one(".property-item-type")
        property_type = clean(type_node.get_text(" ", strip=True)) if type_node else None
        excluded = {"property-item-type", "property-address-list", "property-status", "more-details-btn"}
        description = next((clean(node.get_text(" ", strip=True)) for node in card.find_all("p")
                            if not set(node.get("class") or []) & excluded), None)
        image = card.select_one(".property-item-image img[src]")
        image_url = urljoin(auction["source_url"], image["src"]) if image else None
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row(
            "Smith & Sons", f"smith-sons:{auction['auction_id']}", auction["auction_date"],
            lot, source_id, detail_url,
        )
        row.update(
            appearance_id=f"Smith & Sons|auction:{auction['auction_id']}|lot:{lot}|property:{source_id}",
            address=address, postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address, sector=corpus.sector(" ".join(filter(None, [address, property_type, description]))),
            property_type=property_type,
            guide_price=pounds(guide_values[0]) if guide_values else None,
            guide_price_high=pounds(guide_values[1]) if len(guide_values) > 1 else None,
            sale_price=sale_price, status=status, description=description,
            image_urls=[image_url] if image_url else [], property_id=None,
            identity_method="source_auction_lot_and_detail_slug", record_quality="address_record",
            source_position=position, source_status_text=status_text,
            auction_date_basis="exact date on first-party retained auction result page",
            source_evidence=evidence,
        )
        rows.append(row)

    if len(rows) != auction["published_lots"]:
        raise ValueError(f"catalogue reconciled {len(rows)} of {auction['published_lots']} published lots")
    if len({row["lot_number"] for row in rows}) != len(rows):
        raise ValueError("catalogue contains duplicate lot numbers")
    if len({row["appearance_id"] for row in rows}) != len(rows):
        raise ValueError("catalogue contains duplicate appearance identities")
    state = {
        "auctioneer": "Smith & Sons", "source_auction_id": f"smith-sons:{auction['auction_id']}",
        "auction_date": auction["auction_date"], "catalogue_complete": True,
        "source_rows_complete": True, "published_lots_offered": auction["published_lots"],
        "visible_source_rows": len(rows), "lots_captured": len(rows),
        "source_url": auction["source_url"], "pagination_reconciled": True,
        "denominator_reconciled": True,
        "denominator_basis": "explicit property count on archive and retained unpaginated result page",
        "completion_scope": "every property card on the first-party retained result page",
        "source_evidence": evidence, "errors": [], "checked_at": corpus.now(),
    }
    return rows, state


def fetch(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response.content, response.url


def harvest() -> None:
    archive_raw, archive_resolved = fetch(ARCHIVE_URL)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/smith-sons" / f"past-auctions-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved, "retrieved_at": corpus.now(), "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party past-auctions index with explicit property denominators",
    }
    archive_html = archive_raw.decode("utf-8", "replace")
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    auctions = parse_archive(archive_html, archive_resolved)

    appearance_path = corpus.DATA / "appearances/smith-sons/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    states, failures = {}, []
    for auction in auctions:
        try:
            raw, resolved = fetch(auction["source_url"])
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/smith-sons" / f"auction-{auction['auction_id']}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved, "retrieved_at": corpus.now(), "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": "first-party unpaginated auction result page",
            }
            html = raw.decode("utf-8", "replace")
            rows, state = parse_catalogue(html, auction, evidence)
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            corpus.save_json(corpus.DATA / "auctions/smith-sons" / f"auction-{auction['auction_id']}.json", state)
            states[auction["auction_id"]] = state
            merged.update({row["appearance_id"]: row for row in rows})
        except Exception as exc:
            failures.append({"auction_id": auction["auction_id"], "source_url": auction["source_url"],
                             "error": f"{type(exc).__name__}: {exc}"[:500]})

    total = corpus.write_rows("smith-sons/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": archive_resolved,
        "catalogues_discovered": len(auctions), "catalogues_captured": len(states),
        "catalogues_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "smith_sons_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
