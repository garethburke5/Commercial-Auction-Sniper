"""Bank a complete public Sanity property corpus for a UK auctioneer.

The initial target is Auction Agent.  Its first-party Next.js site reads a
public Sanity dataset containing stable property documents for both the sold
and current pages.  This collector reconciles the document count, preserves an
immutable copy of the structured response, and banks one appearance per stable
Sanity document.  Project, dataset, site and operator names are arguments so
the same schema can be reused without adding a workflow step per auction event.

Only ``soldAt`` and an explicit auction date in the published description are
admitted as dates.  A sold label without either remains undated.  Sanity does
not publish achieved prices in this corpus, so sale_price deliberately remains
null even for sold records.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        1,
    )
}
PUBLISHED_DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(20\d{2})\b",
    re.I,
)
POUND_AMOUNT_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)", re.I)


def fetch_json(url: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - exercised by live retries
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def published_auction_date(description: str | None) -> str | None:
    """Return only an auction-context date explicitly printed in narrative."""
    text = corpus.clean(description)
    if not text or not re.search(r"\b(?:auction|bidding)\b", text, re.I):
        return None
    match = PUBLISHED_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), MONTHS[month.lower()], int(day)).date().isoformat()
    except ValueError:
        return None


def guide_range(value: str | None) -> tuple[int | float | None, int | float | None]:
    amounts = [corpus.money(match) for match in POUND_AMOUNT_RE.findall(value or "")]
    amounts = [int(item) if isinstance(item, float) and item.is_integer() else item for item in amounts if item]
    if not amounts:
        return None, None
    return amounts[0], amounts[1] if len(amounts) > 1 else None


def property_slug(item: dict) -> str:
    value = item.get("slug")
    if isinstance(value, dict):
        value = value.get("current")
    return corpus.clean(value)


def row_from_property(
    item: dict,
    auctioneer: str,
    slug: str,
    site_host: str,
    evidence: dict,
) -> dict:
    source_id = corpus.clean(item.get("_id"))
    page_slug = property_slug(item)
    if not source_id or not page_slug:
        raise ValueError("Sanity property has no stable document id or page slug")

    sold_date = iso_date(item.get("soldAt"))
    narrative_date = published_auction_date(item.get("description"))
    auction_date = sold_date or narrative_date
    date_basis = (
        "exact soldAt date in public Sanity property document"
        if sold_date
        else (
            "explicit auction date in public Sanity property description"
            if narrative_date
            else "no individual date published in public Sanity property document"
        )
    )
    original_url = f"https://{site_host}/property/{page_slug}"
    row = corpus.base_row(
        auctioneer,
        f"{slug}:sanity-public-corpus",
        auction_date,
        None,
        source_id,
        original_url,
    )

    title = corpus.clean(item.get("title")) or None
    location = corpus.clean(item.get("location")) or None
    full_address = corpus.clean(item.get("fullAddress")) or None
    address = full_address or ", ".join(part for part in (title, location) if part) or None
    postcode_search = " ".join(
        corpus.clean(item.get(field)) for field in ("fullAddress", "postcode", "location", "title")
    )
    postcode_match = corpus.PC.search(postcode_search)
    postcode = re.sub(r"\s+", " ", postcode_match.group().upper()) if postcode_match else None
    guide_low, guide_high = guide_range(item.get("guidePrice"))
    description = corpus.clean(item.get("description")) or None
    features = corpus.clean(item.get("features")) or None
    property_type = corpus.clean(item.get("type")) or None
    status_text = corpus.clean(item.get("propertyStatus")) or None
    status = status_text.lower() if status_text else "unknown"
    images = [url for url in item.get("imageUrls", []) if isinstance(url, str) and url]

    row.update(
        appearance_id=f"{auctioneer}|sanity:{source_id}",
        address=address,
        postcode=postcode,
        locality=location,
        property_type=property_type,
        tenure=corpus.clean(item.get("tenure")) or None,
        guide_price=guide_low,
        guide_price_high=guide_high,
        sale_price=None,
        status=status,
        description=description,
        sector=corpus.sector(" ".join(value for value in (title, property_type, description, features) if value)),
        epc=corpus.clean(item.get("epc")) or None,
        image_urls=list(dict.fromkeys(images)),
        identity_method="sanity_stable_document_id",
        record_quality="address_record" if address else "partial_lot",
        source_evidence=evidence,
        auction_date_basis=date_basis,
        source_status=status_text,
        sold_at=item.get("soldAt"),
        published_guide_text=corpus.clean(item.get("guidePrice")) or None,
    )
    return row


def sanity_query_url(project_id: str, dataset: str, api_version: str) -> tuple[str, str]:
    query = (
        '{"total":count(*[_type=="property"]),'
        '"properties":*[_type=="property"] | order(_id asc){'
        '_id,_createdAt,_updatedAt,title,location,postcode,fullAddress,guidePrice,'
        'propertyStatus,soldAt,description,type,tenure,epc,features,slug,useFixedPrice,'
        'showOnSoldPage,"imageUrls":images[].asset->url}}'
    )
    endpoint = f"https://{project_id}.api.sanity.io/{api_version}/data/query/{dataset}"
    return f"{endpoint}?{urlencode({'query': query})}", query


def harvest(
    project_id: str,
    dataset: str,
    auctioneer: str,
    slug: str,
    site_host: str,
    api_version: str = "v2023-05-03",
) -> dict:
    capture_url, query = sanity_query_url(project_id, dataset, api_version)
    response = fetch_json(capture_url)
    result = response.get("result") or {}
    properties = result.get("properties") or []
    total = int(result.get("total") or 0)
    ids = [corpus.clean(item.get("_id")) for item in properties]
    if total < 1:
        raise SystemExit("Sanity source exposed no property documents")
    if len(properties) != total:
        raise SystemExit(f"Sanity query returned {len(properties)} properties; expected {total}")
    if len(set(ids)) != total or any(not item for item in ids):
        raise SystemExit("Sanity source contains missing or duplicate stable document ids")

    retrieved_at = corpus.now()
    snapshot_value = {
        "source_url": f"https://{site_host}/sold-properties",
        "capture_url": capture_url,
        "query": query,
        "retrieved_at": retrieved_at,
        "project_id": project_id,
        "dataset": dataset,
        "total": total,
        "properties": properties,
    }
    snapshot_bytes = json.dumps(
        snapshot_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    snapshot_sha = corpus.digest(snapshot_bytes)
    snapshot_path = corpus.DATA / "sources" / slug / "sanity" / f"public-corpus-{snapshot_sha[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot_value)
    evidence = {
        "source_url": f"https://{site_host}/sold-properties",
        "capture_url": capture_url,
        "snapshot_path": str(snapshot_path.relative_to(corpus.ROOT)),
        "retrieved_at": retrieved_at,
        "sha256": snapshot_sha,
        "basis": "complete reconciled public Sanity property-document query",
    }
    rows = [row_from_property(item, auctioneer, slug, site_host, evidence) for item in properties]
    appearance_path = corpus.DATA / "appearances" / slug / "sanity-public-corpus.jsonl.gz"
    existing_ids = (
        {row["appearance_id"] for row in corpus.iter_rows(appearance_path)}
        if appearance_path.exists()
        else set()
    )
    new_rows = [row for row in rows if row["appearance_id"] not in existing_ids]
    retained = corpus.write_rows(f"{slug}/sanity-public-corpus", rows)
    if retained != total:
        raise SystemExit(f"retained {retained} rows; reconciled source exposes {total}")

    today = datetime.now(timezone.utc).date().isoformat()
    historical = [row for row in rows if row.get("auction_date") and row["auction_date"] <= today]
    future = [row for row in rows if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in rows if not row.get("auction_date")]
    state = {
        "auctioneer": auctioneer,
        "source_auction_id": f"{slug}:sanity-public-corpus",
        "source_url": f"https://{site_host}/sold-properties",
        "visible_source_rows": total,
        "lots_captured": len(rows),
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "legacy_archive_complete": False,
        "national_coverage_complete": False,
        "errors": [],
        "checked_at": corpus.now(),
        "completion_scope": (
            "all property documents in the surviving public Sanity dataset; not a claim that "
            "removed documents, an earlier platform, or the operator's full historical archive are covered"
        ),
    }
    corpus.save_json(corpus.DATA / "auctions" / slug / "sanity-public-corpus.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": auctioneer,
        "source_url": state["source_url"],
        "archive_appearances_captured": retained,
        "run_new_appearances": len(new_rows),
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "dated_historical_records": len(historical),
        "future_dated_records": len(future),
        "undated_records": len(undated),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": sum(row.get("sale_price") is not None for row in rows),
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_status": dict(Counter(row["status"] for row in rows)),
        "historical_source_years": sorted({row["auction_date"][:4] for row in historical}),
        "future_source_years": sorted({row["auction_date"][:4] for row in future}),
        "denominator_reconciled": True,
        "complete": True,
        "completion_scope": state["completion_scope"],
    }
    corpus.save_json(corpus.DATA / f"{slug.replace('-', '_')}_sanity_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default="bqldbdiz")
    parser.add_argument("--dataset", default="production")
    parser.add_argument("--api-version", default="v2023-05-03")
    parser.add_argument("--auctioneer", default="Auction Agent")
    parser.add_argument("--slug", default="auction-agent")
    parser.add_argument("--site-host", default="www.auctionagent.co.uk")
    args = parser.parse_args()
    harvest(
        args.project_id,
        args.dataset,
        args.auctioneer,
        args.slug,
        args.site_host,
        args.api_version,
    )
