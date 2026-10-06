"""Bank Goldings Auctions' retained first-party dated result catalogues.

The public result archive publishes an offered-lot denominator for every sale
and links to the surviving property-card catalogue.  Every visible card is
preserved, but a catalogue is complete only when its distinct source cards
reconcile exactly to that published denominator.  Saved immutable catalogue
snapshots are reused unless ``--refresh`` is requested.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.goldingsauctions.co.uk"
ARCHIVE_URL = BASE + "/auctions/auction-results/"
AJAX_URL = BASE + "/wp-admin/admin-ajax.php"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def catalogue_slug(url: str) -> str:
    return urlsplit(url).path.strip("/").split("/")[-1]


def parse_archive_rows(html: str) -> list[dict]:
    rows = []
    for tr in BeautifulSoup(html, "lxml").select("tr"):
        cells = tr.find_all("td")
        link = tr.select_one('a[href*="/auction/"]')
        if len(cells) < 5 or not link:
            continue
        date_text = clean(cells[0].get_text(" ", strip=True))
        offered_match = re.search(r"\d+", cells[1].get_text(" ", strip=True))
        if not date_text or not offered_match:
            continue
        auction_date = datetime.strptime(date_text, "%A, %d %B %Y").date().isoformat()
        url = urljoin(BASE, link.get("href") or "")
        rows.append(
            {
                "auction_date": auction_date,
                "published_date": date_text,
                "published_lots_offered": int(offered_match.group()),
                "published_percent_sold": clean(cells[2].get_text(" ", strip=True)),
                "published_total_raised": pounds(cells[3].get_text(" ", strip=True)),
                "source_url": url,
                "source_auction_id": "goldings:" + catalogue_slug(url),
            }
        )
    return rows


def parse_catalogue(html: str, catalogue: dict, evidence: dict) -> list[dict]:
    cards = BeautifulSoup(html, "lxml").select(".property-card")
    rows = []
    for position, card in enumerate(cards, 1):
        link = card.select_one('a[href*="/lot/"]')
        address_node = card.select_one(".property-card__additional-meta__address")
        lot_node = card.select_one(".property-card__lot-no strong")
        source_lot_id = clean(card.get("data-lotid"))
        if not all((link, address_node, lot_node, source_lot_id)):
            raise ValueError(f"catalogue card {position} lacks its link, address, lot label or source ID")
        original_url = urljoin(BASE, link.get("href") or "")
        address = clean(address_node.get_text(" ", strip=True))
        lot_number = clean(lot_node.get_text(" ", strip=True))
        if not address or not lot_number:
            raise ValueError(f"catalogue card {position} has an empty address or lot label")
        postcode_match = corpus.PC.search(address)
        if not postcode_match:
            raise ValueError(f"catalogue card {position} address lacks a postcode")

        property_type_node = card.select_one(".property-card__additional-meta .subtitle")
        description_node = card.select_one(".property-card__additional-meta__tagline")
        property_type = clean(property_type_node.get_text(" ", strip=True)) if property_type_node else None
        description = clean(description_node.get_text(" ", strip=True)) if description_node else None
        price_label_node = card.select_one(".property-card__meta-price h4")
        price_value_node = card.select_one(".property-card__meta-price span")
        flag_node = card.select_one(".property-card__sold-flag")
        price_label = clean(price_label_node.get_text(" ", strip=True)) if price_label_node else None
        price_text = clean(price_value_node.get_text(" ", strip=True)) if price_value_node else None
        result_flag = clean(flag_node.get_text(" ", strip=True)) if flag_node else None
        result_text = " ".join(filter(None, [price_label, price_text, result_flag]))
        lowered = result_text.casefold()
        if "sold prior" in lowered:
            status = "sold_prior"
        elif "withdrawn" in lowered:
            status = "withdrawn"
        elif "unsold" in lowered:
            status = "unsold"
        elif "sold" in lowered:
            status = "sold"
        else:
            status = "unknown"
        value = pounds(price_text)
        sale_price = value if status in {"sold", "sold_prior"} else None
        guide_price = value if price_label and "guide" in price_label.casefold() else None
        image_node = card.select_one("img[data-src], img[src]")
        image_url = None
        if image_node:
            image_url = urljoin(BASE, image_node.get("data-src") or image_node.get("src") or "")

        row = corpus.base_row(
            "Goldings Auctions",
            catalogue["source_auction_id"],
            catalogue["auction_date"],
            lot_number,
            source_lot_id,
            original_url,
        )
        row.update(
            appearance_id=f"Goldings Auctions|{catalogue['auction_date']}|lot:{source_lot_id}",
            address=address,
            postcode=postcode_match.group().upper(),
            locality=None,
            sector=corpus.sector(" ".join(filter(None, [property_type, address, description]))),
            property_type=property_type,
            guide_price=guide_price,
            sale_price=sale_price,
            status=status,
            description=description,
            image_urls=[image_url] if image_url else [],
            property_id=None,
            identity_method="first_party_auction_date_and_published_source_lot_id",
            record_quality="address_record",
            source_position=position,
            source_property_id=clean(card.get("data-wpid")),
            source_price_label=price_label,
            source_price_text=price_text,
            source_result_flag=result_flag,
            auction_date_basis="published dated result catalogue",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("catalogue contains duplicate source lot identities")
    return rows


def get(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"unexpectedly short response from {url}")
    return response.content, response.url


def post_archive_page(page: int) -> tuple[int, bytes, str]:
    response = requests.post(
        AJAX_URL,
        headers=HEADERS,
        data={"action": "get_auction_table_rows", "page": page},
        timeout=90,
    )
    response.raise_for_status()
    return page, response.content, response.url


def archive_catalogues() -> tuple[list[dict], list[dict]]:
    first_raw, first_resolved = get(ARCHIVE_URL)
    first_html = first_raw.decode("utf-8", "replace")
    soup = BeautifulSoup(first_html, "lxml")
    max_pages = max([int(node.get("data-page-max")) for node in soup.select("[data-page-max]") if (node.get("data-page-max") or "").isdigit()] or [1])
    pages = {1: (first_raw, first_resolved)}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(post_archive_page, page) for page in range(2, max_pages + 1)]
        for future in as_completed(futures):
            page, raw, resolved = future.result()
            pages[page] = (raw, resolved)

    catalogues, evidence_pages = [], []
    for page in range(1, max_pages + 1):
        raw, resolved = pages[page]
        html = raw.decode("utf-8", "replace")
        sha = corpus.digest(raw)
        snapshot = corpus.DATA / "sources/goldings" / f"archive-page-{page}-{sha[:16]}.json.gz"
        evidence = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party dated auction-results archive",
            "page": page,
            "published_page_max": max_pages,
        }
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        rows = parse_archive_rows(html)
        # The source advertises one empty terminal Ajax page. Retaining it is
        # part of reconciling the archive rather than evidence of a catalogue.
        if page < max_pages and not rows:
            raise ValueError(f"archive page {page} unexpectedly contains no auction rows")
        catalogues.extend(rows)
        evidence_pages.append({**evidence, "auction_rows": len(rows)})

    unique = {}
    for catalogue in catalogues:
        key = catalogue["source_auction_id"]
        if key in unique and unique[key] != catalogue:
            raise ValueError(f"conflicting duplicate archive catalogue {key}")
        unique[key] = catalogue
    if not unique:
        raise ValueError("auction archive contains no dated catalogues")
    return sorted(unique.values(), key=lambda row: row["auction_date"]), evidence_pages


def load_saved_catalogue(catalogue: dict) -> tuple[bytes, str, dict] | None:
    state_path = corpus.DATA / "auctions/goldings" / f"{catalogue_slug(catalogue['source_url'])}.json"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text())
    evidence = state.get("source_evidence") or {}
    snapshot_name = evidence.get("snapshot_path")
    snapshot = corpus.ROOT / snapshot_name if snapshot_name else None
    if state.get("source_url") != catalogue["source_url"] or not snapshot or not snapshot.exists():
        return None
    saved = corpus.read_gzip(snapshot)
    return saved["html"].encode("utf-8"), catalogue["source_url"], saved["evidence"]


def harvest(refresh: bool = False, workers: int = 8) -> None:
    catalogues, archive_evidence = archive_catalogues()
    fetched = {}
    failures = []
    to_fetch = []
    for catalogue in catalogues:
        saved = None if refresh else load_saved_catalogue(catalogue)
        if saved:
            fetched[catalogue["source_auction_id"]] = saved
        else:
            to_fetch.append(catalogue)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        jobs = {pool.submit(get, catalogue["source_url"]): catalogue for catalogue in to_fetch}
        for future in as_completed(jobs):
            catalogue = jobs[future]
            try:
                raw, resolved = future.result()
                fetched[catalogue["source_auction_id"]] = (raw, resolved, None)
            except Exception as exc:
                failures.append({"source_auction_id": catalogue["source_auction_id"], "error": f"{type(exc).__name__}: {exc}"[:400]})

    observed = []
    complete_count = 0
    incomplete_count = 0
    for catalogue in catalogues:
        state_path = corpus.DATA / "auctions/goldings" / f"{catalogue_slug(catalogue['source_url'])}.json"
        item = fetched.get(catalogue["source_auction_id"])
        if not item:
            corpus.save_json(
                state_path,
                {
                    **catalogue,
                    "auctioneer": "Goldings Auctions",
                    "catalogue_complete": False,
                    "source_rows_complete": False,
                    "lots_captured": 0,
                    "pagination_reconciled": True,
                    "denominator_reconciled": False,
                    "completion_scope": "all surviving lot cards in the dated first-party result catalogue",
                    "source_evidence": None,
                    "errors": [x["error"] for x in failures if x["source_auction_id"] == catalogue["source_auction_id"]],
                    "checked_at": corpus.now(),
                },
            )
            incomplete_count += 1
            continue

        raw, resolved, saved_evidence = item
        html = raw.decode("utf-8", "replace")
        if saved_evidence:
            evidence = saved_evidence
        else:
            sha = corpus.digest(raw)
            slug = catalogue_slug(catalogue["source_url"])
            snapshot = corpus.DATA / "sources/goldings" / f"catalogue-{slug}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": resolved,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party dated auction result lot cards",
                "published_lots_offered": catalogue["published_lots_offered"],
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
        rows = parse_catalogue(html, catalogue, evidence)
        reconciled = len(rows) == catalogue["published_lots_offered"]
        complete_count += int(reconciled)
        incomplete_count += int(not reconciled)
        state = {
            **catalogue,
            "auctioneer": "Goldings Auctions",
            "catalogue_complete": reconciled,
            "source_rows_complete": reconciled,
            "visible_source_rows": len(rows),
            "lots_captured": len(rows),
            "pagination_reconciled": True,
            "denominator_reconciled": reconciled,
            "completion_scope": "all surviving lot cards in the dated first-party result catalogue",
            "source_evidence": evidence,
            "reconciliation_errors": [] if reconciled else [f"visible source rows {len(rows)} do not equal published lots offered {catalogue['published_lots_offered']}"],
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(state_path, state)
        observed.extend(rows)

    appearance_path = corpus.DATA / "appearances/goldings/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in observed})
    total = corpus.write_rows("goldings/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    date_values = [row["auction_date"] for row in merged.values() if row.get("auction_date")]
    summary = {
        "checked_at": corpus.now(),
        "source_url": ARCHIVE_URL,
        "catalogues_discovered": len(catalogues),
        "published_lots_offered": sum(row["published_lots_offered"] for row in catalogues),
        "visible_source_rows": len(observed),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "catalogues_complete": complete_count,
        "catalogues_incomplete": incomplete_count,
        "archive_pages_reconciled": len(archive_evidence),
        "archive_source_evidence": archive_evidence,
        "date_range": [min(date_values), max(date_values)] if date_values else [None, None],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "goldings_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refetch saved catalogue pages")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(refresh=args.refresh, workers=args.workers)
