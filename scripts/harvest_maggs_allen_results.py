"""Bank Maggs & Allen's retained first-party auction-results selection.

The result index exposes all retained rows in one ``n=0`` response, stable
property IDs, full addresses, guides and sold prices.  Detail pages provide an
exact auction date where the narrative survives.  The index is a recent-results
selection and publishes no original offered-lot denominator, so reconstructed
auction groups always remain explicitly incomplete.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.maggsandallen.co.uk"
RESULTS_URL = BASE + "/search-auction-sold/?bid=2&orderby=lot_no&n=0&showsold=on&showstc=on"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DETAIL_RE = re.compile(r"/property-details/(\d+)(?:/|$)", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+Auction\b",
    re.I,
)
EXACT_DATE_PATTERNS = (
    re.compile(
        r"(?:online\s+|public\s+)?auction(?:\s+to\s+be\s+held)?\s+on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?[,]?\s*"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        re.I,
    ),
    re.compile(
        r"(?:online\s+|public\s+)?auction[^.]{0,100}?\b(?:on|dated)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?[,]?\s*"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        re.I,
    ),
)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def parse_month(value: str | None) -> str | None:
    match = MONTH_RE.search(value or "")
    return f"{match.group(1).title()} {match.group(2)}" if match else None


def parse_exact_date(value: str | None) -> str | None:
    text = clean(value) or ""
    for pattern in EXACT_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", match.group(1), flags=re.I)
            return datetime.strptime(raw, "%d %B %Y").date().isoformat()
    return None


def reconcile_exact_date(detail_date: str | None, published_month: str | None) -> tuple[str | None, str | None]:
    if detail_date and published_month:
        detail_month = datetime.fromisoformat(detail_date).strftime("%B %Y")
        if detail_month != published_month:
            return None, f"detail narrative date {detail_date} conflicts with retained index month {published_month}"
    return detail_date, None


def parse_index(html: str, evidence: dict) -> list[dict]:
    cards = BeautifulSoup(html, "lxml").select(".card")
    rows = []
    for position, card in enumerate(cards, 1):
        link = card.select_one('a[href*="/property-details/"]')
        title = card.select_one(".card-title h2:first-child")
        result = card.select_one(".card-title h2.black")
        match = DETAIL_RE.search(link.get("href") or "") if link else None
        if not all((link, title, result, match)):
            continue
        address = clean(title.get_text(" ", strip=True))
        postcode_match = corpus.PC.search(address or "")
        if not address or not postcode_match:
            raise ValueError(f"result card {position} lacks a postcode-bearing address")
        bullets = [clean(node.get_text(" ", strip=True)) for node in card.select("li")]
        bullets = [value for value in bullets if value]
        guide_text = next((value for value in bullets if "guide price" in value.casefold()), None)
        published_month = next((parse_month(value) for value in bullets if parse_month(value)), None)
        property_id = match.group(1)
        detail_url = urljoin(BASE, link.get("href") or "")
        image = card.select_one(".auction-property-image")
        image_match = re.search(r"url\(([^)]+)\)", image.get("style") or "", re.I) if image else None
        image_url = urljoin(BASE, image_match.group(1).strip(" '\"")) if image_match else None
        description_parts = [value for value in bullets if value != guide_text and not parse_month(value)]
        rows.append(
            {
                "source_property_id": property_id,
                "address": address,
                "postcode": postcode_match.group().upper(),
                "guide_price": pounds(guide_text),
                "sale_price": pounds(result.get_text(" ", strip=True)),
                "source_result_text": clean(result.get_text(" ", strip=True)),
                "published_auction_month": published_month,
                "description": clean("; ".join(description_parts)),
                "original_url": detail_url,
                "image_urls": [image_url] if image_url else [],
                "source_position": position,
                "index_evidence": evidence,
            }
        )
    identities = [row["source_property_id"] for row in rows]
    if not rows or len(identities) != len(set(identities)):
        raise ValueError("retained result index is empty or contains duplicate property IDs")
    return rows


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    json_description = None
    property_type = None
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("description"):
            json_description = clean(BeautifulSoup(str(value["description"]), "html.parser").get_text(" ", strip=True))
            property_type = clean(str(value.get("@type") or ""))
            break
    text = json_description or clean(soup.get_text(" ", strip=True))
    return {
        "auction_date": parse_exact_date(text),
        "detail_description": text,
        "source_schema_type": property_type,
    }


def get(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"unexpectedly short response from {url}")
    return response.content, response.url


def saved_detail(property_id: str) -> tuple[bytes, str, dict] | None:
    state_path = corpus.DATA / "sources/maggs_allen/detail_states" / f"{property_id}.json"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text())
    snapshot_name = (state.get("source_evidence") or {}).get("snapshot_path")
    snapshot = corpus.ROOT / snapshot_name if snapshot_name else None
    if not snapshot or not snapshot.exists():
        return None
    saved = corpus.read_gzip(snapshot)
    return saved["html"].encode("utf-8"), state["source_url"], saved["evidence"]


def harvest(refresh: bool = False, workers: int = 10) -> None:
    index_raw, index_resolved = get(RESULTS_URL)
    index_sha = corpus.digest(index_raw)
    index_snapshot = corpus.DATA / "sources/maggs_allen" / f"retained-results-{index_sha[:16]}.json.gz"
    index_evidence = {
        "source_url": index_resolved,
        "retrieved_at": corpus.now(),
        "sha256": index_sha,
        "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained auction-results property grid",
        "pagination_request": "n=0",
    }
    corpus.save_gzip(index_snapshot, {"evidence": index_evidence, "html": index_raw.decode("utf-8", "replace")})
    index_rows = parse_index(index_raw.decode("utf-8", "replace"), index_evidence)
    index_evidence["visible_source_rows"] = len(index_rows)

    fetched = {}
    failures = []
    to_fetch = []
    for row in index_rows:
        saved = None if refresh else saved_detail(row["source_property_id"])
        if saved:
            fetched[row["source_property_id"]] = saved
        else:
            to_fetch.append(row)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(get, row["original_url"]): row for row in to_fetch}
        for future in as_completed(jobs):
            row = jobs[future]
            try:
                raw, resolved = future.result()
                fetched[row["source_property_id"]] = (raw, resolved, None)
            except Exception as exc:
                failures.append({"source_property_id": row["source_property_id"], "error": f"{type(exc).__name__}: {exc}"[:400]})

    observed = []
    for source in index_rows:
        property_id = source["source_property_id"]
        item = fetched.get(property_id)
        detail = {"auction_date": None, "detail_description": None, "source_schema_type": None}
        detail_evidence = None
        if item:
            raw, resolved, saved_evidence = item
            html = raw.decode("utf-8", "replace")
            if saved_evidence:
                detail_evidence = saved_evidence
            else:
                sha = corpus.digest(raw)
                snapshot = corpus.DATA / "sources/maggs_allen" / f"detail-{property_id}-{sha[:16]}.json.gz"
                detail_evidence = {
                    "source_url": resolved,
                    "retrieved_at": corpus.now(),
                    "sha256": sha,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "basis": "first-party auction property detail page",
                    "source_property_id": property_id,
                }
                corpus.save_gzip(snapshot, {"evidence": detail_evidence, "html": html})
            detail = parse_detail(html)
            corpus.save_json(
                corpus.DATA / "sources/maggs_allen/detail_states" / f"{property_id}.json",
                {
                    "source_property_id": property_id,
                    "source_url": source["original_url"],
                    "auction_date": detail["auction_date"],
                    "source_evidence": detail_evidence,
                    "errors": [],
                    "checked_at": corpus.now(),
                },
            )

        detail_auction_date = detail["auction_date"]
        auction_date, date_conflict = reconcile_exact_date(detail_auction_date, source["published_auction_month"])
        month_key = (source["published_auction_month"] or "unknown-month").lower().replace(" ", "-")
        source_auction_id = f"maggs-allen:{auction_date or month_key}"
        row = corpus.base_row(
            "Maggs & Allen",
            source_auction_id,
            auction_date,
            None,
            property_id,
            source["original_url"],
        )
        description = detail["detail_description"] or source["description"]
        row.update(
            appearance_id=f"Maggs & Allen|source-property:{property_id}",
            address=source["address"],
            postcode=source["postcode"],
            locality=None,
            sector=corpus.sector(" ".join(filter(None, [source["address"], source["description"]]))),
            property_type=detail["source_schema_type"],
            guide_price=source["guide_price"],
            sale_price=source["sale_price"],
            status="sold",
            description=description,
            image_urls=source["image_urls"],
            property_id=None,
            identity_method="first_party_stable_property_id",
            record_quality="address_record",
            source_position=source["source_position"],
            published_auction_month=source["published_auction_month"],
            source_detail_auction_date=detail_auction_date,
            source_date_conflict=date_conflict,
            source_result_text=source["source_result_text"],
            auction_date_basis=(
                "exact detail-page auction narrative"
                if auction_date
                else "exact date unavailable or conflicts with retained index month; published month retained separately"
            ),
            source_evidence={"index": index_evidence, "detail": detail_evidence},
        )
        observed.append(row)

    appearance_path = corpus.DATA / "appearances/maggs_allen/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in observed})
    total = corpus.write_rows("maggs_allen/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    groups = defaultdict(list)
    for row in observed:
        groups[row["source_auction_id"]].append(row)
    for auction_id, rows in groups.items():
        suffix = auction_id.split(":", 1)[1]
        errors = []
        if not all(row.get("auction_date") for row in rows):
            errors.append("exact auction date unavailable for one or more retained rows")
        state = {
            "auctioneer": "Maggs & Allen",
            "source_auction_id": auction_id,
            "auction_date": rows[0].get("auction_date") if all(row.get("auction_date") == rows[0].get("auction_date") for row in rows) else None,
            "catalogue_complete": False,
            "source_rows_complete": True,
            "published_lots_offered": None,
            "visible_source_rows": len(rows),
            "lots_captured": len(rows),
            "pagination_reconciled": True,
            "denominator_reconciled": False,
            "completion_scope": "all rows retained for this date or month in the first-party recent-results selection; not the original catalogue",
            "source_url": index_resolved,
            "source_evidence": [index_evidence] + [row["source_evidence"]["detail"] for row in rows if row["source_evidence"].get("detail")],
            "reconciliation_errors": ["original offered-lot denominator is not published"] + errors,
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions/maggs_allen" / f"{suffix}.json", state)

    exact_dates = [row["auction_date"] for row in merged.values() if row.get("auction_date")]
    summary = {
        "checked_at": corpus.now(),
        "source_url": index_resolved,
        "visible_source_rows": len(index_rows),
        "distinct_source_property_ids": len({row["source_property_id"] for row in index_rows}),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "details_captured": sum(bool(row["source_evidence"].get("detail")) for row in observed),
        "exact_dates_captured": sum(bool(row.get("auction_date")) for row in observed),
        "catalogue_groups": len(groups),
        "catalogues_complete": 0,
        "catalogues_incomplete": len(groups),
        "date_range": [min(exact_dates), max(exact_dates)] if exact_dates else [None, None],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "maggs_allen_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refetch saved detail pages")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    harvest(refresh=args.refresh, workers=args.workers)
