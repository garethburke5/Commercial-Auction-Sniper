#!/usr/bin/env python3
"""Bank Barney Estates' finite first-party property-sitemap inventory.

The sitemap is a bounded inventory of stable individual property pages, not a
catalogue denominator.  Pages without an explicitly printed auction date stay
undated; WordPress publication/modification dates and vacant-possession dates
are never substituted for the auction date.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import argparse
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


SOURCE = "Barney Estates"
SLUG = "barney-estates"
RUN_SOURCE = "barney_estates_first_party_inventory"
SITEMAP = "https://www.barneyestates.co.uk/property-sitemap.xml"
LEGAL_URL = "https://www.barneyestates.co.uk/"
HOST = "www.barneyestates.co.uk"
OPERATOR = "BARNEY ESTATES LIMITED"
COMPANY_NUMBER = "12821397"
HEADERS = {"User-Agent": "AuctionGeekHistoricalCorpus/1.0 (+https://auctiongeek.co.uk)"}
PROPERTY_RE = re.compile(r"^/property/([^/]+)/$", re.I)
POST_ID_RE = re.compile(r"\bpostid-(\d+)\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
DATE_TEXT = (
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(20\d{2})"
)
AUCTION_DATE_RE = re.compile(rf"\bauction\b[^.\n]{{0,100}}?{DATE_TEXT}", re.I)
SOLD_FOR_RE = re.compile(r"\bsold\s+for\s+£\s*([\d,]+)", re.I)
RENT_RE = re.compile(
    r"(?:rent(?:al)?(?:\s+income)?(?:\s+of)?|let[^.]{0,80}?\bat)\s*£\s*([\d,]+)\s*"
    r"(?:per\s+annum|p\.?a\.?)\b",
    re.I,
)
NEXT_TARGET = (
    "Extend Barney Estates through a materially different retained-event or search-index route beyond the "
    "finite current property sitemap, prioritising exact event dates and achieved prices. If no larger "
    "first-party inventory is recoverable, batch another uncovered genuine auctioneer with an accessible "
    "multi-event catalogue archive. National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=90)
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                if len(response.content) < 500:
                    raise ValueError("source response is unexpectedly short")
                return response.url, response.content
            error = RuntimeError(f"HTTP {response.status_code}")
        except (requests.RequestException, ValueError) as exc:
            error = exc
        time.sleep(min(2 ** attempt, 16))
    raise RuntimeError(f"failed after bounded retries: {error}")


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
            rows.append({"slug": match.group(1).casefold(), "source_url": url})
    if not rows:
        raise ValueError("first-party sitemap exposed zero individual property pages")
    if len({row["slug"] for row in rows}) != len(rows):
        raise ValueError("first-party sitemap contains duplicate property slugs")
    return rows


def visible_lines(soup):
    clone = BeautifulSoup(str(soup), "lxml")
    for node in clone.select("script, style, noscript"):
        node.decompose()
    return [clean(line) for line in clone.get_text("\n").splitlines() if clean(line)]


def parse_money(value):
    match = MONEY_RE.search(value or "")
    if not match:
        return None, None
    return int(match.group(1).replace(",", "")), (
        int(match.group(2).replace(",", "")) if match.group(2) else None
    )


def exact_auction_date(lines):
    matches = []
    for line in lines:
        match = AUCTION_DATE_RE.search(line)
        if match:
            day, month, year = match.groups()
            value = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()
            matches.append(value)
    values = sorted(set(matches))
    if len(values) > 1:
        raise ValueError(f"property page prints conflicting auction dates: {values}")
    return values[0] if values else None


def property_meta(soup):
    values = {}
    for li in soup.select(".property_meta li"):
        label = li.find("span")
        if not label:
            continue
        key = clean(label.get_text(" ")).rstrip(":").casefold()
        text = clean(li.get_text(" "))
        prefix = clean(label.get_text(" "))
        values[key] = clean(text[len(prefix):] if text and prefix else text)
    body = soup.body
    classes = set(body.get("class", [])) if body else set()
    if not values.get("availability"):
        status_class = next((item for item in classes if item.startswith("availability-")), None)
        if status_class:
            values["availability"] = status_class.removeprefix("availability-").replace("-", " ").title()
    if not values.get("type"):
        type_class = next((item for item in classes if item.startswith("property_type-")), None)
        if type_class:
            values["type"] = type_class.removeprefix("property_type-").replace("-", " ").title()
    return values


def description_text(soup):
    heading = next(
        (node for node in soup.find_all(["h2", "h3"]) if clean(node.get_text(" ")) == "Description"),
        None,
    )
    if not heading:
        return None
    container = heading.parent.parent
    text = clean(container.get_text(" ")) if container else None
    if not text:
        return None
    text = re.sub(r"^.*?Description\s+Property Summary\s+", "", text, flags=re.I)
    text = re.split(r"\s+Request More Information\b", text, maxsplit=1, flags=re.I)[0]
    return clean(text)


def parse_detail(raw, config, evidence):
    soup = BeautifulSoup(raw, "lxml")
    body_classes = set(soup.body.get("class", [])) if soup.body else set()
    if "sale_by-auction" not in body_classes:
        raise ValueError("first-party property page is not marked as an auction listing")
    heading = soup.find("h1")
    address = clean(heading.get_text(" ")) if heading else None
    if not address:
        raise ValueError("property page lacks its published property heading")
    post_match = next((POST_ID_RE.fullmatch(item) for item in body_classes if POST_ID_RE.fullmatch(item)), None)
    if not post_match:
        raise ValueError("property page lacks its stable WordPress post ID")
    source_lot_id = post_match.group(1)
    lines = visible_lines(soup)
    meta = property_meta(soup)
    price_node = soup.select_one(".price")
    price_text = clean(price_node.get_text(" ")) if price_node else None
    price_low, price_high = parse_money(price_text)
    guide_price = price_low if price_text and "guide" in price_text.casefold() else None
    guide_price_high = price_high if guide_price is not None else None
    available_price = price_low if price_low is not None and guide_price is None else None
    all_text = clean(" ".join(lines)) or ""
    sold_match = SOLD_FOR_RE.search(all_text)
    sale_price = int(sold_match.group(1).replace(",", "")) if sold_match else None
    raw_status = clean(meta.get("availability"))
    status_key = normalized(raw_status)
    if status_key.startswith("sold"):
        status = "sold"
    elif status_key in {"for sale", "available"}:
        status = "available"
    elif status_key == "under offer":
        status = "under_offer"
    elif "withdrawn" in status_key:
        status = "withdrawn"
    else:
        status = "unknown"
    description = description_text(soup)
    rent_match = RENT_RE.search(description or "")
    annual_rent = int(rent_match.group(1).replace(",", "")) if rent_match else None
    postcode = corpus.PC.search(address)
    property_type = clean(meta.get("type"))
    material = " ".join(filter(None, [property_type, address, description]))
    return {
        **config,
        "source_lot_id": source_lot_id,
        "auction_date": exact_auction_date(lines),
        "address": address,
        "postcode": postcode.group().upper() if postcode else None,
        "property_type": property_type,
        "tenure": clean(meta.get("tenure")),
        "status": status,
        "raw_status": raw_status,
        "guide_price": guide_price,
        "guide_price_high": guide_price_high,
        "available_price": available_price,
        "sale_price": sale_price,
        "annual_rent": annual_rent,
        "rent_text": clean(rent_match.group(0)) if rent_match else None,
        "description": description,
        "sector": corpus.sector(material),
        "source_price_text": price_text,
        "source_evidence": evidence,
    }


def materialize(item, sitemap_evidence, legal_evidence):
    auction_id = f"barney-estates:{item['source_lot_id']}"
    row = corpus.base_row(
        SOURCE, auction_id, item.get("auction_date"), None, item["source_lot_id"], item["source_url"]
    )
    row.update(
        address=item["address"],
        postcode=item["postcode"],
        locality=None,
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
        address_precision="exact_published_heading",
        identity_method="first_party_property_page_wordpress_id_and_published_heading",
        source_property_url=item["source_url"],
        source_event_url=SITEMAP,
        auction_date_precision="day" if item.get("auction_date") else None,
        auction_date_basis=(
            "exact auction date printed on first-party property page"
            if item.get("auction_date") else
            "no exact auction date printed; WordPress and possession dates deliberately not substituted"
        ),
        source_platform="Barney Estates first-party property inventory",
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name="Barney Estates and Auctioneers",
        source_guide_text=item["source_price_text"] if item.get("guide_price") is not None else None,
        source_available_price_text=(
            item["source_price_text"] if item.get("available_price") is not None else None
        ),
        source_outcome_text=item["raw_status"],
        source_evidence={
            "sitemap": sitemap_evidence,
            "detail": item["source_evidence"],
            "operator": legal_evidence,
            "basis": "finite first-party property sitemap and stable individual auction property page",
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


def retained_property_snapshots():
    """Index immutable property snapshots by their canonical URL slug."""
    retained = {}
    source_dir = corpus.DATA / "sources" / SLUG
    prior_summary = corpus.DATA / "barney_estates_collection.json"
    retrieved_at = None
    if prior_summary.exists():
        retrieved_at = json.loads(prior_summary.read_text(encoding="utf-8")).get("checked_at")
    for path in sorted(source_dir.glob("property-*.html.gz")):
        raw = gzip.decompress(path.read_bytes())
        soup = BeautifulSoup(raw, "lxml")
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = clean(canonical.get("href")) if canonical else None
        if not canonical_url:
            continue
        slug = urlparse(canonical_url).path.rstrip("/").split("/")[-1].casefold()
        if slug in retained and retained[slug][0] != raw:
            raise ValueError(f"multiple retained snapshots disagree for slug {slug}")
        retained[slug] = (raw, path, retrieved_at)
    return retained


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
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[RUN_SOURCE] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload[RUN_SOURCE] = summary
    payload["prior_target_blocker"] = (
        "Connect UK's legacy realtime subdomain exposed only three search-index detail URLs, no finite sitemap or "
        "catalogue denominator, and direct first-party retrieval returned HTTP 503. Do not retry without a "
        "materially different saved-page, cache or index inventory route."
    )
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "barney-estates-legacy-events",
        "auctioneer": SOURCE,
        "source_format": "retained first-party event or historical property pages",
        "opportunity": "extend the 128-page current sitemap inventory with exact-dated legacy event evidence",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(reuse_snapshots=False):
    resolved_sitemap, sitemap_raw = get(SITEMAP)
    checked_at = corpus.now()
    sitemap_sha, sitemap_path = snapshot("sitemap", "property", sitemap_raw, "xml")
    sitemap_evidence = {
        "source_url": resolved_sitemap,
        "retrieved_at": checked_at,
        "sha256": sitemap_sha,
        "snapshot_path": str(sitemap_path.relative_to(corpus.ROOT)),
        "basis": "complete first-party XML property-sitemap inventory at retrieval time",
    }
    resolved_legal, legal_raw = get(LEGAL_URL)
    legal_sha, legal_path = snapshot("operator", "homepage", legal_raw, "html")
    legal_text = clean(BeautifulSoup(legal_raw, "lxml").get_text(" ")) or ""
    if "Barney Estates Limited" not in legal_text or COMPANY_NUMBER not in legal_text:
        raise ValueError("first-party legal-name/company-number evidence is missing")
    legal_evidence = {
        "source_url": resolved_legal,
        "retrieved_at": corpus.now(),
        "sha256": legal_sha,
        "snapshot_path": str(legal_path.relative_to(corpus.ROOT)),
        "basis": "first-party footer legal and trading-name statement",
    }
    configs = parse_sitemap(sitemap_raw)
    retained = retained_property_snapshots() if reuse_snapshots else {}

    def collect(config):
        cached = retained.get(config["slug"])
        if cached:
            raw, retained_path, retained_at = cached
            resolved = config["source_url"]
        else:
            resolved, raw = get(config["source_url"])
        parsed = urlparse(resolved)
        match = PROPERTY_RE.fullmatch(parsed.path)
        if parsed.netloc.casefold() != HOST or not match or match.group(1).casefold() != config["slug"]:
            raise ValueError("property detail redirect changed the stable page identity")
        soup = BeautifulSoup(raw, "lxml")
        body_classes = set(soup.body.get("class", [])) if soup.body else set()
        post_match = next((POST_ID_RE.fullmatch(item) for item in body_classes if POST_ID_RE.fullmatch(item)), None)
        if not post_match:
            raise ValueError("property page lacks a stable WordPress post ID")
        if cached:
            sha, path = corpus.digest(raw), retained_path
        else:
            sha, path = snapshot("property", post_match.group(1), raw, "html")
        evidence = {
            "source_url": resolved,
            "retrieved_at": retained_at if cached else corpus.now(),
            "sha256": sha,
            "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "basis": (
                "immutable first-pass property snapshot reused after live sitemap reconciliation"
                if cached else "first-party individual auction-property detail page"
            ),
        }
        heading = soup.find("h1")
        if "sale_by-auction" not in body_classes:
            return {
                **config,
                "source_lot_id": post_match.group(1),
                "excluded_reason": "first-party page is not marked as an auction listing",
                "source_evidence": evidence,
            }
        if not heading or not clean(heading.get_text(" ")):
            return {
                **config,
                "source_lot_id": post_match.group(1),
                "excluded_reason": "empty property shell lacks a published property heading",
                "source_evidence": evidence,
            }
        return parse_detail(raw, {**config, "source_url": resolved}, evidence)

    parsed, exclusions, failures = [], [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(config, pool.submit(collect, config)) for config in configs]
        for position, (config, future) in enumerate(futures, 1):
            try:
                result = future.result()
                if result.get("excluded_reason"):
                    exclusions.append(result)
                else:
                    parsed.append(result)
                print("BARNEY ESTATES", position, "/", len(configs), flush=True)
            except Exception as exc:
                failures.append({
                    "slug": config["slug"],
                    "source_url": config["source_url"],
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })
    if failures or len(parsed) + len(exclusions) != len(configs):
        corpus.save_json(corpus.DATA / "barney_estates_collection.json", {
            "checked_at": corpus.now(),
            "sitemap_property_urls": len(configs),
            "detail_pages_captured": len(parsed) + len(exclusions),
            "non_auction_or_empty_pages_excluded": len(exclusions),
            "exclusions": exclusions,
            "failures": failures,
            "run_new_appearances": 0,
            "national_completeness_verified": False,
        })
        raise SystemExit(1)
    if len({item["source_lot_id"] for item in parsed}) != len(parsed):
        raise ValueError("multiple sitemap URLs resolve to the same WordPress property ID")

    candidates = [materialize(item, sitemap_evidence, legal_evidence) for item in parsed]
    global_exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in candidates:
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), []) if row.get("auction_date") else []
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
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{row['source_lot_id']}.json", {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": row["source_auction_id"],
            "auction_date": row.get("auction_date"),
            "auction_date_precision": row.get("auction_date_precision"),
            "source_url": row["original_url"],
            "lots_captured": 1,
            "published_lots_offered": None,
            "catalogue_complete": False,
            "source_rows_complete": True,
            "denominator_reconciled": False,
            "completion_scope": "stable individual property page; no original event/catalogue denominator",
            "source_evidence": row["source_evidence"],
            "errors": [],
            "checked_at": corpus.now(),
        })

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "source_url": SITEMAP,
        "operator": {
            "canonical_name": SOURCE,
            "legal_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "trading_name": "Barney Estates and Auctioneers",
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "sitemap_property_urls": len(configs),
        "detail_pages_captured": len(parsed) + len(exclusions),
        "auction_property_pages": len(parsed),
        "non_auction_or_empty_pages_excluded": len(exclusions),
        "exclusions": exclusions,
        "stable_property_pages_reconciled": len(candidates),
        "catalogue_or_event_completeness_claimed": False,
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= (row.get("auction_date") or "") <= today for row in added
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
        "legacy_connect_uk_blocker": (
            "three indexed pages only; no finite first-party inventory; direct retrieval returned HTTP 503"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "barney_estates_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-snapshots",
        action="store_true",
        help="reuse exact immutable property snapshots after a live sitemap recheck",
    )
    harvest(parser.parse_args().reuse_snapshots)
