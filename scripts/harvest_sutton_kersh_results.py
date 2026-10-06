"""Bank Sutton Kersh's retained first-party property-auction results.

The public archive publishes exact auction dates and a stable period identifier.
Each period page publishes a property denominator and paginates at 48 rows.  A
catalogue is complete only after every page has been fetched and the distinct
source rows reconcile exactly to that denominator.  The bounded default run
resumes with the oldest incomplete catalogues so repeated workflow runs deepen
the archive without refetching completed periods.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.suttonkersh.co.uk"
ARCHIVE_URL = BASE + "/auctions-property/auction-results/"
LIST_URL = BASE + "/properties/listview/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PAGE_SIZE = 48
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADER_RE = re.compile(r"^header_(\d+)_(\d+)$")
PROPERTY_RE = re.compile(r"/properties/lot/(\d+)/?")
COUNT_RE = re.compile(r"([\d,]+)\s+Properties", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def archive_date(value: str) -> str:
    normalized = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", clean(value) or "", flags=re.I)
    return datetime.strptime(normalized, "%B %d %Y").date().isoformat()


def parse_manifest(html: str) -> list[dict]:
    rows = []
    for link in BeautifulSoup(html, "lxml").select('a[href*="auctionPeriod="]'):
        href = link.get("href") or ""
        match = re.search(r"(?:\?|&)auctionPeriod=(\d+)", href)
        label = clean(link.get_text(" ", strip=True))
        if not match or not label or not re.fullmatch(r"[A-Za-z]+\s+\d+(?:st|nd|rd|th)?\s+\d{4}", label):
            continue
        period = match.group(1)
        rows.append(
            {
                "period_id": period,
                "auction_date": archive_date(label),
                "published_date": label,
                "source_auction_id": f"sutton-kersh:{period}",
            }
        )
    unique = {}
    for row in rows:
        previous = unique.get(row["period_id"])
        if previous and previous != row:
            raise ValueError(f"conflicting archive rows for period {row['period_id']}")
        unique[row["period_id"]] = row
    if not unique:
        raise ValueError("Sutton Kersh archive exposes no dated auction periods")
    return sorted(unique.values(), key=lambda row: (row["auction_date"], int(row["period_id"])))


def catalogue_url(period_id: str, start: int = 0) -> str:
    return LIST_URL + "?" + urlencode(
        {"auctionPeriod": period_id, "perPage": PAGE_SIZE, "section": "auction", "start": start}
    )


def published_total(html: str) -> int:
    node = BeautifulSoup(html, "lxml").select_one(".propertyCount")
    match = COUNT_RE.search(node.get_text(" ", strip=True) if node else "")
    if not match:
        raise ValueError("published property denominator is absent")
    return int(match.group(1).replace(",", ""))


def status(result_text: str | None) -> str:
    value = (result_text or "").casefold()
    if "unsold" in value:
        return "unsold"
    if "sold prior" in value:
        return "sold_prior"
    if "sold post" in value or "sold after" in value:
        return "sold_after"
    if "sold" in value:
        return "sold"
    if "withdrawn" in value:
        return "withdrawn"
    if "postponed" in value:
        return "postponed"
    if "available" in value:
        return "available"
    return "unknown"


def parse_page(html: str, catalogue: dict, evidence: dict, start: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for offset, header in enumerate(soup.select('tr[id^="header_"]')):
        match = HEADER_RE.match(header.get("id") or "")
        cells = header.find_all("td", recursive=False)
        if not match or len(cells) < 4:
            raise ValueError(f"period {catalogue['period_id']} has a malformed row at {start + offset + 1}")
        period_id, source_row_id = match.groups()
        if period_id != catalogue["period_id"]:
            raise ValueError(f"period {catalogue['period_id']} rendered row from period {period_id}")
        detail = soup.select_one(f"#detail_{period_id}_{source_row_id}")
        detail_link = detail.select_one('a[href*="/properties/lot/"]') if detail else None
        property_match = PROPERTY_RE.search(detail_link.get("href") or "") if detail_link else None
        if not detail or not detail_link or not property_match:
            raise ValueError(f"period {period_id} row {source_row_id} lacks its detail identity")

        lot_number = clean(cells[0].get_text(" ", strip=True))
        detail_title = detail.select_one('h3 a[href*="/properties/lot/"]')
        address = clean(cells[1].get_text(" ", strip=True)) or (
            clean(detail_title.get_text(" ", strip=True)) if detail_title else None
        )
        postcode = clean(cells[2].get_text(" ", strip=True))
        result_text = clean(cells[3].get_text(" ", strip=True))
        postcode_match = corpus.PC.search(postcode or address or "")
        property_id = property_match.group(1)
        original_url = urljoin(BASE, detail_link.get("href") or "")
        description_node = detail.select_one(".descriptionText")
        description = clean(description_node.get_text(" ", strip=True)) if description_node else None
        image_node = detail.select_one("img.lotImage[src]")
        image_url = urljoin(BASE, image_node.get("src") or "") if image_node else None
        result_status = status(result_text)
        result_price = pounds(result_text)
        legal_node = cells[4].select_one("a[href]") if len(cells) > 4 else None
        legal_url = urljoin(BASE, legal_node.get("href") or "") if legal_node else None

        row = corpus.base_row(
            "Sutton Kersh",
            catalogue["source_auction_id"],
            catalogue["auction_date"],
            lot_number,
            source_row_id,
            original_url,
        )
        row.update(
            appearance_id=f"Sutton Kersh|period:{period_id}|property:{property_id}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=None,
            sector=corpus.sector(" ".join(filter(None, [address, description]))),
            property_type=None,
            guide_price=result_price if "guide price" in (result_text or "").casefold() else None,
            sale_price=result_price if result_status in {"sold", "sold_after"} else None,
            available_price=result_price if result_status == "available" else None,
            status=result_status,
            description=description,
            image_urls=[image_url] if image_url else [],
            property_id=property_id,
            identity_method="first_party_auction_period_and_stable_property_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=start + offset + 1,
            source_row_id=source_row_id,
            source_property_id=property_id,
            source_result_text=result_text,
            legal_pack_url=legal_url,
            auction_date_basis="first-party dated auction-results archive",
            source_evidence=evidence,
        )
        rows.append(row)
    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError(f"period {catalogue['period_id']} page contains duplicate property identities")
    return rows


def get(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"unexpectedly short response from {url}")
    return response.content, response.url


def snapshot_page(catalogue: dict, start: int, raw: bytes, resolved: str) -> tuple[str, dict]:
    html = raw.decode("utf-8", "replace")
    sha = corpus.digest(raw)
    snapshot = corpus.DATA / "sources/sutton_kersh" / (
        f"period-{catalogue['period_id']}-start-{start}-{sha[:16]}.json.gz"
    )
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party dated auction result page",
        "period_id": catalogue["period_id"],
        "start": start,
        "page_size": PAGE_SIZE,
    }
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
    return html, evidence


def load_complete(catalogue: dict) -> tuple[list[dict], list[dict]] | None:
    state_path = corpus.DATA / "auctions/sutton_kersh" / f"{catalogue['period_id']}.json"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text())
    if not state.get("catalogue_complete"):
        return None
    rows, evidence_pages = [], []
    for evidence in state.get("source_evidence") or []:
        snapshot_name = evidence.get("snapshot_path")
        snapshot = corpus.ROOT / snapshot_name if snapshot_name else None
        if not snapshot or not snapshot.exists():
            return None
        saved = corpus.read_gzip(snapshot)
        page_evidence = saved.get("evidence") or evidence
        rows.extend(parse_page(saved["html"], catalogue, page_evidence, int(page_evidence["start"])))
        evidence_pages.append(page_evidence)
    if len(rows) != state.get("lots_captured"):
        return None
    return rows, evidence_pages


def fetch_catalogue(catalogue: dict, workers: int) -> tuple[list[dict], list[dict], int]:
    first_raw, first_resolved = get(catalogue_url(catalogue["period_id"], 0))
    first_html, first_evidence = snapshot_page(catalogue, 0, first_raw, first_resolved)
    expected = published_total(first_html)
    starts = list(range(PAGE_SIZE, expected, PAGE_SIZE))
    pages = {0: (first_html, first_evidence)}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        jobs = {pool.submit(get, catalogue_url(catalogue["period_id"], start)): start for start in starts}
        for future in as_completed(jobs):
            start = jobs[future]
            raw, resolved = future.result()
            pages[start] = snapshot_page(catalogue, start, raw, resolved)

    rows, evidence_pages = [], []
    for start in [0, *starts]:
        html, evidence = pages[start]
        if published_total(html) != expected:
            raise ValueError(f"period {catalogue['period_id']} changed denominator during pagination")
        page_rows = parse_page(html, catalogue, evidence, start)
        rows.extend(page_rows)
        evidence_pages.append({**evidence, "visible_source_rows": len(page_rows)})
    identities = [row["appearance_id"] for row in rows]
    if len(rows) != expected or len(identities) != len(set(identities)):
        raise ValueError(
            f"period {catalogue['period_id']} reconciles {len(set(identities))}/{expected} distinct rows"
        )
    return rows, evidence_pages, expected


def harvest(catalogues: int = 8, workers: int = 6, refresh: bool = False) -> None:
    archive_raw, archive_resolved = get(ARCHIVE_URL)
    archive_html = archive_raw.decode("utf-8", "replace")
    manifest = parse_manifest(archive_html)
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = corpus.DATA / "sources/sutton_kersh" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_resolved,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party dated auction-results archive",
        "published_auction_periods": len(manifest),
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})

    selected, cached = [], {}
    for catalogue in manifest:
        saved = None if refresh else load_complete(catalogue)
        if saved:
            cached[catalogue["period_id"]] = saved
        elif len(selected) < max(1, catalogues):
            selected.append(catalogue)

    # Reparse completed immutable snapshots on every run so parser corrections
    # can safely enrich the same appearance IDs without a source refetch.
    observed = [row for rows, _ in cached.values() for row in rows]
    failures, completed = [], []
    for catalogue in selected:
        try:
            rows, evidence_pages, expected = fetch_catalogue(catalogue, workers)
            observed.extend(rows)
            completed.append(catalogue["period_id"])
            state = {
                "auctioneer": "Sutton Kersh",
                "source_auction_id": catalogue["source_auction_id"],
                "source_period_id": catalogue["period_id"],
                "auction_date": catalogue["auction_date"],
                "catalogue_complete": True,
                "source_rows_complete": True,
                "published_lots_offered": expected,
                "visible_source_rows": len(rows),
                "lots_captured": len(rows),
                "pagination_reconciled": True,
                "denominator_reconciled": True,
                "completion_scope": "all rows in the first-party dated result catalogue",
                "source_url": catalogue_url(catalogue["period_id"], 0),
                "source_evidence": evidence_pages,
                "archive_evidence": archive_evidence,
                "reconciliation_errors": [],
                "errors": [],
                "checked_at": corpus.now(),
            }
            corpus.save_json(corpus.DATA / "auctions/sutton_kersh" / f"{catalogue['period_id']}.json", state)
        except Exception as exc:
            failures.append(
                {"period_id": catalogue["period_id"], "auction_date": catalogue["auction_date"], "error": f"{type(exc).__name__}: {exc}"[:500]}
            )

    appearance_path = corpus.DATA / "appearances/sutton_kersh/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in observed})
    total = corpus.write_rows("sutton_kersh/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    complete_states = list((corpus.DATA / "auctions/sutton_kersh").glob("*.json"))
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive_resolved,
        "published_auction_periods": len(manifest),
        "appearances_captured": total,
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "complete_catalogues": len(complete_states),
        "catalogues_completed_this_run": completed,
        "catalogues_remaining": len(manifest) - len(complete_states),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "sutton_kersh_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogues", type=int, default=8, help="oldest incomplete catalogues to collect")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    harvest(catalogues=args.catalogues, workers=args.workers, refresh=args.refresh)
