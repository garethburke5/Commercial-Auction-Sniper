"""Bank individually indexed Venmore property pages whose old event grids were cleared.

The live archive still publishes exact-dated first-party detail pages, but its
older event grids either return no lots or leak the current inventory.  This
manifest-driven runner admits only explicitly enumerated detail URLs, validates
their lot number and date, and retains the source HTML as immutable evidence.
An indexed page is an evidenced appearance, never proof of a complete event.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import gzip
import json
from pathlib import Path
import re
import sys
import time

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts import harvest_venmore_catalogues as catalogue


SOURCE = "Venmore Auctions"
SLUG = "venmore-auctions"
RUN_KEY = "venmore-auctions-indexed-details"
ARCHIVE = "https://www.venmoreauctions.co.uk/Past-Auctions"
MANIFEST = corpus.ROOT / "config" / "venmore_indexed_detail_pages.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DETAIL_HEADING = re.compile(
    r"^Lot\s+(?P<lot>\d+)\s+-\s+\w+\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)\s+"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\s+-\s+(?P<address>.+)$"
)
NEXT_TARGET = (
    "Recover Venmore's indexed 2015 and older detail pages only through new "
    "search-index hits, saved files or catalogues; do not refresh the cleared "
    "event grids. In parallel rotate to another uncovered auctioneer archive "
    "with substantial accessible lot inventories. "
    "National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \xa0-") or None


def load_manifest(path=MANIFEST):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = payload.get("pages") or []
    if len(pages) != int(payload["expected_pages"]):
        raise ValueError("indexed detail page denominator does not reconcile")
    references = [str(page["property_reference"]) for page in pages]
    urls = [page["source_url"] for page in pages]
    identities = [(page["auction_date"], str(page["expected_lot_number"])) for page in pages]
    if len(set(references)) != len(pages):
        raise ValueError("manifest contains duplicate property references")
    if len(set(urls)) != len(pages):
        raise ValueError("manifest contains duplicate source URLs")
    if len(set(identities)) != len(pages):
        raise ValueError("manifest contains duplicate event lot identities")
    for page in pages:
        if f"property_reference={page['property_reference']}" not in page["source_url"]:
            raise ValueError("source URL and property reference disagree")
        date.fromisoformat(page["auction_date"])
        if not str(page["expected_lot_number"]).isdigit():
            raise ValueError("expected lot number is not numeric")
    return payload


def fetch(url):
    response = None
    for attempt in range(5):
        response = requests.get(url, headers=HEADERS, timeout=120)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.casefold() or b"<html" not in response.content[:1000].lower():
        raise ValueError("detail URL did not return HTML")
    return response.url, response.content


def save_snapshot(config, raw, sha):
    directory = corpus.DATA / "sources" / SLUG
    path = directory / (
        f"detail-{config['auction_date']}-{config['property_reference']}-"
        f"{sha[:20]}.html.gz"
    )
    compressed = gzip.compress(raw, mtime=0)
    if path.exists():
        if path.read_bytes() != compressed:
            raise ValueError(f"immutable detail snapshot changed at {path}")
    else:
        corpus.atomic(path, compressed)
    if corpus.digest(gzip.decompress(path.read_bytes())) != sha:
        raise ValueError(f"immutable detail snapshot digest mismatch at {path}")
    return {"snapshot_path": str(path.relative_to(corpus.ROOT))}


def retained_snapshot(config):
    directory = corpus.DATA / "sources" / SLUG
    matches = sorted(directory.glob(
        f"detail-{config['auction_date']}-{config['property_reference']}-*.html.gz"
    ))
    if not matches:
        return None
    path = matches[-1]
    return gzip.decompress(path.read_bytes()), {
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
    }


def outcome_status(value):
    text = clean(value) or ""
    if re.search(r"\bsold\s+prior\b", text, re.I):
        return "sold_prior"
    if re.search(r"\bsold\s+(?:after|later)\b", text, re.I):
        return "sold_after"
    if re.search(r"\bwithdrawn\b", text, re.I):
        return "withdrawn"
    if re.search(r"\bpostponed\b", text, re.I):
        return "postponed"
    if re.search(r"\bsold\b", text, re.I):
        return "sold"
    if re.search(r"\bavailable\b", text, re.I):
        return "available"
    return "unknown"


def address_precision(address):
    # One retained 2020 page publishes only "Apartment 7, 150" before its
    # locality and postcode. Preserve that source string, but do not claim the
    # missing street name is exact.
    if re.match(r"^(?:Apartment|Flat)\s+[^,]+,\s*\d+\s*,", address, re.I):
        return "partial"
    return "exact_published"


def parse_detail_page(raw, config):
    soup = BeautifulSoup(raw, "html.parser")
    heading = soup.find("h1")
    heading_text = clean(heading.get_text(" ", strip=True) if heading else None)
    match = DETAIL_HEADING.fullmatch(heading_text or "")
    if not match:
        raise ValueError(f"detail page heading is not an exact lot/date/address identity: {heading_text!r}")
    auction_date = datetime.strptime(
        f"{match.group('day')} {match.group('month')} {match.group('year')}",
        "%d %B %Y",
    ).date().isoformat()
    lot_number = match.group("lot")
    if auction_date != config["auction_date"]:
        raise ValueError(f"detail date {auction_date} does not match manifest")
    if lot_number != str(config["expected_lot_number"]):
        raise ValueError(f"detail lot {lot_number} does not match manifest")
    address = clean(match.group("address"))
    if not address:
        raise ValueError("detail page has a blank address")

    header = soup.select_one("h2.property-header-price")
    price_text = clean(header.get_text(" ", strip=True) if header else None)
    flashes = [clean(tag.get_text(" ", strip=True)) for tag in soup.select(".p-flash")]
    outcome_text = clean(" | ".join(filter(None, flashes + [price_text])))
    status = outcome_status(" ".join(filter(None, flashes))) if flashes else outcome_status(price_text)
    if status == "unknown":
        status = outcome_status(price_text)
    low, high = catalogue.parse_price(price_text)
    sale_price = low if status in {"sold", "sold_after"} and re.search(r"\bsold\b", price_text or "", re.I) else None
    guide_price = (
        low
        if sale_price is None and re.search(r"\b(?:available|guide)\b", price_text or "", re.I)
        else None
    )
    guide_high = high if guide_price is not None else None

    page_text = clean(soup.get_text(" ", strip=True)) or ""
    sector, (annual_rent, rent_text) = catalogue.sector_and_rent(address, page_text)
    return {
        "auction_date": auction_date,
        "lot_number": lot_number,
        "address": address,
        "address_precision": address_precision(address),
        "status": status,
        "guide_price": guide_price,
        "guide_price_high": guide_high,
        "sale_price": sale_price,
        "annual_rent": annual_rent,
        "rent_text": rent_text,
        "sector": sector,
        "source_price_text": price_text,
        "source_outcome_text": outcome_text,
    }


def materialize(config, source_url, evidence, raw):
    item = parse_detail_page(raw, config)
    auction_id = f"{SLUG}:{item['auction_date']}"
    source_lot_id = f"lot:{item['lot_number']}"
    row = corpus.base_row(
        SOURCE, auction_id, item["auction_date"], item["lot_number"],
        source_lot_id, source_url,
    )
    postcode = catalogue.POSTCODE.search(item["address"])
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
        address=item["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=item["address"],
        sector=item["sector"],
        property_type=None,
        status=item["status"],
        guide_price=item["guide_price"],
        guide_price_high=item["guide_price_high"],
        sale_price=item["sale_price"],
        annual_rent=item["annual_rent"],
        rent_text=item["rent_text"],
        identity_method="first_party_exact_event_date_detail_page_lot_number_and_address",
        record_quality=(
            "partial_address"
            if item["address_precision"] == "partial" else "address_record"
        ),
        address_precision=item["address_precision"],
        source_position=int(item["lot_number"]),
        source_event_url=(
            "https://www.venmoreauctions.co.uk/Property-Search?"
            f"auctionID={event_id(item['auction_date'])}"
        ),
        auction_date_precision="day",
        auction_date_basis="exact date printed on first-party property detail page",
        source_platform="Venmore Auctions retained first-party property detail page",
        trading_name=SOURCE,
        source_price_text=item["source_price_text"],
        source_outcome_text=item["source_outcome_text"],
        source_evidence=evidence,
    )
    return row


def event_id(auction_date):
    return {
        "2016-04-13": 23,
        "2016-06-02": 24,
        "2016-07-21": 25,
        "2016-09-12": 26,
        "2016-10-26": 27,
        "2016-12-14": 28,
        "2017-02-17": 29,
        "2017-04-04": 30,
        "2017-05-17": 31,
        "2017-09-13": 33,
        "2017-10-31": 34,
        "2017-12-13": 35,
        "2018-02-14": 36,
        "2018-05-16": 38,
        "2018-07-11": 39,
        "2018-09-12": 40,
        "2018-10-31": 41,
        "2019-02-13": 43,
        "2019-04-04": 44,
        "2019-05-23": 45,
        "2019-07-18": 46,
        "2019-09-03": 47,
        "2019-10-17": 48,
        "2019-12-11": 49,
        "2020-02-12": 50,
        "2020-04-07": 51,
        "2020-04-21": 52,
        "2020-06-08": 58,
        "2020-07-15": 53,
        "2020-09-09": 54,
        "2020-10-27": 55,
        "2020-12-15": 56,
    }[auction_date]


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": RUN_KEY,
        "outcome": "completed" if not summary["failures"] else "partial",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary[
            "run_new_dated_twenty_year_address_records"
        ],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary[
            "run_duplicate_source_evidence_excluded"
        ],
        "national_completeness_verified": False,
    }
    payload["runs"] = [
        run for run in payload.setdefault("runs", [])
        if run.get("source") != RUN_KEY
    ] + [checkpoint]
    payload.setdefault("latest_by_source", {})[RUN_KEY] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "venmore-auctions-2015-indexed-details",
        "auctioneer": SOURCE,
        "source_format": "first-party retained individual property HTML pages",
        "opportunity": (
            "batch newly discovered 2015 and older indexed property pages through "
            "the reusable immutable-HTML runner, or rotate if the index is thin"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    manifest = load_manifest()
    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    summary_path = corpus.DATA / "venmore_indexed_details_collection.json"
    previous_summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists() else None
    )
    manifest_grew = bool(
        previous_summary
        and int(previous_summary.get("indexed_detail_pages_in_batch", 0))
        < int(manifest["expected_pages"])
    )
    if manifest_grew:
        previous_count = int(previous_summary["indexed_detail_pages_in_batch"])
        new_identities = {
            (page["auction_date"], str(page["expected_lot_number"]))
            for page in manifest["pages"][previous_count:]
        }
        baseline_ids = {
            row["appearance_id"]
            for row in existing
            if (row.get("auction_date"), str(row.get("lot_number")))
            not in new_identities
        }
        baseline_years = {
            row["auction_date"][:4]
            for row in existing
            if row.get("auction_date") and row["appearance_id"] in baseline_ids
        }
    elif (
        previous_summary
        and "batch_baseline_appearance_ids" in previous_summary
    ):
        baseline_ids = set(previous_summary["batch_baseline_appearance_ids"])
        baseline_years = set(previous_summary.get(
            "batch_baseline_source_years",
            {
                row["auction_date"][:4]
                for row in existing
                if row.get("auction_date")
                and row["appearance_id"] in baseline_ids
            },
        ))
    else:
        target_dates = {page["auction_date"] for page in manifest["pages"]}
        baseline_ids = {
            row["appearance_id"] for row in existing
            if row.get("auction_date") not in target_dates
        }
        baseline_years = {
            row["auction_date"][:4]
            for row in existing
            if row.get("auction_date")
        }
    pages, failures = [], []
    for position, config in enumerate(manifest["pages"], 1):
        try:
            retained = retained_snapshot(config)
            if retained:
                raw, snapshot_fields = retained
                source_url = config["source_url"]
            else:
                source_url, raw = fetch(config["source_url"])
            sha, retrieved_at = corpus.digest(raw), corpus.now()
            if not retained:
                snapshot_fields = save_snapshot(config, raw, sha)
            evidence = {
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "sha256": sha,
                "basis": "complete first-party exact-dated individual property detail HTML",
                "archive_url": ARCHIVE,
                **snapshot_fields,
            }
            pages.append(materialize(config, source_url, evidence, raw))
            print(
                "VENMORE INDEXED DETAIL", position, "/", len(manifest["pages"]),
                "pages", len(pages), flush=True,
            )
        except Exception as exc:
            failures.append({
                "property_reference": config["property_reference"],
                "auction_date": config["auction_date"],
                "source_url": config["source_url"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

    global_exact = catalogue.global_exact_appearances()
    existing_ids = {row["appearance_id"] for row in existing}
    overlaps, admissible = [], []
    for row in pages:
        if row["appearance_id"] in existing_ids:
            admissible.append(row)
            continue
        matches = global_exact.get(
            (row["auction_date"], catalogue.normalized(row["address"])), []
        )
        if matches:
            overlaps.append({
                "auction_date": row["auction_date"],
                "lot_number": row["lot_number"],
                "address": row["address"],
                "existing": matches,
            })
        else:
            admissible.append(row)

    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in baseline_ids]

    grouped = defaultdict(list)
    for row in pages:
        grouped[row["auction_date"]].append(row)
    states = {}
    for auction_date, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: int(row["lot_number"]))
        state = {
            "auctioneer": SOURCE,
            "trading_name": SOURCE,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "auction_date_precision": "day",
            "source_url": (
                "https://www.venmoreauctions.co.uk/Property-Search?"
                f"auctionID={event_id(auction_date)}"
            ),
            "published_lots": None,
            "lots_captured": len(rows),
            "indexed_detail_pages_captured": len(rows),
            "captured_lot_numbers": [row["lot_number"] for row in rows],
            "guides_captured": sum(row["guide_price"] is not None for row in rows),
            "sale_prices_captured": sum(row["sale_price"] is not None for row in rows),
            "rents_captured": sum(row["annual_rent"] is not None for row in rows),
            "published_outcomes_captured": sum(row["status"] != "unknown" for row in rows),
            "catalogue_complete": False,
            "source_rows_complete": True,
            "denominator_reconciled": False,
            "denominator_basis": (
                "all explicitly enumerated retained first-party detail URLs; "
                "the cleared historical event grid is not a lot denominator"
            ),
            "completion_scope": "every detail URL in the checked indexed-page manifest",
            "auction_date_basis": "exact date printed on every first-party detail page",
            "errors": [],
            "checked_at": corpus.now(),
        }
        states[auction_date] = state
        corpus.save_json(
            corpus.DATA / "auctions" / SLUG / f"{auction_date}.json", state
        )

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [
        row for row in added
        if row.get("address") and cutoff <= row["auction_date"] <= today
    ]
    years_after = {
        row["auction_date"][:4] for row in merged.values() if row.get("auction_date")
    }
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "source_url": ARCHIVE,
        "indexed_detail_pages_in_batch": len(manifest["pages"]),
        "indexed_detail_pages_captured": len(pages),
        "appearances_captured": total,
        "batch_baseline_appearance_ids": sorted(baseline_ids),
        "batch_baseline_source_years": sorted(baseline_years),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_address_strings": sum(
            row.get("address_precision") == "partial" for row in added
        ),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum(
            bool(row.get("auction_date") and row["auction_date"] > today)
            for row in added
        ),
        "run_new_commercial": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use": sum(row.get("sector") == "mixed-use" for row in added),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed-use"} for row in added
        ),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - baseline_years),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "auctions": states,
        "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "coverage_scope": (
            "partial indexed-page recovery only; no event is complete until a "
            "source catalogue or reconciled first-party lot inventory is recovered"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "venmore_indexed_details_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(pages) != int(manifest["expected_pages"]):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    harvest()
