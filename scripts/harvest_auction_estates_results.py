"""Bank every retained Auction Estates first-party result catalogue."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import gzip
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.auctionestates.co.uk"
ARCHIVE_URL = BASE + "/auction-results"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MODERN_DETAIL_RE = re.compile(r"-(\d{4,})$")
AUCTION_RE = re.compile(r"/auction/(\d+)/", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
COUNT_RE = re.compile(r"([\d,]+)\s+results", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def catalogue_manifest(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    select = soup.select_one("#property_filter_auctionDate")
    if not select:
        raise ValueError("auction-date manifest is absent")
    out = []
    for option in select.select("option[value]"):
        value = clean(option.get("value"))
        if not value:
            continue
        date = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").date().isoformat()
        out.append({"auction_date": date, "form_value": value, "label": clean(option.get_text(" ", strip=True))})
    if not out or len({item["auction_date"] for item in out}) != len(out):
        raise ValueError("auction-date manifest is empty or duplicated")
    return out


def published_total(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one(".results-heading .display-results-heading")
    match = COUNT_RE.search(node.get_text(" ", strip=True) if node else "")
    if not match:
        raise ValueError("catalogue result denominator is absent")
    return int(match.group(1).replace(",", ""))


def status(card) -> str:
    ribbon = card.select_one(".property-flash")
    text = (clean(ribbon.get_text(" ", strip=True)) or "").casefold() if ribbon else ""
    classes = {value.casefold() for value in (ribbon.get("class") or [])} if ribbon else set()
    combined = " ".join([*classes, text])
    if "no bids" in combined:
        return "no_bids"
    if "unsold" in combined:
        return "unsold"
    if "sold prior" in combined:
        return "sold_prior"
    if "sold post" in combined or "sold after" in combined:
        return "sold_after"
    if "sold" in combined:
        return "sold"
    if "withdrawn" in combined:
        return "withdrawn"
    if "postponed" in combined:
        return "postponed"
    if "available" in combined:
        return "available"
    if "refer" in combined:
        return "refer_to_auctioneer"
    return "unknown"


def parse_catalogue(html: str, auction_date: str, evidence: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    date_node = soup.select_one(".results-date")
    shown_date = datetime.strptime(clean(date_node.get_text(" ", strip=True)), "%d %B %Y").date().isoformat() if date_node else None
    if shown_date != auction_date:
        raise ValueError(f"requested {auction_date} but source rendered {shown_date}")
    cards = soup.select(".result-container")
    expected = published_total(html)
    if len(cards) != expected:
        raise ValueError(f"{auction_date} exposes {len(cards)} cards of {expected} stated results")
    rows = []
    for position, card in enumerate(cards, 1):
        address_node = card.select_one(".property-title")
        detail_node = card.select_one('a[href*="/property/"]')
        if not address_node or not detail_node:
            raise ValueError(f"{auction_date} card {position} lacks address or detail link")
        address = clean(address_node.get_text(" ", strip=True))
        detail_url = urljoin(BASE, detail_node.get("href") or "")
        slug = detail_url.rstrip("/").split("/")[-1]
        id_match = MODERN_DETAIL_RE.search(slug)
        if not address:
            raise ValueError(f"{auction_date} card {position} lacks an address")
        source_id = id_match.group(1) if id_match else None
        identity_token = f"property:{source_id}" if source_id else f"url:{corpus.digest(detail_url.encode())[:16]}"
        auction_match = AUCTION_RE.search(str(card))
        auction_id = auction_match.group(1) if auction_match else None
        result_status = status(card)
        result_node = card.select_one(".property-flash")
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        lot_match = re.search(r"\bLot\s+No\.?\s*([0-9]+[A-Za-z]?)\b", result_text or "", re.I)
        sale_node = card.select_one(".property-details__price")
        guide_node = card.select_one(".property-guide-price p")
        description = clean(" ".join(node.get_text(" ", strip=True) for node in card.select(".text-container li")))
        image_node = card.select_one("img.result-property-image[src]")
        postcode_match = corpus.PC.search(address)
        row = corpus.base_row(
            "Auction Estates", f"auction-estates:{auction_date}", auction_date,
            lot_match.group(1) if lot_match else None, identity_token, detail_url,
        )
        row.update(
            appearance_id=f"Auction Estates|{auction_date}|{identity_token}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(" ".join(filter(None, [address, description]))),
            property_type=None,
            guide_price=pounds(guide_node.get_text(" ", strip=True) if guide_node else None),
            sale_price=pounds(sale_node.get_text(" ", strip=True) if sale_node else None),
            status=result_status,
            description=description,
            image_urls=[urljoin(BASE, image_node.get("src"))] if image_node else [],
            property_id=source_id,
            identity_method="first_party_auction_date_plus_property_id" if source_id else "first_party_auction_date_plus_exact_property_url",
            record_quality="address_record",
            source_position=position,
            source_auction_platform_id=auction_id,
            source_result_text=result_text,
            auction_date_basis="published results catalogue selector and heading",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError(f"{auction_date} contains duplicate appearance identities")
    return rows


def fetch_root() -> tuple[requests.Session, bytes, str]:
    session = requests.Session()
    response = session.get(ARCHIVE_URL, headers=HEADERS, timeout=90)
    response.raise_for_status()
    return session, response.content, response.url


def fetch_catalogue(item: dict) -> tuple[dict, bytes, str]:
    session, raw, _ = fetch_root()
    soup = BeautifulSoup(raw.decode("utf-8", "replace"), "lxml")
    token = soup.select_one("#property_filter__token")
    if not token:
        raise ValueError("catalogue filter token is absent")
    data = {
        "property_filter[propertyType]": "",
        "property_filter[minimumPrice]": "",
        "property_filter[maximumPrice]": "",
        "property_filter[auctionDate]": item["form_value"],
        "property_filter[distinctSaleStatus]": "",
        "property_filter[submit]": "",
        "property_filter[_token]": token.get("value"),
    }
    response = session.post(ARCHIVE_URL, headers=HEADERS, data=data, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"{item['auction_date']} result response is unexpectedly short")
    return item, response.content, response.url


def harvest(workers: int = 8) -> None:
    _, root_raw, root_resolved = fetch_root()
    root_html = root_raw.decode("utf-8", "replace")
    manifest = catalogue_manifest(root_html)
    state_dir = corpus.DATA / "auctions/auction-estates"
    cached = {}
    for item in manifest:
        path = state_dir / f"{item['auction_date']}.json"
        if not path.exists():
            # A prior interrupted reconciliation may already have saved the
            # immutable source page. Reparse it instead of refetching the site.
            snapshots = sorted((corpus.DATA / "sources/auction-estates").glob(f"results-{item['auction_date']}-*.json.gz"))
            if snapshots:
                snapshot = snapshots[-1]
                saved = corpus.read_gzip(snapshot)
                evidence = saved.get("evidence") or {}
                cached[item["auction_date"]] = (saved["html"].encode("utf-8"), evidence.get("source_url"), evidence)
            continue
        state = json.loads(path.read_text())
        evidence = state.get("source_evidence") or {}
        snapshot_name = evidence.get("snapshot_path")
        snapshot = corpus.ROOT / snapshot_name if snapshot_name else None
        if state.get("catalogue_complete") and snapshot and snapshot.exists():
            saved = corpus.read_gzip(snapshot)
            cached[item["auction_date"]] = (saved["html"].encode("utf-8"), evidence.get("source_url"), evidence)

    fetched = {}
    pending = [item for item in manifest if item["auction_date"] not in cached]
    # The initial GET already represents the newest selected catalogue.
    newest = manifest[0]
    if newest in pending:
        fetched[newest["auction_date"]] = (root_raw, root_resolved, None)
        pending.remove(newest)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_catalogue, item): item for item in pending}
        for future in as_completed(futures):
            item, raw, resolved = future.result()
            fetched[item["auction_date"]] = (raw, resolved, None)

    all_rows, failures, completed = [], [], []
    for item in manifest:
        auction_date = item["auction_date"]
        raw, resolved, saved_evidence = cached.get(auction_date) or fetched[auction_date]
        html = raw.decode("utf-8", "replace")
        evidence = saved_evidence
        if not evidence:
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/auction-estates" / f"results-{auction_date}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party dated auction-results catalogue",
                "auction_date": auction_date,
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        try:
            rows = parse_catalogue(html, auction_date, evidence)
            expected = published_total(html)
            state = {
                "auctioneer": "Auction Estates",
                "source_auction_id": f"auction-estates:{auction_date}",
                "auction_date": auction_date,
                "catalogue_complete": True,
                "source_rows_complete": True,
                "published_lots_offered": expected,
                "visible_source_rows": len(rows),
                "lots_captured": len(rows),
                "source_url": resolved,
                "pagination_reconciled": True,
                "denominator_reconciled": True,
                "source_evidence": evidence,
                "errors": [],
                "checked_at": corpus.now(),
            }
            corpus.save_json(state_dir / f"{auction_date}.json", state)
            all_rows.extend(rows)
            completed.append(auction_date)
        except Exception as exc:
            failures.append({"auction_date": auction_date, "error": f"{type(exc).__name__}: {exc}"})

    if failures:
        raise ValueError(f"Auction Estates catalogue reconciliation failures: {failures}")
    appearance_path = corpus.DATA / "appearances/auction-estates/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    # Early local development treated the leading number in legacy address
    # slugs as a source property ID. It is often only the street number. Drop
    # only those obsolete identities after their exact date+URL replacements
    # have been parsed in this same fully reconciled run.
    obsolete = [
        row for row in existing
        if row.get("identity_method") == "first_party_auction_date_plus_property_id"
        and not MODERN_DETAIL_RE.search((row.get("original_url") or "").rstrip("/").split("/")[-1])
    ]
    if obsolete:
        existing = [row for row in existing if row not in obsolete]
        raw = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in sorted(existing, key=lambda value: value["appearance_id"])
        )
        corpus.atomic(appearance_path, gzip.compress(raw.encode(), mtime=0))
    before_ids = {row["appearance_id"] for row in existing}
    total = corpus.write_rows("auction-estates/canonical", all_rows)
    added = [row for row in all_rows if row["appearance_id"] not in before_ids]
    summary = {
        "checked_at": corpus.now(),
        "source_url": root_resolved,
        "catalogues_discovered": len(manifest),
        "catalogues_complete": len(completed),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "date_range": [min(completed), max(completed)],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in all_rows)),
        "catalogue_completion_claimed": True,
        "failures": [],
    }
    corpus.save_json(corpus.DATA / "auction_estates_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    harvest(workers)
