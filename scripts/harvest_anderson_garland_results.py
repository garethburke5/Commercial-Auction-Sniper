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
LISTINGS_URL = "https://aglandandproperty.com/listings"
LISTING_PATH_RE = re.compile(r"/listings/[^?#\"']*RX(\d+)[^?#\"']*", re.I)
RESULT_COUNT_RE = re.compile(r"Found\s+(\d[\d,]*)\s+results", re.I)
DETAIL_SOLD_RE = re.compile(r"SOLD\s+AT\s+AUCTION\s+FOR\s*£\s*([\d,]+(?:\.\d+)?)", re.I)
EXACT_AUCTION_DATE_RE = re.compile(
    r"FOR\s+SALE\s+BY\s+AUCTION\s*[-–]\s*"
    r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:on\s+)?)?"
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})",
    re.I,
)


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


def parse_listings_index(html: str, source_url: str) -> tuple[int, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    count_match = RESULT_COUNT_RE.search(text)
    if not count_match:
        raise ValueError("listing result count is absent")
    expected = int(count_match.group(1).replace(",", ""))
    urls = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, anchor["href"])
        if LISTING_PATH_RE.search(href) and href not in urls:
            urls.append(href.split("?", 1)[0])
    return expected, urls


def exact_auction_date(text: str) -> str | None:
    match = EXACT_AUCTION_DATE_RE.search(text)
    if not match:
        return None
    value = f"{match.group(1)} {match.group(2)} {match.group(3)}"
    try:
        return __import__("datetime").datetime.strptime(value, "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def parse_listing_detail(html: str, url: str, evidence: dict) -> dict | None:
    """Admit only an exact dated, source-marked sold auction appearance."""
    soup = BeautifulSoup(html, "lxml")
    text = clean(soup.get_text(" ", strip=True)) or ""
    sold_match = DETAIL_SOLD_RE.search(text)
    auction_date = exact_auction_date(text)
    id_match = re.search(r"RX(\d+)", url, re.I)
    if not sold_match or not auction_date or not id_match:
        return None
    source_id = id_match.group(1)
    heading = clean(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else None
    if not heading:
        raise ValueError(f"auction listing {source_id} has no address heading")
    postcode_match = corpus.PC.search(heading)
    guide_match = GUIDE_RE.search(text)
    description = next((
        clean(node.get_text(" ", strip=True))
        for node in soup.find_all(["p", "div"])
        if re.search(r"FOR\s+SALE\s+BY\s+AUCTION", node.get_text(" ", strip=True), re.I)
    ), None)
    tenure_match = re.search(r"\b(Freehold|Leasehold|Virtual Freehold)\b", text, re.I)
    images = []
    for image in soup.find_all("img", src=True):
        src = urljoin(url, image["src"])
        if src not in images and not re.search(r"logo|icon|avatar", src, re.I):
            images.append(src)
    row = corpus.base_row(
        "Anderson & Garland", f"anderson-garland:{auction_date}",
        auction_date, None, f"rex:{source_id}", url,
    )
    row.update(
        appearance_id=f"Anderson & Garland|listing:{source_id}",
        address=heading, postcode=postcode_match.group().upper() if postcode_match else None,
        locality=heading, sector=corpus.sector(f"{heading} {description or ''}"),
        guide_price=pounds(guide_match.group(1)) if guide_match else None,
        sale_price=pounds(sold_match.group(1)), status="sold",
        description=(description[:4000] if description else None),
        tenure=tenure_match.group(1).title() if tenure_match else None,
        property_id=source_id, identity_method="first_party_rex_listing_id",
        record_quality="address_record", image_urls=images[:20],
        auction_date_basis="exact date published on retained first-party listing detail",
        source_result_text=sold_match.group(0), source_evidence=evidence,
    )
    return row


def discover_retained_listings() -> tuple[list[str], list[dict]]:
    """Reconcile every page of the finite first-party property-search result set."""
    expected = None
    urls, evidence = [], []
    for page in range(1, 20):
        page_url = LISTINGS_URL + f"?page={page}"
        response = requests.get(page_url, headers=HEADERS, timeout=75)
        response.raise_for_status()
        raw = response.content
        page_expected, page_urls = parse_listings_index(raw.decode("utf-8", "replace"), response.url)
        if expected is None:
            expected = page_expected
        elif page_expected != expected:
            raise ValueError("listing result count changed during pagination")
        sha = corpus.digest(raw)
        snapshot = corpus.DATA / "sources/anderson-garland/listing-index" / f"page-{page}-{sha[:16]}.json.gz"
        item = {
            "source_url": response.url, "retrieved_at": corpus.now(), "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party paginated property-search index",
        }
        corpus.save_gzip(snapshot, {"evidence": item, "html": raw.decode("utf-8", "replace")})
        evidence.append(item)
        new_urls = [url for url in page_urls if url not in urls]
        urls.extend(new_urls)
        if expected is not None and len(urls) >= expected:
            break
        if not new_urls:
            break
    if expected is None or len(urls) != expected:
        raise ValueError(f"listing pagination reconciled {len(urls)} of {expected}")
    return urls, evidence


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

    listing_urls, listing_index_evidence = discover_retained_listings()
    detail_rows, detail_failures, detail_audit = [], [], []
    for url in listing_urls:
        try:
            detail_response = requests.get(url, headers=HEADERS, timeout=75)
            detail_response.raise_for_status()
            detail_raw = detail_response.content
            detail_sha = corpus.digest(detail_raw)
            id_match = re.search(r"RX(\d+)", url, re.I)
            detail_snapshot = corpus.DATA / "sources/anderson-garland/listings" / (
                f"{id_match.group(1) if id_match else 'unknown'}-{detail_sha[:16]}.json.gz"
            )
            detail_evidence = {
                "source_url": detail_response.url, "retrieved_at": corpus.now(),
                "sha256": detail_sha,
                "snapshot_path": str(detail_snapshot.relative_to(corpus.ROOT)),
                "listing_index_snapshots": [item["snapshot_path"] for item in listing_index_evidence],
                "basis": "retained first-party listing detail enumerated by reconciled property-search pagination",
            }
            detail_html = detail_raw.decode("utf-8", "replace")
            detail_row = parse_listing_detail(detail_html, detail_response.url, detail_evidence)
            detail_audit.append({
                "source_url": detail_response.url, "sha256": detail_sha,
                "admitted": bool(detail_row),
            })
            if detail_row:
                corpus.save_gzip(detail_snapshot, {"evidence": detail_evidence, "html": detail_html})
                detail_rows.append(detail_row)
        except Exception as exc:
            detail_failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    path = corpus.DATA / "appearances/anderson-garland/recent-results.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    existing_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in rows:
        merged[row["appearance_id"]] = row
    by_property_id = {
        str(row["property_id"]): key for key, row in merged.items() if row.get("property_id")
    }
    enriched = 0
    for detail_row in detail_rows:
        prior_key = by_property_id.get(str(detail_row["property_id"]))
        if prior_key:
            prior = merged[prior_key]
            combined = {**prior, **detail_row}
            combined["appearance_id"] = prior_key
            combined["source_evidence"] = {
                "listing_detail": detail_row["source_evidence"],
                "selected_results": prior.get("source_evidence"),
            }
            if not prior.get("auction_date") and combined.get("auction_date"):
                enriched += 1
            merged[prior_key] = combined
        else:
            merged[detail_row["appearance_id"]] = detail_row
            by_property_id[str(detail_row["property_id"])] = detail_row["appearance_id"]
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
        "retained_listing_urls_reconciled": len(listing_urls),
        "dated_sold_auction_details_admitted": len(detail_rows),
        "existing_appearances_exact_date_enriched": enriched,
        "detail_audit": detail_audit,
        "catalogue_scope_warning": "source is a recent selected-results page plus exact dated sold-auction details from the reconciled retained listing index; original catalogue denominators remain unavailable",
        "result_page": state,
        "failures": detail_failures,
    }
    corpus.save_json(corpus.DATA / "anderson_garland_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if detail_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
