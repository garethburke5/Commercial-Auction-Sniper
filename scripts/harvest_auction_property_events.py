"""Bank Auction Property Ltd's surviving first-party past-event cards.

The WordPress past-auction index retains event links while individual event
pages may later be emptied or repurposed.  This collector snapshots the whole
index and every linked event in one batch, admits only visible property cards,
and takes an appearance's exact date from the card itself.  Mutable property
detail pages are deliberately not used to overwrite historical dates or
outcomes when a property is relisted.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
BASE = "https://auctionproperty.co.uk"
INDEX_URL = BASE + "/past-auction-dates/"
OPERATOR = "AUCTION PROPERTY LTD"
COMPANY_NUMBER = "12828051"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_PATH_RE = re.compile(r"^/property/[^/]+/?$", re.I)
EVENT_PATH_RE = re.compile(r"^/auction/[^/]+/?$", re.I)
DATE_RE = re.compile(
    r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(20\d{2})\b",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
STATUS_RE = re.compile(
    r"^(sold\s+prior|sold\s+after|sold\s+stc|sold|withdrawn|postponed|unsold|available\s+post|available)\b",
    re.I,
)
NEXT_TARGET = (
    "Inventory Auction Inspire and Auction Local as one bounded first-party discovery batch. "
    "Select the operator whose public archive exposes the larger individually dated lot inventory, "
    "then bank its complete surviving multi-event grid through a reusable collector; reconcile legal "
    "operators and shared-platform labels before counting either as a new auctioneer."
)


def clean(value: object | None) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        retry_after = response.headers.get("Retry-After")
        delay = int(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 20)
        time.sleep(max(1, delay))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def parse_date(value: str | None) -> str:
    match = DATE_RE.search(clean(value) or "")
    if not match:
        raise ValueError(f"no exact published date in {value!r}")
    day, month, year = match.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()


def discover_events(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    discovered: dict[str, dict] = {}
    for anchor in soup.select('a[href*="/auction/"]'):
        url = urljoin(BASE, anchor.get("href", "")).split("#", 1)[0]
        if not EVENT_PATH_RE.fullmatch(urlparse(url).path):
            continue
        label = clean(anchor.get_text(" ", strip=True))
        try:
            index_date = parse_date(label)
        except ValueError:
            continue
        discovered.setdefault(
            url.rstrip("/") + "/",
            {"url": url.rstrip("/") + "/", "index_label": label, "index_date": index_date},
        )
    return sorted(discovered.values(), key=lambda item: (item["index_date"], item["url"]))


def property_slug(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 2 or parts[0].casefold() != "property":
        raise ValueError(f"unexpected property URL: {url}")
    return parts[1]


def event_key(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 2 or parts[0].casefold() != "auction":
        raise ValueError(f"unexpected auction URL: {url}")
    return parts[1]


def money_values(value: str | None) -> list[int]:
    return [int(round(float(item.replace(",", "")))) for item in MONEY_RE.findall(value or "")]


def guide_values(value: str | None) -> tuple[int | None, int | None]:
    prices = money_values(value)
    return (prices[0] if prices else None, prices[1] if len(prices) > 1 else None)


def outcome_values(value: str | None) -> tuple[str, int | None]:
    text = clean(value) or ""
    match = STATUS_RE.match(text)
    if not match:
        return "unknown", None
    status = re.sub(r"\s+", "_", match.group(1).casefold())
    prices = money_values(text)
    sale_price = prices[0] if prices and status.startswith("sold") else None
    return status, sale_price


def rent_value(value: str | None) -> int | None:
    text = clean(value) or ""
    match = re.search(
        r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?a\.?)\b",
        text,
        re.I,
    )
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def _headings(card) -> list[str]:
    values = [clean(node.get_text(" ", strip=True)) for node in card.select(".elementor-heading-title")]
    return [value for value in values if value]


def parse_event_page(
    html: str,
    source_url: str,
    index_date: str,
    index_label: str,
    evidence: dict,
) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    key = event_key(source_url)
    cards = []
    for card in soup.select(".elementor-element-1dd3b22"):
        links = [
            anchor
            for anchor in card.select('a[href*="/property/"]')
            if PROPERTY_PATH_RE.fullmatch(urlparse(urljoin(BASE, anchor.get("href", ""))).path)
        ]
        if links:
            cards.append(card)

    rows, seen = [], set()
    for position, card in enumerate(cards, 1):
        property_links = []
        for anchor in card.select('a[href*="/property/"]'):
            url = urljoin(BASE, anchor.get("href", "")).split("#", 1)[0]
            if PROPERTY_PATH_RE.fullmatch(urlparse(url).path):
                property_links.append((url.rstrip("/") + "/", clean(anchor.get_text(" ", strip=True))))
        unique_urls = list(dict.fromkeys(url for url, _ in property_links))
        if len(unique_urls) != 1:
            raise ValueError(f"event card {position} has {len(unique_urls)} property identities")
        property_url = unique_urls[0]
        address_candidates = [text for url, text in property_links if url == property_url and text]
        address = max(address_candidates, key=len) if address_candidates else None
        if not address or not corpus.PC.search(address):
            raise ValueError(f"event card {position} has no exact postcode address")
        slug = property_slug(property_url)
        if slug in seen:
            raise ValueError(f"duplicate property card in event: {slug}")
        seen.add(slug)

        headings = _headings(card)
        lot_text = next((value for value in headings if re.fullmatch(r"LOT\s+\S+", value, re.I)), None)
        lot_match = re.fullmatch(r"LOT\s+([A-Z0-9-]+)", lot_text or "", re.I)
        lot_number = lot_match.group(1).upper() if lot_match else None
        date_text = next((value for value in headings if value.casefold().startswith("auction:")), None)
        # The oldest retained 14 December 2023 template prints the exact date
        # in the first-party index/event title but not inside each card.  Use
        # that event-level date only for those cards; never consult the mutable
        # property detail page.
        auction_date = parse_date(date_text) if date_text else index_date
        outcome_text = next((value for value in headings if STATUS_RE.match(value)), None)
        guide_text = next((value for value in headings if value.casefold().startswith("guide")), None)
        ignored = {lot_text, date_text, outcome_text, guide_text, address}
        property_type = next(
            (
                value
                for value in headings
                if value not in ignored
                and not value.casefold().startswith("by order")
                and not re.fullmatch(r"\d+", value)
            ),
            None,
        )
        guide, guide_high = guide_values(guide_text)
        status, sale_price = outcome_values(outcome_text)
        full_text = clean(card.get_text(" ", strip=True))
        annual_rent = rent_value(full_text)
        auction_id = f"{SLUG}:{key}"
        source_lot_id = f"{key}:{slug}"
        row = corpus.base_row(
            SOURCE,
            auction_id,
            auction_date,
            lot_number,
            source_lot_id,
            property_url,
        )
        postcode = corpus.PC.search(address)
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|property:{slug}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            property_type=property_type,
            sector=corpus.sector(" ".join(filter(None, [address, property_type]))),
            status=status,
            guide_price=guide,
            guide_price_high=guide_high,
            sale_price=sale_price,
            annual_rent=annual_rent,
            property_id=slug,
            identity_method="first_party_exact_event_card_date_and_property_url",
            record_quality="address_record",
            source_position=position,
            source_guide_text=guide_text,
            source_outcome_text=outcome_text,
            source_event_date_text=date_text,
            source_event_url=source_url,
            source_property_url=property_url,
            source_index_label=index_label,
            source_index_date=index_date,
            auction_date_precision="day",
            auction_date_basis=(
                "exact date printed on first-party property card"
                if date_text
                else "exact date printed on first-party past-auction index and event title"
            ),
            source_platform="Auction Property first-party past-event archive",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name=SOURCE,
            source_evidence=evidence,
        )
        rows.append(row)

    card_dates = sorted({row["auction_date"] for row in rows})
    if len(card_dates) > 1:
        raise ValueError(f"event page publishes multiple card dates: {card_dates}")
    published_date = card_dates[0] if card_dates else index_date
    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": f"{SLUG}:{key}",
        "auction_date": published_date,
        "auction_date_precision": "day",
        "auction_date_basis": (
            "exact date printed on retained property cards or, for the oldest template, the exact "
            "first-party index/event-title date"
            if rows
            else "exact date label on first-party past-auction index; no property appearance admitted"
        ),
        "index_date": index_date,
        "index_label": index_label,
        "source_url": source_url,
        "visible_property_cards": len(rows),
        "lots_captured": len(rows),
        "catalogue_complete": True,
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "published_lot_denominator": len(rows),
        "completion_scope": (
            "all currently visible individual property cards on the surviving first-party event page; "
            "empty or repurposed shells do not count as properties and deleted earlier lots are not claimed"
        ),
        "empty_or_repurposed_shell": not rows,
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    return state, rows


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def global_exact_appearances() -> Counter:
    values = Counter()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))] += 1
    return values


def exclude_exact_overlaps(rows: list[dict], global_keys: Counter) -> tuple[list[dict], list[dict]]:
    source_keys = Counter(
        (row["auction_date"], normalized_address(row["address"]))
        for row in rows
        if row.get("auction_date") and row.get("address")
    )
    retained, excluded = [], []
    for row in rows:
        key = (row["auction_date"], normalized_address(row["address"]))
        if source_keys[key] == 1 and global_keys[key] >= 1:
            excluded.append(
                {
                    "auction_date": row["auction_date"],
                    "address": row["address"],
                    "source_lot_id": row["source_lot_id"],
                    "original_url": row["original_url"],
                    "existing_match_count": global_keys[key],
                }
            )
        else:
            retained.append(row)
    return retained, excluded


def snapshot(raw: bytes, source_url: str, name: str, basis: str) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.html.gz"
    evidence = {
        "source_url": source_url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return evidence


def persist_continuation(summary: dict) -> None:
    path = corpus.DATA / "continuation_collection.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    smart_path = corpus.DATA / "smart_property_auctions_collection.json"
    smart = json.loads(smart_path.read_text(encoding="utf-8")) if smart_path.exists() else {}

    source_checkpoints = [
        {
            "source": "eig_retained_grid:smart-property-auctions",
            "outcome": "completed",
            "checked_at": smart.get("checked_at"),
            "run_new_appearances": smart.get("run_new_appearances", 0),
            "run_new_dated_twenty_year_address_records": smart.get(
                "run_new_dated_twenty_year_address_records", 0
            ),
            "run_new_commercial_or_mixed": smart.get("run_new_commercial_mixed", 0),
            "run_new_guide_prices": smart.get("run_new_guide_prices", 0),
            "run_new_sale_prices": smart.get("run_new_sale_prices", 0),
            "newly_covered_source_years": smart.get("new_source_years", []),
            "duplicate_source_evidence_excluded": smart.get(
                "run_duplicate_source_evidence_excluded", 0
            ),
            "national_completeness_verified": False,
        },
        {
            "source": SLUG,
            "outcome": "completed",
            "checked_at": summary["checked_at"],
            "run_new_appearances": summary["run_new_appearances"],
            "run_new_dated_twenty_year_address_records": summary[
                "run_new_dated_twenty_year_address_records"
            ],
            "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
            "run_new_guide_prices": summary["run_new_guide_prices"],
            "run_new_sale_prices": summary["run_new_sale_prices"],
            "newly_covered_source_years": summary["newly_covered_source_years"],
            "duplicate_source_evidence_excluded": summary[
                "run_duplicate_source_evidence_excluded"
            ],
            "national_completeness_verified": False,
        },
    ]
    existing_signatures = {
        (item.get("source"), item.get("checked_at")) for item in payload.setdefault("runs", [])
    }
    for checkpoint in source_checkpoints:
        signature = (checkpoint["source"], checkpoint["checked_at"])
        if checkpoint["checked_at"] and signature not in existing_signatures:
            payload["runs"].append(checkpoint)
        payload.setdefault("latest_by_source", {})[checkpoint["source"]] = checkpoint

    combined = {
        "checked_at": summary["checked_at"],
        "opportunity": "Auction Property Ltd and Smart Property Auctions first-party historical batch",
        "attempted_route": (
            "Captured Smart Property Auctions' complete 15-card dedicated past grid through the "
            "reusable EIG runner, then traversed every Auction Property past-event link and banked "
            "all surviving individual cards while retaining empty/repurposed shells as non-property evidence."
        ),
        "net_new_appearances": smart.get("run_new_appearances", 0) + summary["run_new_appearances"],
        "new_address_records": smart.get("run_new_address_records", 0) + summary["run_new_address_records"],
        "new_partial_lots": smart.get("run_new_partial_lots", 0) + summary["run_new_partial_lots"],
        "new_dated_address_records_in_twenty_year_window": smart.get(
            "run_new_dated_twenty_year_address_records", 0
        )
        + summary["run_new_dated_twenty_year_address_records"],
        "commercial_or_mixed_use": smart.get("run_new_commercial_mixed", 0)
        + summary["run_new_commercial_or_mixed"],
        "new_guide_prices": smart.get("run_new_guide_prices", 0) + summary["run_new_guide_prices"],
        "new_sale_prices": smart.get("run_new_sale_prices", 0) + summary["run_new_sale_prices"],
        "new_rent_values": smart.get("run_new_rents", 0) + summary["run_new_rents"],
        "new_undated_appearances": smart.get("run_new_undated", 0) + summary["run_new_undated"],
        "new_future_dated_appearances": smart.get("run_new_future_dated", 0)
        + summary["run_new_future_dated"],
        "newly_covered_source_years": {
            "Smart Property Auctions": smart.get("new_source_years", []),
            "Auction Property Ltd": summary["newly_covered_source_years"],
        },
        "duplicate_source_evidence_excluded": smart.get(
            "run_duplicate_source_evidence_excluded", 0
        )
        + summary["run_duplicate_source_evidence_excluded"],
        "operator_reconciliation": (
            "Smart Property Auctions is a trading platform of CAPITAL PRESTIGE LIMITED (06079839); "
            "Auction Property Ltd is AUCTION PROPERTY LTD (12828051). Directory and platform labels "
            "are not counted as additional auctioneers."
        ),
        "national_completeness_verified": False,
        "different_next_target": NEXT_TARGET,
    }
    payload["last_growth_attempt"] = combined
    payload["last_automated_growth"] = source_checkpoints[-1]
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidates": ["auction-inspire", "auction-local"],
        "opportunity": "two genuine auctioneer directory entries with zero linked retained appearances",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(workers: int = 8) -> dict:
    index_resolved, index_raw = get(INDEX_URL)
    index_evidence = snapshot(
        index_raw,
        index_resolved,
        "past-auction-index",
        "first-party past-auction index with exact date labels and event links",
    )
    events = discover_events(index_raw.decode("utf-8", "replace"))
    if not events:
        raise SystemExit("No first-party past-event links discovered")

    states, run_rows, failures = {}, [], []

    def capture(event: dict):
        resolved, raw = get(event["url"])
        key = event_key(event["url"])
        evidence = snapshot(
            raw,
            resolved,
            f"event-{key}",
            "first-party past-event page with surviving individual property cards or a bounded empty shell",
        )
        state, rows = parse_event_page(
            raw.decode("utf-8", "replace"),
            event["url"],
            event["index_date"],
            event["index_label"],
            evidence,
        )
        return key, state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(capture, event): event for event in events}
        for future in as_completed(jobs):
            event = jobs[future]
            try:
                key, state, rows = future.result()
                corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{key}.json", state)
                states[key] = state
                run_rows.extend(rows)
                print("AUCTION_PROPERTY", len(states), "/", len(events), "pages", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"url": event["url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    if failures or len(states) != len(events):
        failure_path = corpus.DATA / "auction_property_ltd_failures.json"
        corpus.save_json(failure_path, {"checked_at": corpus.now(), "failures": failures})
        raise SystemExit(f"event batch incomplete: {len(failures)} failure(s)")

    identity_counts = Counter(row["appearance_id"] for row in run_rows)
    duplicate_identities = [key for key, count in identity_counts.items() if count > 1]
    if duplicate_identities:
        raise SystemExit(f"duplicate source identities: {duplicate_identities[:5]}")

    admissible, overlap_exclusions = exclude_exact_overlaps(run_rows, global_exact_appearances())
    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    historical_added = [
        row for row in added if row.get("address") and cutoff <= row.get("auction_date", "") <= today
    ]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    empty_states = [state for state in states.values() if not state["lots_captured"]]
    summary = {
        "checked_at": corpus.now(),
        "source_url": INDEX_URL,
        "operator": {
            "canonical_name": SOURCE,
            "company_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "event_pages_discovered": len(events),
        "event_pages_captured": len(states),
        "event_pages_with_individual_lots": len(states) - len(empty_states),
        "event_pages_without_retained_lots": len(empty_states),
        "visible_property_cards": len(run_rows),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(
            bool(row.get("address") and row.get("auction_date")) for row in added
        ),
        "run_new_dated_twenty_year_address_records": len(historical_added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added
        ),
        "source_years": sorted(int(year) for year in years_after),
        "newly_covered_source_years": sorted(int(year) for year in years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "index_evidence": index_evidence,
        "events": states,
        "empty_or_repurposed_event_shells": sorted(
            state["source_url"] for state in empty_states
        ),
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlap_exclusions),
        "duplicate_source_evidence_exclusions": overlap_exclusions,
        "completion_scope": (
            "all currently visible individual property cards across every event linked by the first-party "
            "past-auction index; empty/repurposed shells and deleted earlier lots are not claimed"
        ),
        "mutable_detail_page_policy": (
            "property detail pages can be overwritten by relistings, so historical dates and outcomes are "
            "taken only from the immutable event-page snapshots"
        ),
    }
    corpus.save_json(corpus.DATA / "auction_property_ltd_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)
