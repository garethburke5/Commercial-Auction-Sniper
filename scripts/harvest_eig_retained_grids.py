"""Bank complete retained EIG white-label past-auction grids.

Boultons Harrisons and Online Property Auction Group publish flat, paginated
past-auction grids rather than event catalogues.  Every card carries a stable
EIG lot UUID and an individual outcome date; the detail page adds the guide
price and richer property text.  This collector reconciles every pagination
page and card before claiming the retained grid complete.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCES = {
    "boultons-harrisons": {
        "auctioneer": "Boultons Harrisons Ltd",
        "base": "https://www.boultonsauctions.co.uk",
    },
    "online-property-auction-group": {
        "auctioneer": "Online Property Auction Group",
        "base": "https://www.opagroup.co.uk",
    },
}
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
UUID_RE = re.compile(r"/lot/details/([0-9a-f-]{36})", re.I)
ISO_DATE_RE = re.compile(r"^(20\d{2}-\d{2}-\d{2})")
MONEY_RE = re.compile(r"£?\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)
GUIDE_RE = re.compile(r"Guide Price of\s*£?\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*(per\s+annum|annually|p\.?\s*a\.?)\b", re.I
)
PARSER_VERSION = 2


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def amount(match: re.Match | None) -> int | None:
    if not match:
        return None
    parsed = corpus.money(match.group(1) + (match.group(2) or ""))
    return int(parsed) if parsed else None


def exact_date(value: str | None) -> str | None:
    match = ISO_DATE_RE.match(value or "")
    return match.group(1) if match else None


def get(url: str) -> tuple[bytes, str]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 1000:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").casefold()
    if "sold prior" in text:
        status = "sold_prior"
    elif "sold post" in text or "sold after" in text:
        status = "sold_after"
    elif re.search(r"\bsold\b", text):
        status = "sold"
    elif "withdrawn" in text:
        status = "withdrawn"
    elif "postponed" in text:
        status = "postponed"
    elif "no bids" in text or "unsold" in text:
        status = "unsold"
    elif "available" in text:
        status = "available"
    else:
        status = "unknown"
    price_match = re.search(r"(?:for|price)\s+£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", value or "", re.I)
    price = amount(price_match) if status in {"sold", "sold_prior", "sold_after"} else None
    return status, price


def classify_sector(address: str | None, text: str | None) -> str:
    """Prefer the described asset over speculative alternative-use wording."""
    address_text = (clean(address) or "").casefold()
    detail_text = (clean(text) or "").casefold()
    combined = f"{address_text} {detail_text}"
    if re.search(r"\b(land|plot|woodland|grazing|roadway)\b", address_text):
        return "land"
    if re.search(
        r"\b(mixed[ -]?use|commercial (?:and|with) residential|residential (?:and|with) commercial|"
        r"shop (?:and|with) (?:a )?flat|retail (?:and|with) (?:a )?flat)\b",
        combined,
    ):
        return "mixed-use"
    if re.search(
        r"\b(commercial unit|shop|retail|office|public house|pub|inn|church|chapel|theatre|"
        r"hospital|telephone exchange|ground rents?|warehouse|industrial)\b",
        address_text,
    ):
        return "commercial"
    if re.search(
        r"\b(flat|apartment|house|cottage|bungalow|terrace|bedroom|dwelling|maisonette)\b",
        combined,
    ):
        return "residential"
    return corpus.sector(" ".join(filter(None, [address, text])))


def page_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for link in soup.select('a[href*="page="]'):
        for value in parse_qs(urlsplit(link.get("href") or "").query).get("page", []):
            if value.isdigit():
                pages.add(int(value))
    return max(pages)


def parse_grid(html: str, source: dict, evidence: dict) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    rows, malformed = [], []
    for position, card in enumerate(soup.select(".lot-panel"), 1):
        detail = card.select_one('a[href*="/lot/details/"]')
        identity = UUID_RE.search(detail.get("href") or "") if detail else None
        address_node = card.select_one(".list-address")
        time_node = card.select_one("time[datetime]")
        scheduled_end = card.get("data-end-date-utc")
        auction_date = exact_date(scheduled_end) or exact_date(time_node.get("datetime") if time_node else None)
        address = clean(address_node.get_text(" ", strip=True)) if address_node else None
        if not all((identity, address, auction_date)):
            malformed.append({"position": position, "address": address, "detail_url": detail.get("href") if detail else None})
            continue
        source_lot_id = identity.group(1).lower()
        original_url = urljoin(source["base"], detail.get("href") or "")
        result_node = card.select_one(".list-guideprice")
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        status, sale_price = status_and_price(result_text)
        tagline_node = card.select_one(".lot-data-heading strong")
        summary_node = card.select_one(".list-info p")
        tagline = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
        summary = clean(summary_node.get_text(" ", strip=True)) if summary_node else None
        description = clean(" ".join(dict.fromkeys(filter(None, [tagline, summary]))))
        image = card.select_one("img.list-image[src]")
        postcode = corpus.PC.search(address)
        auction_id = f"{source['slug']}:{auction_date}"
        row = corpus.base_row(
            source["auctioneer"], auction_id, auction_date, None, source_lot_id, original_url
        )
        row.update(
            appearance_id=f"{source['auctioneer']}|eig-lot:{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sale_price=sale_price,
            status=status,
            description=description,
            sector=classify_sector(address, description),
            image_urls=[image.get("src")] if image and image.get("src") else [],
            property_id=source_lot_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            source_platform_lot_id=card.get("data-lot-id"),
            scheduled_auction_end=scheduled_end,
            published_outcome_time=time_node.get("datetime") if time_node else None,
            auction_date_basis=(
                "published scheduled auction end date" if scheduled_end
                else "published individual lot outcome/end date"
            ),
            source_evidence=evidence,
        )
        bid_match = re.search(r"\b(\d+)\s+bids?\b", result_text or "", re.I)
        if bid_match:
            row["bid_count"] = int(bid_match.group(1))
        rows.append(row)
    return rows, malformed


def description_after_heading(soup: BeautifulSoup) -> str | None:
    heading = soup.find(["h2", "h3"], string=lambda value: value and clean(value) == "Description")
    if not heading:
        return None
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag):
            if sibling.name in {"h2", "h3"}:
                break
            text = clean(sibling.get_text(" ", strip=True))
            if text:
                return text
    return None


def enrich_detail(html: str, row: dict, evidence: dict) -> dict:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.select_one("h1.h3")
    detail_address = clean(heading.get_text(" ", strip=True)) if heading else None
    if detail_address and detail_address.casefold() != clean(row["address"]).casefold():
        card_postcode = corpus.PC.search(row["address"] or "")
        detail_postcode = corpus.PC.search(detail_address)
        if not (card_postcode and detail_postcode and card_postcode.group().casefold() == detail_postcode.group().casefold()):
            raise ValueError("detail address does not reconcile to retained result card")
    meta = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
    meta_text = meta.get("content") if meta else None
    description = description_after_heading(soup)
    tagline_node = soup.select_one(".lot-details-tagline")
    tagline = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
    combined = clean(" ".join(dict.fromkeys(filter(None, [tagline, description, row.get("description")]))))
    guide_match = GUIDE_RE.search(meta_text or "")
    rent_match = RENT_RE.search(combined or "")
    images = []
    for node in soup.select('.carousel-inner img[data-src], .carousel-inner img[src], meta[property="og:image"]'):
        candidate = node.get("data-src") or node.get("src") or node.get("content")
        if candidate and not candidate.startswith("data:") and candidate not in images:
            images.append(candidate)
    row.update(
        guide_price=amount(guide_match),
        guide_price_text=clean(guide_match.group(0)) if guide_match else None,
        description=combined,
        sector=classify_sector(row.get("address"), combined),
        annual_rent=int(corpus.money(rent_match.group(1))) if rent_match else None,
        rent_text=clean(rent_match.group(0)) if rent_match else None,
        image_urls=images or row.get("image_urls") or [],
        detail_source_evidence=evidence,
    )
    return row


def snapshot(raw: bytes, resolved: str, source: dict, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / source["slug"] / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def existing_global_ids(exclude_slug: str) -> set[str]:
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            value = clean(str(row.get("source_lot_id") or row.get("property_id") or ""))
            if value and UUID_RE.fullmatch("/lot/details/" + value):
                values.add(value.casefold())
    return values


def harvest(slug: str, workers: int = 10) -> dict:
    if slug not in SOURCES:
        raise ValueError(f"unknown retained grid: {slug}")
    source = {"slug": slug, **SOURCES[slug]}
    archive_url = source["base"] + "/past-auctions?lotResultType=All"
    first_raw, first_resolved = get(archive_url)
    first_html = first_raw.decode("utf-8", "replace")
    pages = page_count(first_html)
    fetched = {1: (first_raw, first_resolved)}
    with ThreadPoolExecutor(max_workers=min(workers, pages)) as pool:
        futures = {
            pool.submit(get, archive_url + f"&page={page}"): page
            for page in range(2, pages + 1)
        }
        for future in as_completed(futures):
            fetched[futures[future]] = future.result()

    archive_evidence, page_rows, malformed = [], [], []
    for page in range(1, pages + 1):
        raw, resolved = fetched[page]
        evidence = snapshot(
            raw, resolved, source, f"past-auctions-page-{page}",
            "first-party retained EIG white-label past-auction grid", page=page, page_count=pages,
        )
        archive_evidence.append(evidence)
        rows, bad = parse_grid(raw.decode("utf-8", "replace"), source, evidence)
        page_rows.append(rows)
        malformed.extend({"page": page, **value} for value in bad)

    rows = [row for page in page_rows for row in page]
    ids = [row["source_lot_id"] for row in rows]
    pagination_complete = bool(
        pages >= 1 and all(page_rows) and not malformed and len(ids) == len(set(ids))
        and all(len(page_rows[page - 1]) == 50 for page in range(1, pages))
        and len(page_rows[-1]) <= 50
    )
    if not pagination_complete:
        raise RuntimeError(
            f"{slug} retained pagination did not reconcile: pages={list(map(len, page_rows))}, "
            f"malformed={len(malformed)}, distinct={len(set(ids))}/{len(ids)}"
        )

    summary_path = corpus.DATA / f"{slug.replace('-', '_')}_collection.json"
    prior = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    archive_sha = corpus.digest("".join(value["sha256"] for value in archive_evidence).encode())
    if (prior.get("archive_sha256") == archive_sha
            and prior.get("archive_pagination_complete") is True
            and prior.get("parser_version") == PARSER_VERSION
            and not prior.get("detail_recovery_failures")):
        checked = datetime.fromisoformat(prior["checked_at"])
        if 0 <= (datetime.now(timezone.utc) - checked).total_seconds() < 86400:
            print(json.dumps({"source": slug, "skipped": "complete unchanged grid checked within 24 hours"}))
            return prior

    detail_results, detail_failures = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get, row["original_url"]): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                raw, resolved = future.result()
                evidence = snapshot(
                    raw, resolved, source, f"lot-{row['source_lot_id']}",
                    "first-party retained EIG property detail page",
                    source_lot_id=row["source_lot_id"],
                )
                detail_results[row["appearance_id"]] = enrich_detail(
                    raw.decode("utf-8", "replace"), row, evidence
                )
            except Exception as exc:
                detail_failures.append({
                    "source_lot_id": row["source_lot_id"], "url": row["original_url"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
                detail_results[row["appearance_id"]] = row
    rows = [detail_results[row["appearance_id"]] for row in rows]

    global_ids = existing_global_ids(slug)
    overlaps = [row for row in rows if row["source_lot_id"] in global_ids]
    admissible = [row for row in rows if row["source_lot_id"] not in global_ids]
    appearance_path = corpus.DATA / "appearances" / slug / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{slug}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]

    by_date = defaultdict(list)
    for row in admissible:
        by_date[row["auction_date"]].append(row)
    for auction_date, date_rows in by_date.items():
        corpus.save_json(corpus.DATA / "auctions" / slug / f"{auction_date}.json", {
            "auctioneer": source["auctioneer"],
            "source_auction_id": f"{slug}:{auction_date}",
            "auction_date": auction_date,
            "source_url": first_resolved,
            "catalogue_complete": True,
            "source_rows_complete": True,
            "pagination_reconciled": True,
            "lots_captured": len(date_rows),
            "completion_scope": "all rows for this date in the reconciled retained flat archive; not evidence of deleted rows or a separate event catalogue",
            "source_evidence": archive_evidence,
            "errors": [],
            "checked_at": corpus.now(),
        })

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    historical = [row for row in added if row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    years_before = {int(row["auction_date"][:4]) for row in existing if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": source["auctioneer"],
        "parser_version": PARSER_VERSION,
        "source_url": first_resolved,
        "archive_sha256": archive_sha,
        "archive_page_count": pages,
        "archive_page_rows": [len(value) for value in page_rows],
        "visible_source_rows": len(rows),
        "distinct_source_identities": len(set(ids)),
        "archive_pagination_complete": True,
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in added),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "new_source_years": sorted(years_after - years_before),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "detail_pages_captured": len(rows) - len(detail_failures),
        "detail_recovery_failures": detail_failures,
        "completion_scope": "every card in every page of the surviving first-party past-auction grid; deleted earlier lots are not claimed",
        "failures": [],
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["all", *SOURCES], nargs="?", default="all")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    targets = list(SOURCES) if args.source == "all" else [args.source]
    results = [harvest(slug, args.workers) for slug in targets]
    print(json.dumps({"sources": targets, "run_new_appearances": sum(value.get("run_new_appearances", 0) for value in results)}, indent=2))


if __name__ == "__main__":
    main()
