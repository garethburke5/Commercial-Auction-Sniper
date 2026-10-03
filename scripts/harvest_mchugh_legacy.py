"""Bank McHugh & Co's retained 2007-2020 first-party result tables.

The legacy ASP.NET archive exposes auction rows through Telerik row-click
postbacks rather than links.  Each response is an unpaginated result table.
Every property row is retained, including residential, available, withdrawn,
and sold-prior lots.  Later runs reuse reconciled per-auction checkpoints.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


ARCHIVE = "https://mchughauctions.co.uk/Auctions/AucList.aspx"
CUTOFF = date(2020, 6, 10)  # the modern mchughandco.com collector starts here
GRID_ID = "ctl00_mainContent_auctionsGrid_ctl00"
RESULT_GRID_ID = "ctl00_mainContent_ListViewGuidesGrid_ctl00"
EVENT_TARGET = "ctl00$mainContent$auctionsGrid"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MONEY_RE = re.compile(r"£\s*([\d,.]+)\s*([MK])?", re.I)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def parse_date(value: str) -> str:
    return datetime.strptime(clean(value) or "", "%A %d %B %Y").date().isoformat()


def discover_auctions(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = []
    for row in soup.select(f'table#{GRID_ID} tr[id^="{GRID_ID}__"]'):
        cells = row.find_all("td", recursive=False)
        match = re.search(r"__(\d+)$", row.get("id", ""))
        if len(cells) < 2 or not match:
            continue
        auction_date = parse_date(cells[0].get_text(" ", strip=True))
        if datetime.strptime(auction_date, "%Y-%m-%d").date() >= CUTOFF:
            continue
        found.append({
            "row_index": int(match.group(1)), "auction_date": auction_date,
            "date_text": clean(cells[0].get_text(" ", strip=True)),
            "venue": clean(cells[1].get_text(" ", strip=True)),
        })
    return sorted(found, key=lambda item: item["auction_date"], reverse=True)


def postback_data(index_html: str, row_index: int) -> dict[str, str]:
    soup = BeautifulSoup(index_html, "lxml")
    data = {
        node.get("name"): node.get("value", "")
        for node in soup.select("input[type=hidden][name]")
    }
    data["__EVENTTARGET"] = EVENT_TARGET
    data["__EVENTARGUMENT"] = f"RowClick;{row_index}"
    return data


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None]:
    text = clean(value) or ""
    lower = text.casefold()
    match = MONEY_RE.search(text)
    amount = corpus.money((match.group(1) + (match.group(2) or "")) if match else None)
    amount = int(round(amount)) if amount is not None else None
    if lower.startswith("available"):
        return "available", None, amount
    if lower.startswith("sold prior"):
        return "sold_prior", amount, None
    if lower.startswith("sold post") or lower.startswith("sold after"):
        return "sold_post", amount, None
    if lower.startswith("withdrawn prior"):
        return "withdrawn_prior", None, None
    for label in ("withdrawn", "postponed", "unsold"):
        if lower.startswith(label):
            return label, None, None
    if amount is not None:
        return "sold", amount, None
    return "unknown", None, None


def parse_result_page(
    html: str, expected_date: str, evidence: dict, venue: str | None = None,
) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    headings = [clean(node.get_text(" ", strip=True)) for node in soup.select("h1,h2,h3")]
    dates = []
    for heading in headings:
        try:
            dates.append(parse_date(heading or ""))
        except ValueError:
            pass
    if expected_date not in dates:
        raise ValueError(f"postback returned the wrong auction: expected {expected_date}, saw {dates}")
    table = soup.select_one(f"table#{RESULT_GRID_ID}")
    if not table:
        raise ValueError("result response has no lot table")

    source_rows = table.select(f'tr[id^="{RESULT_GRID_ID}__"]')
    raw_lot_numbers = []
    for tr in source_rows:
        cells = tr.find_all("td", recursive=False)
        raw_lot_numbers.append(clean(cells[0].get_text(" ", strip=True)) if len(cells) == 4 else None)
    lot_counts = Counter(value for value in raw_lot_numbers if value)

    rows = []
    for position, tr in enumerate(source_rows, 1):
        cells = tr.find_all("td", recursive=False)
        if len(cells) != 4:
            raise ValueError(f"unexpected result columns at source position {position}")
        lot_number, property_type, address_text, result_text = [
            clean(cell.get_text(" ", strip=True)) for cell in cells
        ]
        # The retained table includes one source row with a blank address and
        # one catalogue with a duplicated printed lot number.  Preserve both
        # exactly; source position disambiguates without merging properties.
        source_lot_id = (
            f"{lot_number}#row-{position}" if lot_number and lot_counts[lot_number] > 1
            else lot_number or f"row-{position}"
        )
        postcode_match = corpus.PC.search(address_text or "")
        postcode = postcode_match.group().upper().replace("\u00a0", " ") if postcode_match else None
        address = address_text if postcode else None
        status, sale_price, available_price = status_and_prices(result_text)
        source_auction_id = f"mchugh-legacy:{expected_date}"
        row = corpus.base_row(
            "McHugh & Co", source_auction_id, expected_date,
            lot_number, source_lot_id, ARCHIVE,
        )
        row.update(
            address=address, postcode=postcode, locality=address_text,
            property_type=property_type, description=property_type,
            sector=corpus.sector(f"{property_type or ''} {address_text or ''}"),
            status=status, sale_price=sale_price, available_price=available_price,
            property_id=None,
            identity_method="legacy_auction_date_and_lot_number_or_source_position",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_status_text=result_text,
            source_result_url=ARCHIVE, source_venue=venue, source_evidence=evidence,
        )
        row["appearance_id"] = f"McHugh & Co|legacy-auction:{expected_date}|lot:{source_lot_id}"
        rows.append(row)

    if not rows:
        raise ValueError("result table has no property rows")
    identities = [row["source_lot_id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate lot identities within result table")
    state = {
        "auctioneer": "McHugh & Co", "source_auction_id": f"mchugh-legacy:{expected_date}",
        "auction_date": expected_date, "catalogue_complete": True,
        "source_rows_complete": True, "published_lots_offered": None,
        "visible_source_rows": len(rows), "lots_captured": len(rows),
        "source_url": ARCHIVE, "pagination_reconciled": True,
        "denominator_reconciled": True,
        "denominator_basis": "all rows in the first-party unpaginated result table",
        "completion_scope": "all visible property rows in the first-party unpaginated legacy result table",
        "errors": [], "checked_at": corpus.now(),
    }
    return state, rows


def get(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response


def harvest(workers: int = 8) -> None:
    session = requests.Session()
    archive_response = get(session, ARCHIVE)
    archive_html = archive_response.content.decode("utf-8", "replace")
    archive_sha, retrieved_at = corpus.digest(archive_response.content), corpus.now()
    archive_snapshot = corpus.DATA / "sources/mchugh-legacy" / f"auction-list-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive_response.url, "retrieved_at": retrieved_at,
        "sha256": archive_sha, "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party legacy auction index",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    auctions = discover_auctions(archive_html)
    if not auctions:
        raise SystemExit("No pre-modern McHugh auction rows discovered")

    path = corpus.DATA / "appearances/mchugh-legacy/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction: dict[str, list[dict]] = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)

    states, run_rows, failures, pending, reused = {}, [], [], [], 0
    for item in auctions:
        state_path = corpus.DATA / f"auctions/mchugh-legacy/auction-{item['auction_date']}.json"
        old_state = None
        if state_path.exists():
            try:
                old_state = json.loads(state_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        old_rows = existing_by_auction.get(f"mchugh-legacy:{item['auction_date']}", [])
        if (old_state and old_state.get("catalogue_complete") and
                old_state.get("lots_captured") == len(old_rows) and old_rows):
            states[item["auction_date"]] = old_state
            run_rows.extend(old_rows)
            reused += 1
        else:
            pending.append(item)

    def capture(item: dict):
        fresh = requests.Session()
        index_response = get(fresh, ARCHIVE)
        index_html = index_response.content.decode("utf-8", "replace")
        response = fresh.post(
            ARCHIVE, data=postback_data(index_html, item["row_index"]),
            headers=HEADERS, timeout=90,
        )
        response.raise_for_status()
        if len(response.content) < 1000:
            raise ValueError("result response is unexpectedly short")
        page_sha, captured_at = corpus.digest(response.content), corpus.now()
        snapshot = corpus.DATA / "sources/mchugh-legacy" / f"auction-{item['auction_date']}-{page_sha[:16]}.json.gz"
        evidence = {
            "source_url": response.url, "retrieved_at": captured_at, "sha256": page_sha,
            "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
            "basis": "first-party unpaginated legacy result table via archive row postback",
            "archive_row_index": item["row_index"],
        }
        page_html = response.content.decode("utf-8", "replace")
        corpus.save_gzip(snapshot, {"evidence": evidence, "html": page_html})
        state, rows = parse_result_page(page_html, item["auction_date"], evidence, item["venue"])
        return state, rows

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
        jobs = {pool.submit(capture, item): item for item in pending}
        for future in as_completed(jobs):
            item = jobs[future]
            try:
                state, rows = future.result()
                corpus.save_json(
                    corpus.DATA / f"auctions/mchugh-legacy/auction-{item['auction_date']}.json", state,
                )
                states[item["auction_date"]] = state
                run_rows.extend(rows)
                print("MCHUGH LEGACY", len(states), "/", len(auctions), "auctions", len(run_rows), "lots", flush=True)
            except Exception as exc:
                failures.append({
                    "auction_date": item["auction_date"], "row_index": item["row_index"],
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("mchugh-legacy/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "date_range": [min(item["auction_date"] for item in auctions), max(item["auction_date"] for item in auctions)],
        "auctions_discovered": len(auctions), "auctions_captured": len(states),
        "auctions_reused": reused, "auctions_fetched": len(states) - reused,
        "auctions_complete": sum(bool(state.get("catalogue_complete")) for state in states.values()),
        "appearances_captured": total, "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "archive_evidence": archive_evidence, "auctions": states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "mchugh_legacy_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(auctions):
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
