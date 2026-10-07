"""Incrementally bank Future Property Auctions' public BidJS archive.

The unauthenticated first-party feed publishes a stable archive manifest and a
complete listing map for each retained auction.  A bounded newest-first tranche
is captured per run so scheduled collection remains resumable.  Public lot and
sale fields are snapshotted, while bidder/registrant identifiers and unpublished
reserve values are deliberately discarded.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


API = "https://hove.eu-west-2.bidjs.com/auction-007/api"
ARCHIVE_URL = API + "/v1/auctionsArchived"
AUCTION_URL = API + "/v3/auctions/{uuid}"
PUBLIC_AUCTIONS = "https://www.futurepropertyauctions.co.uk/onlineauctions.html#!/"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)",
    "x-forwarded-client-id": "futureproperty",
}
PROPERTY_ID_RE = re.compile(r"property_details\.asp\?id=(\d+)", re.I)
FAILURE_COOLDOWN_SECONDS = 2 * 60 * 60
SOURCE_403_COOLDOWN_SECONDS = 24 * 60 * 60
ITEM_FAILURE_COOLDOWN_SECONDS = 24 * 60 * 60


def epoch_date(value: int | float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).date().isoformat()


def fetch_json(url: str) -> tuple[bytes, dict]:
    response = None
    for attempt in range(4):
        try:
            response = requests.get(url, headers=HEADERS, timeout=150)
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2.0 * (attempt + 1))
            continue
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
            break
        retry_after = response.headers.get("Retry-After", "")
        delay = float(retry_after) if retry_after.isdigit() else 2.0 * (attempt + 1)
        time.sleep(min(delay, 30.0))
    assert response is not None
    response.raise_for_status()
    raw = response.content
    if len(raw) < 20 or "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("source did not return the expected JSON")
    return raw, response.json()


def failure_cooldown_seconds(summary: dict) -> int:
    """Return the bounded source cooldown represented by a run summary."""
    failures = summary.get("failures") or []
    source_wide_403 = (
        bool(failures)
        and "403" in str(summary.get("manifest_refresh_error") or "")
        and all("403" in str(item.get("error") or "") for item in failures)
    )
    return SOURCE_403_COOLDOWN_SECONDS if source_wide_403 else FAILURE_COOLDOWN_SECONDS


def full_failure_cooldown(summary: dict, now: datetime | None = None) -> bool:
    """Avoid repeating a tranche where every fresh request failed.

    A source-wide 403 is held for a full day so scheduled runs do not burn
    through different catalogue UUIDs while the BidJS host is refusing both
    its archive manifest and every selected auction payload.
    """
    attempted = int(summary.get("catalogues_attempted_this_run") or 0)
    failures = summary.get("failures") or []
    if attempted <= 0 or len(failures) != attempted or summary.get("run_new_appearances"):
        return False
    try:
        checked = datetime.fromisoformat(str(summary["checked_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    current = now or datetime.now(timezone.utc)
    return 0 <= (current - checked).total_seconds() < failure_cooldown_seconds(summary)



def recent_403_failures(summary: dict, now: datetime | None = None) -> list[dict]:
    """Defer catalogue URLs for one day after a source-level 403."""
    current = now or datetime.now(timezone.utc)
    inherited_checked = summary.get("checked_at")
    records = list(summary.get("deferred_failures") or []) + list(summary.get("failures") or [])
    kept = {}
    for item in records:
        auction_uuid = str(item.get("auction_uuid") or "")
        if not auction_uuid or "403" not in str(item.get("error") or ""):
            continue
        try:
            checked = datetime.fromisoformat(
                str(item.get("checked_at") or inherited_checked).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            continue
        age = (current - checked).total_seconds()
        if 0 <= age < ITEM_FAILURE_COOLDOWN_SECONDS:
            kept[auction_uuid] = {**item, "checked_at": checked.isoformat()}
    return list(kept.values())

def fetch_manifest() -> tuple[dict, dict, str | None]:
    """Refresh the archive index, falling back to its newest saved evidence.

    BidJS can temporarily refuse the archive-index request after a successful
    collection run.  A retained first-party manifest is safe to reuse as a work
    queue: individual auctions are still fetched afresh and must reconcile
    before any appearance is admitted.
    """
    snapshot_dir = corpus.DATA / "sources/future_property_auctions"
    try:
        raw, payload = fetch_json(ARCHIVE_URL)
    except requests.RequestException as exc:
        candidates = []
        for path in snapshot_dir.glob("archive-*.json.gz"):
            try:
                saved = corpus.read_gzip(path)
                evidence = saved.get("evidence") or {}
                payload = saved.get("payload")
                manifest_rows(payload)
                candidates.append((evidence.get("retrieved_at") or "", path, payload, evidence))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        if not candidates:
            raise
        _, path, payload, evidence = max(candidates, key=lambda item: item[0])
        error = f"{type(exc).__name__}: {exc}"[:500]
        return payload, evidence, error

    manifest_sha, retrieved_at = corpus.digest(raw), corpus.now()
    snapshot = snapshot_dir / f"archive-{manifest_sha[:16]}.json.gz"
    evidence = {
        "source_url": ARCHIVE_URL, "retrieved_at": retrieved_at, "sha256": manifest_sha,
        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party public BidJS archived-auction manifest",
    }
    corpus.save_gzip(snapshot, {"evidence": evidence, "payload": payload})
    return payload, evidence, None


def manifest_rows(payload: dict) -> list[dict]:
    rows = payload.get("basicAuctionBidJSModelList")
    if not isinstance(rows, list) or not rows:
        raise ValueError("archive manifest has no auctions")
    seen = set()
    normalized = []
    for row in rows:
        uuid = str(row.get("auctionUuid") or "")
        auction_id = row.get("auctionId")
        if not uuid or auction_id is None or uuid in seen:
            raise ValueError("archive manifest contains a missing or duplicate identity")
        seen.add(uuid)
        title = corpus.plain(row.get("auctionTitle"))
        if title and title.casefold() == "test auction":
            continue
        normalized.append({
            "auction_uuid": uuid,
            "auction_id": str(auction_id),
            "title": title,
            "auction_end_time": row.get("auctionEndTime"),
            "auction_date": epoch_date(row.get("auctionEndTime")),
        })
    if not normalized:
        raise ValueError("archive manifest has no non-test auctions")
    return normalized


def image_urls(listing: dict, attachments: dict) -> list[str]:
    result = []
    for attachment_id in listing.get("images") or []:
        item = attachments.get(attachment_id) or {}
        base = str(item.get("basePath") or "").rstrip("/")
        public_id = str(item.get("versionAndPublicId") or "").lstrip("/")
        if base and public_id:
            result.append(base + "/" + public_id)
    return list(dict.fromkeys(result))


def highest_bid(payload: dict, status: dict) -> dict | None:
    bid_uuid = status.get("highestBidUuid")
    bid = (payload.get("sellingInformation", {}).get("bids") or {}).get(bid_uuid)
    if not isinstance(bid, dict) or bid.get("cancelled"):
        return None
    amount = corpus.money(bid.get("amount"))
    return {"amount": amount, "placed_at": bid.get("placedAt")} if amount is not None else None


def status_value(status: dict) -> str:
    if status.get("withdrawn"):
        return "withdrawn"
    if status.get("suspended"):
        return "suspended"
    if status.get("sold"):
        return "sold"
    if status.get("complete"):
        return "unsold"
    return "unknown"


def parse_auction(payload: dict, manifest: dict, evidence: dict) -> tuple[list[dict], dict]:
    info = payload.get("information") or {}
    auction = info.get("auction") or {}
    listings = info.get("listings") or {}
    sales = (payload.get("sellingInformation") or {}).get("sales") or {}
    statuses = (payload.get("sellingInformation") or {}).get("saleStatuses") or {}
    attachments = payload.get("attachments") or {}
    if auction.get("uuid") != manifest["auction_uuid"]:
        raise ValueError("auction UUID does not match archive manifest")
    if not isinstance(listings, dict) or not listings:
        raise ValueError("auction has no published listing map")
    listing_ids = set(listings)
    if listing_ids != set(sales) or listing_ids != set(statuses):
        raise ValueError("listing, sale and status maps do not reconcile")
    if len({str(item.get("id")) for item in listings.values()}) != len(listings):
        raise ValueError("listing numeric IDs are not distinct")

    auction_date = epoch_date(auction.get("endsAt")) or manifest["auction_date"]
    rows = []
    for listing_uuid, listing in listings.items():
        if listing.get("uuid") != listing_uuid or listing.get("auctionUuid") != manifest["auction_uuid"]:
            raise ValueError("listing identity does not reconcile to auction")
        lot_number = corpus.clean(listing.get("lotNumber")) or None
        if lot_number == "0":
            continue
        address = corpus.plain(listing.get("title"))
        description_html = str(listing.get("description") or "")
        property_match = PROPERTY_ID_RE.search(description_html)
        property_id = property_match.group(1) if property_match else None
        public_url = ("https://www.futurepropertyauctions.co.uk/property_details.asp?id=" + property_id
                      if property_id else PUBLIC_AUCTIONS)
        state = statuses[listing_uuid]
        bid = highest_bid(payload, state)
        status = status_value(state)
        summary = corpus.plain(listing.get("summary"))
        description = corpus.plain(description_html)
        row = corpus.base_row(
            "Future Property Auctions", f"future-property:{manifest['auction_uuid']}",
            auction_date, lot_number, listing_uuid, public_url,
        )
        row.update(
            address=address,
            postcode=(corpus.PC.search(address).group().upper() if address and corpus.PC.search(address) else None),
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, summary, description]))),
            property_type=summary,
            tenure=("freehold" if summary and "freehold" in summary.casefold() else
                    "leasehold" if summary and "leasehold" in summary.casefold() else None),
            sale_price=(bid["amount"] if status == "sold" and bid else None),
            status=status,
            description=description,
            image_urls=image_urls(listing, attachments),
            property_id=property_id,
            identity_method="bidjs_listing_uuid",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis="UTC date of the first-party auction/listing closing timestamp",
            listing_uuid=listing_uuid,
            bidjs_listing_id=listing.get("id"),
            lot_end_at=state.get("endsAt"),
            total_bids=sales[listing_uuid].get("totalBids"),
            highest_bid=(bid["amount"] if bid else None),
            source_evidence=evidence,
        )
        row["appearance_id"] = f"Future Property Auctions|auction:{manifest['auction_uuid']}|listing:{listing_uuid}"
        rows.append(row)

    state = {
        "auctioneer": "Future Property Auctions",
        "source_auction_id": f"future-property:{manifest['auction_uuid']}",
        "source_numeric_auction_id": manifest["auction_id"],
        "auction_uuid": manifest["auction_uuid"],
        "auction_title": manifest["title"],
        "auction_date": auction_date,
        "catalogue_complete": len(rows) == len(listings),
        "source_rows_complete": len(rows) == len(listings),
        "published_listing_count": len(listings),
        "lots_captured": len(rows),
        "pagination_reconciled": True,
        "denominator_reconciled": len(rows) == len(listings),
        "denominator_basis": "complete first-party BidJS listing map for this archived auction",
        "completion_scope": "all listing UUIDs in the archived auction payload",
        "source_url": evidence["source_url"],
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    if not state["catalogue_complete"]:
        raise ValueError("auction listing count did not reconcile")
    return rows, state


def sanitized_snapshot(payload: dict, evidence: dict) -> dict:
    info = payload.get("information") or {}
    selling = payload.get("sellingInformation") or {}
    listings = info.get("listings") or {}
    statuses = selling.get("saleStatuses") or {}
    sales = selling.get("sales") or {}
    attachments = payload.get("attachments") or {}
    used_attachments = {item for listing in listings.values() for item in (listing.get("images") or [])}
    public_sales = {}
    for listing_uuid, status in statuses.items():
        bid = highest_bid(payload, status)
        public_sales[listing_uuid] = {
            "status": status,
            "totalBids": (sales.get(listing_uuid) or {}).get("totalBids"),
            "highestBid": bid,
        }
    return {
        "evidence": evidence,
        "privacy_note": "registrants, bidder/user UUIDs, full bid histories and reserve values omitted",
        "auction": info.get("auction"),
        "listings": listings,
        "public_sales": public_sales,
        "attachments": {key: attachments[key] for key in used_attachments if key in attachments},
    }


def harvest(limit: int = 12, workers: int = 3) -> None:
    summary_path = corpus.DATA / "future_property_auctions_collection.json"
    try:
        previous_summary = json.loads(summary_path.read_text())
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        previous_summary = {}
    if full_failure_cooldown(previous_summary):
        print(json.dumps({
            "skipped": "recent tranche had no successful fresh auction payloads",
            "cooldown_seconds": failure_cooldown_seconds(previous_summary),
            "catalogues_pending": previous_summary.get("catalogues_pending"),
            "previous_checked_at": previous_summary.get("checked_at"),
        }), flush=True)
        return

    manifest_payload, manifest_evidence, manifest_refresh_error = fetch_manifest()
    manifest = manifest_rows(manifest_payload)

    appearance_path = corpus.DATA / "appearances/future_property_auctions/archive.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)

    completed, states, pending = set(), {}, []
    for item in manifest:
        state_path = corpus.DATA / "auctions/future_property_auctions" / f"{item['auction_id']}.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            state = None
        source_auction_id = f"future-property:{item['auction_uuid']}"
        old_rows = existing_by_auction.get(source_auction_id, [])
        if (state and state.get("catalogue_complete") and
                state.get("lots_captured") == len(old_rows) and old_rows):
            completed.add(item["auction_uuid"])
            states[item["auction_id"]] = state
        else:
            pending.append(item)
    deferred_failures = recent_403_failures(previous_summary)
    deferred_uuids = {item["auction_uuid"] for item in deferred_failures}
    eligible = [item for item in pending if item["auction_uuid"] not in deferred_uuids]
    selected = eligible[:max(0, limit)] if limit else eligible
    run_rows, failures = [], []

    def capture(item: dict):
        url = AUCTION_URL.format(uuid=item["auction_uuid"])
        auction_raw, payload = fetch_json(url)
        sha, checked = corpus.digest(auction_raw), corpus.now()
        snapshot = corpus.DATA / "sources/future_property_auctions" / item["auction_id"] / f"auction-{sha[:16]}.json.gz"
        evidence = {
            "source_url": url, "public_url": PUBLIC_AUCTIONS, "retrieved_at": checked,
            "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "archive_snapshot_path": manifest_evidence["snapshot_path"],
            "basis": "complete first-party public BidJS archived-auction payload",
        }
        rows, state = parse_auction(payload, item, evidence)
        corpus.save_gzip(snapshot, sanitized_snapshot(payload, evidence))
        return item, rows, state

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        jobs = {pool.submit(capture, item): item for item in selected}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                item, rows, state = future.result()
                corpus.save_json(
                    corpus.DATA / "auctions/future_property_auctions" / f"{item['auction_id']}.json", state)
                states[item["auction_id"]] = state
                completed.add(item["auction_uuid"])
                run_rows.extend(rows)
                print("FUTURE PROPERTY", len(completed), "/", len(manifest), "auctions", len(run_rows), "run lots", flush=True)
            except Exception as exc:
                failures.append({
                    "auction_id": item["auction_id"], "auction_uuid": item["auction_uuid"],
                    "title": item["title"], "error": f"{type(exc).__name__}: {exc}"[:500],
                    "checked_at": corpus.now(),
                })

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("future_property_auctions/archive", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE_URL,
        "archive_auctions_discovered": len(manifest),
        "archive_date_min": min(x["auction_date"] for x in manifest if x["auction_date"]),
        "archive_date_max": max(x["auction_date"] for x in manifest if x["auction_date"]),
        "catalogues_complete": len(completed),
        "catalogues_pending": len(manifest) - len(completed),
        "catalogues_attempted_this_run": len(selected),
        "catalogues_deferred_recent_403": len(deferred_failures),
        "catalogues_eligible_after_deferrals": len(eligible),
        "selected_auction_uuids": [item["auction_uuid"] for item in selected],
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "privacy_note": "source snapshots exclude registrants, bidder/user UUIDs, full bid histories and reserve values",
        "manifest_refresh_error": manifest_refresh_error,
        "archive_evidence": manifest_evidence, "auctions": states,
        "deferred_failures": deferred_failures, "failures": failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=12, help="maximum incomplete archived auctions this run; 0 means all")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    harvest(args.limit, args.workers)
