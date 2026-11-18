"""Bank Stags' paginated all-sector Homeflow auction-property inventory.

The public ``tag-auction`` search exposes a reconciled page count and stable
Homeflow property ids.  Detail pages retain the individual particulars,
features, branch attribution and original URL.  This runner captures every
page in one operation; it does not create one workflow or deployment per lot.

An item marked ``Sold`` by Homeflow is not treated as achieved-price evidence:
Stags' page publishes only that status and the guide.  Dates without a year are
accepted only where the page also publishes a weekday and that weekday uniquely
matches the collection year.  Otherwise the date remains null.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Stags"
SLUG = "stags"
BASE = "https://www.stags.co.uk"
CATALOGUE = BASE + "/properties/sales/tag-auction"
MONTHS = {
    name.lower(): number for number, name in enumerate(
        "January February March April May June July August September October November December".split(), 1
    )
}
MONTH_RE = "|".join(MONTHS)
WEEKDAYS = {name.lower(): number for number, name in enumerate(
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
)}


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


def config_json(text: str, key: str) -> dict:
    match = re.search(r"Ctesius\.addConfig\(['\"]" + re.escape(key) + r"['\"],\s*", text)
    if not match:
        raise ValueError(f"page has no {key} Homeflow payload")
    return json.JSONDecoder().raw_decode(text[match.end():])[0]


def properties_payload(raw: bytes) -> dict:
    return config_json(raw.decode("utf-8", "replace"), "properties")


def clean_text(node) -> str | None:
    if node is None:
        return None
    return corpus.clean(node.get_text(" ", strip=True)) or None


def detail_material(raw: bytes, source_id: str) -> dict:
    text = raw.decode("utf-8", "replace")
    soup = BeautifulSoup(text, "lxml")
    properties = properties_payload(raw).get("properties") or []
    if len(properties) != 1 or str(properties[0].get("property_id")) != source_id:
        raise ValueError(f"detail identity mismatch for {source_id}")
    show = config_json(text, "properties_show_data")
    if str(show.get("propertyId")) != source_id:
        raise ValueError(f"branch/detail identity mismatch for {source_id}")
    features_node = soup.select_one(".property-features__list")
    description_node = soup.select_one(".propertyMainDescriptionText")
    features = [corpus.clean(node.get_text(" ", strip=True)) for node in features_node.select("li")] if features_node else []
    description = clean_text(description_node)
    return {
        "property": properties[0],
        "features": features,
        "description": description,
        "description_html": str(description_node) if description_node else None,
        "branch": show.get("branch"),
    }


def _candidate(day_value: str, month_value: str, year_value: str | None, weekday: str | None,
               collection_year: int) -> tuple[str, str] | None:
    year = int(year_value) if year_value else collection_year
    if year < 100:
        year += 2000
    try:
        value = date(year, MONTHS[month_value.lower()], int(day_value))
    except (KeyError, ValueError):
        return None
    if weekday and value.weekday() != WEEKDAYS[weekday.lower()]:
        return None
    basis = "published auction date"
    if not year_value:
        if not weekday:
            return None
        basis = "published auction weekday/day/month; year fixed by sole matching collection-year weekday"
    return value.isoformat(), basis


def auction_date(text: str, collection_year: int) -> tuple[str | None, str]:
    """Return a conservative exact auction date and its evidence basis."""
    text = corpus.clean(text)
    contexts = [text[:700]]
    for match in re.finditer(
        r"(?i)(?:auction\s+(?:end\s+date|ending|ends?|finish(?:ing)?|concluding)|"
        r"end\s+bidding\s+time|concluding)\b.{0,180}", text
    ):
        contexts.append(match.group(0))
    candidates: dict[str, str] = {}
    for context in contexts:
        for match in re.finditer(r"(?i)\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", context):
            try:
                year = int(match.group(3)); year += 2000 if year < 100 else 0
                value = date(year, int(match.group(2)), int(match.group(1))).isoformat()
                candidates[value] = "published numeric auction date"
            except ValueError:
                pass
        pattern = (
            rf"(?i)\b(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
            rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_RE})"
            rf"(?:\s+|,\s*)(20\d{{2}})?\b"
        )
        for match in re.finditer(pattern, context):
            found = _candidate(match.group(2), match.group(3), match.group(4), match.group(1), collection_year)
            if found:
                candidates[found[0]] = found[1]
        reverse = rf"(?i)\b({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+)(20\d{{2}})\b"
        for match in re.finditer(reverse, context):
            found = _candidate(match.group(2), match.group(1), match.group(3), None, collection_year)
            if found:
                candidates[found[0]] = found[1]
    if not candidates:
        return None, "no exact auction date published or safely recoverable"
    if len(candidates) != 1:
        raise ValueError("conflicting auction dates: " + ", ".join(sorted(candidates)))
    value = next(iter(candidates))
    return value, candidates[value]


def money_value(value: str | None) -> int | float | None:
    if not value:
        return None
    match = re.search(r"£\s*([\d,.]+)\s*([km])?", value, re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    if match.group(2):
        amount *= 1_000 if match.group(2).lower() == "k" else 1_000_000
    return int(amount) if amount.is_integer() else amount


def guide_range(price: str | None, text: str) -> tuple[int | float | None, int | float | None]:
    opening = text[:1200]
    match = re.search(
        r"(?i)(?:auction\s+)?guide(?:\s+price)?\s*[:\-]?\s*(£\s*[\d,.]+\s*[km]?)"
        r"\s*(?:to|[-–])\s*(£\s*[\d,.]+\s*[km]?)", opening
    )
    if match:
        return money_value(match.group(1)), money_value(match.group(2))
    return money_value(price), None


def annual_rent(text: str) -> tuple[int | float | None, str | None]:
    match = re.search(r"(?i)(£\s*[\d,]+(?:\.\d+)?\s*(?:per\s+annum|p\.?a\.?))", text)
    return (money_value(match.group(1)), match.group(1)) if match else (None, None)


def property_sector(tags: list[str], text: str) -> str:
    """Classify the asset without Homeflow's cross-agent taxonomy pollution."""
    primary = set(tags[:5])
    residential = bool(primary & {
        "house", "attached house", "detached house", "flat", "apartment", "bungalow", "residential"
    })
    land = bool(primary & {"farm and land", "land", "development land", "woodland"})
    opening = text[:2200]
    commercial = bool(re.search(
        r"(?i)\b(?:commercial premises|shop investment|retail unit|office building|industrial unit|"
        r"warehouse|business premises|public house|restaurant|hotel)\b", opening
    ))
    if land and residential:
        return "mixed-use"
    if residential:
        return "residential"
    if land:
        return "land"
    if commercial:
        return "commercial"
    return corpus.sector(opening)


