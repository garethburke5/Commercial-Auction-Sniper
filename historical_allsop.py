"""Resumable capture of every past lot in Allsop's public search corpus."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import re
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import historical_corpus as h

BASE = "https://www.allsop.co.uk"
LONDON = ZoneInfo("Europe/London")


def epoch_day(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        instant = datetime.fromtimestamp(float(value) / 1000, timezone.utc)
    else:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=LONDON)
    return instant.astimezone(LONDON).date().isoformat()


def reference_day(value):
    """Return the catalogue day encoded in Allsop's stable R/CYYMMDD reference."""
    match = re.match(r"^[RC](\d{2})(\d{2})(\d{2})(?:\s|$)", h.clean(value), re.I)
    if not match:
        return None
    year = 2000 + int(match.group(1))
    try:
        return datetime(year, int(match.group(2)), int(match.group(3))).date().isoformat()
    except ValueError:
        return None


def auction_day(raw):
    return reference_day(raw.get("allsop_auctionreference")) or epoch_day(raw.get("allsop_auctiondate"))


def lot_url(raw):
    title = h.plain(raw.get("allsop_propertybyline") or raw.get("property_byline")) or "property"
    town = h.clean(raw.get("allsop_propertytown") or raw.get("town"))
    slug = re.sub(r"\s+", "-", re.sub(r"[^a-zA-Z0-9\s]", "", title + " in " + town)).lower()
    reference = h.clean(raw.get("allsop_name") or raw.get("reference")).lower().replace(" ", "-")
    return f"{BASE}/lot-overview/{slug}/{reference}"


def convert(raw, evidence):
    """Convert one public search record, preserving residential lots too."""
    lot_id = h.clean(raw.get("allsop_lotid"))
    auction_id = h.clean(raw.get("allsop_auctionid"))
    lot_number = h.clean(raw.get("lot_number_text") or raw.get("allsop_lotnumber"))
    auction_date = reference_day(raw.get("reference") or raw.get("allsop_name")) or epoch_day(raw.get("auction_date"))
    address = h.plain(raw.get("full_address") or raw.get("allsop_address"))
    searchable = " ".join(h.clean(raw.get(k)) for k in
                          ("full_address", "allsop_address", "allsop_propertybyline", "property_byline"))
    if not lot_id or not auction_id or not auction_date:
        return None, "missing stable lot, auction or date identity"
    if lot_number in ("", "0"):
        return None, "unnumbered or lot-zero section/test record"
    if not address:
        return None, "no published property address"
    if re.match(r"^\s*TEST(?:\s|\d|[-_:])", searchable, re.I):
        return None, "explicit test record"
    url = lot_url(raw)
    row = h.base_row("Allsop", "allsop:" + auction_id, auction_date, lot_number, lot_id, url)
    row["address"] = address
    postcode = h.clean(raw.get("postcode") or raw.get("allsop_propertypostcode"))
    if h.PC.fullmatch(postcode):
        row["postcode"] = postcode.upper()
    elif match := h.PC.search(address):
        row["postcode"] = match.group().upper()
    row["locality"] = h.clean(raw.get("town") or raw.get("allsop_propertytown")) or None
    types = raw.get("property_types") or raw.get("allsop_propertytype") or []
    types = [types] if isinstance(types, str) else types
    row["property_type"] = " / ".join(h.clean(x) for x in types if h.clean(x)) or None
    row["tenure"] = h.plain(raw.get("property_tenure") or raw.get("allsop_propertytenure"))
    byline = h.plain(raw.get("property_byline") or raw.get("allsop_propertybyline"))
    features = raw.get("features") or []
    features = [features] if isinstance(features, str) else features
    row["description"] = ". ".join(x for x in [byline, *(h.plain(v) for v in features)] if x) or None
    row["sector"] = h.sector(" ".join(x or "" for x in (row["property_type"], row["description"])),
                             bool(raw.get("is_residential")), bool(raw.get("is_commercial")))
    row["guide_price"] = h.money(raw.get("guide_price_lower"))
    row["guide_price_high"] = h.money(raw.get("guide_price_upper"))
    status = h.clean(raw.get("lot_status") or raw.get("allsop_lotstatus")).lower() or "unknown"
    row["status"] = status
    if "sold" in status:
        row["sale_price"] = h.money(raw.get("sale_price"))
    row["available_price"] = h.money(raw.get("available_at_price"))
    row["annual_rent"] = h.money(raw.get("current_rent_per_annum") or raw.get("income"))
    row["rent_text"] = h.plain(raw.get("current_rent_per_annum_text"))
    row["lease_information"] = h.plain(raw.get("type_tenancy") or raw.get("property_tenancy"))
    row["yield"] = raw.get("yield") or None
    image_id = h.clean(raw.get("featured_image_file_id") or raw.get("image_file_id"))
    if image_id:
        row["image_urls"] = [f"{BASE}/api/image/{image_id}/884/497"]
    row["legal_pack_url"] = url + "#legal"
    row["source_reference"] = h.clean(raw.get("reference") or raw.get("allsop_name")) or None
    row["source_evidence"] = evidence
    row["record_quality"] = "address_record"
    return row, None


