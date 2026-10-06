"""Bank complete, evidenced BidX1 UK historical auction catalogues.

Each seed is a first-party auction ID with its own filtered result set. The
collector reconciles the published result count to stable property links and
requires every detail page before marking that auction complete. Individual
closing timestamps provide exact appearance dates; no container date is
invented. Residential and commercial lots are retained together.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://bidx1.com"
SEARCH = BASE + "/en/united-kingdom/property-for-auction"
PROPERTY_RE = re.compile(r"/auction/property/(\d+)(?:[/?#]|$)", re.I)
RESULT_COUNT_RE = re.compile(r"\b(\d[\d,]*)\s+results?\b", re.I)
DATE_RE = re.compile(r"Closing\s+Time.*?(\d{1,2}/\d{1,2}/\d{4})", re.I | re.S)
LOT_RE = re.compile(r"\bLot\s+([0-9]+[A-Za-z]?)\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)

# Add only independently verified first-party auction IDs. Combined search URLs
# are discovery evidence, not a claim that several auctions form one catalogue.
AUCTIONS = {
    "4561": {"discovery": "first-party indexed historical result set"},
    "6854": {"discovery": "first-party indexed historical result set; 19 published results"},
    "7260": {"discovery": "first-party indexed historical result set; 19 published results"},
    "7445": {"discovery": "first-party indexed historical result set; 1 published result"},
    # First-party combined UK result-page evidence captured 2026-10-04.
    # Every ID is still fetched and reconciled independently before banking.
    "2838": {"discovery": "first-party indexed historical result set; combined UK page evidence"},
    "3184": {"discovery": "first-party indexed historical result set; combined UK page evidence"},
    "3185": {"discovery": "first-party indexed historical result set; combined UK page evidence"},
    "3200": {"discovery": "first-party indexed historical result set; combined UK page evidence"},
    # Independently filterable first-party UK result sets verified 2026-10-05.
    "3182": {"discovery": "first-party indexed historical result set; 10 published results"},
    "5857": {"discovery": "first-party indexed historical result set; 24 published results"},
    "7569": {"discovery": "first-party indexed historical result set; 4 published results"},
    "7593": {"discovery": "first-party indexed historical result set; 1 published result"},
    # Older first-party result URLs retained by the public search index.  The
    # source URLs sometimes combine several IDs, but each ID below was fetched
    # independently and reconciled to its own published result count before it
    # was admitted here (2026-10-06).
    "2221": {"discovery": "first-party indexed historical result set; 10 published results"},
    "2454": {"discovery": "first-party indexed historical result set; 10 published results"},
    "2767": {"discovery": "first-party indexed historical result set; 5 published results"},
    "2808": {"discovery": "first-party indexed historical result set; 1 published result"},
    "2852": {"discovery": "first-party indexed historical result set; 1 published result"},
    "2860": {"discovery": "first-party indexed historical result set; 1 published result"},
    "2886": {"discovery": "first-party indexed historical result set; 1 published result"},
    "2916": {"discovery": "first-party indexed historical result set; 2 published results"},
    "2936": {"discovery": "first-party indexed historical result set; 1 published result"},
    "3083": {"discovery": "first-party indexed historical result set; 1 published result"},
    "4321": {"discovery": "first-party indexed historical result set; 1 published result"},
    "4451": {"discovery": "first-party indexed historical result set; 9 published results"},
    "4506": {"discovery": "first-party indexed historical result set; 2 published results"},
    "4547": {"discovery": "first-party indexed historical result set; 1 published result"},
    "4553": {"discovery": "first-party indexed historical result set; 1 published result"},
    "5711": {"discovery": "first-party indexed historical result set; 15 published results"},
    "5969": {"discovery": "first-party indexed historical result set; 20 published results"},
    "6016": {"discovery": "first-party indexed historical result set; 1 published result"},
    "6024": {"discovery": "first-party indexed historical result set; 1 published result"},
    "6293": {"discovery": "first-party indexed historical result set; 23 published results"},
    "6366": {"discovery": "first-party indexed historical result set; 1 published result"},
    "6378": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7024": {"discovery": "first-party indexed historical result set; 29 published results"},
    "7147": {"discovery": "first-party indexed historical result set; 19 published results"},
    "7215": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7263": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7269": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7379": {"discovery": "first-party indexed historical result set; 20 published results"},
    "7386": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7432": {"discovery": "first-party indexed historical result set; 1 published result"},
    "7455": {"discovery": "first-party indexed historical result set; 1 published result"},
}

# Seen only in a combined first-party result URL; independent filters returned
# no BidX1 result content on 2026-10-04. Retain as negative provenance so later
# collection runs do not repeat known-empty probes.
BLOCKED_AUCTIONS = {
    "3201": "combined-page-only ID; independent filter returned no result content",
    "3215": "combined-page-only ID; independent filter returned no result content",
}


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip(" ,")
    return value or None


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def search_url(auction_id: str, page: int = 1) -> str:
    query = {
        "auctionids": auction_id, "firstload": "true",
        "group_by_region": "false", "ismapsearch": "true", "page": page,
        "region": 2, "salestatus": "34,36,37,38,39,40,41,42,43",
    }
    return SEARCH + "?" + urlencode(query)


def parse_index(html: str, source_url: str) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    match = RESULT_COUNT_RE.search(soup.get_text(" ", strip=True))
    if not match:
        raise ValueError("BidX1 result count is absent")
    expected = int(match.group(1).replace(",", ""))
    rows: dict[str, dict] = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, anchor["href"])
        property_match = PROPERTY_RE.search(href)
        if not property_match:
            continue
        source_id = property_match.group(1)
        anchor_text = clean(anchor.get_text(" ", strip=True)) or ""
        lot_match = LOT_RE.search(anchor_text)
        rows.setdefault(source_id, {
            "source_id": source_id, "url": href.split("?", 1)[0],
            "lot_number": lot_match.group(1).upper() if lot_match else None,
            "index_text": anchor_text or None,
        })
        if rows[source_id]["lot_number"] is None and lot_match:
            rows[source_id]["lot_number"] = lot_match.group(1).upper()
    return expected, list(rows.values())


def heading_address(soup: BeautifulSoup) -> str | None:
    for heading in soup.find_all(["h1", "h2"]):
        text = clean(heading.get_text(" ", strip=True))
        if text and corpus.PC.search(text):
            return text
    return None


def exact_label(soup: BeautifulSoup, labels: set[str]) -> str | None:
    for node in soup.find_all(string=True):
        value = clean(str(node))
        if value and value.lower() in labels:
            return value
    return None


def embedded_closing_date(soup: BeautifulSoup, evidence: dict) -> str | None:
    """Recover the exact source date from BidX1's public closing countdown.

    Withdrawn-prior pages suppress the human-readable ``Closing Time`` label,
    but retain a server-rendered ``_seconds-to-closing`` value.  Combining that
    first-party value with the exact snapshot retrieval timestamp reconstructs
    the page's closing timestamp independently for each property.
    """
    countdown = soup.select_one('input#_seconds-to-closing[value]')
    retrieved_at = evidence.get("retrieved_at")
    if not countdown or not retrieved_at:
        return None
    try:
        retrieved = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
        seconds = int(countdown.get("value"))
    except (TypeError, ValueError):
        return None
    return (retrieved + timedelta(seconds=seconds)).date().isoformat()


def parse_detail(html: str, source_url: str, auction_id: str,
                 index_row: dict, evidence: dict,
                 auction_date_override: str | None = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    source_match = PROPERTY_RE.search(source_url)
    if not source_match or source_match.group(1) != index_row["source_id"]:
        raise ValueError("detail URL/property ID mismatch")
    date_match = DATE_RE.search(text)
    countdown_date = embedded_closing_date(soup, evidence) if not date_match else None
    if not date_match and not countdown_date and not auction_date_override:
        raise ValueError("detail page has no exact closing date")
    auction_date = (datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat()
                    if date_match else countdown_date or auction_date_override)
    address = heading_address(soup)
    if not address:
        raise ValueError("detail page has no postcode-bearing address heading")
    lot_number = index_row.get("lot_number")
    if not lot_number:
        lot_match = LOT_RE.search(text)
        lot_number = lot_match.group(1).upper() if lot_match else None

    lower = text.lower()
    sale_match = re.search(r"Sold\s+for\s+£\s*[\d,]+(?:\.\d+)?", text, re.I)
    if sale_match:
        status, sale_price = "sold", money(sale_match.group())
    elif "sold prior" in lower:
        status, sale_price = "sold_prior", None
    elif "withdrawn prior" in lower:
        status, sale_price = "withdrawn_prior", None
    elif "withdrawn" in lower:
        status, sale_price = "withdrawn", None
    elif "bidding closed" in lower:
        status, sale_price = "unsold", None
    else:
        status, sale_price = "unknown", None

    published_type = exact_label(soup, {"commercial", "residential"})
    property_type = exact_label(soup, {
        "land/site", "mixed use", "industrial", "office", "other",
        "leisure / hospitality", "apartments", "houses",
    })
    sector = (published_type or "").lower() or corpus.sector(
        " ".join(filter(None, [property_type, address])))
    postcode = corpus.PC.search(address)
    row = corpus.base_row("BidX1", f"bidx1:{auction_id}", auction_date,
                          lot_number, index_row["source_id"], source_url)
    row.update(
        address=address, postcode=postcode.group().upper() if postcode else None,
        locality=address, sector=sector, property_type=property_type,
        sale_price=sale_price, status=status, property_id=index_row["source_id"],
        identity_method="source_property_id", record_quality="address_record",
        auction_date_basis=("exact individual lot closing date published by source" if date_match else
            "exact individual lot closing date reconstructed from the first-party "
            "server-rendered seconds-to-closing value and snapshot retrieval timestamp"
            if countdown_date else
            f"same exact BidX1 auction ID {auction_id}; all dated sibling detail pages publish {auction_date}"),
        source_evidence=evidence, index_result_text=index_row.get("index_text"),
    )
    row["appearance_id"] = f"BidX1|auction:{auction_id}|property:{index_row['source_id']}"
    return row


def fetch(session: requests.Session, url: str, required: bytes) -> bytes:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000 or required not in raw:
        raise ValueError("source returned no expected BidX1 content")
    return raw


def harvest() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "Commercial-Auction-Sniper/1.0 (+historical lot research)"
    all_rows, auction_summaries, failures = [], {}, []
    for auction_id, metadata in AUCTIONS.items():
        index_url = search_url(auction_id)
        try:
            index_raw = fetch(session, index_url, b"/auction/property/")
            index_sha, retrieved_at = corpus.digest(index_raw), corpus.now()
            index_snapshot = corpus.DATA / "sources/bidx1" / f"auction-{auction_id}/index-{index_sha[:16]}.json.gz"
            index_html = index_raw.decode("utf-8", "replace")
            corpus.save_gzip(index_snapshot, {"source_url": index_url,
                "retrieved_at": retrieved_at, "sha256": index_sha, "html": index_html})
            expected, index_rows = parse_index(index_html, index_url)
            if expected != len(index_rows):
                raise ValueError(f"published result count {expected} != {len(index_rows)} stable property links")

            rows, detail_failures, undated = [], [], []
            for index_row in index_rows:
                try:
                    raw = fetch(session, index_row["url"], b"Property Summary")
                    sha = corpus.digest(raw)
                    snapshot = corpus.DATA / "sources/bidx1" / f"auction-{auction_id}/property-{index_row['source_id']}-{sha[:16]}.json.gz"
                    evidence = {"source_url": index_row["url"], "index_url": index_url,
                        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "index_snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
                        "sha256": sha, "retrieved_at": corpus.now(),
                        "basis": "first-party BidX1 auction result card and exact property detail page"}
                    html = raw.decode("utf-8", "replace")
                    corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
                    try:
                        rows.append(parse_detail(html, index_row["url"], auction_id,
                                                 index_row, evidence))
                    except ValueError as exc:
                        if str(exc) == "detail page has no exact closing date" and re.search(
                                r"\b(?:Withdrawn|Sold)\s+Prior\b", html, re.I):
                            undated.append((index_row, html, evidence))
                        else:
                            raise
                except Exception as exc:
                    detail_failures.append({"source_id": index_row["source_id"],
                        "url": index_row["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})
                time.sleep(0.3)

            dated = sorted({row["auction_date"] for row in rows})
            if undated and len(dated) == 1:
                for index_row, html, evidence in undated:
                    try:
                        rows.append(parse_detail(html, index_row["url"], auction_id,
                                                 index_row, evidence, dated[0]))
                    except Exception as exc:
                        detail_failures.append({"source_id": index_row["source_id"],
                            "url": index_row["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})
            elif undated:
                for index_row, _, _ in undated:
                    detail_failures.append({"source_id": index_row["source_id"],
                        "url": index_row["url"],
                        "error": "undated prior outcome has no single reconciled sibling auction date"})

            unique_ids = {row["source_lot_id"] for row in rows}
            complete = not detail_failures and len(rows) == expected and len(unique_ids) == expected
            dates = sorted({row["auction_date"] for row in rows})
            state = {"auctioneer": "BidX1", "source_auction_id": f"bidx1:{auction_id}",
                "auction_date": dates[0] if len(dates) == 1 else None,
                "catalogue_complete": complete, "published_result_count": expected,
                "lots_captured": len(rows), "source_property_ids": sorted(unique_ids, key=int),
                "errors": detail_failures,
                "completion_scope": "all stable property links in the auction-ID-specific first-party result set",
                "discovery": metadata["discovery"], "checked_at": corpus.now()}
            corpus.save_json(corpus.DATA / f"auctions/bidx1/{auction_id}.json", state)
            auction_summaries[auction_id] = state
            all_rows.extend(rows)
            if not complete:
                failures.append({"auction_id": auction_id, "error": "catalogue did not reconcile",
                                 "details": detail_failures})
        except Exception as exc:
            failures.append({"auction_id": auction_id, "url": index_url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})

    existing_path = corpus.DATA / "appearances/bidx1/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(existing_path)) if existing_path.exists() else []
    merged = {row["appearance_id"]: row for row in existing}
    before = len(merged)
    for row in all_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("bidx1/canonical", sorted(merged.values(), key=lambda row: row["appearance_id"]))
    added = total - before
    summary = {"checked_at": corpus.now(), "seed_auctions": len(AUCTIONS),
        "catalogues_complete": sum(bool(v["catalogue_complete"]) for v in auction_summaries.values()),
        "property_appearances_captured": total, "run_new_appearances": added,
        "run_new_address_records": added, "run_new_partial_lots": 0,
        "by_sector": dict(Counter(row["sector"] for row in merged.values())),
        "auctions": {key: {"published_result_count": value["published_result_count"],
                            "lots_captured": value["lots_captured"],
                            "catalogue_complete": value["catalogue_complete"]}
                     for key, value in auction_summaries.items()}, "failures": failures}
    corpus.save_json(corpus.DATA / "bidx1_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
