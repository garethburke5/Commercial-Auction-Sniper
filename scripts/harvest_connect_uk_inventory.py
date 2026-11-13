"""Bank Connect UK Auctions' finite first-party property sitemap inventory.

The current first-party sitemap enumerates stable property-detail URLs.  Each
detail page is itself the property evidence: it publishes an address, sector,
status and guide, while traditional-auction pages also print an exact date.
Modern-method pages without a date remain explicitly undated; scheduled future
lots remain future-dated and are never counted as historical-window growth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import gzip
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Connect UK Auctions"
SLUG = "connect-uk-auctions"
RUN_SOURCE = "connect_uk_first_party_inventory"
SITEMAP = "https://connectukauctions.co.uk/sitemap.xml"
HOST = "connectukauctions.co.uk"
OPERATOR = "CONNECT UK SALES LTD"
COMPANY_NUMBER = "11808965"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_RE = re.compile(r"^/property/([a-z0-9]+)$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
DATE_RE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})$")
RENT_RE = re.compile(
    r"(?:rent(?:al)?(?:\s+income)?(?:\s+of)?|let[^.]{0,80}?\bat)\s*£\s*([\d,]+)\s*"
    r"(?:per\s+annum|p\.?a\.?)\b",
    re.I,
)
NEXT_TARGET = (
    "Inventory Connect UK Auctions' surviving legacy realtime.connectukauctions.co.uk "
    "property pages through a sitemap, search-index or saved-page route, deduplicating "
    "exact date/address overlaps with this current-site inventory. If no finite legacy "
    "inventory is recoverable, batch another uncovered genuine auctioneer with an "
    "accessible multi-event catalogue archive. National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    for attempt in range(5):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def snapshot(kind, source_id, raw, suffix):
    digest = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{kind}-{source_id}-{digest[:20]}.{suffix}.gz"
    compressed = gzip.compress(raw, mtime=0)
    if path.exists():
        if path.read_bytes() != compressed:
            raise ValueError(f"immutable snapshot changed at {path}")
    else:
        corpus.atomic(path, compressed)
    return digest, path


def parse_sitemap(raw):
    soup = BeautifulSoup(raw, "xml")
    rows = []
    for loc in soup.select("url > loc"):
        url = clean(loc.get_text())
        parsed = urlparse(url or "")
        match = PROPERTY_RE.fullmatch(parsed.path)
        if parsed.netloc.casefold() == HOST and match:
            rows.append({"source_lot_id": match.group(1).lower(), "source_url": url})
    if not rows:
        raise ValueError("first-party sitemap exposed zero property pages")
    if len({row["source_lot_id"] for row in rows}) != len(rows):
        raise ValueError("first-party sitemap contains duplicate property IDs")
    return rows


def visible_lines(raw):
    soup = BeautifulSoup(raw, "lxml")
    for node in soup.select("script, style, noscript"):
        node.decompose()
    return [clean(line) for line in soup.get_text("\n").splitlines() if clean(line)]


def parse_money(value):
    match = MONEY_RE.search(value or "")
    if not match:
        return None, None
    return int(match.group(1).replace(",", "")), (
        int(match.group(2).replace(",", "")) if match.group(2) else None
    )


def parse_date(value):
    match = DATE_RE.fullmatch(value or "")
    if not match:
        return None
    day, month, year = match.groups()
    # The site uses both the standard ``Sep`` and the publisher spelling
    # ``Sept``.  Normalize only that explicit variant before strict parsing.
    if month.casefold() == "sept":
        month = "Sep"
    return datetime.strptime(f"{day} {month} {year}", "%d %b %Y").date().isoformat()


def value_after(lines, label, start=0):
    for index in range(start, len(lines) - 1):
        if lines[index].casefold() == label.casefold():
            return lines[index + 1]
    return None


def parse_detail(raw, config, evidence):
    lines = visible_lines(raw)
    try:
        start = lines.index("Back to listings")
    except ValueError as exc:
        raise ValueError("property page lacks its first-party detail header") from exc
    head = lines[start + 1 : start + 20]
    if len(head) < 8:
        raise ValueError("property page header is incomplete")
    lead_status, sale_method = head[0], head[1]
    cursor = 2
    auction_date = None
    if head[cursor] == "Auction:":
        auction_date = parse_date(head[cursor + 1])
        if not auction_date:
            raise ValueError("property page prints an invalid auction date")
        cursor += 2
    property_type, title, locality = head[cursor : cursor + 3]
    if head[cursor + 3] != "Guide price":
        raise ValueError("property page header lacks its guide-price label")
    guide_text = head[cursor + 4]
    guide_price, guide_high = parse_money(guide_text)
    if guide_price is None:
        raise ValueError("property page prints an unparseable guide price")
    address = clean(f"{title}, {locality}")
    postcode = corpus.PC.search(address or "")
    tenure = value_after(lines, "Tenure", start)
    detail_property_type = value_after(lines, "Property type", start)
    source_starting_bid_text = value_after(lines, "Starting bid", start)
    starting_bid, _ = parse_money(source_starting_bid_text)
    sold_for_text = value_after(lines, "Sold for", start)
    sale_price, _ = parse_money(sold_for_text)
    status_area = " | ".join(lines[start + 1 : start + 35])
    if re.search(r"\bsold\b", status_area, re.I):
        status = "sold"
    elif re.search(r"\bwithdrawn\b", status_area, re.I):
        status = "withdrawn"
    elif re.search(r"\bavailable\b|\bfor sale\b", status_area, re.I):
        status = "available"
    else:
        status = "unknown"
    detail_start = next(
        (index for index in range(start, len(lines)) if lines[index] == "Property details"),
        start,
    )
    detail_end = next(
        (index for index in range(detail_start + 1, len(lines)) if lines[index] == "Legal Pack"),
        min(len(lines), detail_start + 80),
    )
    description = clean(" ".join(lines[detail_start + 1 : detail_end]))
    annual_rent = None
    rent_text = None
    rent_match = RENT_RE.search(description or "")
    if rent_match:
        annual_rent = int(rent_match.group(1).replace(",", ""))
        rent_text = clean(rent_match.group(0))
    material = " ".join(filter(None, [property_type, detail_property_type, title, description]))
    return {
        **config,
        "auction_date": auction_date,
        "address": address,
        "postcode": postcode.group().upper() if postcode else None,
        "locality": locality,
        "property_type": detail_property_type or property_type,
        "tenure": tenure,
        "sale_method": sale_method,
        "status": status,
        "guide_price": guide_price,
        "guide_price_high": guide_high,
        "available_price": starting_bid,
        "sale_price": sale_price,
        "annual_rent": annual_rent,
        "rent_text": rent_text,
        "description": description,
        "sector": corpus.sector(material),
        "source_guide_text": guide_text,
        "source_starting_bid_text": source_starting_bid_text,
        "source_outcome_text": lead_status,
        "source_evidence": evidence,
    }


def materialize(item, sitemap_evidence):
    source_id = item["source_lot_id"]
    auction_id = f"connect-uk:{source_id}"
    row = corpus.base_row(
        SOURCE, auction_id, item.get("auction_date"), None, source_id, item["source_url"]
    )
    row.update(
        address=item["address"],
        postcode=item["postcode"],
        locality=item["locality"],
        sector=item["sector"],
        property_type=item["property_type"],
        tenure=item["tenure"],
        status=item["status"],
        guide_price=item["guide_price"],
        guide_price_high=item["guide_price_high"],
        available_price=item["available_price"],
        sale_price=item["sale_price"],
        annual_rent=item["annual_rent"],
        rent_text=item["rent_text"],
        description=item["description"],
        record_quality="address_record",
        address_precision="exact_published",
        identity_method="first_party_property_page_stable_id_and_published_address",
        source_property_url=item["source_url"],
        source_event_url=SITEMAP,
        auction_date_precision="day" if item.get("auction_date") else None,
        auction_date_basis=(
            "exact date printed on first-party property page"
            if item.get("auction_date") else
            "no exact individual date published on first-party property page"
        ),
        source_platform="Connect UK Auctions first-party property inventory",
        sale_method=item["sale_method"],
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        source_guide_text=item["source_guide_text"],
        source_starting_bid_text=item["source_starting_bid_text"],
        source_outcome_text=item["source_outcome_text"],
        source_evidence={
            "sitemap": sitemap_evidence,
            "detail": item["source_evidence"],
            "basis": "stable first-party property URL and linked property detail page",
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
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[RUN_SOURCE] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["connect_uk_first_party_inventory"] = summary
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "connect-uk-legacy-realtime-inventory",
        "auctioneer": SOURCE,
        "source_format": "legacy first-party individual property pages",
        "opportunity": "recover the older realtime subdomain's indexed property inventory",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    resolved_sitemap, sitemap_raw = get(SITEMAP)
    checked_at = corpus.now()
    sitemap_sha, sitemap_path = snapshot("sitemap", "property", sitemap_raw, "xml")
    sitemap_evidence = {
        "source_url": resolved_sitemap,
        "retrieved_at": checked_at,
        "sha256": sitemap_sha,
        "snapshot_path": str(sitemap_path.relative_to(corpus.ROOT)),
        "basis": "complete first-party XML sitemap property-URL inventory",
    }
    configs = parse_sitemap(sitemap_raw)

    def collect(config):
        resolved, raw = get(config["source_url"])
        parsed = urlparse(resolved)
        match = PROPERTY_RE.fullmatch(parsed.path)
        if parsed.netloc.casefold() != HOST or not match or match.group(1).lower() != config["source_lot_id"]:
            raise ValueError("property detail redirect changed the stable page identity")
        sha, path = snapshot("property", config["source_lot_id"], raw, "html")
        evidence = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "basis": "first-party individual property detail page",
        }
        return parse_detail(raw, {**config, "source_url": resolved}, evidence)

    parsed, failures = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(config, pool.submit(collect, config)) for config in configs]
        for position, (config, future) in enumerate(futures, 1):
            try:
                parsed.append(future.result())
                print("CONNECT UK", position, "/", len(configs), flush=True)
            except Exception as exc:
                failures.append({
                    "source_lot_id": config["source_lot_id"],
                    "source_url": config["source_url"],
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })
    if failures or len(parsed) != len(configs):
        corpus.save_json(corpus.DATA / "connect_uk_collection.json", {
            "checked_at": corpus.now(),
            "sitemap_property_urls": len(configs),
            "detail_pages_captured": len(parsed),
            "failures": failures,
            "run_new_appearances": 0,
            "national_completeness_verified": False,
        })
        raise SystemExit(1)

    candidates = [materialize(item, sitemap_evidence) for item in parsed]
    global_exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in candidates:
        matches = global_exact.get(
            (row["auction_date"], normalized(row["address"])), []
        ) if row.get("auction_date") else []
        if matches:
            overlaps.append({
                "source_lot_id": row["source_lot_id"],
                "auction_date": row["auction_date"],
                "address": row["address"],
                "existing": matches,
            })
        else:
            admissible.append(row)

    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    for row in candidates:
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": row["source_auction_id"],
            "auction_date": row.get("auction_date"),
            "auction_date_precision": row.get("auction_date_precision"),
            "source_url": row["original_url"],
            "lots_captured": 1,
            "published_lots_offered": 1,
            "catalogue_complete": True,
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": "one stable first-party single-property page",
            "source_evidence": row["source_evidence"],
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(
            corpus.DATA / "auctions" / SLUG / f"{row['source_lot_id']}.json", state
        )

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    years_before = {
        row["auction_date"][:4] for row in existing if row.get("auction_date")
    }
    years_after = {
        row["auction_date"][:4] for row in merged.values() if row.get("auction_date")
    }
    summary = {
        "checked_at": corpus.now(),
        "source_url": SITEMAP,
        "operator": {
            "canonical_name": SOURCE,
            "legal_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "sitemap_property_urls": len(configs),
        "detail_pages_captured": len(parsed),
        "complete_single_property_pages": len(candidates),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= (row.get("auction_date") or "") <= today
            for row in added
        ),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_appearances": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_appearances": sum(
            bool(row.get("auction_date")) and row["auction_date"] > today for row in added
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added
        ),
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
    corpus.save_json(corpus.DATA / "connect_uk_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
