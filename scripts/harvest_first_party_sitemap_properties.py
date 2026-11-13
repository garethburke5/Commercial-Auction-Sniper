"""Bank individual property pages exposed by a first-party XML sitemap.

This runner is deliberately source-configured rather than event-configured: one
bounded execution reconciles the complete surviving sitemap inventory, stores
immutable sitemap and detail-page snapshots, and merges only new stable
property identities.  Unknown dates and prices remain null.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


PARSER_VERSION = 1
SOURCES = {
    "connect-uk-auctions": {
        "auctioneer": "Connect UK Auctions",
        "base": "https://connectukauctions.co.uk",
        "sitemap": "https://connectukauctions.co.uk/sitemap.xml",
        "property_prefix": "https://connectukauctions.co.uk/property/",
        "operator_legal_name": "CONNECT UK SALES LTD",
        "operator_company_number": "11808965",
        "historical_trading_names": ["Connect UK Land Auctions"],
    },
}

DATE_RE = re.compile(
    r"(?:Auction:\s*)?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+"
    r"(\d{1,2})\s+([A-Z][a-z]{2})\s+(20\d{2})"
)
LONG_DATE_RE = re.compile(
    r"Auction Date:\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(20\d{2})",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d{1,2})?)\s*(?:per\s+annum|p\.?a\.?)\b", re.I
)


def get(url: str, *, timeout: int = 60) -> tuple[bytes, str]:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "AuctionGeekHistoricalCorpus/1.0 (+evidence capture)"},
    )
    response.raise_for_status()
    return response.content, response.url


def snapshot(raw: bytes, resolved: str, slug: str, name: str, basis: str, **extra) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / slug / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **extra,
    }
    if not path.exists():
        corpus.save_gzip(
            path,
            {"evidence": evidence, "html": raw.decode("utf-8", "replace")},
        )
    return evidence


def sitemap_urls(raw: bytes, prefix: str) -> list[str]:
    soup = BeautifulSoup(raw, "xml")
    urls = [node.get_text(strip=True) for node in soup.find_all("loc")]
    selected = [url for url in urls if url.startswith(prefix)]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("sitemap property inventory is empty or contains duplicate URLs")
    return selected


def structured_place(soup: BeautifulSoup) -> dict:
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or "{}")
        except json.JSONDecodeError:
            continue
        if value.get("@type") in {"Place", "RealEstateListing"}:
            return value
    raise ValueError("property page has no structured property evidence")


def published_date(text: str, description: str | None) -> str | None:
    match = DATE_RE.search(text)
    if match:
        return datetime.strptime(" ".join(match.groups()), "%d %b %Y").date().isoformat()
    match = LONG_DATE_RE.search(description or "")
    if match:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
    return None


def field_between(text: str, start: str, end: str) -> str | None:
    match = re.search(re.escape(start) + r"\s+(.+?)\s+" + re.escape(end), text, re.I)
    return corpus.clean(match.group(1)) if match else None


def postal_address(place: dict) -> tuple[str | None, str | None, str | None]:
    value = place.get("address") or {}
    parts = [
        corpus.clean(value.get("streetAddress")),
        corpus.clean(value.get("addressLocality")),
        corpus.clean(value.get("addressRegion")),
        corpus.clean(value.get("postalCode")),
    ]
    address = ", ".join(part for part in parts if part) or None
    postcode = corpus.clean(value.get("postalCode")).upper() or None
    locality = corpus.clean(value.get("addressLocality")) or None
    return address, postcode, locality


def parse_property(raw: bytes, resolved: str, source: dict, evidence: dict) -> dict:
    soup = BeautifulSoup(raw, "html.parser")
    place = structured_place(soup)
    text = " ".join(soup.stripped_strings)
    source_id = urlsplit(resolved).path.rstrip("/").split("/")[-1]
    if not source_id or place.get("url") != resolved:
        raise ValueError("structured property identity does not match resolved URL")
    auction_date = published_date(text, place.get("description"))
    address, postcode, locality = postal_address(place)
    if not address:
        raise ValueError("structured property page has no postal address")
    guide_text_match = re.search(r"Guide price\s+(£\s*[\d,]+(?:\.\d{1,2})?\+?)", text, re.I)
    offer = place.get("offers") or {}
    guide = corpus.money(offer.get("price"))
    if guide is None and guide_text_match:
        guide = corpus.money(MONEY_RE.search(guide_text_match.group(1)).group(1))
    availability = str(offer.get("availability") or "").rsplit("/", 1)[-1].casefold()
    if "This lot has been sold" in text or availability == "soldout":
        status = "sold"
    elif re.search(r"\bWithdrawn\b", text, re.I):
        status = "withdrawn"
    elif re.search(r"\bUnsold\b", text, re.I):
        status = "unsold"
    elif re.search(r"\bAvailable\b|\bFor sale\b", text, re.I):
        status = "available"
    else:
        status = "unknown"
    property_type = field_between(text, "Property type", "Sale method")
    tenure = field_between(text, "Tenure", "Property type")
    sale_method = field_between(text, "Sale method", "Property details")
    description = corpus.clean(place.get("description")) or None
    rent_match = RENT_RE.search(description or "")
    row = corpus.base_row(
        source["auctioneer"],
        f"{source['slug']}:{auction_date or 'undated'}",
        auction_date,
        None,
        source_id,
        resolved,
    )
    row.update(
        appearance_id=f"{source['auctioneer']}|first-party-property:{source_id}",
        address=address,
        postcode=postcode,
        locality=locality,
        sector=corpus.sector(" ".join(filter(None, [property_type, description]))),
        property_type=property_type,
        tenure=tenure,
        guide_price=guide,
        status=status,
        description=description,
        annual_rent=corpus.money(rent_match.group(1)) if rent_match else None,
        rent_text=rent_match.group(0) if rent_match else None,
        image_urls=[place["image"]] if place.get("image") else [],
        property_id=source_id,
        identity_method="first_party_stable_property_id",
        record_quality="address_record",
        guide_price_text=guide_text_match.group(1) if guide_text_match else None,
        source_result_text=status,
        auction_date_basis=(
            "published individual property auction date" if auction_date else
            "not published on surviving individual property page"
        ),
        sale_method=sale_method,
        operator_legal_name=source.get("operator_legal_name"),
        operator_company_number=source.get("operator_company_number"),
        source_evidence=evidence,
    )
    return row


def exact_key(row: dict) -> tuple[str, str] | None:
    auction_date = row.get("auction_date")
    address = re.sub(r"[^a-z0-9]+", " ", row.get("address") or "", flags=re.I).strip().casefold()
    return (auction_date, address) if auction_date and address else None


def global_exact_counts(exclude_slug: str) -> Counter:
    counts = Counter()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            key = exact_key(row)
            if key:
                counts[key] += 1
    return counts


def harvest(slug: str, workers: int = 8) -> dict:
    if slug not in SOURCES:
        raise ValueError(f"unknown sitemap source: {slug}")
    source = {"slug": slug, **SOURCES[slug]}
    sitemap_raw, sitemap_resolved = get(source["sitemap"])
    sitemap_evidence = snapshot(
        sitemap_raw,
        sitemap_resolved,
        slug,
        "sitemap",
        "first-party XML sitemap property inventory",
    )
    urls = sitemap_urls(sitemap_raw, source["property_prefix"])
    fetched = {}
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get, url): url for url in urls}
        for future, url in [(future, url) for future, url in futures.items()]:
            try:
                fetched[url] = future.result()
            except Exception as exc:
                failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    if failures or len(fetched) != len(urls):
        raise RuntimeError(f"{slug} detail inventory incomplete: {len(fetched)}/{len(urls)}")

    rows = []
    for position, url in enumerate(urls, start=1):
        raw, resolved = fetched[url]
        evidence = snapshot(
            raw,
            resolved,
            slug,
            f"property-{urlsplit(url).path.rstrip('/').split('/')[-1]}",
            "first-party individual property detail page",
            sitemap_evidence=sitemap_evidence,
        )
        row = parse_property(raw, resolved, source, evidence)
        row["source_position"] = position
        rows.append(row)

    ids = [row["source_lot_id"] for row in rows]
    if len(ids) != len(set(ids)) or len(rows) != len(urls):
        raise RuntimeError("detail identities do not reconcile to the sitemap inventory")
    source_keys = Counter(filter(None, (exact_key(row) for row in rows)))
    global_keys = global_exact_counts(slug)
    overlaps, admissible = [], []
    for row in rows:
        key = exact_key(row)
        if key and source_keys[key] == 1 and global_keys[key] >= 1:
            overlaps.append({
                "auction_date": row["auction_date"],
                "address": row["address"],
                "source_lot_id": row["source_lot_id"],
                "original_url": row["original_url"],
                "existing_match_count": global_keys[key],
            })
        else:
            admissible.append(row)

    appearance_path = corpus.DATA / "appearances" / slug / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{slug}/canonical", list(merged.values()), preserve_existing=False)
    run_new = [row for key, row in merged.items() if key not in {old["appearance_id"] for old in existing}]

    by_date = defaultdict(list)
    for row in admissible:
        by_date[row.get("auction_date")].append(row)
    for auction_date, date_rows in by_date.items():
        corpus.save_json(
            corpus.DATA / "auctions" / slug / f"{auction_date or 'undated'}.json",
            {
                "auctioneer": source["auctioneer"],
                "source_auction_id": f"{slug}:{auction_date or 'undated'}",
                "auction_date": auction_date,
                "source_url": sitemap_resolved,
                "catalogue_complete": False,
                "source_rows_complete": True,
                "lots_captured": len(date_rows),
                "completion_scope": (
                    "all surviving individual property URLs in the reconciled first-party "
                    "sitemap, grouped by published date; not proof of an original event catalogue"
                ),
                "source_evidence": sitemap_evidence,
                "errors": [],
                "checked_at": corpus.now(),
            },
        )

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": source["auctioneer"],
        "parser_version": PARSER_VERSION,
        "source_url": sitemap_resolved,
        "sitemap_sha256": sitemap_evidence["sha256"],
        "sitemap_property_urls": len(urls),
        "distinct_source_identities": len(set(ids)),
        "detail_pages_captured": len(rows),
        "sitemap_inventory_reconciled": True,
        "appearances_captured": len(merged),
        "run_new_appearances": len(run_new),
        "run_new_address_records": sum(bool(row.get("address")) for row in run_new),
        "run_new_partial_lots": sum(not row.get("address") for row in run_new),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= (row.get("auction_date") or "") <= today
            for row in run_new
        ),
        "run_new_commercial_mixed": sum(
            row.get("sector") in {"commercial", "mixed-use"} for row in run_new
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in run_new),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in run_new),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in run_new),
        "run_new_undated": sum(not row.get("auction_date") for row in run_new),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in run_new),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "exact_overlap_reconciliation": overlaps,
        "new_source_years": sorted({
            int(row["auction_date"][:4]) for row in run_new if row.get("auction_date")
        }),
        "date_range": [
            min((row["auction_date"] for row in merged.values() if row.get("auction_date")), default=None),
            max((row["auction_date"] for row in merged.values() if row.get("auction_date")), default=None),
        ],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "operator_legal_name": source.get("operator_legal_name"),
        "operator_company_number": source.get("operator_company_number"),
        "historical_trading_names_not_counted_as_auctioneers": source.get("historical_trading_names", []),
        "completion_scope": (
            "every surviving first-party sitemap property page; undated modern-method "
            "listings remain null-dated and original historical completeness is not claimed"
        ),
        "failures": [],
    }
    corpus.save_json(corpus.DATA / f"{slug.replace('-', '_')}_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", choices=list(SOURCES), nargs="+", default=["connect-uk-auctions"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    results = [harvest(slug, args.workers) for slug in args.sources]
    print(json.dumps({
        "sources": args.sources,
        "run_new_appearances": sum(row["run_new_appearances"] for row in results),
        "run_new_dated_twenty_year_address_records": sum(
            row["run_new_dated_twenty_year_address_records"] for row in results
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