def row_from_material(summary: dict, material: dict, evidence: dict, collection_year: int) -> dict:
    source_id = str(summary.get("property_id") or "")
    if not source_id or str(material["property"].get("property_id")) != source_id:
        raise ValueError("property has no stable or matching Homeflow id")
    url = urljoin(BASE, summary["property_url"])
    combined = corpus.clean(" ".join(
        [summary.get("short_description") or ""] + material.get("features", []) + [material.get("description") or ""]
    ))
    exact, date_basis = auction_date(combined, collection_year)
    row = corpus.base_row(SOURCE, f"stags-homeflow:{source_id}", exact, None, source_id, url)
    address = corpus.clean(summary.get("display_address")) or None
    postcode_match = corpus.PC.search(address or "")
    low, high = guide_range(summary.get("price"), combined)
    rent, rent_text = annual_rent(combined)
    source_status = corpus.clean(summary.get("status")) or None
    status = {
        "sold": "sold",
        "sale agreed": "sale agreed",
        "for sale": "available",
    }.get((source_status or "").lower(), "unknown")
    if re.search(r"\bsold\s+prior\s+to\s+auction\b", combined[:1000], re.I):
        status = "sold prior"
    tags = [corpus.clean(value) for value in summary.get("tags") or []]
    branch = material.get("branch") or {}
    row.update(
        appearance_id=f"{SOURCE}|homeflow:{source_id}",
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=corpus.clean(summary.get("town")) or None,
        sector=property_sector(tags, combined),
        property_type=next((tag.title() for tag in tags if tag in {
            "commercial", "farm and land", "land", "house", "flat", "apartment", "bungalow", "development land"
        }), None),
        tenure=corpus.clean(summary.get("tenure")) or None,
        guide_price=low,
        guide_price_high=high,
        sale_price=None,
        status=status,
        description=material.get("description") or corpus.clean(summary.get("short_description")) or None,
        annual_rent=rent,
        rent_text=rent_text,
        site_area=(f"{summary['acreage']} acres" if str(summary.get("acreage") or "0") not in {"", "0", "0.0"} else None),
        image_urls=[urljoin(BASE, value) for value in summary.get("photos") or []],
        identity_method="homeflow_stable_property_id",
        record_quality="address_record" if address else "partial_lot",
        source_evidence=evidence,
        auction_date_basis=date_basis,
        source_status=source_status,
        source_branch=corpus.clean(branch.get("branchName")) or None,
        source_branch_id=branch.get("branchId"),
        source_tags=tags,
        operator_canonical_name=SOURCE,
        branches_and_trading_names_counted_separately=False,
    )
    return row


