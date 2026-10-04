"""Bank every retained Brown&Co property-auction result card.

The first-party results page exposes a rolling set of address-bearing cards
whose links contain stable EIG lot IDs.  It does not publish a total archive or
original catalogue denominators, so this collector preserves every visible
card and never marks an auction complete.  Earlier saved appearances are
merged back in when the rolling page changes.
"""
from __future__ import annotations

from collections import Counter
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


SOURCE_URL = "https://www.brown-co.com/auctions/property-land/results"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
LOT_ID_RE = re.compile(r"brownandco\.eigonlineauctions\.com/lot/details/(\d+)", re.I)
DATE_RANGE_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def iso_date(value: str) -> str:
    value = re.sub(r"\bSept\b", "Sep", value, flags=re.I)
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid published auction date: {value!r}")


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def parse_status(meta: str | None, price_text: str | None) -> tuple[str, int | None]:
    text = clean(" ".join(part for part in (meta, price_text) if part)) or ""
    lower = text.casefold()
    if "withdrawn" in lower:
        return "withdrawn", None
    if "unsold" in lower:
        return "unsold", None
    if "sold" in lower:
        return "sold", pounds(text)
    return "unknown", None


def parse_results(html: str, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select('a.card--property-auction[href*="brownandco.eigonlineauctions.com/lot/details/"]')
    if not cards:
        raise ValueError("no Brown&Co auction-result cards found")
    rows = []
    for source_position, card in enumerate(cards, 1):
        href = urljoin(SOURCE_URL, card.get("href") or "")
        id_match = LOT_ID_RE.search(href)
        date_text = clean((card.select_one(".cp-loc") or card).get_text(" ", strip=True))
        date_match = DATE_RANGE_RE.search(date_text or "")
        address_node = card.select_one(".cp-long-address")
        lot_node = card.select_one(".ad-day")
        if not id_match or not date_match or address_node is None or lot_node is None:
            raise ValueError(f"result card {source_position} lacks identity, dates, lot or address")
        source_id = id_match.group(1)
        start_date, end_date = iso_date(date_match.group(1)), iso_date(date_match.group(2))
        address = clean(address_node.get_text(" ", strip=True))
        lot_number = clean(lot_node.get_text(" ", strip=True))
        if not address or lot_number is None:
            raise ValueError(f"result card {source_position} has an empty address or lot number")
        meta = clean(card.select_one(".cp-price-meta").get_text(" ", strip=True)) if card.select_one(".cp-price-meta") else None
        price_text = clean(card.select_one(".cp-price").get_text(" ", strip=True)) if card.select_one(".cp-price") else None
        status, sale_price = parse_status(meta, price_text)
        postcode_match = corpus.PC.search(address)
        image = card.find("img")
        image_url = urljoin(SOURCE_URL, image.get("src") or image.get("data-src")) if image else None
        row = corpus.base_row(
            "Brown&Co", f"brown-co:{end_date}", end_date, lot_number, source_id, href,
        )
        row.update(
            appearance_id=f"Brown&Co|eig-lot:{source_id}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address),
            status=status,
            sale_price=sale_price,
            image_urls=[image_url] if image_url else [],
            property_id=source_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record",
            auction_start_date=start_date,
            auction_end_date=end_date,
            auction_date_basis="published auction end date; exact source date range retained",
            source_position=source_position,
            source_result_text=clean(" ".join(part for part in (meta, price_text) if part)),
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["source_lot_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate EIG lot IDs on Brown&Co results page")
    return rows


def harvest() -> None:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=75)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("Brown&Co results response is unexpectedly short")
    sha = corpus.digest(raw)
    snapshot = corpus.DATA / "sources/brown-co" / f"results-{sha[:16]}.json.gz"
    evidence = {
        "source_url": response.url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained property-auction result cards",
    }
    html = raw.decode("utf-8", "replace")
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
    observed = parse_results(html, evidence)

    path = corpus.DATA / "appearances/brown-co/results.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in observed})
    total = corpus.write_rows("brown-co/results", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    state = {
        "auctioneer": "Brown&Co",
        "source_auction_id": "brown-co:rolling-results-page",
        "auction_date": None,
        "catalogue_complete": False,
        "lots_captured": len(observed),
        "source_url": response.url,
        "completion_scope": "every currently visible first-party result card; rolling page has no archive denominator",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions/brown-co/rolling-results.json", state)
    summary = {
        "checked_at": corpus.now(),
        "source_url": response.url,
        "visible_result_cards_captured": len(observed),
        "banked_appearances": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "catalogue_completion_claimed": False,
        "completion_scope": state["completion_scope"],
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "brown_co_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    harvest()
