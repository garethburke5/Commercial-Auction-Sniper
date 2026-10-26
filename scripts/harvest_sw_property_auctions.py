"""Bank SW Property Auctions' complete retained first-party result archive."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://swpropertyauctions.co.uk"
ARCHIVE_URL = BASE + "/past-auction-results"
AUCTIONEER = "SW Property Auctions"
SLUG = "sw-property-auctions"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b")
DISPLAY_RE = re.compile(r"Displaying\s+1\s*-\s*\d+\s+of\s+([\d,]+)\s+Properties", re.I)
LOT_RE = re.compile(r"^Lot\s+(.+?)\s+-\s+(.+)$", re.I)
DETAIL_RE = re.compile(r"/lot/details/([0-9a-f-]{36})", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*(per\s+annum|p\.?\s*a\.?)\b", re.I
)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def exact_date(value: str | None) -> str | None:
    match = DATE_RE.search(value or "")
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def amount(match: re.Match | None) -> int | None:
    if not match:
        return None
    value = corpus.money(match.group(1) + (match.group(2) or ""))
    return int(value) if value else None


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


def discover(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    catalogues = {}
    for link in soup.select('a[href^="/past-auctions/"]'):
        source_id = urlsplit(link.get("href") or "").path.rstrip("/").rsplit("/", 1)[-1]
        row = link.find_parent("tr")
        cells = row.find_all("td") if row else []
        date = exact_date(cells[0].get_text(" ", strip=True)) if cells else None
        if not source_id.isdigit() or len(cells) < 5 or not date:
            raise ValueError("archive contains a result row without stable ID or exact date")
        offered = clean(cells[1].get_text(" ", strip=True))
        sold = clean(cells[2].get_text(" ", strip=True))
        if not (offered or "").isdigit() or not (sold or "").isdigit():
            raise ValueError(f"archive entry {source_id} lacks published outcome statistics")
        item = {
            "source_id": source_id,
            "catalogue_date": date,
            "published_lots_offered": int(offered),
            "published_lots_sold": int(sold),
            "published_percent_sold": clean(cells[3].get_text(" ", strip=True)),
            "published_total_raised": amount(MONEY_RE.search(cells[4].get_text(" ", strip=True))),
            "source_url": urljoin(BASE, link.get("href") or ""),
        }
        prior = catalogues.setdefault(source_id, item)
        if prior != item:
            raise ValueError(f"archive entry {source_id} has conflicting metadata")
    if not catalogues:
        raise ValueError("archive contains no dated catalogue rows")
    return sorted(catalogues.values(), key=lambda value: (value["catalogue_date"], int(value["source_id"])))


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
    elif "available" in text:
        status = "available"
    elif "unsold" in text or "no bids" in text:
        status = "unsold"
    else:
        status = "unknown"
    price = amount(MONEY_RE.search(value or "")) if status in {"sold", "sold_prior", "sold_after"} else None
    return status, price


def parse_catalogue(html: str, item: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)
    displayed = DISPLAY_RE.search(page_text)
    cards = soup.select(".lot-panel")
    rows, malformed = [], []
    for position, card in enumerate(cards, 1):
        heading = card.select_one(".grid-address")
        detail = card.select_one('a[href*="/lot/details/"]')
        time_node = card.select_one("time[datetime]")
        heading_match = LOT_RE.match(clean(heading.get_text(" ", strip=True)) or "") if heading else None
        detail_url = urljoin(BASE, detail.get("href") or "") if detail else None
        identity = DETAIL_RE.search(detail_url or "")
        if not all((heading_match, time_node, identity)):
            malformed.append({"position": position, "heading": clean(heading.get_text(" ", strip=True)) if heading else None})
            continue
        lot_number, address = clean(heading_match.group(1)), clean(heading_match.group(2))
        source_lot_id = identity.group(1).lower()
        auction_date = datetime.fromisoformat(time_node["datetime"]).date().isoformat()
        tagline_node = card.select_one(".grid-tagline")
        description = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
        ribbon = card.select_one("[data-ribbon]")
        result_text = clean(ribbon.get("data-ribbon")) if ribbon else None
        status, sale_price = status_and_price(result_text)
        image = card.select_one("img.grid-img[src]")
        postcode = corpus.PC.search(address or "")
        row = corpus.base_row(
            AUCTIONEER, f"{SLUG}:{item['source_id']}", auction_date,
            lot_number, source_lot_id, detail_url,
        )
        row.update(
            appearance_id=f"{AUCTIONEER}|eig-lot:{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, description]))),
            sale_price=sale_price,
            status=status,
            description=description,
            image_urls=[urljoin(BASE, image.get("src"))] if image else [],
            property_id=source_lot_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            source_catalogue_date=item["catalogue_date"],
            auction_date_basis="published individual lot auction end date",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    denominator = int(displayed.group(1).replace(",", "")) if displayed else None
    complete = bool(
        denominator is not None
        and not malformed
        and denominator == len(cards) == len(rows) == len(set(identities))
    )
    return rows, {
        "published_lots_offered": item["published_lots_offered"],
        "published_lots_sold": item["published_lots_sold"],
        "published_offered_semantics": "archive outcome statistic; not the retained page row denominator",
        "source_row_denominator": denominator,
        "visible_source_rows": len(cards),
        "distinct_source_identities": len(set(identities)),
        "malformed_source_rows": malformed,
        "catalogue_complete": complete,
    }


def _key_points(soup: BeautifulSoup) -> dict[str, str]:
    result = {}
    container = soup.select_one(".lot-details-key-points")
    for block in container.find_all("div", recursive=False) if container else []:
        heading = block.find("h6")
        if not heading:
            continue
        key = clean(heading.get_text(" ", strip=True))
        heading.extract()
        result[key] = clean(block.get_text(" ", strip=True))
    return {key: value for key, value in result.items() if key and value}


def enrich_detail(html: str, row: dict, evidence: dict) -> dict:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h2", string=lambda value: value and LOT_RE.match(clean(value) or ""))
    match = LOT_RE.match(clean(heading.get_text(" ", strip=True)) or "") if heading else None
    if not match or clean(match.group(1)) != row["lot_number"]:
        raise ValueError("detail heading does not reconcile to the retained result card")
    detail_address = clean(match.group(2))
    if clean(detail_address).casefold() != clean(row["address"]).casefold():
        raise ValueError("detail address does not reconcile to the retained result card")
    guide_node = soup.find("h4", string=lambda value: value and "guide price" in value.casefold())
    guide_text = clean(guide_node.get_text(" ", strip=True)) if guide_node else None
    guide_values = [amount(value) for value in MONEY_RE.finditer(guide_text or "")]
    guide_values = [value for value in guide_values if value]
    points = _key_points(soup)
    summary_node = soup.select_one(".lot-details-property-summary")
    tagline_node = soup.select_one(".lot-details-tagline")
    summary = clean(summary_node.get_text(" ", strip=True)) if summary_node else None
    tagline = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
    description = clean(" ".join(dict.fromkeys(filter(None, [tagline, summary, row.get("description")]))))
    rent_match = RENT_RE.search(" ".join(filter(None, [tagline, summary])))
    legal = soup.select_one('a[href*="legal" i]')
    property_type = points.get("Property Type")
    published_type = points.get("Type")
    row.update(
        guide_price=guide_values[0] if guide_values else None,
        guide_price_high=guide_values[1] if len(guide_values) > 1 else None,
        guide_price_text=guide_text,
        tenure=points.get("Tenure"),
        property_type=property_type,
        description=description,
        sector=corpus.sector(
            " ".join(filter(None, [published_type, property_type, description])),
            residential=(published_type or "").casefold() == "residential",
            commercial=(published_type or "").casefold() == "commercial",
        ),
        annual_rent=int(corpus.money(rent_match.group(1))) if rent_match else None,
        rent_text=clean(rent_match.group(0)) if rent_match else None,
        legal_pack_url=urljoin(BASE, legal.get("href")) if legal else None,
        detail_source_evidence=evidence,
    )
    return row


def snapshot(raw: bytes, resolved: str, kind: str, name: str, **metadata) -> tuple[dict, Path]:
    sha = corpus.digest(raw)
    path = corpus.DATA / f"sources/{SLUG}" / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved, "retrieved_at": corpus.now(), "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)), "basis": kind, **metadata,
    }
    corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence, path


def harvest(workers: int = 8) -> dict:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    catalogues = discover(archive_html)
    archive_evidence, _ = snapshot(
        archive_raw, archive_resolved,
        "first-party retained auction archive with dates and outcome statistics", "archive",
        catalogues_discovered=len(catalogues),
    )
    summary_path = corpus.DATA / "sw_property_auctions_collection.json"
    prior = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    prior_checked = prior.get("checked_at")
    if prior_checked and prior.get("archive_sha256") == archive_evidence["sha256"] and prior.get("catalogue_completion_claimed"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(prior_checked)).total_seconds()
        if 0 <= age < 86400:
            print(json.dumps({"skipped": "complete unchanged archive checked within 24 hours", "appearances_captured": prior.get("appearances_captured")}, indent=2))
            return prior

    fetched = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get, item["source_url"]): item for item in catalogues}
        for future in as_completed(futures):
            item = futures[future]
            fetched[item["source_id"]] = (*future.result(), item)

    rows, states, failures = [], [], []
    for item in catalogues:
        raw, resolved, _ = fetched[item["source_id"]]
        evidence, _ = snapshot(
            raw, resolved, "first-party retained auction property grid",
            f"auction-{item['source_id']}", source_auction_id=item["source_id"],
        )
        parsed, reconciliation = parse_catalogue(raw.decode("utf-8", "replace"), item, evidence)
        state = {
            "auctioneer": AUCTIONEER,
            "source_auction_id": f"{SLUG}:{item['source_id']}",
            "auction_date": item["catalogue_date"],
            "source_url": resolved,
            "catalogue_complete": reconciliation["catalogue_complete"],
            "source_rows_complete": reconciliation["catalogue_complete"],
            "pagination_reconciled": reconciliation["catalogue_complete"],
            "lots_captured": len(parsed),
            **reconciliation,
            "source_evidence": evidence,
            "errors": [] if reconciliation["catalogue_complete"] else ["retained page row denominator did not reconcile"],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / f"auctions/{SLUG}/{item['source_id']}.json", state)
        states.append(state)
        if not reconciliation["catalogue_complete"]:
            failures.append({"source_auction_id": item["source_id"], "error": state["errors"][0]})
        rows.extend(parsed)

    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("retained archive contains duplicate EIG lot identities across catalogues")

    detail_results, detail_failures = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get, row["original_url"]): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                raw, resolved = future.result()
                evidence, _ = snapshot(
                    raw, resolved, "first-party retained property detail page",
                    f"lot-{row['source_lot_id']}", source_lot_id=row["source_lot_id"],
                )
                detail_results[row["appearance_id"]] = enrich_detail(raw.decode("utf-8", "replace"), row, evidence)
            except Exception as exc:
                detail_failures.append({"source_lot_id": row["source_lot_id"], "url": row["original_url"], "error": f"{type(exc).__name__}: {exc}"})
                detail_results[row["appearance_id"]] = row
    rows = [detail_results[row["appearance_id"]] for row in rows]

    appearance_path = corpus.DATA / f"appearances/{SLUG}/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in rows})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]
    complete = not failures and len(rows) == sum(state["source_row_denominator"] for state in states)
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive_resolved,
        "archive_sha256": archive_evidence["sha256"],
        "catalogues_discovered": len(catalogues),
        "catalogues_complete": sum(state["catalogue_complete"] for state in states),
        "published_archive_lots_offered": sum(item["published_lots_offered"] for item in catalogues),
        "visible_source_rows": len(rows),
        "distinct_source_identities": len(set(identities)),
        "appearances_captured": len(merged),
        "detail_pages_captured": len(rows) - len(detail_failures),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "with_guide_price": sum(row.get("guide_price") is not None for row in merged.values()),
        "with_sale_price": sum(row.get("sale_price") is not None for row in merged.values()),
        "with_annual_rent": sum(row.get("annual_rent") is not None for row in merged.values()),
        "catalogue_completion_claimed": complete,
        "completion_scope": "every retained property card in every first-party past-auction result page",
        "failures": failures,
        "detail_recovery_failures": detail_failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
