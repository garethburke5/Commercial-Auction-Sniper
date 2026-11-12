"""Bank Taylor James Auctions' retained first-party event catalogues.

The official auction sitemap exposes event pages rather than a rolling grid.
Each event page publishes its exact date and a complete set of individual lot
cards with stable property URLs, lot numbers, guide prices and outcomes.  One
page may represent a re-offer of the same property from an earlier auction;
those appearances remain distinct because their published event dates differ.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.taylorjamesauctions.co.uk"
SITEMAP_URL = BASE + "/auction-sitemap.xml"
AUCTIONEER = "Taylor James Auctions"
SLUG = "taylor-james-auctions"
RECOVERED_EVENT_MANIFEST = corpus.ROOT / "config" / "taylor_james_recovered_events.json"
HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)",
    "Accept": "text/html,application/xhtml+xml,application/xml",
}
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
RENT_RE = re.compile(r"(?:rental\s+income\s+of\s+)?£\s*([\d,]+)\s*(?:per\s+annum|p\.?a\.?)", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def annual_rent(value: str | None) -> int | None:
    match = RENT_RE.search(value or "")
    return int(match.group(1).replace(",", "")) if match else None


def event_date(value: str | None) -> str:
    text = clean(value)
    if not text:
        raise ValueError("auction event page has no published date heading")
    text = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
    return datetime.strptime(text, "%A %d %B %Y").date().isoformat()


def outcome(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").casefold()
    if text.startswith("sold prior"):
        return "sold_prior", None
    if text.startswith("sold after"):
        return "sold_after", None
    if text.startswith("sold"):
        return "sold", pounds(value)
    if text.startswith("withdrawn"):
        return "withdrawn", None
    if text.startswith("postponed"):
        return "postponed", None
    if text.startswith("unsold"):
        return "unsold", None
    if text.startswith("no bids"):
        return "no_bids", None
    if text.startswith("available post"):
        return "available_post", None
    if text.startswith("available"):
        return "available", None
    return "unknown", None


def fetch(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"short first-party response: {url}")
    return response.content, response.url


def parse_sitemap(xml: bytes) -> list[str]:
    soup = BeautifulSoup(xml, "xml")
    urls = [clean(node.get_text()) for node in soup.select("url > loc")]
    urls = [url for url in urls if url and url.startswith(BASE + "/auction/")]
    if not urls or len(urls) != len(set(urls)):
        raise ValueError("auction sitemap is empty or contains duplicate event URLs")
    return urls


def recovered_event_manifest(path: Path = RECOVERED_EVENT_MANIFEST) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events") or []
    if not events:
        raise ValueError("Taylor James recovered-event manifest is empty")
    urls = []
    for event in events:
        url = event.get("url")
        expected = event.get("expected_property_cards")
        if not url or not url.startswith(BASE + "/auction/"):
            raise ValueError(f"invalid Taylor James recovered event URL: {url!r}")
        if not isinstance(expected, int) or expected <= 0:
            raise ValueError(f"invalid expected property-card count for {url}")
        urls.append(url)
    if len(urls) != len(set(urls)):
        raise ValueError("Taylor James recovered-event manifest contains duplicate URLs")
    return events


def parse_event_page(html: str, source_url: str, evidence: dict) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.select_one(".container-header h1 .month")
    auction_date = event_date(heading.get_text(" ", strip=True) if heading else None)
    rows = []
    for position, card in enumerate(soup.select(".property-block"), 1):
        link = card.select_one('a.property-link[href*="/property/"]')
        address_node = card.select_one("h3")
        lot_node = card.select_one(".lot-number")
        if not address_node:
            raise ValueError(f"{source_url} card {position} lacks an address")
        address = clean(address_node.get_text(" ", strip=True))
        lot_number = clean(lot_node.get_text(" ", strip=True)) if lot_node else None
        detail_url = urljoin(BASE, link.get("href") or "") if link else None
        property_slug = (
            urlparse(detail_url).path.strip("/").split("/")[-1]
            if detail_url else None
        )
        if not address:
            raise ValueError(f"{source_url} card {position} has an empty address")
        if not property_slug:
            identity = "|".join((auction_date, lot_number or str(position), address.casefold()))
            property_slug = "unlinked-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        feature_node = card.select_one(".feature")
        feature = clean(feature_node.get_text(" ", strip=True)) if feature_node else None
        guide_node = card.select_one(".property-price")
        guide_text = clean(guide_node.get_text(" ", strip=True)) if guide_node else None
        status_node = card.select_one(".property-status")
        outcome_text = clean(status_node.get_text(" ", strip=True)) if status_node else None
        status, sale_price = outcome(outcome_text)
        image_node = card.select_one("img[src]")
        image_url = urljoin(source_url, image_node.get("src")) if image_node else None
        postcode = corpus.PC.search(address)
        auction_id = f"{SLUG}:{auction_date}"
        row = corpus.base_row(
            AUCTIONEER, auction_id, auction_date, lot_number, property_slug, detail_url or source_url,
        )
        row.update(
            appearance_id=(
                f"{AUCTIONEER}|{auction_date}|property:{property_slug}|"
                f"lot:{lot_number or f'position-{position}'}"
            ),
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, feature]))),
            property_type=feature,
            guide_price=pounds(guide_text),
            sale_price=sale_price,
            annual_rent=annual_rent(feature),
            status=status,
            description=feature,
            image_urls=[image_url] if image_url else [],
            property_id=property_slug,
            identity_method=(
                "first_party_exact_event_date_property_url_and_lot_number"
                if detail_url and lot_number else
                "first_party_exact_event_date_card_address_and_published_position"
            ),
            record_quality="address_record",
            auction_date_precision="day",
            auction_date_basis="exact date published in first-party auction event heading",
            source_platform="Taylor James Auctions first-party event archive",
            source_position=position,
            source_guide_text=guide_text,
            source_outcome_text=outcome_text,
            source_detail_url=detail_url,
            source_evidence=evidence,
        )
        rows.append(row)
    ids = [row["appearance_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source_url} contains duplicate event/property/lot identities")
    return auction_date, rows


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value or "", flags=re.I).strip().casefold()


def global_exact_appearances() -> dict[tuple[str, str], list[dict]]:
    values: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                    "lot_number": row.get("lot_number"),
                    "original_url": row.get("original_url"),
                })
    return values


def persist_continuation(summary: dict) -> None:
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    if summary["run_new_appearances"]:
        payload.setdefault("runs", []).append(checkpoint)
        payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
        payload["last_automated_growth"] = checkpoint
    payload["hh_land_estates_pre_2022_blocker"] = {
        "checked_at": summary["checked_at"],
        "outcome": "no_retained_first_party_pre_2022_inventory",
        "evidence": (
            "The official sitemap exposed 301 news URLs with the retained archive beginning in 2022; "
            "targeted 2020/2021 searches produced no first-party event inventory."
        ),
        "next_route": "Revisit only if an older first-party or independently archived catalogue route is discovered.",
    }
    next_target = (
        "Recover Taylor James Auctions' advertised 10 July 2024 event through an exact first-party or archived "
        "event URL, then test a materially different archival route for catalogues before October 2020. Reuse "
        "the event-page runner and literal card denominators without overwriting the banked 2020-2024 "
        "appearances. If those routes are thin, rotate to Regional Property Auctioneers' multi-year first-party "
        "catalogue archive. National completeness remains false."
    )
    payload["next_growth_target"] = next_target
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "taylor-james-july-2024-and-pre-2020",
        "auctioneer": AUCTIONEER,
        "source_format": "first-party event pages and individual property pages",
        "opportunity": "the advertised July 2024 event and older catalogues omitted from the retained sitemap",
        "next_growth_target": next_target,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def reusable_event_states(event_urls: list[str], existing: list[dict], refresh_existing: bool) -> dict:
    if refresh_existing:
        return {}
    existing_by_auction = defaultdict(list)
    for row in existing:
        existing_by_auction[row.get("source_auction_id")].append(row)
    reusable = {}
    for path in (corpus.DATA / "auctions" / SLUG).glob("*.json"):
        state = json.loads(path.read_text(encoding="utf-8"))
        url = state.get("source_url")
        rows = existing_by_auction.get(state.get("source_auction_id"), [])
        if (
            url in event_urls
            and state.get("source_rows_complete") is True
            and len(rows) == state.get("lots_captured")
        ):
            reusable[url] = (path.stem, state, rows)
    return reusable


def harvest(workers: int = 8, refresh_existing: bool = False) -> dict:
    sitemap_raw, sitemap_resolved = fetch(SITEMAP_URL)
    sitemap_urls = parse_sitemap(sitemap_raw)
    recovered_events = recovered_event_manifest()
    recovered_by_url = {event["url"]: event for event in recovered_events}
    overlap = set(sitemap_urls) & set(recovered_by_url)
    if overlap:
        raise ValueError(f"recovered Taylor James URLs already present in official sitemap: {sorted(overlap)}")
    event_urls = sitemap_urls + list(recovered_by_url)
    shard_path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard_path)) if shard_path.exists() else []
    reusable_states = reusable_event_states(event_urls, existing, refresh_existing)
    sitemap_sha = corpus.digest(sitemap_raw)
    sitemap_path = corpus.DATA / "sources" / SLUG / f"auction-sitemap-{sitemap_sha[:16]}.xml.gz"
    if not sitemap_path.exists():
        corpus.atomic(sitemap_path, gzip.compress(sitemap_raw, mtime=0))
    sitemap_evidence = {
        "source_url": sitemap_resolved,
        "retrieved_at": corpus.now(),
        "sha256": sitemap_sha,
        "snapshot_path": str(sitemap_path.relative_to(corpus.ROOT)),
        "basis": "first-party auction-event sitemap",
        "published_event_urls": len(event_urls),
    }

    fetched: dict[str, tuple[bytes, str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch, url): url
            for url in event_urls
            if url not in reusable_states
        }
        for future in as_completed(futures):
            fetched[futures[future]] = future.result()

    run_rows, states, empty_events = [], {}, []
    for event_url in event_urls:
        if event_url in reusable_states:
            event_key, state, rows = reusable_states[event_url]
            states[event_key] = state
            run_rows.extend(rows)
            if not rows:
                empty_events.append({
                    "event_key": event_key,
                    "auction_date": state["auction_date"],
                    "source_url": state["source_url"],
                })
            continue
        raw, resolved = fetched[event_url]
        sha = corpus.digest(raw)
        snapshot = corpus.DATA / "sources" / SLUG / f"event-{sha[:16]}.html.gz"
        if not snapshot.exists():
            corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
        evidence = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party Taylor James auction event page",
            "discovery_basis": (
                "first-party auction-event sitemap"
                if event_url in sitemap_urls else
                "recovered first-party event URL manifest"
            ),
            "sitemap_evidence": sitemap_evidence if event_url in sitemap_urls else None,
            "recovered_manifest_evidence": (
                {
                    "manifest_path": str(RECOVERED_EVENT_MANIFEST.relative_to(corpus.ROOT)),
                    "expected_property_cards": recovered_by_url[event_url]["expected_property_cards"],
                    "discovery_note": recovered_by_url[event_url].get("discovery_note"),
                }
                if event_url in recovered_by_url else None
            ),
        }
        auction_date, rows = parse_event_page(raw.decode("utf-8", "replace"), resolved, evidence)
        expected_cards = recovered_by_url.get(event_url, {}).get("expected_property_cards")
        if expected_cards is not None and len(rows) != expected_cards:
            raise ValueError(
                f"{event_url} published {len(rows)} cards; recovered manifest expected {expected_cards}"
            )
        event_key = urlparse(resolved).path.strip("/").split("/")[-1]
        state = {
            "auctioneer": AUCTIONEER,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "auction_date_precision": "day",
            "source_url": resolved,
            "published_lot_cards": len(rows),
            "lots_captured": len(rows),
            "catalogue_complete": bool(rows),
            "event_inventory_complete": bool(rows),
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": (
                "every individual property card on the retained first-party event page"
                if rows else
                "retained event placeholder contained no property cards and is not property evidence"
            ),
            "source_evidence": evidence,
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event_key}.json", state)
        states[event_key] = state
        if rows:
            run_rows.extend(rows)
        else:
            empty_events.append({"event_key": event_key, "auction_date": auction_date, "source_url": resolved})

    before_ids = {row["appearance_id"] for row in existing}
    global_exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in run_rows:
        if row["appearance_id"] in before_ids:
            admissible.append(row)
            continue
        matches = global_exact.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlaps.append({
                "appearance_id": row["appearance_id"],
                "address": row["address"],
                "auction_date": row["auction_date"],
                "lot_number": row["lot_number"],
                "existing": matches,
            })
        else:
            admissible.append(row)

    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    dated = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": AUCTIONEER,
        "source_url": sitemap_resolved,
        "sitemap_event_urls": len(sitemap_urls),
        "recovered_manifest_event_urls": len(recovered_events),
        "event_urls_discovered": len(event_urls),
        "event_pages_with_property_cards": sum(bool(state["published_lot_cards"]) for state in states.values()),
        "empty_event_pages": empty_events,
        "published_property_cards": len(run_rows),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": len(dated),
        "run_new_partial_lots": sum(row.get("record_quality") != "address_record" for row in added),
        "run_new_undated_lots": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_lots": sum((row.get("auction_date") or today) > today for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "events": states,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "catalogue_completion_claimed": False,
        "completion_scope": (
            f"the {len(sitemap_urls)} event URLs in the retained official sitemap plus "
            f"{len(recovered_events)} omitted but surviving first-party event pages in the recovered manifest; "
            "not a claim of twenty-year completeness"
        ),
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "taylor_james_auctions_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--refresh-existing", action="store_true")
    args = parser.parse_args()
    harvest(workers=max(1, args.workers), refresh_existing=args.refresh_existing)
