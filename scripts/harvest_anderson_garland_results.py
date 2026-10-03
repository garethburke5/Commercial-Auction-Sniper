"""Bank Anderson & Garland's retained first-party recent auction results.

The source is one curated results page rather than a dated catalogue.  Every
published sold-property block is retained, but catalogue completeness is never
claimed and auction_date remains null because the page publishes no sale day.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE_URL = "https://aglandandproperty.com/auction-results"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
SOLD_RE = re.compile(r"sold\s*at\s*aucti\s*on\s*for\s*£\s*([\d,]+(?:\.\d+)?)", re.I)
GUIDE_RE = re.compile(r"(?:guide|estimate)\s*£\s*([\d,]+(?:\.\d+)?)", re.I)
LISTING_RE = re.compile(r"/listings/(\d+)/", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,.\xa0")
    return value or None


def pounds(value: str) -> int:
    return int(round(float(value.replace(",", ""))))


def fallback_id(address: str) -> str:
    normalized = re.sub(r"\W+", " ", address.casefold()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:20]


def previous_text(paragraphs: list[Tag], index: int, count: int = 2) -> list[tuple[int, str]]:
    found = []
    for position in range(index - 1, -1, -1):
        text = clean(paragraphs[position].get_text(" ", strip=True))
        if not text or SOLD_RE.search(text):
            continue
        found.append((position, text))
        if len(found) == count:
            break
    return found


def image_before(paragraphs: list[Tag], result_index: int, prior_result_index: int) -> str | None:
    for position in range(result_index - 1, prior_result_index, -1):
        image = paragraphs[position].find("img", src=True)
        if image:
            return urljoin(SOURCE_URL, image["src"])
    return None


def parse_results(html: str, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one("#about-content")
    if body is None:
        raise ValueError("recent-results content container is absent")
    heading = clean(body.get_text(" ", strip=True)) or ""
    if "Selling Success at Auction" not in heading:
        raise ValueError("first-party auction-results heading is absent")

    paragraphs = body.find_all("p")
    result_indexes = [index for index, node in enumerate(paragraphs)
                      if SOLD_RE.search(clean(node.get_text(" ", strip=True)) or "")]
    if not result_indexes:
        raise ValueError("no sold result blocks found")

    rows = []
    prior_result = -1
    for source_position, result_index in enumerate(result_indexes, 1):
        result_text = clean(paragraphs[result_index].get_text(" ", strip=True)) or ""
        previous = previous_text(paragraphs, result_index)
        if len(previous) != 2:
            raise ValueError(f"result {source_position} has no address/description pair")
        description = previous[0][1]
        address = previous[1][1]
        image_url = image_before(paragraphs, result_index, prior_result)
        prior_result = result_index

        sale_match = SOLD_RE.search(result_text)
        guide_match = GUIDE_RE.search(result_text)
        if not sale_match:
            raise ValueError(f"result {source_position} has no sale price")
        listing_match = LISTING_RE.search(image_url or "")
        source_id = f"rex:{listing_match.group(1)}" if listing_match else f"heading:{fallback_id(address)}"
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row(
            "Anderson & Garland", "anderson-garland:recent-auction-results",
            None, None, source_id, SOURCE_URL,
        )
        row.update(
            appearance_id=f"Anderson & Garland|recent-auction-results|{source_id}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(f"{address} {description}"),
            guide_price=pounds(guide_match.group(1)) if guide_match else None,
            sale_price=pounds(sale_match.group(1)),
            status="sold",
            description=description,
            property_id=listing_match.group(1) if listing_match else None,
            identity_method="first_party_rex_listing_id" if listing_match else "exact_source_heading_hash",
            record_quality="address_record",
            auction_date_basis="source publishes no auction date; date deliberately remains null",
            source_position=source_position,
            source_result_text=result_text,
            image_urls=[image_url] if image_url else [],
            source_evidence=evidence,
        )
        rows.append(row)

    identities = [row["source_lot_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate source identities on recent-results page")
    return rows


def harvest() -> None:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=75)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    retrieved_at, sha = corpus.now(), corpus.digest(raw)
    snapshot = corpus.DATA / "sources/anderson-garland" / f"recent-auction-results-{sha[:16]}.json.gz"
    evidence = {
        "source_url": response.url,
        "retrieved_at": retrieved_at,
        "sha256": sha,
        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained recent auction results page",
    }
    html = raw.decode("utf-8", "replace")
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
    rows = parse_results(html, evidence)

    path = corpus.DATA / "appearances/anderson-garland/recent-results.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    existing_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("anderson-garland/recent-results", list(merged.values()))
    added = [row for key, row in merged.items() if key not in existing_ids]

    state = {
        "auctioneer": "Anderson & Garland",
        "source_auction_id": "anderson-garland:recent-auction-results",
        "auction_date": None,
        "catalogue_complete": False,
        "result_page_rows_complete": True,
        "published_selected_results": len(rows),
        "lots_captured": len(rows),
        "source_url": response.url,
        "completion_scope": "every sold-property block on the first-party recent-results page; not a dated full catalogue",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions/anderson-garland/recent-results.json", state)
    summary = {
        "checked_at": corpus.now(),
        "source_url": response.url,
        "selected_result_appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "catalogue_scope_warning": "source is a recent selected-results page, not a complete dated auction catalogue",
        "result_page": state,
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "anderson_garland_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    harvest()
