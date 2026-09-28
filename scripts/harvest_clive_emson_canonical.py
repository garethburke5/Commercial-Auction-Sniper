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
    soup = BeautifulSoup(index_html, "lxml")
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
    soup = BeautifulSoup(raw, "lxml")
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
    }


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
    args = parser.parse_args()
    harvest(args.auction_id, args.all_incomplete)
