"""Bank City & Rural Property Auctions' retained first-party auction cards.

The official auction sitemap retains exact-dated event pages.  Each admitted
appearance is an individual property card with an address, postcode, guide and
published outcome.  Event pages and the sitemap are saved as immutable source
snapshots.  A dash in the source's lot field remains null; no lot number or
price is inferred.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "City & Rural Property Auctions"
SLUG = "city-rural-property-auctions"
BASE = "https://cityandruralpropertyauctions.com"
SITEMAP = BASE + "/auction-sitemap.xml"
OPERATOR = "CITY & RURAL PROPERTY AUCTIONS LTD"
COMPANY_NUMBER = "14273913"
NEXT_TARGET_URL = "https://media.onthemarket.com/properties/7772028/1171489795/document-0.pdf"
NEXT_TARGET = (
    "Collect the surviving TW Gaze 2019 Land & Property Auction results brochure at "
    f"{NEXT_TARGET_URL}. It publishes nine individual property rows with guide and achieved "
    "prices; preserve the brochure snapshot, recover the exact auction date from the document, "
    "bank each address once, and then inventory adjacent TW Gaze land/property auction brochures "
    "on the same retained media route. Reconcile TWG (1857) Ltd / TW Gaze as one operator and keep "
    "national completeness false."
)
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
EVENT_RE = re.compile(r"/(?:auction|live-stream|online-timed-auction)-([0-3]\d)-([01]\d)-(20\d{2})-(?:\d{4})/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value: object | None) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def get(url: str) -> tuple[str, bytes]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def event_date(url: str) -> str:
    match = EVENT_RE.search(urlparse(url).path)
    if not match:
        raise ValueError(f"auction URL has no exact date: {url}")
    day, month, year = match.groups()
    return datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y").date().isoformat()


def discover_event_urls(xml: str, today: str | None = None) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(xml, "xml")
    cutoff = today or date.today().isoformat()
    retained, future = [], []
    for node in soup.find_all("loc"):
        url = clean(node.get_text())
        if not url or not EVENT_RE.search(urlparse(url).path):
            continue
        (future if event_date(url) > cutoff else retained).append(url.rstrip("/") + "/")
    return sorted(set(retained), key=lambda value: (event_date(value), value)), sorted(set(future))


def money_values(value: str | None) -> list[int]:
    return [int(round(float(item.replace(",", "")))) for item in MONEY_RE.findall(value or "")]


def guide_values(value: str | None) -> tuple[int | None, int | None]:
    prices = money_values(value)
    return (prices[0] if prices else None, prices[1] if len(prices) > 1 else None)


def outcome_values(value: str | None) -> tuple[str, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    price = money_values(text)
    sale_price = price[0] if price else None
    if lower.startswith("sold prior"):
        return "sold_prior", sale_price
    if lower.startswith("sold after"):
        return "sold_after", sale_price
    if lower.startswith("sold stc"):
        return "sold_stc", sale_price
    if lower.startswith("sold"):
        return "sold", sale_price
    if lower.startswith("available post"):
        return "available_post", None
    if lower.startswith("available"):
        return "available", None
    if lower.startswith("withdrawn"):
        return "withdrawn", None
    if lower.startswith("postponed"):
        return "postponed", None
    if lower.startswith("unsold"):
        return "unsold", None
    return "unknown", None


def property_slug(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 2 or parts[0] != "property":
        raise ValueError(f"unexpected property URL: {url}")
    return parts[1]


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def global_exact_appearances() -> dict[tuple[str, str], list[dict]]:
    values: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append(
                    {
                        "appearance_id": row.get("appearance_id"),
                        "auctioneer": row.get("auctioneer"),
                        "original_url": row.get("original_url"),
                    }
                )
    return values


def persist_continuation(summary: dict) -> None:
    path = corpus.DATA / "continuation_collection.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
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
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "tw-gaze-2019-results-brochure",
        "auctioneer": "TW Gaze",
        "source_urls": [NEXT_TARGET_URL],
        "source_format": "retained first-party result brochure PDF on a free public media cache",
        "opportunity": "nine uncaptured individual property rows with both guide and achieved prices",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def parse_event_page(html: str, source_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    auction_date = event_date(source_url)
    soup = BeautifulSoup(html, "lxml")
    cards = [
        card for card in soup.select("article")
        if card.select_one('h2 a[href*="/property/"]')
    ]
    rows, seen = [], set()
    for position, card in enumerate(cards, 1):
        property_links = card.select('h2 a[href*="/property/"]')
        if len(property_links) != 1:
            raise ValueError(f"event card {position} has {len(property_links)} property links")
        property_url = property_links[0].get("href", "").split("#", 1)[0]
        address = clean(property_links[0].get_text(" ", strip=True))
        if not address or not corpus.PC.search(address):
            raise ValueError(f"event card {position} has no exact postcode address")
        slug = property_slug(property_url)
        if slug in seen:
            raise ValueError(f"duplicate property card in event: {slug}")
        seen.add(slug)

        headings = [
            clean(node.get_text(" ", strip=True))
            for node in card.select(".elementor-heading-title")
        ]
        headings = [value for value in headings if value]
        lot_text = next((value for value in headings if re.fullmatch(r"Lot\s+\S+", value, re.I)), None)
        lot_match = re.fullmatch(r"Lot\s+([A-Z0-9]+)", lot_text or "", re.I)
        lot_number = lot_match.group(1).upper() if lot_match else None
        guide_text = next((value for value in headings if value.casefold().startswith("guide price")), None)
        if guide_text is None:
            raise ValueError(f"event card {position} has no guide heading")
        outcome_text = next(
            (
                value for value in headings
                if re.match(r"^(?:sold|available|withdrawn|postponed|unsold)\b", value, re.I)
            ),
            None,
        )
        property_type = next(
            (
                value for value in headings
                if value not in {lot_text, guide_text, outcome_text, address}
                and not value.casefold().startswith("lot ")
            ),
            None,
        )
        guide, guide_high = guide_values(guide_text)
        status, sale_price = outcome_values(outcome_text)
        source_id = hashlib.sha256(f"{auction_date}|{slug}".encode()).hexdigest()[:24]
        auction_id = f"{SLUG}:{auction_date}"
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_id, property_url)
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
            annual_rent=None,
            property_id=slug,
            identity_method="first_party_exact_auction_date_and_property_detail_url",
            record_quality="address_record",
            source_position=position,
            source_guide_text=guide_text,
            source_outcome_text=outcome_text,
            source_event_url=source_url,
            source_property_url=property_url,
            auction_date_precision="day",
            auction_date_basis="exact date in first-party auction URL",
            source_platform="City & Rural Property Auctions first-party event archive",
            operator_legal_name=OPERATOR,
            operator_company_number=COMPANY_NUMBER,
            trading_name=SOURCE,
            source_evidence=evidence,
        )
        rows.append(row)

    state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": f"{SLUG}:{auction_date}",
        "auction_date": auction_date,
        "auction_date_precision": "day",
        "source_url": source_url,
        "visible_property_cards": len(rows),
        "lots_captured": len(rows),
        "catalogue_complete": bool(rows),
        "source_rows_complete": bool(rows),
        "denominator_reconciled": bool(rows),
        "published_lot_denominator": len(rows) if rows else None,
        "completion_scope": "all visible individual property cards on the retained first-party event page",
        "source_evidence": evidence,
        "errors": [] if rows else ["retained event page exposes no individual property cards"],
        "checked_at": corpus.now(),
    }
    return state, rows


def harvest(workers: int = 10) -> dict:
    sitemap_url, raw = get(SITEMAP)
    sitemap_sha, retrieved_at = corpus.digest(raw), corpus.now()
    sitemap_snapshot = corpus.DATA / "sources" / SLUG / f"auction-sitemap-{sitemap_sha[:16]}.xml.gz"
    sitemap_evidence = {
        "source_url": sitemap_url,
        "retrieved_at": retrieved_at,
        "sha256": sitemap_sha,
        "snapshot_path": str(sitemap_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party auction sitemap",
    }
    if not sitemap_snapshot.exists():
        corpus.atomic(sitemap_snapshot, __import__("gzip").compress(raw, mtime=0))
    event_urls, future_urls = discover_event_urls(raw.decode("utf-8", "replace"))
    if not event_urls:
        raise SystemExit("No retained first-party event pages discovered")

    run_rows, states, failures = [], {}, []

    def capture(url: str):
        resolved, page_raw = get(url)
        captured_at, page_sha = corpus.now(), corpus.digest(page_raw)
        auction_date = event_date(resolved)
        snapshot = corpus.DATA / "sources" / SLUG / f"event-{auction_date}-{page_sha[:16]}.html.gz"
        evidence = {
            "source_url": resolved,
            "retrieved_at": captured_at,
            "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party exact-dated auction page with individual property cards",
        }
        if not snapshot.exists():
            corpus.atomic(snapshot, __import__("gzip").compress(page_raw, mtime=0))
        state, rows = parse_event_page(page_raw.decode("utf-8", "replace"), resolved, evidence)
        event_key = urlparse(resolved).path.strip("/").split("/")[-1]
        return event_key, state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(capture, url): url for url in event_urls}
        for future in as_completed(jobs):
            url = jobs[future]
            try:
                event_key, state, rows = future.result()
                corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{event_key}.json", state)
                states[event_key] = state
                run_rows.extend(rows)
                print("CITY_RURAL", len(states), "/", len(event_urls), "pages", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    global_exact = global_exact_appearances()
    overlap_exclusions, admissible = [], []
    for row in run_rows:
        matches = global_exact.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlap_exclusions.append(
                {
                    "auction_date": row["auction_date"],
                    "lot_number": row["lot_number"],
                    "address": row["address"],
                    "city_rural_appearance_id": row["appearance_id"],
                    "existing": matches,
                }
            )
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    empty_states = [state for state in states.values() if not state["lots_captured"]]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    historical_added = [
        row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today
    ]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "source_url": SITEMAP,
        "operator": {
            "canonical_name": SOURCE,
            "company_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "event_pages_discovered": len(event_urls),
        "event_pages_captured": len(states),
        "event_pages_with_individual_lots": sum(bool(state["lots_captured"]) for state in states.values()),
        "event_pages_without_retained_lots": len(empty_states),
        "future_event_pages_excluded": len(future_urls),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(historical_added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_rows_without_published_outcome": sum(
            not row.get("source_outcome_text") for row in added
        ),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added
        ),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "sitemap_evidence": sitemap_evidence,
        "auctions": states,
        "future_event_urls": future_urls,
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlap_exclusions),
        "duplicate_source_evidence_exclusions": overlap_exclusions,
        "catalogue_pdf_route": {
            "url": "https://catalogue.cityandruralpropertyauctions.com/march23/catalogue.pdf",
            "status": "temporarily unavailable from collector route (HTTP 503); event-page evidence banked independently",
        },
    }
    corpus.save_json(corpus.DATA / "city_rural_property_auctions_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(event_urls):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    harvest(args.workers)
