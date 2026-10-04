"""Bank Strettons' retained first-party past-auction catalogue JSON.

The Gatsby site publishes a compact past-auction index plus one unpaginated
``page-data.json`` payload per auction.  Every embedded property is retained,
including residential, withdrawn, sold-prior, and currently unresulted lots.
Completed auction checkpoints are reused until the source ``updatedAt`` value
changes.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.strettons.co.uk"
INDEX = BASE + "/data/past_auction.json"
DETAIL = BASE + "/page-data/auctions/past-auctions/past-auction-details/{auction_id}/page-data.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)

# First-party past-auction HTML pages retained by Strettons but omitted from
# the compact index. Their former page-data endpoints returned HTTP 404 on
# 2026-10-04, so they are evidence pointers only and are never re-probed by the
# collector until a usable lot source is found.
BLOCKED_RECOVERED_AUCTIONS = (
    {
        "auction_id": "2765", "auction_date": "2025-07-10", "updated_at": None,
        "discovery_url": BASE + "/auctions/past-auctions/past-auction-details/2765/",
    },
    {
        "auction_id": "2766", "auction_date": "2025-09-11", "updated_at": None,
        "discovery_url": BASE + "/auctions/past-auctions/past-auction-details/2766/",
    },
    {
        "auction_id": "2767", "auction_date": "2025-10-23", "updated_at": None,
        "discovery_url": BASE + "/auctions/past-auctions/past-auction-details/2767/",
    },
)

# Only recovered IDs with a live, reconcilable lot payload belong here.
RECOVERED_AUCTIONS: tuple[dict, ...] = ()


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def money_from_result(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def status_and_price(status: str | None, result: str | None) -> tuple[str, int | None]:
    text = clean(result) or clean(status) or ""
    lower = text.casefold()
    price = money_from_result(text)
    if "sold prior" in lower:
        return "sold_prior", price
    if "sold after" in lower or "sold post" in lower:
        return "sold_after", price
    if lower.startswith("sold") or clean(status) == "Sold":
        return "sold", price
    for label in ("withdrawn", "postponed", "unsold", "available"):
        if label in lower:
            return label, None
    return "unknown", None


def discover_auctions(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("past-auction index is not a list")
    found = []
    for item in payload:
        auction_id = clean(item.get("crm_id"))
        auction_date = clean(item.get("auctionDate"))
        if not auction_id or not auction_date or not auction_date[:10].count("-") == 2:
            continue
        if item.get("publish") is False:
            continue
        found.append({
            "auction_id": auction_id,
            "auction_date": auction_date[:10],
            "updated_at": clean(item.get("updatedAt")),
            "summary": item,
        })
    if not found:
        raise ValueError("past-auction index contains no published auctions")
    return sorted(found, key=lambda value: value["auction_date"])



def include_recovered_auctions(indexed: list[dict]) -> list[dict]:
    """Merge retained first-party catalogue pages absent from the live index."""
    found = {item["auction_id"]: item for item in indexed}
    for recovered in RECOVERED_AUCTIONS:
        found.setdefault(recovered["auction_id"], {
            **recovered,
            "summary": None,
            "discovery_basis": "retained first-party past-auction page absent from live index",
        })
    return sorted(found.values(), key=lambda value: value["auction_date"])

def property_url(item: dict) -> str:
    prefix = (
        "/auction-residential-property-for-sale"
        if item.get("department") == "auction_residential"
        else "/auction-commercial-property-for-sale"
    )
    return f"{BASE}{prefix}/{item.get('slug')}-{item.get('id')}/"


def parse_detail(payload: dict, expected: dict, evidence: dict) -> tuple[dict, list[dict]]:
    context = (payload.get("result") or {}).get("pageContext") or {}
    auction_id = clean(context.get("auctionId"))
    properties = context.get("properties")
    if auction_id != expected["auction_id"]:
        raise ValueError(f"wrong auction payload: expected {expected['auction_id']}, saw {auction_id}")
    if not isinstance(properties, list) or not properties:
        raise ValueError("auction payload contains no property rows")

    rows = []
    for position, item in enumerate(properties, 1):
        source_id = clean(item.get("id"))
        extra = item.get("extra") or {}
        lot_number = clean(extra.get("lotNumber")) or clean(item.get("alt_lot_number"))
        auction_date = clean(item.get("auctionDate"))
        if not source_id or not lot_number:
            raise ValueError(f"lot identity missing at source position {position}")
        if not auction_date or auction_date[:10] != expected["auction_date"]:
            raise ValueError(f"auction date mismatch at source position {position}")
        address_text = clean(item.get("display_address"))
        postcode_match = corpus.PC.search(address_text or "")
        postcode = postcode_match.group().upper() if postcode_match else None
        address = address_text if postcode else None
        result_text = clean(extra.get("resultPrice"))
        status, sale_price = status_and_price(item.get("status"), result_text)
        building = item.get("building") or []
        property_type = clean(", ".join(str(value) for value in building))
        description = clean(extra.get("tagline")) or clean(item.get("title"))
        source_auction_id = f"strettons:{auction_id}"
        detail_url = property_url(item)
        row = corpus.base_row(
            "Strettons", source_auction_id, expected["auction_date"],
            lot_number, source_id, detail_url,
        )
        row.update(
            address=address, postcode=postcode, locality=address_text,
            property_type=property_type, description=description,
            sector=corpus.sector(f"{item.get('department') or ''} {property_type or ''} {description or ''}"),
            status=status, sale_price=sale_price,
            guide_price=int(item["price"]) if item.get("price") is not None else None,
            property_id=None,
            identity_method="source_auction_and_embedded_property_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_status_text=clean(item.get("status")),
            source_result_text=result_text, source_result_url=DETAIL.format(auction_id=auction_id),
            source_department=clean(item.get("department")), source_evidence=evidence,
        )
        row["appearance_id"] = f"Strettons|auction:{auction_id}|property:{source_id}"
        rows.append(row)

    identities = [row["source_lot_id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate embedded property identities within auction")
    state = {
        "auctioneer": "Strettons", "source_auction_id": f"strettons:{auction_id}",
        "auction_date": expected["auction_date"], "catalogue_complete": True,
        "source_rows_complete": True, "published_lots_offered": None,
        "visible_source_rows": len(rows), "lots_captured": len(rows),
        "source_url": DETAIL.format(auction_id=auction_id),
        "source_updated_at": expected.get("updated_at"),
        "pagination_reconciled": True, "denominator_reconciled": True,
        "denominator_basis": "all rows in the first-party unpaginated Gatsby pageContext.properties array",
        "completion_scope": "all embedded property rows in the first-party past-auction payload",
        "errors": [], "checked_at": corpus.now(),
    }
    return state, rows


def get_json(url: str) -> tuple[dict | list, bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 100:
        raise ValueError("source response is unexpectedly short")
    return response.json(), raw, response.url


def harvest(workers: int = 4) -> None:
    index, index_raw, index_url = get_json(INDEX)
    index_sha, retrieved_at = corpus.digest(index_raw), corpus.now()
    index_snapshot = corpus.DATA / "sources/strettons" / f"past-auction-index-{index_sha[:16]}.json.gz"
    index_evidence = {
        "source_url": index_url, "retrieved_at": retrieved_at, "sha256": index_sha,
        "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party past-auction index JSON",
    }
    corpus.save_gzip(index_snapshot, {"evidence": index_evidence, "payload": index})
    indexed_auctions = discover_auctions(index)
    auctions = include_recovered_auctions(indexed_auctions)

    path = corpus.DATA / "appearances/strettons/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)

    states, run_rows, pending, failures, reused = {}, [], [], [], 0
    for item in auctions:
        state_path = corpus.DATA / f"auctions/strettons/auction-{item['auction_id']}.json"
        old_state = None
        if state_path.exists():
            try:
                old_state = json.loads(state_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        old_rows = existing_by_auction.get(f"strettons:{item['auction_id']}", [])
        if (old_state and old_state.get("catalogue_complete") and old_rows and
                old_state.get("lots_captured") == len(old_rows) and
                old_state.get("source_updated_at") == item.get("updated_at")):
            states[item["auction_id"]] = old_state
            run_rows.extend(old_rows)
            reused += 1
        else:
            pending.append(item)

    def capture(item: dict):
        url = DETAIL.format(auction_id=item["auction_id"])
        payload, raw, resolved = get_json(url)
        sha, captured_at = corpus.digest(raw), corpus.now()
        snapshot = corpus.DATA / "sources/strettons" / f"auction-{item['auction_id']}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": resolved, "retrieved_at": captured_at, "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated Gatsby page-data payload",
        }
        corpus.save_gzip(snapshot, {"evidence": evidence, "payload": payload})
        state, rows = parse_detail(payload, item, evidence)
        return item["auction_id"], state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        jobs = {pool.submit(capture, item): item for item in pending}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                auction_id, state, rows = future.result()
                corpus.save_json(corpus.DATA / f"auctions/strettons/auction-{auction_id}.json", state)
                states[auction_id] = state
                run_rows.extend(rows)
                print("STRETTONS", len(states), "/", len(auctions), "auctions", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({
                    "auction_id": item["auction_id"], "auction_date": item["auction_date"],
                    "url": DETAIL.format(auction_id=item["auction_id"]),
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("strettons/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": INDEX,
        "live_index_auctions": len(indexed_auctions),
        "recovered_catalogue_seeds": [item["auction_id"] for item in RECOVERED_AUCTIONS],
        "blocked_recovery_evidence": [
            {**item, "reason": "retained HTML survives but first-party page-data payload returns HTTP 404"}
            for item in BLOCKED_RECOVERED_AUCTIONS
        ],
        "auctions_discovered": len(auctions), "auctions_captured": len(states),
        "auctions_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "auctions_reused": reused, "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "index_evidence": index_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "strettons_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    harvest(workers)