def harvest(workers: int = 8, collection_year: int | None = None) -> dict:
    collection_year = collection_year or datetime.now(timezone.utc).year
    first_raw = fetch(CATALOGUE)
    first = properties_payload(first_raw)
    pagination = first["pagination"]
    total = int(pagination["total_count"])
    page_count = int(pagination["page_count"])
    pages: dict[int, dict] = {1: first}

    def collect_page(number: int) -> tuple[int, dict]:
        url = CATALOGUE + f"/page-{number}"
        return number, properties_payload(fetch(url))

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as executor:
        jobs = [executor.submit(collect_page, number) for number in range(2, page_count + 1)]
        for future in as_completed(jobs):
            number, payload = future.result()
            if int(payload["pagination"]["current_page"]) != number:
                raise SystemExit(f"Stags page {number} returned a different page")
            if int(payload["pagination"]["total_count"]) != total:
                raise SystemExit("Stags denominator changed during collection")
            pages[number] = payload
            print(f"STAGS INDEX {number}/{page_count}", flush=True)

    summaries = [item for number in sorted(pages) for item in pages[number]["properties"]]
    by_id = {str(item.get("property_id")): item for item in summaries}
    if len(summaries) != total or len(by_id) != total:
        raise SystemExit(f"Stags pagination returned {len(summaries)} rows/{len(by_id)} ids; expected {total}")

    materials: dict[str, dict] = {}

    def collect_detail(item: dict) -> tuple[str, dict]:
        source_id = str(item["property_id"])
        return source_id, detail_material(fetch(urljoin(BASE, item["property_url"])), source_id)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as executor:
        jobs = [executor.submit(collect_detail, item) for item in by_id.values()]
        for position, future in enumerate(as_completed(jobs), 1):
            source_id, material = future.result()
            materials[source_id] = material
            if position % 10 == 0 or position == total:
                print(f"STAGS DETAIL {position}/{total}", flush=True)

    snapshot = {
        "source_url": CATALOGUE,
        "retrieved_at": corpus.now(),
        "total_count": total,
        "page_count": page_count,
        "index_pages": [pages[number] for number in sorted(pages)],
        "property_details": {source_id: materials[source_id] for source_id in sorted(materials)},
    }
    snapshot_bytes = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    snapshot_sha = corpus.digest(snapshot_bytes)
    snapshot_path = corpus.DATA / "sources" / SLUG / "homeflow" / f"auction-tag-{snapshot_sha[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot)
    evidence = {
        "source_url": CATALOGUE,
        "snapshot_path": str(snapshot_path.relative_to(corpus.ROOT)),
        "retrieved_at": snapshot["retrieved_at"],
        "sha256": snapshot_sha,
        "basis": "complete paginated Stags Homeflow auction tag plus stable property detail particulars",
    }
    rows = [row_from_material(by_id[source_id], materials[source_id], evidence, collection_year)
            for source_id in sorted(by_id)]
    appearance_path = corpus.DATA / "appearances" / SLUG / "homeflow-auction-tag.jsonl.gz"
    existing_ids = {row["appearance_id"] for row in corpus.iter_rows(appearance_path)} if appearance_path.exists() else set()
    new_rows = [row for row in rows if row["appearance_id"] not in existing_ids]
    retained = corpus.write_rows(f"{SLUG}/homeflow-auction-tag", rows)
    if retained != total:
        raise SystemExit(f"retained {retained} rows; reconciled source exposes {total}")

    today = datetime.now(timezone.utc).date().isoformat()
    past = [row for row in rows if row.get("auction_date") and row["auction_date"] <= today]
    future = [row for row in rows if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in rows if not row.get("auction_date")]
    state = {
        "auctioneer": SOURCE,
        "source_auction_id": "stags:homeflow-auction-tag",
        "source_url": CATALOGUE,
        "source_rows_complete": True,
        "catalogue_complete": True,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "visible_source_rows": total,
        "lots_captured": len(rows),
        "detail_pages_captured": len(materials),
        "page_count": page_count,
        "errors": [],
        "checked_at": corpus.now(),
        "completion_scope": "all listings in the surviving public Stags Homeflow auction tag; not a claim that deleted listings, the separate commercial website filter, or earlier platforms are covered",
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "homeflow-auction-tag.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "operator": {
            "canonical_name": SOURCE,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
            "source_branches": sorted({row["source_branch"] for row in rows if row.get("source_branch")}),
        },
        "source_url": CATALOGUE,
        "archive_appearances_captured": retained,
        "run_new_appearances": len(new_rows),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "dated_historical_records": len(past),
        "future_dated_records": len(future),
        "undated_records": len(undated),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": 0,
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_year": dict(Counter(row["auction_date"][:4] if row.get("auction_date") else "undated" for row in rows)),
        "source_years": sorted({row["auction_date"][:4] for row in past}),
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "complete": True,
        "completion_scope": state["completion_scope"],
    }
    corpus.save_json(corpus.DATA / "stags_homeflow_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--collection-year", type=int)
    args = parser.parse_args()
    harvest(args.workers, args.collection_year)
