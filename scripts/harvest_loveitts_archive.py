"""Bank Loveitts' retained first-party property-auction archive.

The Loveitts index publishes dated event links from 2022 onward.  Each linked
event page exposes one card per retained property, and the property page can
add an exact event date, guide, achieved result, rent and description.  This
collector snapshots every level, refuses incomplete event-page parses, and
excludes exact date/address appearances already banked from a shared platform.

Completeness is deliberately limited to the cards still visible in each
linked first-party event page.  The five index rows without a property link,
and any properties removed from old pages, are not represented as zero-lot
events or claimed as recovered.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Loveitts"
SLUG = "loveitts"
BASE = "https://www.loveitts.co.uk"
ARCHIVE_URL = f"{BASE}/auctions/past-auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
EVENT_RE = re.compile(r"/auctions/past-auctions/(\d+)(?:[/?#]|$)", re.I)
GUIDE_RE = re.compile(
    r"Guide Price:\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:-\s*£?\s*([\d,]+(?:\.\d+)?))?",
    re.I,
)
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*"
    r"(per\s+annum|annually|p\.?\s*a\.?|per\s+calendar\s+month|"
    r"per\s+month|monthly|p\.?\s*c\.?\s*m\.?)\b",
    re.I,
)
PARSER_VERSION = 1


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def exact_date(value: str | None) -> str | None:
    value = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", clean(value) or "", flags=re.I)
    for pattern in ("%A %d %b %Y", "%A %d %B %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def amount(value: str | None) -> int | None:
    parsed = corpus.money(value)
    return int(parsed) if parsed else None


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = clean(value) or ""
    folded = text.casefold()
    if "sold prior" in folded:
        status = "sold_prior"
    elif "sold after" in folded or "sold post" in folded:
        status = "sold_after"
    elif re.search(r"\bsold\b", folded):
        status = "sold"
    elif "withdrawn" in folded:
        status = "withdrawn"
    elif "postponed" in folded:
        status = "postponed"
    elif "unsold" in folded or "available" in folded:
        status = "unsold"
    else:
        status = "unknown"
    price_match = re.search(
        r"(?:sold(?:\s+(?:at auction|prior(?:\s+to\s+auction)?|"
        r"(?:after|post)(?:\s+auction)?))?(?:\s+for)?|"
        r"sale agreed(?:\s+(?:prior|after|post))?(?:\s+for)?)\s*[-:]?\s*£\s*([\d,]+(?:\.\d+)?)",
        text,
        re.I,
    )
    price = amount(price_match.group(1)) if price_match and status.startswith("sold") else None
    return status, price


def annual_rent(text: str | None) -> tuple[int | None, str | None]:
    match = RENT_RE.search(text or "")
    if not match:
        return None, None
    value = amount(match.group(1))
    if value and re.search(r"month|p\.?\s*c\.?\s*m", match.group(2), re.I):
        value *= 12
    return value, clean(match.group(0))


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 800:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def snapshot(raw: bytes, resolved: str, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def parse_archive(html: str, base_url: str = ARCHIVE_URL) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    events, unlinked = [], []
    for position, item in enumerate(soup.select(".auctions__item"), 1):
        date_node = item.select_one(".auctions__item__date--secondary")
        published_date = clean(date_node.get_text(" ", strip=True)) if date_node else None
        auction_date = exact_date(published_date)
        link = item.select_one('a[href*="/auctions/past-auctions/"]')
        identity = EVENT_RE.search(link.get("href") or "") if link else None
        if not auction_date:
            raise ValueError(f"archive row {position} has no exact date: {published_date!r}")
        if not identity:
            unlinked.append({
                "source_position": position,
                "published_date": published_date,
                "auction_date": auction_date,
                "reason": "first-party index row has no retained property-page link",
            })
            continue
        event_id = identity.group(1)
        events.append({
            "event_id": event_id,
            "auction_date": auction_date,
            "published_date": published_date,
            "event_url": urljoin(base_url, link.get("href") or ""),
            "source_position": position,
        })
    identities = [event["event_id"] for event in events]
    if not events or len(identities) != len(set(identities)):
        raise ValueError("Loveitts archive has no linked events or duplicate event identities")
    return events, unlinked


def parse_event(html: str, event: dict, evidence: dict) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(["h2", "h3"], string=lambda value: exact_date(value) is not None)
    heading_date = exact_date(heading.get_text(" ", strip=True)) if heading else None
    if heading_date != event["auction_date"]:
        raise ValueError(
            f"event {event['event_id']} heading date {heading_date!r} does not match index {event['auction_date']}"
        )
    rows, malformed = [], []
    for position, card in enumerate(soup.select(".property--sml"), 1):
        link = card.select_one("a.property--sml__content[href]")
        title = card.select_one(".property--sml__ttl")
        if not link or not title:
            malformed.append({"position": position, "reason": "missing property link or address title"})
            continue
        original_url = urljoin(event["event_url"], link.get("href") or "")
        path = urlsplit(original_url).path.strip("/")
        if not path.startswith("auctions/") or path == "auctions/past-auctions":
            malformed.append({"position": position, "url": original_url, "reason": "invalid property URL"})
            continue
        source_lot_id = path.removeprefix("auctions/")
        address = clean(title.get_text(" ", strip=True))
        subtitle = card.select_one(".property--sml__subttl")
        property_type = clean(subtitle.get_text(" ", strip=True)) if subtitle else None
        price_node = card.select_one(".property--sml__price")
        guide_text = clean(price_node.get_text(" ", strip=True)) if price_node else None
        status_node = card.select_one(".property--sml__status")
        status_text = clean(status_node.get_text(" ", strip=True)) if status_node else None
        card_text = clean(card.get_text(" ", strip=True))
        status, sale_price = status_and_price(status_text or card_text)
        guide_match = GUIDE_RE.search(guide_text or card_text or "")
        guide = amount(guide_match.group(1)) if guide_match else None
        guide_high = amount(guide_match.group(2)) if guide_match and guide_match.group(2) else None
        postcode = corpus.PC.search(address or "")
        image = card.select_one(".property--sml__img__link__img")
        image_match = re.search(r"url\(['\"]?([^'\")]+)", image.get("style") or "", re.I) if image else None
        auction_id = f"{SLUG}:{event['event_id']}"
        row = corpus.base_row(SOURCE, auction_id, event["auction_date"], None, source_lot_id, original_url)
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, property_type]))),
            property_type=property_type,
            guide_price=guide,
            guide_price_high=guide_high,
            sale_price=sale_price,
            status=status,
            description=property_type,
            image_urls=[urljoin(event["event_url"], image_match.group(1))] if image_match else [],
            property_id=source_lot_id,
            identity_method="first_party_event_id_and_property_path",
            record_quality="address_record",
            source_position=position,
            source_status_text=status_text,
            guide_price_text=guide_text,
            source_platform="Loveitts retained property archive",
            operator_legal_name="Loveitts Limited",
            operator_company_number="07558151",
            source_evidence=evidence,
        )
        rows.append(row)
    if not rows:
        raise ValueError(f"event {event['event_id']} exposes no property cards")
    return rows, malformed


def detail_date(text: str | None) -> str | None:
    match = re.search(
        r"\bAuction\s+((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})\b",
        text or "",
        re.I,
    )
    return exact_date(match.group(1)) if match else None


def enrich_detail(html: str, row: dict, evidence: dict) -> tuple[dict, str | None]:
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup.select_one("[role=main]") or soup.body or soup
    text = clean(main.get_text(" ", strip=True)) or ""
    heading = soup.find("h1")
    address = clean(heading.get_text(" ", strip=True)) if heading else None
    if address and normalized_address(address) != normalized_address(row.get("address")):
        row_pc = corpus.PC.search(row.get("address") or "")
        detail_pc = corpus.PC.search(address)
        if not (row_pc and detail_pc and row_pc.group().casefold() == detail_pc.group().casefold()):
            raise ValueError("detail address does not reconcile to event card")
    observed_date = detail_date(text)
    if observed_date != row["auction_date"]:
        return row, observed_date
    guide_match = GUIDE_RE.search(text)
    status, sale_price = status_and_price(text)
    rent, rent_text = annual_rent(text)
    description_match = re.search(r"\bDESCRIPTION\b\s*(.*?)(?:\bKEY FACTS\b|$)", text, re.I)
    description = clean(description_match.group(1)) if description_match else row.get("description")
    tenure_match = re.search(r"\bTENURE\b\s*([^.;]{3,180}[.;]?)", text, re.I)
    row.update(
        guide_price=amount(guide_match.group(1)) if guide_match else row.get("guide_price"),
        guide_price_high=(
            amount(guide_match.group(2)) if guide_match and guide_match.group(2)
            else row.get("guide_price_high")
        ),
        sale_price=sale_price or row.get("sale_price"),
        status=status if status != "unknown" else row.get("status"),
        description=description,
        sector=corpus.sector(" ".join(filter(None, [row.get("address"), row.get("property_type"), description]))),
        tenure=clean(tenure_match.group(1)) if tenure_match else row.get("tenure"),
        annual_rent=rent,
        rent_text=rent_text,
        detail_source_evidence=evidence,
        detail_auction_date=observed_date,
    )
    return row, observed_date


def global_exact_appearances(exclude_slug: str) -> dict[tuple[str, str], list[dict]]:
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                key = (row["auction_date"], normalized_address(row["address"]))
                values[key].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                    "original_url": row.get("original_url"),
                })
    return values


def harvest(workers: int = 16) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_evidence = snapshot(
        archive_raw, archive_resolved, "past-auctions",
        "first-party dated Loveitts event index",
    )
    events, unlinked = parse_archive(archive_raw.decode("utf-8", "replace"), archive_resolved)

    fetched_events, failures = {}, []
    with ThreadPoolExecutor(max_workers=min(workers, len(events))) as pool:
        futures = {pool.submit(get, event["event_url"]): event for event in events}
        for future in as_completed(futures):
            event = futures[future]
            try:
                fetched_events[event["event_id"]] = future.result()
            except Exception as exc:
                failures.append({"event_id": event["event_id"], "url": event["event_url"], "error": str(exc)})
    if failures:
        raise RuntimeError(f"event pages failed before admission: {failures}")

    rows, event_summaries = [], []
    for event in events:
        raw, resolved = fetched_events[event["event_id"]]
        evidence = snapshot(
            raw, resolved, f"event-{event['event_id']}",
            "first-party retained event property-card inventory",
            event_id=event["event_id"], auction_date=event["auction_date"],
        )
        event_rows, malformed = parse_event(raw.decode("utf-8", "replace"), event, evidence)
        identities = [row["source_lot_id"] for row in event_rows]
        if malformed or len(identities) != len(set(identities)):
            raise RuntimeError(
                f"event {event['event_id']} did not reconcile: rows={len(event_rows)}, "
                f"malformed={malformed}, distinct={len(set(identities))}"
            )
        rows.extend(event_rows)
        event_summaries.append({**event, "visible_property_cards": len(event_rows), "source_evidence": evidence})

    detail_by_url, detail_failures = {}, []
    by_url = defaultdict(list)
    for row in rows:
        by_url[row["original_url"]].append(row)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get, url): url for url in by_url}
        for future in as_completed(futures):
            url = futures[future]
            try:
                raw, resolved = future.result()
                source_lot_id = by_url[url][0]["source_lot_id"]
                evidence = snapshot(
                    raw, resolved, f"property-{corpus.digest(url.encode())[:16]}",
                    "first-party retained property detail page",
                    source_lot_id=source_lot_id,
                )
                detail_by_url[url] = (raw.decode("utf-8", "replace"), evidence)
            except Exception as exc:
                detail_failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

    detail_date_mismatches = []
    for row in rows:
        detail = detail_by_url.get(row["original_url"])
        if not detail:
            continue
        try:
            _, observed_date = enrich_detail(detail[0], row, detail[1])
            if observed_date != row["auction_date"]:
                detail_date_mismatches.append({
                    "appearance_id": row["appearance_id"],
                    "event_date": row["auction_date"],
                    "detail_date": observed_date,
                    "url": row["original_url"],
                })
        except Exception as exc:
            detail_failures.append({
                "url": row["original_url"], "appearance_id": row["appearance_id"],
                "error": f"{type(exc).__name__}: {exc}",
            })

    exact_global = global_exact_appearances(SLUG)
    overlap_exclusions, admissible = [], []
    for row in rows:
        matches = exact_global.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlap_exclusions.append({
                "auction_date": row["auction_date"], "address": row["address"],
                "loveitts_appearance_id": row["appearance_id"], "existing": matches,
            })
        else:
            admissible.append(row)

    appearance_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    existing_by_id = {row["appearance_id"]: row for row in existing}
    merged = dict(existing_by_id)
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    persisted = list(corpus.iter_rows(appearance_path))
    if len(persisted) != len(merged) or {row["appearance_id"] for row in persisted} != set(merged):
        raise RuntimeError("Loveitts canonical rows did not persist exactly")
    new_rows = [row for key, row in merged.items() if key not in existing_by_id]

    admitted_by_event = defaultdict(list)
    for row in admissible:
        admitted_by_event[row["source_auction_id"]].append(row)
    for event in events:
        event_id = f"{SLUG}:{event['event_id']}"
        source_summary = next(value for value in event_summaries if value["event_id"] == event["event_id"])
        excluded = [value for value in overlap_exclusions if value["loveitts_appearance_id"].startswith(f"{SOURCE}|{event_id}|")]
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"event-{event['event_id']}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": event_id,
            "auction_date": event["auction_date"],
            "source_url": event["event_url"],
            "visible_source_rows": source_summary["visible_property_cards"],
            "lots_captured": len(admitted_by_event[event_id]),
            "exact_shared_platform_overlaps_excluded": len(excluded),
            "source_rows_complete": True,
            "catalogue_complete": True,
            "completion_scope": "every property card still visible on this retained first-party event page; not evidence of removed original lots",
            "source_evidence": [archive_evidence, source_summary["source_evidence"]],
            "errors": [],
            "checked_at": corpus.now(),
        })

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    historical_new = [row for row in new_rows if row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    all_rows = list(merged.values())
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "operator_legal_name": "Loveitts Limited",
        "operator_company_number": "07558151",
        "trading_name_not_counted_as_separate_operator": "Loveitts",
        "shared_auction_house_platform_not_counted_as_separate_loveitts_operator": "Auction House Coventry & Warwickshire",
        "parser_version": PARSER_VERSION,
        "source_url": archive_resolved,
        "archive_index_rows": len(events) + len(unlinked),
        "linked_event_pages": len(events),
        "unlinked_index_rows": len(unlinked),
        "unlinked_index_entries": unlinked,
        "visible_source_rows": len(rows),
        "distinct_event_property_identities": len({row["appearance_id"] for row in rows}),
        "appearances_captured": len(merged),
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical_new),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_new_undated": sum(not row.get("auction_date") for row in new_rows),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(overlap_exclusions),
        "exact_shared_platform_overlap_exclusions": overlap_exclusions,
        "new_source_years": sorted(years_after - years_before),
        "source_years_visible": sorted({int(row["auction_date"][:4]) for row in rows}),
        "date_range": [
            min(row["auction_date"] for row in all_rows),
            max(row["auction_date"] for row in all_rows),
        ] if all_rows else None,
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in all_rows)),
        "detail_pages_captured": len(detail_by_url),
        "detail_recovery_failures": detail_failures,
        "detail_event_date_mismatches_not_enriched": len(detail_date_mismatches),
        "detail_date_mismatch_examples": detail_date_mismatches[:50],
        "completion_scope": "every card in all 83 currently linked first-party event pages; five unlinked index dates and removed original lots remain outside the claim",
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "loveitts_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    harvest(args.workers)


if __name__ == "__main__":
    main()