def harvest(workers=4, page_size=1000):
    manifest_url = f"{BASE}/api/auctions/all-past"
    manifest_response = h.fetch(manifest_url)
    manifest = json.loads(manifest_response.text)["auction"]
    # Commercial is the priority corpus. Residential remains fully retained, but
    # commercial UUIDs are attempted first so a resumable/rate-limited run makes
    # the highest-value progress before moving through older residential shells.
    manifest_rows = [row for department in ("commercial", "residential") for row in manifest.get(department, [])]
    manifest_ids = [h.clean(row.get("allsop_auctionid")) for row in manifest_rows]
    if not manifest_rows or len(set(manifest_ids)) != len(manifest_rows):
        raise ValueError("Allsop past-auction manifest is empty or has duplicate auction IDs")
    manifest_snapshot = h.DATA / "sources" / "allsop" / "past-auctions.json.gz"
    manifest_evidence = {"source_url": manifest_url, "retrieved_at": h.now(),
                         "response_sha256": h.digest(manifest_response.content),
                         "snapshot_path": str(manifest_snapshot.relative_to(h.ROOT))}
    h.save_gzip(manifest_snapshot, {**manifest_evidence, "auctions": manifest})
    today = datetime.now(LONDON).date().isoformat()
    def is_test_auction(row):
        label = " ".join(h.clean(row.get(k)) for k in ("allsop_auctionreference", "allsop_name"))
        return bool(re.search(r"(?:^|\W)test(?:\W|$)", label, re.I))

    rejected = [row for row in manifest_rows if is_test_auction(row)]
    targets = [row for row in manifest_rows if not is_test_auction(row) and auction_day(row) <= today]
    # Remove previously generated canonical rows/states if an auction is later identified
    # as an explicit test. Raw snapshots remain preserved as provenance.
    for row in rejected:
        auction_id = h.clean(row.get("allsop_auctionid"))
        (h.DATA / "appearances" / "allsop" / (auction_id + ".jsonl.gz")).unlink(missing_ok=True)
        (h.DATA / "auctions" / "allsop" / (auction_id + ".json")).unlink(missing_ok=True)

    def page(auction_id, n):
        url = f"{BASE}/api/search?" + urlencode({"auction_id": auction_id, "size": page_size, "page": n})
        snapshot = h.DATA / "sources" / "allsop" / auction_id / f"page-{n}.json.gz"
        if snapshot.exists():
            saved = h.read_gzip(snapshot)
            if saved.get("page") == n and saved.get("page_size") == page_size and isinstance(saved.get("results"), list):
                ev = {k: saved[k] for k in ("source_url", "retrieved_at", "response_sha256", "snapshot_path")}
                return int(saved["total"]), saved["results"], ev
        last_error = None
        for attempt in range(4):
            try:
                response = h.fetch(url)
                data = json.loads(response.text)["data"]
                if data == []:
                    rows, total = [], 0
                else:
                    rows, total = data["results"], int(data["total"])
                if not isinstance(rows, list) or len(rows) > page_size:
                    raise ValueError("Invalid Allsop auction search page shape")
                if any(h.clean(row.get("allsop_auctionid")) != auction_id for row in rows):
                    raise ValueError("Auction-filtered search returned a row from another auction")
                ev = {"source_url": url, "retrieved_at": h.now(), "response_sha256": h.digest(response.content),
                      "snapshot_path": str(snapshot.relative_to(h.ROOT))}
                h.save_gzip(snapshot, {**ev, "auction_id": auction_id, "page": n,
                                       "page_size": page_size, "total": total, "results": rows})
                return total, rows, ev
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(2 ** attempt)
        raise last_error

    def catalogue(auction):
        auction_id = h.clean(auction["allsop_auctionid"])
        expected, rows, evidence = page(auction_id, 1)
        pages_expected = math.ceil(expected / page_size) if expected else 1
        by_id, evidence_by_id = {}, {}
        for n in range(1, pages_expected + 1):
            if n > 1:
                total, rows, evidence = page(auction_id, n)
                if total != expected:
                    raise ValueError(f"Auction total changed from {expected} to {total}")
            for raw in rows:
                lot_id = h.clean(raw.get("allsop_lotid"))
                if not lot_id or lot_id in by_id:
                    raise ValueError("Missing or duplicate stable lot ID within auction")
                by_id[lot_id], evidence_by_id[lot_id] = raw, evidence
        if len(by_id) != expected:
            raise ValueError(f"Auction count mismatch: {len(by_id)}/{expected}")
        kept, excluded = [], []
        for lot_id, raw in by_id.items():
            row, reason = convert(raw, evidence_by_id[lot_id])
            if row is None:
                excluded.append({"source_lot_id": lot_id, "reason": reason})
            else:
                kept.append(row)
        reconciled = len(kept) + len(excluded) == expected
        if kept:
            h.write_rows("allsop/" + auction_id, kept)
            h.save_json(h.DATA / "auctions" / "allsop" / (auction_id + ".json"), {
                "auctioneer": "Allsop", "source_auction_id": "allsop:" + auction_id,
                "auction_date": auction_day(auction),
                "auction_name": h.clean(auction.get("allsop_name") or auction.get("allsop_auctionreference")) or None,
                "catalogue_complete": reconciled,
                "completion_scope": "all rows for this UUID in the public Allsop past-auction manifest and search API",
                "lots_captured": len(kept), "raw_records_observed": len(by_id),
                "expected_raw_records": expected, "pages_expected": pages_expected,
                "pages_captured": pages_expected, "excluded_non_properties": excluded,
                "errors": [], "checked_at": h.now()})
        return {"auction_id": auction_id, "expected": expected, "captured": len(kept),
                "excluded": len(excluded), "complete": reconciled, "has_lots": bool(kept)}

    results, failures = [], []

    def checkpoint():
        banked = [json.loads(path.read_text())
                  for path in sorted((h.DATA / "auctions" / "allsop").glob("*.json"))]
        state = {"checked_at": h.now(), "past_auction_manifest_count": len(targets),
                 "catalogues_checked": len(results) + len(failures),
                 "catalogues_with_property_lots": len(banked),
                 "catalogues_complete": sum(bool(x.get("catalogue_complete")) for x in banked),
                 "past_property_lots_captured": sum(int(x.get("lots_captured") or 0) for x in banked),
                 "raw_records_observed": sum(int(x.get("raw_records_observed") or 0) for x in banked),
                 "excluded_non_properties": sum(len(x.get("excluded_non_properties") or []) for x in banked),
                 "manifest_evidence": manifest_evidence, "failures": failures,
                 "complete": len(results) == len(targets) and not failures}
        h.save_json(h.DATA / "allsop_collection.json", state)
        return state

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        jobs = {executor.submit(catalogue, auction): auction for auction in targets}
        for future in as_completed(jobs):
            auction = jobs[future]
            try:
                result = future.result()
                results.append(result)
                print("ALLSOP_AUCTION", len(results), "/", len(targets), result["captured"],
                      auction_day(auction), flush=True)
            except Exception as exc:
                failures.append({"auction_id": auction.get("allsop_auctionid"),
                                 "auction_date": auction_day(auction),
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
            if (len(results) + len(failures)) % 5 == 0:
                checkpoint()

    state = checkpoint()
    print(json.dumps(state, indent=2), flush=True)
    if failures:
        raise RuntimeError("Some Allsop catalogues failed; successful catalogues were checkpointed")
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    harvest(args.workers)
