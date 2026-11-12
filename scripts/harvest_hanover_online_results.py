"""Bank Hanover Auctions' finite retained EIG online-result inventory.

The public search page is a single 26-card inventory.  Cards publish stable
UUIDs, addresses and outcomes but omit dates.  Each linked detail page exposes
an EIG bidding-panel endpoint; its first-party response publishes the exact
end timestamp and outcome and is therefore required before a lot is admitted.
The runner snapshots the index, legal-operator terms, detail page and bidding
panel for every lot, then merges only non-overlapping dated appearances.
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


SOURCE = "Hanover Auction"
SLUG = "hanover-auction"
RUN_SOURCE = "hanover_online_results"
INDEX = "https://www.hanoverauctionhouse.com/search"
HOST = "www.hanoverauctionhouse.com"
TERMS = (
    "https://www.hanoverauctionhouse.com/account/viewdocument/"
    "167aa3c3-9c74-4e7d-a971-f6b06c4918d7/terms-conditions"
)
OPERATOR = "HANOVER AIREY DEVELOPMENT LIMITED"
COMPANY_NUMBER = "04515105"
TRADING_NAME = "Hanover Auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DETAIL_RE = re.compile(r"^/lot/details/([0-9a-f-]{36})$", re.I)
MONEY_RE = re.compile(r"(?:£|&#163;)\s*([\d,]+)", re.I)
GUIDE_RE = re.compile(r"(?:£|&#163;)?\s*([\d,]+)(?:\s*(?:-|\u2013|to)\s*(?:£|&#163;)?\s*([\d,]+))?", re.I)
NEXT_TARGET = (
    "Batch Auction Property Ltd's first-party archive: /past-auction-dates currently exposes 32 linked event pages "
    "from 2023-2026 while /sold-properties exposes address-level result cards. The directory label has zero retained "
    "appearances. Build one reusable multi-event runner, reconcile every event denominator and exact date, preserve "
    "guides and outcomes, and deduplicate overlaps before claiming growth. National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def request(session, method, url, **kwargs):
    response = None
    headers = {**HEADERS, **kwargs.pop("headers", {})}
    for attempt in range(6):
        response = session.request(method, url, headers=headers, timeout=90, **kwargs)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 50:
        raise ValueError("source response is unexpectedly short")
    return response


def status_and_price(result_text):
    value = clean(result_text) or ""
    folded = value.casefold()
    amount = MONEY_RE.search(value)
    sale_price = int(amount.group(1).replace(",", "")) if amount else None
    if "withdrawn" in folded:
        return "withdrawn", None
    if "no bids" in folded or "unsold" in folded or "not sold" in folded:
        return "unsold", None
    if "agreed prior" in folded or "sold prior" in folded:
        return "sold_prior", sale_price
    if "agreed post" in folded or "sold post" in folded:
        return "sold_post", sale_price
    if folded.startswith("sale agreed") or folded.startswith("sold"):
        return "sold", sale_price
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
        address_node = panel.select_one(".grid-address")
        result_node = panel.select_one(".result-price b")
        if not match or not address_node or not result_node:
            raise ValueError(f"online result card {position} lacks identity, address or outcome")
        source_id = match.group(1).lower()
        result_text = clean(result_node.get_text(" ", strip=True))
        status, sale_price = status_and_price(result_text)
        rows.append({
            "source_lot_id": source_id,
            "source_position": position,
            "address": clean(address_node.get_text(" ", strip=True)),
            "status": status,
            "sale_price": sale_price,
            "source_outcome_text": result_text,
            "original_url": urljoin(source_url, anchor["href"]),
            "index_evidence": evidence,
        })
    if len(rows) != 26:
        raise ValueError(f"expected complete 26-card inventory, found {len(rows)}")
    if len({row["source_lot_id"] for row in rows}) != len(rows):
        raise ValueError("online result index contains duplicate lot UUIDs")
    return rows


def description_from_detail(soup):
    heading = next((node for node in soup.select("h3.lot-details-heading")
                    if clean(node.get_text(" ", strip=True)) == "Description"), None)
    parts = []
    if heading:
        for sibling in heading.next_siblings:
            name = getattr(sibling, "name", None)
            if name == "h3":
                break
            text = clean(sibling.get_text(" ", strip=True)) if name else clean(sibling)
            if text:
                parts.append(text)
    tagline = soup.select_one(".lot-details-tagline")
    return clean(" ".join(filter(None, [
        clean(tagline.get_text(" ", strip=True)) if tagline else None,
        " ".join(parts) or None,
    ])))


def published_rent(text):
    value = clean(text) or ""
    patterns = (
        r"(?:rent(?:al)?\s+income|income|rent)\s+(?:of\s+|is\s+|at\s+|circa\s+|approximately\s+)*£\s*([\d,]+)\s*(?:per\s+annum|p\.?\s*a\.?)",
        r"£\s*([\d,]+)\s*(?:per\s+annum|p\.?\s*a\.?)\s+(?:rent|rental\s+income|income)",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            amount = int(match.group(1).replace(",", ""))
            sentence = next((clean(part) for part in re.split(r"(?<=[.!?])\s+", value)
                             if match.group(0) in part), match.group(0))
            return amount, sentence
    # Preserve a compact "11k pa" publication exactly, without treating an
    # unlabelled buyer premium or starting bid as rent.
    match = re.search(r"(?:rent(?:al)?\s+income|income|rent)[^.]{0,35}?\b([\d]+(?:\.\d+)?)\s*k\s*p\.?\s*a\.?", value, re.I)
    if match:
        return int(float(match.group(1)) * 1000), clean(match.group(0))
    return None, None


def parse_detail(raw, item, requested_url, evidence):
    soup = BeautifulSoup(raw, "lxml")
    match = DETAIL_RE.match(urlparse(requested_url).path)
    if not match or match.group(1).lower() != item["source_lot_id"]:
        raise ValueError("detail URL does not match result-card UUID")
    address_node = soup.select_one(".lot-heading h1")
    detail_heading = clean(address_node.get_text(" ", strip=True)) if address_node else None
    lot_number = None
    address = detail_heading
    prefixed = re.match(r"^Lot\s+(.+?)\s+-\s+(.+)$", detail_heading or "", re.I)
    if prefixed:
        lot_number, address = clean(prefixed.group(1)), clean(prefixed.group(2))
    if normalized(item["address"]) != normalized(address):
        raise ValueError("detail-page address differs from result-card address")
    guide_text = next((clean(li.get_text(" ", strip=True)) for li in soup.select(".lot-highlights li")
                       if "guide price" in li.get_text(" ", strip=True).casefold()), None)
    guide_low = guide_high = None
    if guide_text:
        amount = GUIDE_RE.search(guide_text)
        if not amount:
            raise ValueError("detail page prints an unparseable guide price")
        guide_low = int(amount.group(1).replace(",", ""))
        guide_high = int(amount.group(2).replace(",", "")) if amount.group(2) else None
    loader = soup.select_one("#bidding-panel-loader")
    panel_path = loader.get("data-bidding-panel-url") if loader else None
    token_path = loader.get("data-panel-token-url") if loader else None
    if not panel_path or not token_path:
        raise ValueError("detail page lacks first-party bidding-panel route")
    description = description_from_detail(soup)
    annual_rent, rent_text = published_rent(description)
    return {
        **item,
        "address": address,
        "lot_number": lot_number,
        "description": description,
        "guide_price": guide_low,
        "guide_price_high": guide_high,
        "source_guide_text": guide_text,
        "annual_rent": annual_rent,
        "rent_text": rent_text,
        "panel_url": urljoin(requested_url, panel_path),
        "token_url": urljoin(requested_url, token_path),
        "detail_evidence": evidence,
    }


def parse_panel(raw, item, evidence):
    soup = BeautifulSoup(raw, "lxml")
    timestamp = soup.select_one("time.end-date-time[datetime]")
    script = next((node.get_text(" ", strip=True) for node in soup.find_all("script")
                   if "BiddingDefaults" in node.get_text()), None)
    if not script:
        raise ValueError("bidding panel lacks exact end-date defaults")
    match = re.search(r"var\s+BiddingDefaults\s*=\s*({.*?})\s*;", script, re.S)
    if not match:
        raise ValueError("bidding defaults JSON is missing")
    defaults = json.loads(match.group(1))
    # A prior/post agreement can close a lot before its scheduled deadline.
    # The visible `time` is the actual ended timestamp; EndDateUtc remains
    # useful as separately labelled scheduled evidence.
    actual_end = timestamp["datetime"] if timestamp else defaults.get("EndDateUtc", "")
    ended = actual_end[:10]
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", ended):
        raise ValueError("bidding defaults lack an exact end date")
    outcome_node = soup.select_one(".bidding-panel-bid-state h2")
    panel_outcome = clean(outcome_node.get_text(" ", strip=True)) if outcome_node else None
    if panel_outcome:
        panel_status, panel_price = status_and_price(panel_outcome)
        if item["status"] != panel_status or item["sale_price"] != panel_price:
            raise ValueError("index and bidding-panel outcomes disagree")
    material = " ".join(filter(None, [item.get("address"), item.get("description")]))
    return {
        **item,
        "auction_date": ended,
        "auction_start": defaults.get("StartDateUtc"),
        "auction_end": actual_end,
        "scheduled_auction_end": defaults.get("EndDateUtc"),
        "source_panel_outcome_text": panel_outcome,
        "sector": corpus.sector(material) if material else "unknown",
        "panel_evidence": evidence,
    }


def materialize(item):
    source_id = item["source_lot_id"]
    auction_date = item["auction_date"]
    auction_id = f"hanover-online:{auction_date}:{source_id}"
    row = corpus.base_row(SOURCE, auction_id, auction_date, item.get("lot_number"), source_id, item["original_url"])
    postcode = corpus.PC.search(item["address"] or "")
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|{source_id}",
        address=item["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=item["address"],
        sector=item["sector"],
        status=item["status"],
        guide_price=item.get("guide_price"),
        guide_price_high=item.get("guide_price_high"),
        sale_price=item.get("sale_price"),
        description=item.get("description"),
        annual_rent=item.get("annual_rent"),
        rent_text=item.get("rent_text"),
        record_quality="address_record",
        identity_method="first_party_online_lot_uuid_exact_bidding_panel_end_date_and_address",
        source_position=item["source_position"],
        source_guide_text=item.get("source_guide_text"),
        source_outcome_text=item.get("source_outcome_text"),
        source_panel_outcome_text=item.get("source_panel_outcome_text"),
        source_event_url=INDEX,
        source_property_url=item["original_url"],
        auction_start=item.get("auction_start"),
        auction_end=item.get("auction_end"),
        scheduled_auction_end=item.get("scheduled_auction_end"),
        auction_date_precision="day",
        auction_date_basis="exact ended date printed on first-party Hanover Auctions bidding panel",
        source_platform="Hanover Auctions EIG online auctions",
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=TRADING_NAME,
        source_evidence={
            "index": item.get("index_evidence"),
            "detail": item.get("detail_evidence"),
            "bidding_panel": item.get("panel_evidence"),
            "operator_terms": item.get("operator_evidence"),
            "basis": "first-party result card, linked detail page and exact-dated bidding panel",
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


def snapshot(raw, relative_prefix, source_url, basis, checked_at=None):
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources/hanover-auction/online" / f"{relative_prefix}-{sha[:20]}.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": checked_at or corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


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
    session = requests.Session()
    index_response = request(session, "GET", INDEX)
    checked_at = corpus.now()
    index_evidence = snapshot(index_response.content, "search", index_response.url,
                              "complete unpaginated 26-card first-party ended result inventory", checked_at)
    index_rows = parse_index(index_response.content, index_response.url, index_evidence)

    terms_response = request(session, "GET", TERMS)
    if not terms_response.content.startswith(b"%PDF"):
        raise ValueError("operator terms are not the expected first-party PDF")
    terms_evidence = snapshot(terms_response.content, "operator-terms", terms_response.url,
                              "first-party terms naming legal operator and Hanover Auctions trading name")

    parsed, failures = [], []
    for position, item in enumerate(index_rows, 1):
        try:
            detail_response = request(session, "GET", item["original_url"])
            detail_evidence = snapshot(detail_response.content, f"lot-{item['source_lot_id']}-detail",
                                       detail_response.url, "linked first-party Hanover Auctions lot detail")
            enriched = parse_detail(detail_response.content, item, detail_response.url, detail_evidence)
            token_response = request(session, "GET", enriched["token_url"],
                                     headers={**HEADERS, "Referer": detail_response.url})
            token = token_response.text.strip()
            if not token or len(token) < 40:
                raise ValueError("anti-forgery token is missing")
            panel_response = request(
                session, "POST", enriched["panel_url"],
                data={"__RequestVerificationToken": token},
                headers={**HEADERS, "Referer": detail_response.url},
            )
            panel_evidence = snapshot(panel_response.content, f"lot-{item['source_lot_id']}-panel",
                                      panel_response.url, "first-party exact-dated EIG bidding panel")
            enriched["operator_evidence"] = terms_evidence
            parsed.append(parse_panel(panel_response.content, enriched, panel_evidence))
            print("HANOVER ONLINE", position, "/", len(index_rows), flush=True)
        except Exception as exc:
            failures.append({"source_lot_id": item["source_lot_id"], "url": item["original_url"],
                             "error": f"{type(exc).__name__}: {exc}"[:500]})

    if failures or len(parsed) != len(index_rows):
        corpus.save_json(corpus.DATA / "hanover_online_collection.json", {
            "checked_at": corpus.now(), "source_url": INDEX, "index_lots": len(index_rows),
            "dated_panels_captured": len(parsed), "failures": failures,
            "run_new_appearances": 0, "next_growth_target": NEXT_TARGET,
            "national_completeness_verified": False,
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

    shard = corpus.DATA / "appearances/hanover-auction/canonical.jsonl.gz"
    existing_all = list(corpus.iter_rows(shard)) if shard.exists() else []
    existing = [row for row in existing_all if str(row.get("source_auction_id", "")).endswith(
        str(row.get("source_lot_id", "__missing__"))
    )]
    superseded_identity_rows = len(existing_all) - len(existing)
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    # This finite inventory is fully reconciled on every successful run.  An
    # identity-version repair must replace its own prior parser artefacts so
    # date-level IDs cannot survive beside the corrected UUID-scoped IDs.
    corpus.write_rows("hanover-auction/canonical", list(merged.values()), preserve_existing=False)
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
            "operator_company_number": COMPANY_NUMBER,
            "trading_name": TRADING_NAME,
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
        corpus.save_json(corpus.DATA / "auctions/hanover-auction-online" /
                         f"{row['auction_date']}-{row['source_lot_id']}.json", state)

    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "operator": {"canonical_name": SOURCE, "legal_name": OPERATOR,
                     "company_number": COMPANY_NUMBER, "trading_name": TRADING_NAME,
                     "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "index_lots_reconciled": len(index_rows),
        "detail_pages_captured": len(parsed),
        "exact_dated_bidding_panels_captured": len(parsed),
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
        "superseded_prebank_date_level_identity_rows": superseded_identity_rows,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "hanover_online_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
