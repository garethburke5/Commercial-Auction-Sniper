"""Bank complete public Auction House London catalogue pages."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from datetime import date
import json
import re
from urllib.parse import urljoin

from historical_corpus import (
    DATA, PC, base_row, build_database, clean, digest, fetch, money,
    now, plain, save_gzip, save_json, sector, write_rows,
)

ROOT_URL = "https://auctionhouselondon.co.uk"
ARCHIVE_URL = ROOT_URL + "/past-auctions"
SITEMAP_URL = ROOT_URL + "/sitemap.xml"


def next_payload(text):
    chunks = []
    pattern = r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)'
    for match in re.finditer(pattern, text, re.S):
        chunks.append(json.loads(match.group(1)))
    return "".join(chunks)


def embedded_auction(payload):
    marker = '"auction":'
    for match in re.finditer(re.escape(marker), payload):
        try:
            value = json.JSONDecoder().raw_decode(payload, match.end())[0]
        except (json.JSONDecodeError, TypeError):
            continue
        if (isinstance(value, dict) and value.get("slug")
                and isinstance(value.get("lots"), list)):
            return value
    raise ValueError("Missing embedded auction object")


def auction_page(route, refresh=False):
    route_slug = route.rstrip("/").rsplit("/", 1)[-1]
    state_path = DATA / "auctions" / "auction_house_london" / (route_slug + ".json")
    if state_path.exists() and not refresh:
        saved = json.loads(state_path.read_text())
        if saved.get("catalogue_complete"):
            saved["already_banked"] = True
            return saved
    url = urljoin(ROOT_URL, route)
    response = fetch(url)
    auction = embedded_auction(next_payload(response.text))
    lots = auction.get("lots") or []
    expected = auction.get("lotsTotal")
    if not auction.get("slug") or not auction.get("dayOneDate"):
        raise ValueError("Missing auction identity/date")
    if expected is None or len(lots) != int(expected):
        raise ValueError(f"Catalogue reconciliation failed: {len(lots)} != {expected}")
    if len({lot.get("slug") for lot in lots}) != len(lots) or any(not lot.get("slug") for lot in lots):
        raise ValueError("Missing or duplicate source lot slug")
    auction_date = auction["dayOneDate"][:10]
    if auction_date > date.today().isoformat():
        return {"future": True, "source_url": url, "auction_date": auction_date,
                "source_auction_id": "ahl:" + auction["slug"]}
    key = "auction_house_london/" + auction["slug"]
    snapshot = DATA / "sources" / key / "catalogue.json.gz"
    evidence = {
        "source_url": url, "retrieved_at": now(),
        "response_sha256": digest(response.content),
        "snapshot_path": str(snapshot.relative_to(DATA.parent.parent)),
    }
    public = {
        k: auction.get(k) for k in (
            "id", "slug", "dayOneDate", "additionalSessions", "formattedDate",
            "lotsNumber", "lotsSold", "lotsTotal", "percentageSold", "totalRaised"
        )
    }
    save_gzip(snapshot, {**evidence, "auction": public, "lots": lots})
    rows = []
    for lot in lots:
        detail = urljoin(ROOT_URL, "/lot/" + lot["slug"])
        row = base_row("Auction House London", "ahl:" + auction["slug"], auction_date,
                       lot.get("lotNumber"), lot["slug"], detail)
        address = plain(lot.get("fullAddress"))
        result = clean(lot.get("resultPrice"))
        status_type = clean(lot.get("soldStatusType")).lower()
        status_stage = clean(lot.get("soldStatusStage")).lower()
        row.update(
            address=address, property_type=plain(lot.get("propertyType")),
            tenure=plain(lot.get("tenureType")), guide_price=money(lot.get("guidePrice")),
            description=plain(lot.get("tagline")), legal_pack_url=lot.get("legalDocumentUrl"),
            image_urls=[lot["image"]] if lot.get("image") else [],
            status=("sold prior" if status_stage == "prior" and status_type == "sold"
                    else status_type or "unknown"),
            record_quality="address_record" if address else "partial_lot",
        )
        if address and (match := PC.search(address)):
            row["postcode"] = match.group().upper()
        row["sector"] = sector(" ".join(str(v or "") for v in
                                (lot.get("propertyCategory"), lot.get("propertyType"),
                                 lot.get("tagline"))))
        if match := re.search(r"£\s*([\d,]+)", result):
            row["sale_price"] = money(match.group(1))
        row["result_text"] = result or None
        row["source_evidence"] = evidence
        rows.append(row)
    captured = write_rows(key, rows)
    state = {
        "auctioneer": "Auction House London", "source_auction_id": "ahl:" + auction["slug"],
        "auction_date": auction_date, "auction_name": plain(auction.get("formattedDate")),
        "catalogue_complete": captured == int(expected),
        "completion_scope": "all lot rows in the surviving public catalogue page",
        "lots_captured": captured, "expected_raw_records": int(expected),
        "pages_expected": 1, "pages_captured": 1, "errors": [], "checked_at": now(),
    }
    save_json(DATA / "auctions" / (key + ".json"), state)
    return state


def discover_routes(years=None):
    """Discover historical result routes retained in the first-party sitemap."""
    routes = set()
    for response in (fetch(ARCHIVE_URL), fetch(SITEMAP_URL)):
        routes.update(re.findall(r'href="/auction/([^"]+)"', response.text))
        routes.update(re.findall(
            r'<loc>https://auctionhouselondon\.co\.uk/auction/([^<]+)</loc>',
            response.text,
        ))
    if years:
        routes = {route for route in routes if any(route.endswith(str(year)) for year in years)}
    return ["/auction/" + route for route in sorted(routes)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="*", type=int)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    routes = discover_routes(set(args.years or []))
    if not routes:
        raise SystemExit("No Auction House London catalogue routes discovered")
    states = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = {executor.submit(auction_page, route, args.refresh): route for route in routes}
        for future in as_completed(jobs):
            state = future.result()
            if state.get("future"):
                print("AHL future", state["source_auction_id"], state["auction_date"], flush=True)
                continue
            states.append(state)
            print("AHL", state["source_auction_id"], state["lots_captured"], flush=True)
    if any(not state["catalogue_complete"] for state in states):
        raise SystemExit("Auction House London catalogue reconciliation failed")
    all_states = []
    for path in (DATA / "auctions" / "auction_house_london").glob("*.json"):
        state = json.loads(path.read_text())
        if state.get("catalogue_complete"):
            all_states.append(state)
    save_json(DATA / "auction_house_london_collection.json", {
        "checked_at": now(), "catalogues_captured": len(all_states),
        "lots_captured": sum(s["lots_captured"] for s in all_states),
        "catalogues_complete": True, "source_url": ARCHIVE_URL,
        "discovery_url": SITEMAP_URL,
    })
    build_database()


if __name__ == "__main__":
    main()
