"""Bank Pattinson's retained sold online-auction property pages.

Pattinson does not publish a historical catalogue index.  Its first-party XML
sitemap does retain property URLs, however, and each URL has a public JSON card
endpoint.  This collector scans that finite denominator and admits only cards
which explicitly say both ``isSold`` and ``isOnlineAuction``.  Current/live
auction cards are never admitted.  The retained pages are standalone property
auctions, not catalogues, so this collector deliberately creates no catalogue
completion records.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import re
import sys
import threading
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.pattinson.co.uk"
SITEMAP = BASE + "/sitemap.xml"
CARD = BASE + "/api/property/{}/card"
PROPERTY = BASE + "/property/{}"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_URL_RE = re.compile(r"https://www\.pattinson\.co\.uk/property/(\d+)")
_local = threading.local()


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def discover_property_ids(xml: str) -> list[str]:
    ids = PROPERTY_URL_RE.findall(xml)
    if not ids:
        raise ValueError("Pattinson sitemap contains no property URLs")
    if len(ids) != len(set(ids)):
        raise ValueError("Pattinson sitemap contains duplicate property URLs")
    return ids


def compose_address(parts: dict) -> tuple[str | None, str | None, str | None]:
    if not isinstance(parts, dict):
        return None, None, None
    postcode = clean(parts.get("postcode"))
    postcode = postcode.upper() if postcode and corpus.PC.fullmatch(postcode) else None
    ordered = []
    for key in ("houseNameNumber", "street", "locality", "city", "county"):
        value = clean(parts.get(key))
        if not value or value in {".", "-"}:
            continue
        if value.casefold() not in {item.casefold() for item in ordered}:
            ordered.append(value)
    if postcode:
        ordered.append(postcode)
    return (", ".join(ordered) or None, postcode, clean(parts.get("city")))


def historical_auction(card: dict) -> bool:
    """Require explicit first-party evidence of a concluded online auction."""
    return (
        isinstance(card, dict)
        and card.get("isSold") is True
        and card.get("isOnlineAuction") is True
        and card.get("isRental") is not True
        and bool(card.get("id"))
    )


def published_past_deadline(value, observed_at: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date().isoformat() if parsed <= observed else None


def card_row(card: dict, evidence: dict, observed_at: str) -> dict:
    if not historical_auction(card):
        raise ValueError("card lacks sold online-auction evidence")
    source_id = str(card["id"])
    address, postcode, locality = compose_address(card.get("address") or {})
    deadline = card.get("deadline")
    auction_date = published_past_deadline(deadline, observed_at)
    row = corpus.base_row(
        "Pattinson Auctions", f"pattinson-online-property:{source_id}",
        auction_date, None, source_id, PROPERTY.format(source_id),
    )
    price_description = clean(card.get("priceDescription"))
    price = corpus.money(card.get("price"))
    description_parts = [clean(card.get("headline")), clean(card.get("salesDescription"))]
    description = " ".join(part for part in description_parts if part) or None
    images = []
    for item in card.get("propertyImages") or []:
        if isinstance(item, dict) and clean(item.get("image")):
            images.append(clean(item["image"]))
    if clean(card.get("image")) and clean(card.get("image")) not in images:
        images.insert(0, clean(card["image"]))
    row.update(
        address=address, postcode=postcode, locality=locality,
        property_type=clean(card.get("propertyTypeName")), tenure=clean(card.get("tenure")),
        guide_price=price if price_description and re.search(r"starting bid|guide", price_description, re.I) else None,
        status="sold", description=description, image_urls=images,
        sector=corpus.sector(" ".join(filter(None, (clean(card.get("propertyTypeName")), description)))),
        record_quality="address_record" if address else "partial_lot",
        identity_method="first_party_property_id_for_appearance_only",
        source_price=price, source_price_description=price_description,
        source_deadline=clean(deadline),
        auction_date_basis="published_past_deadline" if auction_date else "not_exposed_on_retained_sold_card",
        bedrooms=card.get("bedrooms"), bathrooms=card.get("bathrooms"),
        receptions=card.get("receptions"), source_evidence=evidence,
    )
    row["appearance_id"] = f"Pattinson Auctions|property:{source_id}"
    return row


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(HEADERS)
    return _local.session


def fetch_card(property_id: str) -> tuple[str, int, dict | None]:
    response = _session().get(CARD.format(property_id), timeout=60)
    if response.status_code == 404:
        return property_id, 404, None
    response.raise_for_status()
    payload = response.json()
    card = payload.get("property") if isinstance(payload, dict) else None
    if not isinstance(card, dict) or str(card.get("id")) != property_id:
        raise ValueError(f"card identity mismatch for property {property_id}")
    return property_id, response.status_code, payload


def harvest(workers: int = 32) -> None:
    sitemap_response = requests.get(SITEMAP, headers=HEADERS, timeout=90)
    existing_path = corpus.DATA / "appearances/pattinson/canonical.jsonl.gz"
    existing_summary = corpus.DATA / "pattinson_collection.json"
    if sitemap_response.status_code == 403 and existing_path.exists() and existing_summary.exists():
        # Pattinson currently blocks GitHub-hosted runner addresses.  Retain
        # the already banked, source-snapshotted rows; a blocked refresh must
        # never erase or rewrite them.
        print("PATTINSON_REFRESH_BLOCKED_403 retaining persisted source-snapshotted rows", flush=True)
        return
    sitemap_response.raise_for_status()
    raw_sitemap = sitemap_response.content
    xml = raw_sitemap.decode("utf-8", "replace")
    property_ids = discover_property_ids(xml)
    observed_at = corpus.now()
    sitemap_sha = corpus.digest(raw_sitemap)
    sitemap_snapshot = corpus.DATA / "sources/pattinson" / f"sitemap-{sitemap_sha[:16]}.json.gz"
    sitemap_evidence = {
        "source_url": sitemap_response.url, "retrieved_at": observed_at,
        "sha256": sitemap_sha, "snapshot_path": str(sitemap_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party XML sitemap property URL denominator",
    }
    corpus.save_gzip(sitemap_snapshot, {"evidence": sitemap_evidence, "xml": xml})

    payloads, unavailable, failures = {}, [], []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 48))) as pool:
        jobs = {pool.submit(fetch_card, property_id): property_id for property_id in property_ids}
        for position, future in enumerate(as_completed(jobs), 1):
            property_id = jobs[future]
            try:
                property_id, status, payload = future.result()
                if status == 404:
                    unavailable.append(property_id)
                else:
                    payloads[property_id] = payload
            except Exception as exc:
                failures.append({"property_id": property_id, "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 500 == 0:
                print("PATTINSON", position, "/", len(property_ids), "card endpoints", flush=True)

    # Preserve every admitted raw card verbatim.  For the much larger set of
    # rejected live/non-auction cards, retain the admission flags plus a hash
    # of the raw response so the finite sitemap audit remains reproducible
    # without adding megabytes of unrelated live-property imagery each run.
    candidate_payloads = {}
    audit = {}
    for property_id, payload in payloads.items():
        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        card = payload.get("property") if isinstance(payload, dict) else None
        audit[property_id] = {
            "sha256": corpus.digest(raw_payload),
            "isSold": card.get("isSold") if isinstance(card, dict) else None,
            "isOnlineAuction": card.get("isOnlineAuction") if isinstance(card, dict) else None,
            "isRental": card.get("isRental") if isinstance(card, dict) else None,
        }
        if historical_auction(card):
            candidate_payloads[property_id] = payload
    snapshot_value = {
        "observed_at": observed_at, "sitemap_evidence": sitemap_evidence,
        "property_urls_discovered": len(property_ids), "candidate_cards": candidate_payloads,
        "card_admission_audit": audit,
        "unavailable_property_ids": sorted(unavailable), "failures": failures,
    }
    snapshot_bytes = json.dumps(snapshot_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    cards_sha = corpus.digest(snapshot_bytes)
    cards_snapshot = corpus.DATA / "sources/pattinson" / f"card-scan-{cards_sha[:16]}.json.gz"
    cards_evidence = {
        "source_url": SITEMAP, "retrieved_at": observed_at, "sha256": cards_sha,
        "snapshot_path": str(cards_snapshot.relative_to(corpus.ROOT)),
        "basis": "raw admitted first-party cards plus admission flags and response hashes for every resolvable sitemap URL",
        "sitemap_sha256": sitemap_sha,
    }
    corpus.save_gzip(cards_snapshot, snapshot_value)

    path = existing_path
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    rows = []
    for property_id in property_ids:
        payload = payloads.get(property_id)
        card = payload.get("property") if isinstance(payload, dict) else None
        if historical_auction(card):
            rows.append(card_row(card, cards_evidence, observed_at))
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in rows})
    total = corpus.write_rows("pattinson/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": SITEMAP,
        "property_urls_discovered": len(property_ids), "card_endpoints_resolved": len(payloads),
        "card_endpoints_unavailable": len(unavailable), "unavailable_property_ids": sorted(unavailable),
        "verified_historical_online_auction_appearances": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "sitemap_evidence": sitemap_evidence, "card_scan_evidence": cards_evidence,
        "failures": failures,
        "admission_rule": "isSold=true AND isOnlineAuction=true AND isRental!=true",
        "catalogue_completion_claimed": False,
        "completion_scope": "standalone retained property pages only; no parent historical catalogue is published",
    }
    corpus.save_json(corpus.DATA / "pattinson_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 32)
