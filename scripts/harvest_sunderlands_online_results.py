"""Bank Sunderlands' retained EIG online-auction result inventory.

The first-party search page exposes one finite, unpaginated list of ended
online lots.  Each card publishes a stable UUID, exact end date, address and
outcome; the linked detail page supplies the guide.  This runner snapshots the
index and every detail page, validates the two sources against each other and
merges the resulting appearances into the existing Sunderlands shard.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import gzip
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Sunderlands"
SLUG = "sunderlands"
RUN_SOURCE = "sunderlands_online_results"
INDEX = "https://onlineauctions.sunderlands.co.uk/search"
HOST = "onlineauctions.sunderlands.co.uk"
OPERATOR = "SUNDERLANDS 1862 LLP"
FORMER_NAME = "SUNDERLANDS AND THOMPSONS LLP"
COMPANY_NUMBER = "OC338911"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DETAIL_RE = re.compile(r"^/lot/details/([0-9a-f-]{36})$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
GUIDE_RE = re.compile(r"([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
NEXT_TARGET = (
    "Batch Hanover Auction's first-party EIG /search inventory: 26 individually addressed result cards with "
    "published outcomes and stable lot links. Hanover Auction is currently unlinked with zero retained appearances "
    "in the source register. Reuse the index-plus-detail pattern, reconcile the legal operator and preserve guides, "
    "achieved prices and immutable source snapshots. Do not refresh the now-reconciled Sunderlands inventories. "
    "National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def status_and_price(result_text):
    value = clean(result_text) or ""
    folded = value.casefold()
    amount = MONEY_RE.search(value)
    sale_price = int(amount.group(1).replace(",", "")) if amount else None
    if folded.startswith("sold for"):
        return "sold", sale_price
    if "sold prior" in folded:
        return "sold_prior", None
    if folded.startswith("sold"):
        return "sold", sale_price
    if "unsold" in folded or "no bids" in folded:
        return "unsold", None
    if "withdrawn" in folded:
        return "withdrawn", None
    return "unknown", sale_price


def parse_index(raw, source_url=INDEX, evidence=None):
    soup = BeautifulSoup(raw, "lxml")
    numbered_pages = {
        int(a.get_text(" ", strip=True)) for a in soup.select(".pagination a")
        if a.get_text(" ", strip=True).isdigit()
    }
    if numbered_pages - {1}:
        raise ValueError("online result inventory unexpectedly spans multiple pages")
    rows = []
    for position, panel in enumerate(soup.select("div.lot-panel"), 1):
        anchor = panel.select_one('a[href*="/lot/details/"]')
        match = DETAIL_RE.match(urlparse(anchor.get("href") or "").path) if anchor else None
        timestamp = panel.select_one("time[datetime]")
        result = panel.select_one(".lot-result strong")
        if not match or not timestamp or not result:
            raise ValueError(f"online result card {position} lacks identity, exact date or outcome")
        source_id = match.group(1).lower()
        auction_date = timestamp["datetime"][:10]
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", auction_date):
            raise ValueError(f"online result card {position} has invalid date")
        result_text = clean(result.get_text(" ", strip=True))
        status, sale_price = status_and_price(result_text)
        address_node = panel.select_one(".list-address")
        description_node = panel.select_one(".lot-desc")
        heading_node = panel.select_one(".lot-data-heading")
        rows.append({
            "source_lot_id": source_id,
            "source_position": position,
            "auction_date": auction_date,
            "address": clean(address_node.get_text(" ", strip=True)) if address_node else None,
            "description": clean(description_node.get_text(" ", strip=True)) if description_node else None,
            "headline": clean(heading_node.get_text(" ", strip=True)) if heading_node else None,
            "status": status,
            "sale_price": sale_price,
            "source_outcome_text": result_text,
            "original_url": urljoin(source_url, anchor["href"]),
            "index_evidence": evidence,
        })
    if not rows:
        raise ValueError("online result index exposed zero lots")
    if len({row["source_lot_id"] for row in rows}) != len(rows):
        raise ValueError("online result index contains duplicate lot UUIDs")
    return rows


def parse_detail(raw, item, requested_url, evidence):
    soup = BeautifulSoup(raw, "lxml")
    match = DETAIL_RE.match(urlparse(requested_url).path)
    if not match or match.group(1).lower() != item["source_lot_id"]:
        raise ValueError("detail URL does not match result-card UUID")
    address_node = soup.select_one("h1.lot-addr")
    address = clean(address_node.get_text(" ", strip=True)) if address_node else None
    if item.get("address") and normalized(item["address"]) != normalized(address):
        raise ValueError("detail-page address differs from result-card address")
    guide_text = next((clean(li.get_text(" ", strip=True)) for li in soup.select(".nav-links li")
                       if "guide price" in li.get_text(" ", strip=True).casefold()), None)
    guide_low = guide_high = None
    if guide_text:
        amount = GUIDE_RE.search(guide_text.split(":", 1)[-1])
        if not amount:
            raise ValueError("detail page prints an unparseable guide price")
        guide_low = int(amount.group(1).replace(",", ""))
        guide_high = int(amount.group(2).replace(",", "")) if amount.group(2) else None
    material = " ".join(filter(None, [address, item.get("headline"), item.get("description")]))
    return {
        **item,
        "address": address or item.get("address"),
        "guide_price": guide_low,
        "guide_price_high": guide_high,
        "source_guide_text": guide_text,
        "sector": corpus.sector(material) if material else "unknown",
        "detail_evidence": evidence,
    }


def materialize(item):
    source_id = item["source_lot_id"]
    auction_date = item["auction_date"]
    auction_id = f"sunderlands-online:{auction_date}"
    row = corpus.base_row(SOURCE, auction_id, auction_date, None, source_id, item["original_url"])
    postcode = corpus.PC.search(item.get("address") or "")
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|{source_id}",
        address=item["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=item.get("address"),
        sector=item["sector"],
        status=item["status"],
        guide_price=item.get("guide_price"),
        guide_price_high=item.get("guide_price_high"),
        sale_price=item.get("sale_price"),
        description=item.get("description"),
        annual_rent=None,
        record_quality="address_record" if item.get("address") else "partial_lot",
        identity_method="first_party_online_lot_uuid_exact_end_date_and_address",
        source_position=item["source_position"],
        source_guide_text=item.get("source_guide_text"),
        source_outcome_text=item.get("source_outcome_text"),
        source_event_url=INDEX,
        source_property_url=item["original_url"],
        auction_date_precision="day",
        auction_date_basis="exact ended date printed on first-party Sunderlands online result card",
        source_platform="Sunderlands EIG online auctions",
        operator_legal_name=OPERATOR,
        operator_former_name=FORMER_NAME,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        source_evidence={
            "index": item.get("index_evidence"),
            "detail": item.get("detail_evidence"),
            "basis": "first-party ended online lot card plus linked first-party detail page",
        },
    )
    return row


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                })
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": RUN_SOURCE,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[RUN_SOURCE] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    resolved_index, index_raw = get(INDEX)
    index_sha, checked_at = corpus.digest(index_raw), corpus.now()
    index_snapshot = corpus.DATA / "sources/sunderlands/online" / f"search-{index_sha[:20]}.html.gz"
    if not index_snapshot.exists():
        corpus.atomic(index_snapshot, gzip.compress(index_raw, mtime=0))
    index_evidence = {
        "source_url": resolved_index,
        "retrieved_at": checked_at,
        "sha256": index_sha,
        "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
        "basis": "complete unpaginated first-party ended online-auction result inventory",
    }
    index_rows = parse_index(index_raw, resolved_index, index_evidence)
    parsed, failures = [], []
    for position, item in enumerate(index_rows, 1):
        try:
            resolved, raw = get(item["original_url"])
            sha, captured_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources/sunderlands/online" / f"lot-{item['source_lot_id']}-{sha[:20]}.html.gz"
            if not snapshot.exists():
                corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": resolved,
                "retrieved_at": captured_at,
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "linked first-party Sunderlands online-auction detail page",
            }
            parsed.append(parse_detail(raw, item, resolved, evidence))
            print("SUNDERLANDS ONLINE", position, "/", len(index_rows), flush=True)
        except Exception as exc:
            failures.append({"source_lot_id": item["source_lot_id"], "url": item["original_url"],
                             "error": f"{type(exc).__name__}: {exc}"[:500]})

    if failures or len(parsed) != len(index_rows):
        corpus.save_json(corpus.DATA / "sunderlands_online_collection.json", {
            "checked_at": corpus.now(), "source_url": INDEX, "index_lots": len(index_rows),
            "detail_lots_captured": len(parsed), "failures": failures,
            "run_new_appearances": 0, "national_completeness_verified": False,
        })
        raise SystemExit(1)

    candidates = [materialize(item) for item in parsed]
    overlaps, admissible = [], []
    global_exact = global_exact_appearances()
    for row in candidates:
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({"auction_date": row["auction_date"], "address": row["address"],
                             "source_lot_id": row["source_lot_id"], "existing": matches})
        else:
            admissible.append(row)

    shard = corpus.DATA / "appearances/sunderlands/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    corpus.write_rows("sunderlands/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}

    states = []
    for row in candidates:
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_former_name": FORMER_NAME,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": row["source_auction_id"],
            "auction_date": row["auction_date"],
            "auction_date_precision": "day",
            "source_url": row["original_url"],
            "lots_captured": 1,
            "published_lots_offered": 1,
            "catalogue_complete": True,
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": "single-property ended online auction represented by one stable first-party lot UUID",
            "source_evidence": row["source_evidence"],
            "errors": [],
            "checked_at": corpus.now(),
        }
        states.append(state)
        corpus.save_json(corpus.DATA / "auctions/sunderlands-online" /
                         f"{row['auction_date']}-{row['source_lot_id']}.json", state)

    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "operator": {"canonical_name": SOURCE, "legal_name": OPERATOR, "former_name": FORMER_NAME,
                     "company_number": COMPANY_NUMBER,
                     "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "index_lots_reconciled": len(index_rows),
        "detail_pages_captured": len(parsed),
        "complete_single_lot_events": len(states),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "sunderlands_online_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
