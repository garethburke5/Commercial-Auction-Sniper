#!/usr/bin/env python3
"""Bank Clive Emson's surviving first-party result cards canonically.

The archive publishes every surviving lot card in one catalogue page.  Those
cards are useful appearances even before a detail page is revisited: they retain
the stable auction/lot identity, locality, headline, outcome and (when shown)
the result or available price.  Street addresses remain null until evidenced;
town names are never promoted to addresses.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import historical_corpus as corpus


BASE = "https://www.cliveemson.co.uk"
INDEX = BASE + "/future/results/"
HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper historical research (+public Clive Emson results)",
    "Accept": "text/html,application/xhtml+xml",
}
MONTHS = "January February March April May June July August September October November December"
DATE_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS.replace(' ', '|')})\s+(20\d{{2}})\b", re.I)
LOT_PATH_RE = re.compile(r"^/properties/(\d+)/(\d+[A-Za-z]?)/?$", re.I)


def session():
    value = requests.Session()
    value.headers.update(HEADERS)
    return value


def get(client, url):
    response = client.get(url, timeout=45)
    response.raise_for_status()
    return response.url, response.content


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_date(text):
    match = DATE_RE.search(clean(text))
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def discover(index_html):
    soup = BeautifulSoup(index_html, "html.parser")
    auctions = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(BASE, link["href"])
        match = re.fullmatch(rf"{re.escape(BASE)}/properties/(\d+)/?", href.rstrip("/") + "/")
        if not match:
            continue
        item = link.find_parent("li")
        label = clean(item.find("b").get_text(" ", strip=True)) if item and item.find("b") else None
        span = clean(item.find("span").get_text(" ", strip=True)) if item and item.find("span") else None
        extent = re.search(r"Lots?\s+(\d+)\s*[-–]\s*(\d+)", span or "", re.I)
        auction_id = match.group(1)
        auctions[auction_id] = {
            "auction_id": auction_id,
            "url": f"{BASE}/properties/{auction_id}/",
            "archive_label": label,
            "published_first_lot": int(extent.group(1)) if extent else None,
            "published_last_lot": int(extent.group(2)) if extent else None,
        }
    return sorted(auctions.values(), key=lambda row: int(row["auction_id"]), reverse=True)


def normalize_status(value):
    value = clean(value).lower()
    if not value:
        return "unknown"
    if value.startswith(("available in our", "re-entered into")) or value.endswith(" auction"):
        return "reoffered"
    return value


def visible_price(card):
    box = card.select_one(".statusBox")
    if not box:
        return None
    strong = box.find("strong")
    if not strong:
        return None
    match = re.search(r"£\s*([\d,]+(?:\.\d+)?)", strong.get_text(" ", strip=True))
    return corpus.money(match.group(1)) if match else None


def image_url(auction_id, card):
    name = clean(card.get("data-mainpic"))
    if not name:
        return None
    # The public HTML stores filenames already percent-escaped. Preserve escapes
    # and encode only genuinely unsafe characters.
    return f"{BASE}/Auc{auction_id}/pics/{quote(name, safe='/%') }"


def parse_catalogue(raw, auction, evidence):
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    heading = soup.find("h1")
    date = parse_date(title) or parse_date(heading.get_text(" ", strip=True) if heading else "")
    if not date:
        raise ValueError("catalogue page has no evidenced auction date")

    link_lots = set()
    for link in soup.find_all("a", href=True):
        path = requests.utils.urlparse(urljoin(BASE, link["href"])).path
        match = LOT_PATH_RE.fullmatch(path)
        if match and match.group(1) == auction["auction_id"]:
            link_lots.add(match.group(2).upper())

    rows = []
    seen = set()
    for card in soup.select("div.lot[data-lot]"):
        lot = clean(card.get("data-lot")).upper()
        if not lot or lot == "0" or lot in seen:
            continue
        link = None
        match = None
        for candidate in card.find_all("a", href=True):
            path = requests.utils.urlparse(urljoin(BASE, candidate["href"])).path
            candidate_match = LOT_PATH_RE.fullmatch(path)
            if candidate_match and candidate_match.group(1) == auction["auction_id"] and candidate_match.group(2).upper() == lot:
                link, match = candidate, candidate_match
                break
        if not link or not match:
            continue
        seen.add(lot)
        url = urljoin(BASE, link["href"])
        headline = clean(card.get("data-cathead"))
        if not headline:
            node = card.select_one(".LotHeading")
            headline = clean(node.get_text(" ", strip=True) if node else None)
        locality = clean(card.get("data-loc"))
        if not locality:
            node = card.select_one(".LotLocation")
            locality = clean(node.get_text(" ", strip=True) if node else None)
        source_status = clean(card.get("data-ceastatus"))
        status = normalize_status(source_status)
        if status == "unknown":
            box = card.select_one(".statusBox")
            source_status = clean(box.get_text(" ", strip=True) if box else None)
            status = normalize_status(source_status)
        price = visible_price(card)
        row = corpus.base_row("Clive Emson", "clive-emson:" + auction["auction_id"], date, lot, lot, url)
        row.update(
            locality=locality or None,
            property_type=headline or None,
            description=headline or None,
            sector=corpus.sector(headline),
            status=status,
            record_quality="partial_lot",
            source_evidence=evidence,
            source_status_text=source_status or None,
        )
        if price and status.startswith("sold"):
            row["sale_price"] = price
        elif price and status.startswith("available"):
            row["available_price"] = price
        image = image_url(auction["auction_id"], card)
        if image:
            row["image_urls"] = [image]
        rows.append(row)

    if not link_lots:
        raise ValueError("catalogue page exposes zero lot links")
    if not rows:
        raise ValueError("catalogue page exposes lot links but zero parseable lot cards")
    suffixes = sorted(lot for lot in seen if not lot.isdigit())
    numeric = {int(lot) for lot in seen if lot.isdigit()}
    first = auction.get("published_first_lot")
    last = auction.get("published_last_lot")
    gaps = sorted(set(range(first or 1, (last or max(numeric, default=0)) + 1)) - numeric)
    complete = bool(rows) and seen == link_lots and len(rows) == len(seen)
    reconciliation = {
        "auction_date": date,
        "published_numbering_extent": [first, last],
        "surviving_distinct_lot_links": len(link_lots),
        "captured_lot_rows": len(rows),
        "numbering_gaps": gaps,
        "suffix_lot_numbers": suffixes,
        "pagination_pages_captured": [1],
        "pagination_pages_expected": 1,
        "catalogue_complete": complete,
    }
    return rows, reconciliation


def state_path(auction_id):
    return corpus.DATA / "auctions/clive-emson" / f"{auction_id}.json"


def is_complete(auction_id):
    try:
        return bool(json.loads(state_path(auction_id).read_text()).get("catalogue_complete"))
    except (OSError, ValueError, TypeError):
        return False


def collection_summary(auctions):
    states = []
    for auction in auctions:
        try:
            states.append(json.loads(state_path(auction["auction_id"]).read_text()))
        except (OSError, ValueError, TypeError):
            pass
    complete = [state for state in states if state.get("catalogue_complete")]
    enriched = 0
    partial = 0
    for auction in auctions:
        shard = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
        if not shard.exists():
            continue
        for row in corpus.iter_rows(shard):
            enriched += bool(row.get("address"))
            partial += not bool(row.get("address"))
    return {
        "checked_at": corpus.now(),
        "auctions_discovered": len(auctions),
        "catalogue_states_present": len(states),
        "catalogues_complete": len(complete),
        "surviving_lot_rows": sum(int(state.get("lots_captured") or 0) for state in states),
        "incomplete_auction_ids": [a["auction_id"] for a in auctions if not is_complete(a["auction_id"])],
        "first_auction_date": min((s.get("auction_date") for s in states if s.get("auction_date")), default=None),
        "last_auction_date": max((s.get("auction_date") for s in states if s.get("auction_date")), default=None),
        "complete": bool(auctions) and len(complete) == len(auctions),
        "detail_rows_enriched": enriched,
        "detail_rows_remaining": partial,
    }


def synchronize_detail_states(auctions):
    """Keep per-auction detail counts aligned with the canonical shards.

    Another evidenced source can fill an address (for example an official
    addendum after a detail URL disappears), so state must be derived from the
    shard rather than only from the most recent detail-page request batch.
    """
    for auction in auctions:
        shard = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
        state_file = state_path(auction["auction_id"])
        if not shard.exists() or not state_file.exists():
            continue
        rows = list(corpus.iter_rows(shard))
        state = json.loads(state_file.read_text())
        state["detail_rows_enriched"] = sum(bool(row.get("address")) for row in rows)
        state["detail_rows_remaining"] = sum(not bool(row.get("address")) for row in rows)
        state["detail_enrichment_complete"] = not state["detail_rows_remaining"]
        if state["detail_enrichment_complete"]:
            state["detail_enrichment_errors"] = []
        corpus.save_json(state_file, state)


def detail_fields(raw, expected_auction_id, expected_lot, expected_date):
    """Parse one official lot page, refusing cross-auction or guessed identity."""
    soup = BeautifulSoup(raw, "html.parser")
    header = soup.select_one(".lotDetailsHeader")
    h1 = header.find("h1") if header else None
    h2 = header.find("h2") if header else None
    if not h1 or not h2:
        raise ValueError("detail page has no lot header/address")
    lot_match = re.search(r"\bLot\s+(\d+[A-Za-z]?)\b", h1.get_text(" ", strip=True), re.I)
    lot = lot_match.group(1).upper() if lot_match else None
    date = parse_date(h1.get_text(" ", strip=True))
    if lot != str(expected_lot).upper():
        raise ValueError(f"detail lot {lot!r} does not match {expected_lot!r}")
    if date != expected_date:
        raise ValueError(f"detail date {date!r} does not match {expected_date!r}")
    title_identity = clean(h1.get("title"))
    identity = title_identity.split("/", 1)[1] if "/" in title_identity else None
    address = clean(h2.get_text(" ", strip=True))
    if not address or address.lower().startswith(("key features", "location", "accommodation")):
        raise ValueError("detail page has no published street address")
    params = {}
    for cell in soup.select(".lotParams .row > div"):
        label_node = cell.find("span")
        if not label_node:
            continue
        label = clean(label_node.get_text(" ", strip=True)).lower()
        text = clean(cell.get_text(" ", strip=True))
        value = clean(text[len(clean(label_node.get_text(" ", strip=True))):])
        params[label] = value or None
    title_parts = [clean(node.get_text(" ", strip=True)) for node in h1.find_all("span")]
    headline = title_parts[1] if len(title_parts) > 1 else None
    detail = soup.select_one(".lotPropertyDetails")
    description = clean(detail.get_text(" ", strip=True)) if detail else None
    box = header.select_one(".statusBox")
    status_text = clean(box.get_text(" ", strip=True)) if box else None
    status = normalize_status(status_text)
    price = visible_price(header)
    images = []
    for node in soup.select("[data-hires]"):
        url = urljoin(BASE, node.get("data-hires"))
        if url and url not in images:
            images.append(url)
    postcode = corpus.PC.search(address)
    return {
        "source_property_id": identity,
        "address": address,
        "postcode": postcode.group().upper() if postcode else None,
        "property_type": params.get("category") or headline,
        "tenure": params.get("tenure"),
        "description": description or headline,
        "sector": corpus.sector(" ".join(filter(None, [params.get("category"), headline, description]))),
        "status": status,
        "sale_price": price if price and status.startswith("sold") else None,
        "available_price": price if price and status.startswith("available") else None,
        "image_urls": images,
        "source_status_text": status_text,
    }


def enrich_one(row):
    response = requests.get(row["original_url"], headers=HEADERS, timeout=45)
    response.raise_for_status()
    raw = response.content
    fields = detail_fields(raw, row["source_auction_id"].split(":")[-1], row["lot_number"], row["auction_date"])
    auction_id = row["source_auction_id"].split(":")[-1]
    snapshot = corpus.DATA / "sources/clive-emson/details" / auction_id / f"{row['lot_number']}-{corpus.digest(raw)[:16]}.json.gz"
    evidence = {
        "source_url": response.url,
        "snapshot_path": str(snapshot.relative_to(ROOT)),
        "sha256": corpus.digest(raw),
        "retrieved_at": corpus.now(),
        "basis": "official Clive Emson lot detail page",
    }
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return row["appearance_id"], fields, evidence


def enrich_auction(auction_id, workers=4):
    shard = corpus.DATA / "appearances/clive-emson" / f"{auction_id}.jsonl.gz"
    state_file = state_path(auction_id)
    if not shard.exists() or not state_file.exists():
        raise SystemExit(f"Clive Emson auction {auction_id} is not banked")
    rows = {row["appearance_id"]: row for row in corpus.iter_rows(shard)}
    selected = [row for row in rows.values() if not row.get("address")]
    failures = []
    enriched = 0
    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as executor:
        jobs = {executor.submit(enrich_one, row): row for row in selected}
        for future in as_completed(jobs):
            original = jobs[future]
            try:
                appearance_id, fields, evidence = future.result()
                row = rows[appearance_id]
                for field, value in fields.items():
                    if value not in (None, "", []):
                        row[field] = value
                row["record_quality"] = "address_record"
                additional = list(row.get("additional_source_evidence") or [])
                if not any(item.get("snapshot_path") == evidence["snapshot_path"] for item in additional):
                    additional.append(evidence)
                row["additional_source_evidence"] = additional
                enriched += 1
            except Exception as exc:
                failures.append({"appearance_id": original["appearance_id"], "url": original["original_url"],
                                 "error": f"{type(exc).__name__}: {exc}"})
            processed += 1
            if processed % 25 == 0 or processed == len(jobs):
                print(json.dumps({
                    "auction_id": str(auction_id),
                    "detail_rows_processed": processed,
                    "detail_rows_selected": len(jobs),
                    "run_detail_rows_enriched": enriched,
                    "run_detail_failures": len(failures),
                }), flush=True)
    corpus.write_rows(f"clive-emson/{auction_id}", list(rows.values()))
    state = json.loads(state_file.read_text())
    state.update({
        "detail_rows_enriched": sum(bool(row.get("address")) for row in rows.values()),
        "detail_rows_remaining": sum(not bool(row.get("address")) for row in rows.values()),
        "detail_enrichment_complete": all(bool(row.get("address")) for row in rows.values()),
        "detail_enrichment_errors": failures,
        "detail_enrichment_checked_at": corpus.now(),
    })
    corpus.save_json(state_file, state)
    index_url, index_raw = get(session(), INDEX)
    auctions = discover(index_raw)
    synchronize_detail_states(auctions)
    summary = collection_summary(auctions)
    summary.update({"run_detail_rows_enriched": enriched, "run_detail_failures": failures})
    corpus.save_json(corpus.DATA / "clive_emson_collection.json", summary)
    report = corpus.build_database()
    print(json.dumps({
        "auction_id": str(auction_id), "selected": len(selected), "enriched": enriched,
        "failures": len(failures), "records_with_address": report["records_with_address"],
        "partial_lot_records": report["partial_lot_records"],
    }, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


def next_enrichment_auction():
    candidates = []
    for path in sorted((corpus.DATA / "appearances/clive-emson").glob("*.jsonl.gz"), key=lambda p: int(p.stem.split(".")[0])):
        auction_id = path.stem.split(".")[0]
        partial_ids = {row["appearance_id"] for row in corpus.iter_rows(path) if not row.get("address")}
        if not partial_ids:
            continue
        terminal_failures = set()
        try:
            state = json.loads(state_path(auction_id).read_text())
        except (OSError, ValueError, TypeError):
            state = {}
        for failure in state.get("detail_enrichment_errors") or []:
            error = str(failure.get("error") or "")
            if "detail date" in error or "detail lot" in error:
                terminal_failures.add(failure.get("appearance_id"))
        if partial_ids - terminal_failures:
            candidates.append(auction_id)
    return candidates[0] if candidates else None


def harvest(selected_id=None, all_incomplete=False):
    client = session()
    index_url, index_raw = get(client, INDEX)
    auctions = discover(index_raw)
    if not auctions:
        raise SystemExit("Clive Emson results index exposed zero auctions")
    index_snapshot = corpus.DATA / "sources/clive-emson" / f"index-{corpus.digest(index_raw)[:16]}.json.gz"
    corpus.save_gzip(index_snapshot, {
        "source_url": index_url, "retrieved_at": corpus.now(),
        "sha256": corpus.digest(index_raw), "html": index_raw.decode("utf-8", "replace"),
    })
    if selected_id:
        selected = [auction for auction in auctions if auction["auction_id"] == str(selected_id)]
        if not selected:
            raise SystemExit(f"Auction {selected_id} is not present in the public results index")
    elif all_incomplete:
        selected = [auction for auction in auctions if not is_complete(auction["auction_id"])]
    else:
        selected = auctions

    before = json.loads((corpus.DATA / "progress.json").read_text())
    added = []
    failures = []
    for auction in selected:
        try:
            final_url, raw = get(client, auction["url"])
            snapshot = corpus.DATA / "sources/clive-emson" / f"{auction['auction_id']}-{corpus.digest(raw)[:16]}.json.gz"
            evidence = {
                "source_url": final_url,
                "source_index_url": index_url,
                "snapshot_path": str(snapshot.relative_to(ROOT)),
                "index_snapshot_path": str(index_snapshot.relative_to(ROOT)),
                "sha256": corpus.digest(raw),
                "retrieved_at": corpus.now(),
                "basis": "all distinct lot cards in the surviving unpaginated official result catalogue",
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
            rows, reconciliation = parse_catalogue(raw, auction, evidence)
            path = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
            existing = {row["appearance_id"] for row in corpus.iter_rows(path)} if path.exists() else set()
            corpus.write_rows(f"clive-emson/{auction['auction_id']}", rows)
            added.extend(row for row in rows if row["appearance_id"] not in existing)
            state = {
                "auctioneer": "Clive Emson",
                "source_auction_id": "clive-emson:" + auction["auction_id"],
                "source_url": final_url,
                "auction_id": auction["auction_id"],
                "auction_date": reconciliation.pop("auction_date"),
                "lots_captured": len(rows),
                **reconciliation,
                "completion_scope": "all surviving official result-card rows; street-address detail enrichment remains separate",
                "appearance_ids": [row["appearance_id"] for row in rows],
                "errors": [] if reconciliation["catalogue_complete"] else ["Visible lot-card/link reconciliation failed"],
                "checked_at": corpus.now(),
            }
            corpus.save_json(state_path(auction["auction_id"]), state)
            print(f"BANKED Clive Emson {auction['auction_id']} {len(rows)} rows complete={state['catalogue_complete']}", flush=True)
        except Exception as exc:
            failures.append({"auction_id": auction["auction_id"], "url": auction["url"], "error": f"{type(exc).__name__}: {exc}"})
            print("FAILED", failures[-1], flush=True)
        time.sleep(0.15)

    summary = collection_summary(auctions)
    summary.update({
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_by_sector": dict(Counter(row.get("sector") for row in added)),
        "failures": failures,
    })
    corpus.save_json(corpus.DATA / "clive_emson_collection.json", summary)
    report = corpus.build_database()
    print(json.dumps({
        "baseline_appearances": before["individual_lot_records_captured"],
        "persisted_appearances": report["individual_lot_records_captured"],
        **summary,
    }, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--auction-id")
    mode.add_argument("--all-incomplete", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--enrich-auction")
    mode.add_argument("--enrich-next", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.enrich_auction:
        enrich_auction(args.enrich_auction, args.workers)
    elif args.enrich_next:
        target = next_enrichment_auction()
        if target:
            enrich_auction(target, args.workers)
        else:
            print("All banked Clive Emson detail rows already have addresses", flush=True)
    else:
        harvest(args.auction_id, args.all_incomplete)
