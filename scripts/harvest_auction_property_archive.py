"""Bank Auction Property Ltd's surviving first-party event archive.

The first-party past-dates page currently links 32 event pages.  Those pages
retain 51 property cards across 17 non-empty events; another 15 event shells
retain no property cards.  This runner snapshots the complete index, every
linked event, the sold-property grid and every surviving detail page.  It
admits only property cards with an exact published event date and address.

The surviving page inventory is not represented as the original catalogue
denominator: high lot numbers and empty event shells prove that earlier cards
may have been removed.  Event states therefore distinguish a completely read
live page from an unreconciled original event catalogue.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
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


SOURCE = "Auction Property Ltd"
SLUG = "auction-property-ltd"
RUN_SOURCE = "auction_property_archive"
INDEX = "https://auctionproperty.co.uk/past-auction-dates/"
SOLD = "https://auctionproperty.co.uk/sold-properties/"
HOST = "auctionproperty.co.uk"
OPERATOR = "AUCTION PROPERTY LTD"
COMPANY_NUMBER = "12828051"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
EVENT_RE = re.compile(r"^/auction/([^/]+)/?$", re.I)
PROPERTY_RE = re.compile(r"^/property/([^/]+)/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(20\d{2})\b",
    re.I,
)
MONTHS = {name.lower(): number for number, name in enumerate(
    "January February March April May June July August September October November December".split(), 1
)}
NEXT_TARGET = (
    "Batch Halls' first-party Collective Property & Land Auction archive through one reusable runner. Start with "
    "the official 24 July 2026 event page and its linked results page and catalogue PDF, then inventory the four "
    "published 2025 collective-auction dates (25 April, 25 July, 26 September and 28 November). Reconcile Halls' "
    "branches and trading labels under the legal operator, preserve exact dates, lots, guides, outcomes and rents, "
    "and establish each first-party event denominator before claiming growth. Do not use the third-party directory "
    "count as a captured-lot denominator. National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def parse_date(value):
    match = DATE_RE.search(clean(value) or "")
    if not match:
        return None
    return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1))).isoformat()


def request(session, url):
    response = None
    for attempt in range(6):
        response = session.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response


def parse_event_index(raw, source_url=INDEX):
    soup = BeautifulSoup(raw, "lxml")
    urls = []
    for anchor in soup.select('a[href*="/auction/"]'):
        url = urljoin(source_url, anchor.get("href") or "")
        parsed = urlparse(url)
        if parsed.hostname not in {HOST, "www." + HOST} or not EVENT_RE.match(parsed.path):
            continue
        url = f"https://{HOST}{parsed.path}"
        if url not in urls:
            urls.append(url)
    if len(urls) != 32:
        raise ValueError(f"expected 32 linked event pages, found {len(urls)}")
    return urls


def status_from_text(value):
    text = (clean(value) or "").casefold()
    if text == "sold prior":
        return "sold_prior"
    if text in {"sold after", "sold post", "sold post auction"}:
        return "sold_post"
    if text == "sold":
        return "sold"
    if text in {"unsold", "not sold"}:
        return "unsold"
    if text == "withdrawn":
        return "withdrawn"
    if text == "postponed":
        return "postponed"
    return "unknown"


def parse_event_page(raw, source_url, evidence=None):
    soup = BeautifulSoup(raw, "lxml")
    event_match = EVENT_RE.match(urlparse(source_url).path)
    if not event_match:
        raise ValueError("event page URL lacks stable event slug")
    heading = soup.select_one("h1.elementor-heading-title") or soup.find("h1")
    event_heading = clean(heading.get_text(" ", strip=True)) if heading else None
    event_date = parse_date(event_heading)
    if not event_date:
        event_date = parse_date(soup.title.get_text(" ", strip=True) if soup.title else None)
    if not event_date:
        raise ValueError("event page lacks an exact published date")
    rows = []
    for position, card in enumerate(soup.select(".ae-post-item-inner"), 1):
        root = card.select_one("[data-obj-id]")
        anchor = next((a for a in card.select('a[href*="/property/"]')
                       if clean(a.get_text(" ", strip=True))), None)
        if not root or not root.get("data-obj-id") or not anchor:
            raise ValueError(f"event card {position} lacks a stable post id or address link")
        property_url = urljoin(source_url, anchor.get("href") or "")
        property_match = PROPERTY_RE.match(urlparse(property_url).path)
        if not property_match:
            raise ValueError(f"event card {position} has invalid property URL")
        source_id = str(root["data-obj-id"])
        address = clean(anchor.get_text(" ", strip=True))
        headings = [clean(node.get_text(" ", strip=True)) for node in card.select(".elementor-heading-title")]
        headings = [value for value in headings if value]
        lot_text = next((value for value in headings if re.fullmatch(r"LOT\s+.+", value, re.I)), None)
        if not lot_text:
            raise ValueError(f"event card {position} lacks a published lot label")
        lot_number = clean(re.sub(r"^LOT\s+", "", lot_text, flags=re.I))
        card_date_text = next((value for value in headings if value.casefold().startswith("auction:")), None)
        card_date = parse_date(card_date_text)
        if card_date and card_date != event_date:
            raise ValueError(f"event card {position} date differs from event heading")
        address_index = next((i for i, value in enumerate(headings)
                              if normalized(value) == normalized(address)), None)
        if address_index is None or address_index == 0:
            raise ValueError(f"event card {position} address is not represented in headings")
        property_type = headings[address_index - 1]
        tail = headings[address_index + 1:]
        guide_text = next((value for value in tail if value.casefold().startswith("guide price")), None)
        guide_low = guide_high = None
        if guide_text:
            amount = MONEY_RE.search(guide_text)
            if not amount:
                raise ValueError(f"event card {position} has unparseable guide")
            guide_low = int(amount.group(1).replace(",", ""))
            guide_high = int(amount.group(2).replace(",", "")) if amount.group(2) else None
        outcome_text = next((value for value in tail if status_from_text(value) != "unknown"), None)
        rows.append({
            "event_slug": event_match.group(1).lower(),
            "event_url": source_url,
            "event_heading": event_heading,
            "event_evidence": evidence,
            "source_position": position,
            "source_lot_id": source_id,
            "property_slug": property_match.group(1).lower(),
            "original_url": f"https://{HOST}{urlparse(property_url).path}",
            "auction_date": event_date,
            "lot_number": lot_number,
            "address": address,
            "property_type": property_type,
            "status": status_from_text(outcome_text),
            "source_outcome_text": outcome_text,
            "guide_price": guide_low,
            "guide_price_high": guide_high,
            "source_guide_text": guide_text,
        })
    if len({(row["event_slug"], row["source_lot_id"]) for row in rows}) != len(rows):
        raise ValueError("event page contains duplicate property post ids")
    return {
        "event_slug": event_match.group(1).lower(),
        "event_url": source_url,
        "event_heading": event_heading,
        "auction_date": event_date,
        "event_evidence": evidence,
        "rows": rows,
    }


def parse_sold_page(raw, source_url=SOLD, evidence=None):
    soup = BeautifulSoup(raw, "lxml")
    rows = {}
    for position, card in enumerate(soup.select(".ae-post-item-inner"), 1):
        root = card.select_one("[data-obj-id]")
        anchor = next((a for a in card.select('a[href*="/property/"]')
                       if clean(a.get_text(" ", strip=True))), None)
        headings = [clean(node.get_text(" ", strip=True)) for node in card.select(".elementor-heading-title")]
        headings = [value for value in headings if value]
        if not root or not root.get("data-obj-id") or not anchor:
            raise ValueError(f"sold-property card {position} lacks stable identity or address")
        source_id = str(root["data-obj-id"])
        address = clean(anchor.get_text(" ", strip=True))
        address_index = next((i for i, value in enumerate(headings)
                              if normalized(value) == normalized(address)), None)
        if address_index is None:
            raise ValueError(f"sold-property card {position} lacks address heading")
        outcome_text = next((value for value in headings[address_index + 1:]
                             if status_from_text(value) != "unknown"), None)
        event_text = next((value for value in headings if value.casefold().startswith("auction:")), None)
        event_date = parse_date(event_text)
        if not event_date or not outcome_text:
            raise ValueError(f"sold-property card {position} lacks date or published outcome")
        if source_id in rows:
            raise ValueError("sold-property grid contains duplicate post ids")
        rows[source_id] = {
            "source_position": position,
            "source_lot_id": source_id,
            "auction_date": event_date,
            "address": address,
            "status": status_from_text(outcome_text),
            "source_outcome_text": outcome_text,
            "sold_page_evidence": evidence,
            "source_url": source_url,
        }
    if len(rows) != 16:
        raise ValueError(f"expected 16 sold-property cards, found {len(rows)}")
    return rows


def published_rent(text):
    value = clean(text) or ""
    patterns = (
        r"(?:rent(?:al)?\s+income|income|rent)\s+(?:of\s+|is\s+|at\s+|circa\s+|approximately\s+)*£\s*([\d,]+)\s*(?:per\s+annum|p\.?\s*a\.?)",
        r"£\s*([\d,]+)\s*(?:per\s+annum|p\.?\s*a\.?)\s+(?:rent|rental\s+income|income)",
        r"(?:rent(?:al)?\s+income|income|rent)[^.]{0,45}?£\s*([\d,]+)\s*(?:pcm|per\s+calendar\s+month)",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            amount = int(match.group(1).replace(",", ""))
            if re.search(r"pcm|calendar\s+month", match.group(0), re.I):
                amount *= 12
            return amount, clean(match.group(0))
    return None, None


def explicit_sector(property_type, description):
    category = (clean(property_type) or "").casefold()
    material = " ".join(filter(None, [property_type, description]))
    found = corpus.sector(material)
    if found != "unknown":
        return found
    if category in {"pub", "commercial property", "commercial development", "shop", "land (commercial)"}:
        return "commercial"
    if category in {"farm", "smallholding", "land", "plot"}:
        return "land"
    return "unknown"


def parse_detail(raw, item, requested_url, evidence):
    soup = BeautifulSoup(raw, "lxml")
    wrapper = soup.select_one(".dce-elementor-post-" + item["source_lot_id"])
    if not wrapper:
        wrapper = soup.select_one(f".post-{item['source_lot_id']}")
    if not wrapper:
        raise ValueError("detail page does not expose the event-card WordPress post id")
    heading = soup.select_one("h1.elementor-heading-title") or soup.find("h1")
    detail_address = clean(heading.get_text(" ", strip=True)) if heading else None
    if normalized(detail_address) != normalized(item["address"]):
        raise ValueError("detail-page address differs from event-card address")
    description = None
    for node in soup.select('[data-widget_type="text-editor.default"] .elementor-widget-container'):
        value = clean(node.get_text(" ", strip=True))
        if not value or value == "Sitemap" or value.startswith("Guide Prices & Reserves"):
            continue
        if value.startswith("Here’s what you’ll receive") or value.startswith("We understand that you would like"):
            continue
        description = value
        break
    annual_rent, rent_text = published_rent(description)
    return {
        **item,
        "description": description,
        "annual_rent": annual_rent,
        "rent_text": rent_text,
        "sector": explicit_sector(item.get("property_type"), description),
        "detail_evidence": evidence,
    }


def materialize(item):
    auction_id = f"auction-property:{item['auction_date']}:{item['event_slug']}"
    row = corpus.base_row(SOURCE, auction_id, item["auction_date"], item["lot_number"],
                          item["source_lot_id"], item["original_url"])
    postcode = corpus.PC.search(item.get("address") or "")
    row.update(
        address=item["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=item["address"],
        sector=item["sector"],
        property_type=item.get("property_type"),
        status=item["status"],
        guide_price=item.get("guide_price"),
        guide_price_high=item.get("guide_price_high"),
        sale_price=None,
        description=item.get("description"),
        annual_rent=item.get("annual_rent"),
        rent_text=item.get("rent_text"),
        record_quality="address_record",
        identity_method="first_party_event_slug_wordpress_post_id_exact_date_and_address",
        source_position=item["source_position"],
        source_guide_text=item.get("source_guide_text"),
        source_outcome_text=item.get("source_outcome_text"),
        source_event_url=item["event_url"],
        source_property_url=item["original_url"],
        auction_date_precision="day",
        auction_date_basis="exact date printed on first-party Auction Property Ltd event page",
        source_platform="Auction Property Ltd first-party WordPress event archive",
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        source_evidence={
            "archive_index": item.get("index_evidence"),
            "event_page": item.get("event_evidence"),
            "property_detail": item.get("detail_evidence"),
            "sold_grid": item.get("sold_page_evidence"),
            "basis": "first-party exact-dated event card and linked property detail page",
        },
    )
    return row


def snapshot(raw, prefix, source_url, basis, checked_at=None):
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources/auction-property-ltd/first-party" / f"{prefix}-{sha[:20]}.html.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": checked_at or corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


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
    payload.setdefault("coverage_follow_through_2026_11_07", {})["different_next_target"] = NEXT_TARGET
    corpus.save_json(path, payload)


def harvest(workers=8):
    session = requests.Session()
    checked_at = corpus.now()
    index_response = request(session, INDEX)
    index_evidence = snapshot(index_response.content, "past-auction-dates", index_response.url,
                              "complete first-party 32-link past-event index", checked_at)
    event_urls = parse_event_index(index_response.content, index_response.url)
    index_text = BeautifulSoup(index_response.content, "lxml").get_text(" ", strip=True)
    if COMPANY_NUMBER not in index_text or "Auction Property Ltd" not in index_text:
        raise ValueError("first-party footer does not identify the legal operator")

    sold_response = request(session, SOLD)
    sold_evidence = snapshot(sold_response.content, "sold-properties", sold_response.url,
                             "complete first-party 16-card sold-property grid", checked_at)
    sold_rows = parse_sold_page(sold_response.content, sold_response.url, sold_evidence)

    event_pages = []
    failures = []
    def fetch_event(url):
        response = request(requests.Session(), url)
        slug = EVENT_RE.match(urlparse(url).path).group(1).lower()
        evidence = snapshot(response.content, f"event-{slug}", response.url,
                            "complete current first-party event page and surviving card inventory")
        return parse_event_page(response.content, response.url, evidence)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        jobs = {executor.submit(fetch_event, url): url for url in event_urls}
        for future in as_completed(jobs):
            try:
                event_pages.append(future.result())
            except Exception as exc:
                failures.append({"url": jobs[future], "error": f"{type(exc).__name__}: {exc}"[:500]})
    event_pages.sort(key=lambda item: event_urls.index(item["event_url"]))
    if failures or len(event_pages) != len(event_urls):
        raise ValueError(f"event archive did not reconcile: {failures}")
    cards = [row for event in event_pages for row in event["rows"]]
    if len(cards) != 51:
        raise ValueError(f"expected 51 surviving event cards, found {len(cards)}")
    if len({(row["event_slug"], row["source_lot_id"]) for row in cards}) != len(cards):
        raise ValueError("event archive contains duplicate event/property identities")
    event_ids = {row["source_lot_id"] for row in cards}
    if set(sold_rows) - event_ids:
        raise ValueError("sold-property grid contains cards absent from linked event archive")
    for row in cards:
        row["index_evidence"] = index_evidence
        sold = sold_rows.get(row["source_lot_id"])
        if sold:
            if (sold["auction_date"] != row["auction_date"] or
                    normalized(sold["address"]) != normalized(row["address"]) or
                    sold["status"] != row["status"]):
                raise ValueError("sold-property and event-card evidence disagree")
            row["sold_page_evidence"] = sold_evidence

    parsed = []
    def fetch_detail(item):
        response = request(requests.Session(), item["original_url"])
        evidence = snapshot(response.content, f"property-{item['source_lot_id']}-{item['property_slug']}",
                            response.url, "linked first-party property detail page")
        return parse_detail(response.content, item, response.url, evidence)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        jobs = {executor.submit(fetch_detail, item): item for item in cards}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                parsed.append(future.result())
            except Exception as exc:
                failures.append({"source_lot_id": item["source_lot_id"], "url": item["original_url"],
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
    parsed.sort(key=lambda item: (event_urls.index(item["event_url"]), item["source_position"]))
    if failures or len(parsed) != len(cards):
        corpus.save_json(corpus.DATA / "auction_property_archive_collection.json", {
            "checked_at": corpus.now(), "source_url": INDEX, "linked_event_pages": len(event_urls),
            "surviving_event_cards": len(cards), "detail_pages_captured": len(parsed),
            "failures": failures, "run_new_appearances": 0, "next_growth_target": NEXT_TARGET,
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

    shard = corpus.DATA / "appearances/auction-property-ltd/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    corpus.write_rows("auction-property-ltd/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}

    for event in event_pages:
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"auction-property:{event['auction_date']}:{event['event_slug']}",
            "auction_date": event["auction_date"],
            "auction_date_precision": "day",
            "source_url": event["event_url"],
            "lots_captured": len(event["rows"]),
            "surviving_visible_cards": len(event["rows"]),
            "published_lots_offered": None,
            "catalogue_complete": False,
            "source_rows_complete": True,
            "denominator_reconciled": False,
            "completion_scope": (
                "every property card surviving on the current first-party event page; original catalogue denominator "
                "is unreconciled and empty event shells are retained without inventing removed lots"
            ),
            "source_evidence": event["event_evidence"],
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions/auction-property-ltd" /
                         f"{event['auction_date']}-{event['event_slug']}.json", state)

    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX,
        "operator": {"canonical_name": SOURCE, "legal_name": OPERATOR,
                     "company_number": COMPANY_NUMBER,
                     "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "linked_event_pages": len(event_pages),
        "nonempty_event_pages": sum(bool(event["rows"]) for event in event_pages),
        "empty_event_shells": sum(not event["rows"] for event in event_pages),
        "surviving_event_cards_reconciled": len(cards),
        "sold_grid_cards_reconciled_as_overlapping_evidence": len(sold_rows),
        "detail_pages_captured": len(parsed),
        "original_event_denominators_reconciled": 0,
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
        "completion_scope": (
            "all 32 linked event pages, all 51 surviving property cards, all 51 linked details and all 16 sold-grid "
            "cards; not proof of removed lots or original event catalogue completeness"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "auction_property_archive_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
