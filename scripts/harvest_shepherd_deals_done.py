"""Bank Shepherd's complete public ``Deals Done`` auction-property inventory.

The page mixes ordinary sales and lettings with auction properties.  All cards
are present in the first response; its ``Load More`` button only reveals twelve
more pre-rendered cards at a time.  This collector snapshots that denominator,
selects every card explicitly labelled ``Auction Property``, fetches the
first-party detail pages in one reusable batch and banks exact-dated property
appearances.  Existing rows from the saved live board are enriched with the
result outcome instead of being counted twice.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE_NAME = "Shepherd Commercial Auctions"
SLUG = "shepherd-commercial"
INDEX_URL = "https://www.shepherd.co.uk/deals-done/"
DETAIL_ID_RE = re.compile(r"/property/details/(\d+)(?:/|$)", re.I)
DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\b",
    re.I,
)
PRICE_RE = re.compile(
    r"Guide\s+Price\s*[:\-]?\s*£\s*([\d,]+(?:\.\d+)?)"
    r"(?:\s*(?:-|–|to)\s*£\s*([\d,]+(?:\.\d+)?))?",
    re.I,
)
PRICE_BEFORE_LABEL_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)"
    r"(?:\s*(?:-|–|to)\s*£\s*([\d,]+(?:\.\d+)?))?\s+Guide\s+price",
    re.I,
)
ANNUAL_RENT_PATTERNS = (
    re.compile(
        r"\b(?:current\s+)?passing\s+rent\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)"
        r"\s*(?:per\s+annum|p\.?\s*a\.?)",
        re.I,
    ),
    re.compile(
        r"\b(?:current\s+)?rental\s+income\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)"
        r"\s*(?:per\s+annum|p\.?\s*a\.?)",
        re.I,
    ),
    re.compile(
        r"\b(?:currently\s+)?let\s+(?:at|for)\s+(?:a\s+rent\s+of\s+)?"
        r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?\s*a\.?)",
        re.I,
    ),
    re.compile(
        r"\b(?:producing|annual\s+income\s+of)\s+£\s*([\d,]+(?:\.\d+)?)"
        r"\s*(?:per\s+annum|p\.?\s*a\.?)?",
        re.I,
    ),
)


def fetch(url: str, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - live retry path
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def clean_text(node) -> str | None:
    if node is None:
        return None
    return corpus.clean(node.get_text(" ", strip=True)) or None


def source_id(url: str) -> str:
    match = DETAIL_ID_RE.search(urlsplit(url).path)
    if match:
        return match.group(1)
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def money(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return None


def guide_candidates(text: str) -> list[tuple[int, int | None, str]]:
    matches = list(PRICE_RE.finditer(text)) + list(PRICE_BEFORE_LABEL_RE.finditer(text))
    values = []
    for match in matches:
        low, high = money(match.group(1)), money(match.group(2))
        if low is not None:
            values.append((low, high, corpus.clean(match.group(0))))
    unique = []
    for value in values:
        if value[:2] not in [item[:2] for item in unique]:
            unique.append(value)
    return unique


def parse_guide(text: str) -> tuple[int | None, int | None, str | None]:
    values = guide_candidates(text)
    return values[0] if values else (None, None, None)


def parse_annual_rent(text: str) -> tuple[int | None, str | None]:
    matches = []
    for pattern in ANNUAL_RENT_PATTERNS:
        for match in pattern.finditer(text):
            value = money(match.group(1))
            if value is not None:
                matches.append((value, corpus.clean(match.group(0))))
    if not matches:
        return None, None
    distinct = {value for value, _ in matches}
    if len(distinct) != 1:
        return None, None
    return matches[0]


def exact_date(value: str | None) -> str | None:
    match = DATE_RE.search(value or "")
    if not match:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def outcome(detail: BeautifulSoup, fallback: str | None) -> tuple[str, str | None]:
    candidates = [clean_text(node) for node in detail.select(".featured-bullets .bullet-item")]
    description = clean_text(detail.select_one(".detail-description"))
    candidates.extend([description, fallback])
    for value in filter(None, candidates):
        normalized = re.sub(r"[*_:]+", " ", value).casefold()
        if re.search(r"\bsold\s+prior\b", normalized):
            return "sold prior", value
        if re.search(r"\bsold\s+at\s+auction\b", normalized):
            return "sold at auction", value
        if re.search(r"\bsold\b", normalized):
            return "sold", value
        if re.search(r"\bwithdrawn\b", normalized):
            return "withdrawn", value
        if re.search(r"\bunsold\b", normalized):
            return "unsold", value
    return "unknown", fallback


def parse_index(raw: bytes, index_url: str = INDEX_URL) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(raw, "html.parser")
    wrappers = soup.select(".property-wrapper")
    rows = []
    for wrapper in wrappers:
        types = [clean_text(node) for node in wrapper.select(".item-size span")]
        if not any(value and value.casefold() == "auction property" for value in types):
            continue
        link = wrapper.select_one('a[href*="/property/details/"]')
        address = clean_text(wrapper.select_one(".item-address"))
        if not link or not address:
            raise ValueError("auction-property card lacks a detail URL or address")
        url = urljoin(index_url, link.get("href"))
        rows.append({
            "source_id": source_id(url),
            "url": url,
            "address": address,
            "card_price_text": clean_text(wrapper.select_one(".item-cost")),
            "lot_number": (clean_text(wrapper.select_one(".lot-number")) or "").removeprefix("Lot No.").strip() or None,
            "card_status": clean_text(wrapper.select_one(".unavailable-status")),
            "types": [value for value in types if value and value.casefold() != "auction property"],
        })
    if not wrappers or not rows:
        raise ValueError("Deals Done page exposes no property denominator or auction-property rows")
    if len({row["url"] for row in rows}) != len(rows):
        raise ValueError("duplicate auction-property detail URL in Deals Done index")
    return len(wrappers), rows


def snapshot_raw(raw: bytes, name: str) -> tuple[str, Path]:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.html.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wb") as handle:
            handle.write(raw)
    return sha, path


def parse_detail(card: dict, raw: bytes, evidence: dict) -> dict:
    soup = BeautifulSoup(raw, "html.parser")
    address = clean_text(soup.select_one("h1.property-address")) or card["address"]
    date_text = clean_text(soup.select_one(".property-auction span"))
    auction_date = exact_date(date_text)
    if not auction_date:
        raise ValueError("detail page lacks an exact published auction date")
    detail_lot = clean_text(soup.select_one(".property-lot"))
    lot_number = (detail_lot or "").removeprefix("Lot No.").strip() or card.get("lot_number")
    description = clean_text(soup.select_one(".detail-description"))
    bullets = " ".join(filter(None, (clean_text(node) for node in soup.select(".featured-bullets .bullet-item"))))
    displayed_price = " ".join(
        filter(None, (clean_text(node) for node in soup.select(".property-cost-size .item-cost")))
    )
    price_sources = [displayed_price, bullets, description, card.get("card_price_text") or ""]
    guide, guide_high, guide_text = None, None, None
    for price_source in price_sources:
        guide, guide_high, guide_text = parse_guide(price_source)
        if guide is not None:
            break
    all_guides = []
    for price_source in price_sources:
        for low, high, text in guide_candidates(price_source):
            if (low, high) not in [(item["low"], item["high"]) for item in all_guides]:
                all_guides.append({"low": low, "high": high, "text": text})
    annual_rent, rent_text = parse_annual_rent(" ".join(filter(None, [bullets, description])))
    status, status_text = outcome(soup, card.get("card_status"))
    types = [clean_text(node) for node in soup.select(".property-cost-size .item-size span")]
    types = [value for value in types if value and value.casefold() != "auction property"] or card["types"]
    type_text = ", ".join(types) or None
    size_text = clean_text(soup.select_one(".property-cost-size .item-size")) or ""
    floor_match = re.search(r"([\d,]+(?:\.\d+)?)\s*Sq\s*Ft\b", size_text, re.I)
    site_match = re.search(r"([\d,]+(?:\.\d+)?)\s*Acres?\b", size_text, re.I)
    images = []
    for image in soup.select(".property-images-slider img[src]"):
        url = urljoin(card["url"], image.get("src"))
        if url not in images:
            images.append(url)
    brochure = soup.find("a", string=re.compile(r"Download brochure", re.I))
    postcode_match = corpus.PC.search(address)
    sid = card["source_id"]
    row = corpus.base_row(
        SOURCE_NAME,
        f"shepherd:{auction_date}",
        auction_date,
        lot_number,
        sid,
        card["url"],
    )
    row.update(
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector=corpus.sector(" ".join(filter(None, [type_text, description]))),
        property_type=type_text,
        tenure=None,
        guide_price=guide,
        guide_price_high=guide_high,
        sale_price=None,
        status=status,
        status_text=status_text,
        description=description,
        annual_rent=annual_rent,
        rent_text=rent_text,
        floor_area=float(floor_match.group(1).replace(",", "")) if floor_match else None,
        site_area=float(site_match.group(1).replace(",", "")) if site_match else None,
        image_urls=images,
        brochure_url=urljoin(card["url"], brochure.get("href")) if brochure else None,
        property_id=f"shepherd-detail:{sid}",
        identity_method="same_auction_and_first_party_shepherd_detail_id",
        record_quality="address_record",
        auction_date_basis="exact date published on first-party Shepherd detail page",
        source_evidence=evidence,
        guide_price_text=guide_text,
        published_guide_price_evidence=all_guides,
        achieved_price_basis="no numeric achieved price published on Deals Done or detail page",
        operator_reconciliation_pending=True,
        operator_reconciliation_note=(
            "Shepherd Commercial Auctions, Shepherd Commercial Ltd, John Shepherd "
            "Chartered Surveyors and branch labels remain aliases pending legal-operator reconciliation"
        ),
    )
    return row


def duplicate_reason(candidate: dict, matches: list[dict]) -> str | None:
    for match in matches:
        if candidate.get("property_id") and candidate.get("property_id") == match.get("property_id"):
            return "same first-party Shepherd detail identity"
        if candidate.get("guide_price") is not None and candidate.get("guide_price") == match.get("guide_price"):
            return "same date/address and guide price"
        if candidate.get("sale_price") is not None and candidate.get("sale_price") == match.get("sale_price"):
            return "same date/address and achieved price"
    return None


def enrich_overlap(existing: dict, candidate: dict) -> bool:
    changed = False
    if existing.get("status") in (None, "", "unknown") and candidate.get("status") not in (None, "", "unknown"):
        existing["status"] = candidate["status"]
        existing["status_text"] = candidate.get("status_text")
        changed = True
    for field in ("annual_rent", "rent_text", "guide_price_high"):
        if existing.get(field) is None and candidate.get(field) is not None:
            existing[field] = candidate[field]
            changed = True
    retained = list(existing.get("additional_source_evidence") or [])
    evidence = candidate["source_evidence"]
    if not any(item.get("response_sha256") == evidence.get("response_sha256") for item in retained):
        retained.append(evidence)
        existing["additional_source_evidence"] = retained
        changed = True
    return changed


def twenty_year_cutoff(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year - 20)
    except ValueError:
        return as_of.replace(year=as_of.year - 20, day=28)


def run_collection(workers: int, as_of: date) -> dict:
    index_raw = fetch(INDEX_URL)
    denominator, cards = parse_index(index_raw)
    index_sha, index_path = snapshot_raw(index_raw, "deals-done-index")
    retrieved_at = corpus.now()

    rows, errors = [], []
    def collect(card: dict) -> dict:
        raw = fetch(card["url"])
        detail_sha, detail_path = snapshot_raw(raw, f"deal-{card['source_id']}")
        evidence = {
            "source_url": card["url"],
            "index_url": INDEX_URL,
            "retrieved_at": retrieved_at,
            "response_sha256": detail_sha,
            "snapshot_path": str(detail_path.relative_to(corpus.ROOT)),
            "index_response_sha256": index_sha,
            "index_snapshot_path": str(index_path.relative_to(corpus.ROOT)),
            "evidence_tier": "first-party Shepherd Deals Done index and property detail page",
        }
        return parse_detail(card, raw, evidence)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(collect, card): card for card in cards}
        for future in as_completed(futures):
            card = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:  # retain successful evidence and prior rows
                errors.append({"url": card["url"], "error": f"{type(exc).__name__}: {exc}"})
    rows.sort(key=lambda row: (row["auction_date"], row.get("lot_number") or "", row["source_lot_id"]))

    appearance_path = corpus.DATA / "appearances" / SLUG / "deals-done.jsonl.gz"
    previous_deals = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    previous_deals_by_id = {row["appearance_id"]: row for row in previous_deals}
    previous_all = []
    paths_by_appearance: dict[str, Path] = {}
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == appearance_path:
            continue
        for existing in corpus.iter_rows(path):
            previous_all.append(existing)
            paths_by_appearance[existing["appearance_id"]] = path

    by_property: dict[str, list[dict]] = {}
    by_key: dict[tuple[str | None, str], list[dict]] = {}
    for existing in previous_all:
        if existing.get("property_id"):
            by_property.setdefault(existing["property_id"], []).append(existing)
        by_key.setdefault((existing.get("auction_date"), normalized_address(existing.get("address"))), []).append(existing)

    admitted, duplicates, related = [], [], []
    enriched_paths: dict[Path, dict[str, dict]] = {}
    enriched_existing, new_outcomes_on_existing = 0, 0
    for row in rows:
        matches = by_property.get(row.get("property_id"), [])
        if not matches:
            matches = by_key.get((row.get("auction_date"), normalized_address(row.get("address"))), [])
        reason = duplicate_reason(row, matches)
        if reason:
            changed_ids = []
            for match in matches:
                if match.get("property_id") != row.get("property_id"):
                    continue
                before_status = match.get("status")
                if enrich_overlap(match, row):
                    changed_ids.append(match["appearance_id"])
                    enriched_existing += 1
                    if before_status in (None, "", "unknown") and match.get("status") not in (None, "", "unknown"):
                        new_outcomes_on_existing += 1
                    path = paths_by_appearance[match["appearance_id"]]
                    enriched_paths.setdefault(path, {})[match["appearance_id"]] = match
            duplicates.append({
                "source_lot_id": row["source_lot_id"],
                "reason": reason,
                "matched_appearance_ids": [match["appearance_id"] for match in matches],
                "enriched_appearance_ids": changed_ids,
            })
            continue
        if matches:
            related.append(row["appearance_id"])
        admitted.append(row)

    for path, changes in enriched_paths.items():
        original = list(corpus.iter_rows(path))
        updated = [changes.get(row["appearance_id"], row) for row in original]
        relative = path.relative_to(corpus.DATA / "appearances").as_posix().removesuffix(".jsonl.gz")
        corpus.write_rows(relative, updated)

    merged_deals = dict(previous_deals_by_id)
    merged_deals.update({row["appearance_id"]: row for row in admitted})
    retained = corpus.write_rows(f"{SLUG}/deals-done", merged_deals.values())
    if retained != len(merged_deals):
        raise ValueError(f"retained {retained} Deals Done rows; expected {len(merged_deals)}")
    new_rows = [row for row in admitted if row["appearance_id"] not in previous_deals_by_id]
    cutoff = twenty_year_cutoff(as_of).isoformat()
    in_window = [row for row in new_rows if row.get("auction_date") and cutoff <= row["auction_date"] <= as_of.isoformat()]
    future = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > as_of.isoformat()]
    undated = [row for row in new_rows if not row.get("auction_date")]
    partial = [row for row in new_rows if not row.get("address")]

    all_shepherd = []
    for path in (corpus.DATA / "appearances" / SLUG).glob("*.jsonl.gz"):
        all_shepherd.extend(corpus.iter_rows(path))
    by_date = Counter(row["auction_date"] for row in all_shepherd if row.get("auction_date"))
    source_evidence = {
        "source_url": INDEX_URL,
        "retrieved_at": retrieved_at,
        "response_sha256": index_sha,
        "snapshot_path": str(index_path.relative_to(corpus.ROOT)),
        "evidence_tier": "complete rendered first-party Deals Done card denominator",
    }
    for auction_date, count in sorted(by_date.items()):
        state_path = corpus.DATA / "auctions" / SLUG / f"{auction_date}.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        state.update({
            "auctioneer": SOURCE_NAME,
            "source_auction_id": f"shepherd:{auction_date}",
            "auction_date": auction_date,
            "catalogue_complete": False,
            "deals_done_inventory_reconciled": not errors,
            "completion_scope": "all auction-property cards in the current Shepherd Deals Done denominator; not the original catalogue denominator",
            "lots_captured": count,
            "deals_done_source_snapshot": source_evidence,
            "errors": errors,
            "checked_at": corpus.now(),
        })
        corpus.save_json(state_path, state)

    previous_years = {
        row["auction_date"][:4]
        for row in previous_all
        if row.get("auctioneer") == SOURCE_NAME and row.get("auction_date")
    }
    summary = {
        "checked_at": corpus.now(),
        "source": "shepherd-deals-done",
        "auctioneer": SOURCE_NAME,
        "index_url": INDEX_URL,
        "source_snapshot": source_evidence,
        "total_deal_cards": denominator,
        "auction_property_cards": len(cards),
        "detail_pages_captured": len(rows),
        "detail_page_errors": errors,
        "appearances_captured_from_deals_done": len(merged_deals),
        "run_new_appearances": len(new_rows),
        "run_new_address_records": len(new_rows) - len(partial),
        "run_new_dated_twenty_year_address_records": len([row for row in in_window if row.get("address")]),
        "run_new_partial_lots": len(partial),
        "run_new_undated": len(undated),
        "run_new_future_dated": len(future),
        "run_new_commercial_or_mixed": sum(row["sector"] in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_new_published_outcomes": sum(row.get("status") not in (None, "", "unknown") for row in new_rows) + new_outcomes_on_existing,
        "run_enriched_existing_appearances": enriched_existing,
        "run_new_outcomes_on_existing_appearances": new_outcomes_on_existing,
        "run_duplicate_source_evidence_excluded": len(duplicates),
        "duplicate_evidence": duplicates,
        "related_interest_candidates_preserved": len(related),
        "related_interest_candidate_ids": related,
        "new_source_years": sorted({row["auction_date"][:4] for row in in_window} - previous_years),
        "source_event_dates": sorted({row["auction_date"] for row in rows}),
        "by_date": dict(sorted(Counter(row["auction_date"] for row in rows).items())),
        "by_sector_new": dict(Counter(row["sector"] for row in new_rows)),
        "deals_done_inventory_reconciled": len(rows) == len(cards) and not errors,
        "historical_archive_complete": False,
        "operator_reconciliation_pending": True,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "shepherd_deals_done_collection.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--as-of-date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    run_collection(args.workers, date.fromisoformat(args.as_of_date))


if __name__ == "__main__":
    main()
