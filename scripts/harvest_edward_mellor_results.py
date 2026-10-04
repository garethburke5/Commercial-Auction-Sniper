"""Bank Edward Mellor's retained first-party auction result pages.

The archive publishes discrete auction pages with stable property links, lot
numbers and outcomes.  This collector preserves every visible property card,
then enriches it from the retained detail page when the exact property ID and
lot number agree.  Two-day catalogue headings are not treated as a lot's exact
date; an exact date is used only when the detail page publishes it.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://edwardmellor.co.uk"
ARCHIVE = BASE + "/auctions/catalogue-and-results-archive/"
AUCTION_RE = re.compile(r"^/auctions/([^/]+)/?$", re.I)
DETAIL_RE = re.compile(r"^/property-for-sale/(\d+)/?$", re.I)
LOT_RE = re.compile(r"\bLOT\s+(\d+[A-Za-z]?)\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"), 1
)}
_local = __import__("threading").local()
DETAIL_REPAIR_VERSION = 1


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def ordinal_date(day: str, month: str, year: str) -> str:
    return date(int(year), MONTHS[month.lower()], int(day)).isoformat()


def parse_date_span(label: str) -> tuple[str | None, str | None]:
    text = clean(label) or ""
    cross = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*[-–]\s*"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if cross and cross.group(2).lower() in MONTHS and cross.group(4).lower() in MONTHS:
        return (ordinal_date(cross.group(1), cross.group(2), cross.group(5)),
                ordinal_date(cross.group(3), cross.group(4), cross.group(5)))
    same = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?"
        r"\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if same and same.group(3).lower() in MONTHS:
        return (ordinal_date(same.group(1), same.group(3), same.group(4)),
                ordinal_date(same.group(2), same.group(3), same.group(4)))
    single = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if single and single.group(2).lower() in MONTHS:
        value = ordinal_date(single.group(1), single.group(2), single.group(3))
        return value, value
    month_first = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(20\d{2})", text, re.I)
    if month_first and month_first.group(1).lower() in MONTHS:
        value = ordinal_date(month_first.group(2), month_first.group(1), month_first.group(3))
        return value, value
    return None, None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=75)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def discover_auctions(html: str, page_url: str = ARCHIVE, year_min: int = 2021) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    today = date.today().isoformat()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"]).split("#", 1)[0].split("?", 1)[0]
        match = AUCTION_RE.match(urlparse(url).path)
        if not match:
            continue
        slug = match.group(1).lower()
        if slug in {"catalogue-and-results-archive", "calendar"}:
            continue
        label = clean(anchor.get_text(" ", strip=True))
        start, end = parse_date_span(label or "")
        if not end or int(end[:4]) < year_min or end > today:
            continue
        found[slug] = {"slug": slug, "url": url, "label": label,
                       "auction_date_start": start, "auction_date_end": end}
    return sorted(found.values(), key=lambda item: (item["auction_date_end"], item["slug"]), reverse=True)


def status_and_prices(text: str | None) -> tuple[str, int | None, int | None]:
    value = clean(text) or ""
    lower = value.casefold()
    sold = re.search(r"sold\s+at\s+£\s*([\d,]+(?:\.\d+)?)", value, re.I)
    guide = re.search(r"(?:guide price|starting bid)\s*£\s*([\d,]+(?:\.\d+)?)", value, re.I)
    sold_price = int(round(float(sold.group(1).replace(",", "")))) if sold else None
    guide_price = int(round(float(guide.group(1).replace(",", "")))) if guide else None
    if "sold prior" in lower:
        return "sold_prior", sold_price, guide_price
    if "sold post" in lower:
        return "sold_after", sold_price, guide_price
    if re.search(r"\bsold\b", lower):
        return "sold", sold_price, guide_price
    if "withdrawn" in lower:
        return "withdrawn", None, guide_price
    if "available" in lower:
        return "available", None, guide_price
    if "postponed" in lower:
        return "postponed", None, guide_price
    return "unknown", None, guide_price


def card_container(anchor: Tag) -> Tag | None:
    for parent in anchor.parents:
        if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
            continue
        text = clean(parent.get_text(" ", strip=True)) or ""
        lots = LOT_RE.findall(text)
        if len(lots) == 1:
            return parent
    return None


def parse_auction_page(html: str, auction: dict, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        detail_url = urljoin(auction["url"], anchor["href"]).split("?", 1)[0]
        detail_match = DETAIL_RE.match(urlparse(detail_url).path)
        if not detail_match:
            continue
        property_id = detail_match.group(1)
        if property_id in seen:
            continue
        container = card_container(anchor)
        if container is None:
            continue
        card_text = clean(container.get_text(" ", strip=True)) or ""
        lot_match = LOT_RE.search(card_text)
        if not lot_match:
            continue
        lot_number = lot_match.group(1).upper()
        address_text = clean(anchor.get_text(" ", strip=True))
        if not address_text or address_text in {",", "-"}:
            address_text = None
        status, sale_price, guide_price = status_and_prices(card_text)
        row = corpus.base_row(
            "Edward Mellor", f"edward-mellor:{auction['slug']}",
            auction["auction_date_start"] if auction["auction_date_start"] == auction["auction_date_end"] else None,
            lot_number, property_id, detail_url,
        )
        postcode = None
        if address_text and (match := corpus.PC.search(address_text)):
            postcode = match.group().upper()
        row.update(
            address=address_text if postcode else None,
            postcode=postcode, locality=address_text,
            guide_price=guide_price, sale_price=sale_price, status=status,
            sector=corpus.sector(address_text or ""),
            property_id=None, identity_method="source_auction_and_property_id",
            record_quality="address_record" if postcode else "partial_lot",
            source_position=len(rows) + 1, source_card_text=card_text,
            auction_date_start=auction["auction_date_start"],
            auction_date_end=auction["auction_date_end"],
            auction_date_basis=("single-day archive heading" if row["auction_date"] else
                                "two-day archive range; exact lot day not yet exposed"),
            source_evidence=evidence,
        )
        row["appearance_id"] = f"Edward Mellor|auction:{auction['slug']}|property:{property_id}"
        rows.append(row)
        seen.add(property_id)
    if not rows:
        raise ValueError("auction page contains no stable property cards")
    return rows


def detail_address(soup: BeautifulSoup, locality: str | None) -> tuple[str | None, str | None]:
    street = clean((locality or "").split(",", 1)[0])
    street_words = {word.casefold() for word in re.findall(r"[A-Za-z]{4,}", street or "")}
    candidates = []
    for text in soup.stripped_strings:
        value = clean(text)
        if not value or not (postcode_match := corpus.PC.search(value)):
            continue
        score = sum(word in value.casefold() for word in street_words)
        if re.search(r"\b\d+[A-Za-z]?(?:\s*[-–/]\s*\d+[A-Za-z]?)?\b", value):
            score += 2
        candidates.append((score, len(value), value, postcode_match.group().upper()))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    score, _, value, postcode = candidates[0]
    return (value, postcode) if score >= 2 else (None, None)


def parse_detail(html: str, row: dict) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = clean(soup.get_text(" ", strip=True)) or ""
    detail_lots = sorted({value.upper() for value in LOT_RE.findall(text)})
    appearance_matches = not detail_lots or row["lot_number"] in detail_lots
    row["detail_lot_numbers"] = detail_lots
    row["detail_appearance_matches"] = appearance_matches
    exact = re.search(
        r"Appearing\s+At\s+Auction(?:\s+[A-Za-z]+)?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if exact and exact.group(2).lower() in MONTHS and appearance_matches:
        exact_date = ordinal_date(exact.group(1), exact.group(2), exact.group(3))
        if row["auction_date_start"] <= exact_date <= row["auction_date_end"]:
            row["auction_date"] = exact_date
            row["auction_date_basis"] = "exact first-party detail-page auction date"
    address, postcode = detail_address(soup, row.get("locality"))
    if address:
        row["address"], row["postcode"] = address, postcode
        row["record_quality"] = "address_record"
    heading = soup.find("h1")
    if heading:
        row["property_type"] = clean(heading.get_text(" ", strip=True))
    tenure_match = re.search(r"\bTenure\s*:\s*(Freehold|Leasehold|Commonhold)\b", text, re.I)
    if tenure_match:
        row["tenure"] = tenure_match.group(1).title()
    start_bid = re.search(r"£\s*([\d,]+(?:\.\d+)?)\s+Starting Bid", text, re.I)
    if start_bid and not row.get("guide_price"):
        row["guide_price"] = int(round(float(start_bid.group(1).replace(",", ""))))
    images = []
    for image in soup.find_all("img", src=True):
        alt = clean(image.get("alt"))
        if alt and re.search(r"Property at|Floorplan for", alt, re.I):
            url = urljoin(row["original_url"], image["src"])
            if url not in images:
                images.append(url)
    row["image_urls"] = images
    row["sector"] = corpus.sector(" ".join(filter(None, (row.get("property_type"), row.get("address"), row.get("locality")))))
    return row


def harvest(limit: int = 12, workers: int = 8, year_min: int = 2021, refresh: bool = False) -> None:
    final_url, raw = get(ARCHIVE)
    retrieved_at, archive_sha = corpus.now(), corpus.digest(raw)
    archive_snapshot = corpus.DATA / "sources/edward-mellor" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": final_url, "retrieved_at": retrieved_at, "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party catalogue and results archive",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": raw.decode("utf-8", "replace")})
    auctions = discover_auctions(raw.decode("utf-8", "replace"), final_url, year_min)
    if not auctions:
        raise SystemExit("No past Edward Mellor auction pages discovered")

    summary_path = corpus.DATA / "edward_mellor_collection.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    previous_states = previous.get("auctions") if isinstance(previous.get("auctions"), dict) else {}
    selected = auctions if refresh else [
        item for item in auctions
        if item["slug"] not in previous_states
        or previous_states[item["slug"]].get("detail_repair_version", 0) < DETAIL_REPAIR_VERSION
    ]
    if limit > 0:
        selected = selected[:limit]

    states = dict(previous_states)
    existing_path = corpus.DATA / "appearances/edward-mellor/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    before_address = {row["appearance_id"]: bool(row.get("address")) for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    failures = []

    for position, auction in enumerate(selected, 1):
        try:
            resolved, page_raw = get(auction["url"])
            page_sha, captured_at = corpus.digest(page_raw), corpus.now()
            snapshot = corpus.DATA / "sources/edward-mellor" / f"auction-{auction['slug']}-{page_sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved, "retrieved_at": captured_at, "sha256": page_sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party unpaginated auction result page",
            }
            page_html = page_raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
            rows = parse_auction_page(page_html, auction, evidence)

            def enrich(row: dict):
                try:
                    resolved_detail, detail_raw = get(row["original_url"])
                    if not DETAIL_RE.match(urlparse(resolved_detail).path):
                        return row, {"property_id": row["source_lot_id"], "kind": "detail_redirect_removed"}
                    detail_sha, detail_at = corpus.digest(detail_raw), corpus.now()
                    detail_snapshot = corpus.DATA / "sources/edward-mellor/details" / (
                        f"property-{row['source_lot_id']}-{detail_sha[:16]}.json.gz")
                    detail_evidence = {
                        "source_url": resolved_detail, "retrieved_at": detail_at, "sha256": detail_sha,
                        "snapshot_path": str(detail_snapshot.relative_to(corpus.ROOT)),
                        "basis": "first-party retained property detail page",
                    }
                    corpus.save_gzip(detail_snapshot, {
                        "evidence": detail_evidence, "html": detail_raw.decode("utf-8", "replace")})
                    row = parse_detail(detail_raw.decode("utf-8", "replace"), row)
                    row["detail_source_evidence"] = detail_evidence
                    return row, None
                except Exception as exc:
                    return row, {"property_id": row["source_lot_id"],
                                 "kind": "detail", "error": f"{type(exc).__name__}: {exc}"[:500]}

            detail_failures = []
            with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
                jobs = [pool.submit(enrich, row) for row in rows]
                enriched = []
                for future in as_completed(jobs):
                    row, error = future.result()
                    enriched.append(row)
                    if error:
                        detail_failures.append(error)
            enriched.sort(key=lambda row: row["source_position"])
            for row in enriched:
                merged[row["appearance_id"]] = row
            state = {
                "auctioneer": "Edward Mellor",
                "source_auction_id": f"edward-mellor:{auction['slug']}",
                "auction_date": (auction["auction_date_start"] if
                                 auction["auction_date_start"] == auction["auction_date_end"] else None),
                "auction_date_start": auction["auction_date_start"],
                "auction_date_end": auction["auction_date_end"],
                "catalogue_complete": False,
                "source_rows_complete": True,
                "visible_source_rows": len(enriched),
                "lots_captured": len(enriched),
                "address_records": sum(bool(row.get("address")) for row in enriched),
                "partial_lot_records": sum(not row.get("address") for row in enriched),
                "duplicate_lot_numbers": sorted(
                    lot for lot, count in Counter(row["lot_number"] for row in enriched).items()
                    if count > 1
                ),
                "detail_pages_enriched": sum(bool(row.get("detail_source_evidence")) for row in enriched),
                "detail_repair_version": DETAIL_REPAIR_VERSION,
                "source_url": resolved,
                "completion_scope": "every visible card on the first-party unpaginated result page; original offered denominator is not published",
                "errors": [],
                "detail_page_failures": detail_failures,
                "checked_at": corpus.now(),
            }
            corpus.save_json(corpus.DATA / f"auctions/edward-mellor/{auction['slug']}.json", state)
            states[auction["slug"]] = state
            print("EDWARD_MELLOR", position, "/", len(selected), auction["slug"],
                  len(enriched), "lots", flush=True)
        except Exception as exc:
            failures.append({"slug": auction["slug"], "url": auction["url"],
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
        time.sleep(0.2)

    total = corpus.write_rows("edward-mellor/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "archive_auctions_discovered": len(auctions),
        "auction_pages_selected": len(selected),
        "auction_pages_captured_total": len(states),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_upgraded_address_records": sum(
            key in before_address and not before_address[key] and bool(row.get("address"))
            for key, row in merged.items()
        ),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
        "catalogue_scope_warning": "visible result pages publish no original offered denominator",
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--year-min", type=int, default=2021)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    harvest(args.limit, args.workers, args.year_min, args.refresh)
