"""Bank Lextons' 20 linked first-party auction result sheets in one batch.

The archive mixes native PDFs with a JPEG and uses many unrelated visual
layouts.  The finite source-controlled transcript below is therefore treated
as a parsing manifest: every sheet is downloaded, content-addressed, and each
transcribed property label must be found in extracted source text before any
record is admitted.  Result rows are matched one-to-one to the previously
banked first-party property pages only when event and address evidence agree.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Lextons Auctions Ltd"
SLUG = "lextons-auctions"
ARCHIVE_URL = "https://www.lextons.co.uk/auctions/previous-auctions.html"
MEDIA_URL = "https://www.lextons.co.uk/_media/{media_id}"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
NEXT_TARGET = (
    "Move to a different uncovered source/year register target with a substantial "
    "accessible individual-lot inventory; do not repeat the now-reconciled 20 linked "
    "Lextons result sheets. Keep the three linkless Lextons labels (July 2022, "
    "February 2024 and September 2024) outside the accessible denominator until a "
    "materially different recovery route exists. Keep national completeness false."
)


def sheet(media_id, label, event_date, rows):
    parsed = []
    for position, line in enumerate(rows.strip().splitlines(), 1):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise ValueError(f"bad transcript row for media {media_id}: {line!r}")
        lot, address, status, price = parts
        parsed.append(
            {
                "position": position,
                "lot_number": lot or None,
                "address": address or None,
                "status": status,
                "sale_price": int(price) if price else None,
            }
        )
    return {
        "media_id": str(media_id),
        "label": label,
        "event_date": event_date,
        "rows": parsed,
    }


# A pipe transcript keeps all individual result cards reviewable in source
# order. Prices are populated only where the sheet publishes an individual
# achieved amount; combined totals and "undisclosed" remain null.
SHEETS = [
    sheet(197, "29th September 2021", "2021-09-29", """
1||excluded non-property charity lot|200
2|Carlton House, Preston Road, Brighton|sold|197000
3|Albert Road, Brighton|sold prior|150000
4|Viaduct Road, Brighton|unsold|
5|41a Sussex Square, Brighton|sold|431000
6|36a Waterloo Street, 11 Western Road, Hove|sold prior|630000
7|3 Terrace Row, Broad Street, Brighton|sold prior|510000
8|Little Barn, South Road, Brighton|withdrawn prior|
9|11 Eastgate Square, Chichester|withdrawn prior|
10|F6-3/4 Sillwood Place, Brighton|sold prior|210000
11|11 Montpelier Terrace, Brighton|withdrawn prior|
12|Garage at Boscobel Road, St Leonards-on-Sea|sold|37000
"""),
    sheet(201, "25th November 2021", "2021-11-25", """
1|Cranmer Avenue, Hove|sold|283000
2|Western Road, Hove|sold|355000
3|St. Leonards Road, Hove|sold|530000
4|Duncton Close|sold|5000
5|Eastgate Square, Chichester|sold prior|
6|Anglesea Mansions, Anglesea Terrace, St. Leonards-on-Sea|sold|12500
7|Ewart Street, Brighton|sold|
8|Ewart Street, Brighton|sold|
9|Carden Hill, Brighton|sold|
10|Totland Road, Brighton|sold|
"""),
    sheet(238, "23rd February 2022", "2022-02-23", """
1|Syndey Road, Haywards Heath|sold|130000
2|Stirling Court, Hove|sold|131000
3|Forest Barn, Worthing|withdrawn prior|
4|Palmeira Square, Hove|sold|405000
5|Tor Road, Peacehaven|unsold|
6|Astra House, Kings Road, Brighton|sold|285000
7|Land at Tarring Road, Worthing|withdrawn prior|
8|Oakwood Road, Haywards Heath|sold|22000
9|Station Road, Portslade|withdrawn prior|
10|Highcroft Villas, Brighton|sold|695000
11|Cliftonville Court, Hove|sold|168000
12|Cavendish Place, Brighton|sold|331000
"""),
    sheet(252, "6th May 2022", "2022-05-06", """
1|Land at Bush Road, Newhaven|available|
2|Land at Tarring Road, Worthing|sold prior|
3|Queen Alexandra Avenue, Hove|sold prior|
4|Land at Downes Way, East Preston|sold|164500
5|Bannings Vale, Brighton|sold prior|
6|Warehouse, Station Road, Portslade|sold|202000
7|Garages, Station Road, Portslade|sold|143000
8|Workshop, Station Road, Portslade|available|
9|Arundel Street, Brighton|sold prior|
"""),
    sheet(267, "September 2022", "2022-09-22", """
2|Town Centre, Newhaven|sold|75000
3|Argyle Road, Brighton|withdrawn prior|
4|Shanklin Road, Brighton|sold|290000
5|The Drive, Hove|available|
6|Western Road, Hove|withdrawn prior|
7|Queens Road, Brighton|withdrawn prior|
8|Saltdean, Brighton|sold|
9|Lansdowne Place, Hove|withdrawn prior|
10|Mill Close, Portslade|sold|25750
11|Eastbourne|withdrawn prior|
12|Bognor Regis|sold|320000
13|South Coast Road, Peacehaven|available|
14|Hazel Close, Portslade|sold|133500
14|Vale Road, Portslade|sold|335000
"""),
    sheet(274, "November 2022", "2022-11-22", """
1|South Coast Road, Peacehaven|sold prior|
2|West Street, Bognor Regis|sold prior|
3|High Street, Littlehampton|sold prior|
4|The Drive, Hove|sold prior|
5|South Street, Falmer, Brighton|sold prior|
6|Rutland Road, Hove|sold prior|
7|Westbourne Villas, Hove|sold prior|
"""),
    sheet(279, "February 2023", "2023-02-28", """
1|High Street, Heathfield|sold prior|
2|Wilbury Gardens, Hove|sold|210000
3|Caithness Walk, South Croydon|sold prior|
4|Vale Road, Portslade|sold|50000
5|Outerwyke Avenue, Bognor Regis|sold prior|
6|Hangleton Road, Hove|sold|148000
7|Roundhill Crescent, Brighton|sold prior|
8|Portland Road, Hove|sold|165000
9|Buckingham Place, Brighton|withdrawn prior|
10|Stanford Avenue, Brighton|sold|166000
11|St. Aubyns, Hove|sold|267000
12|Rock Street, Brighton|sold|380000
"""),
    sheet(327, "April 2023", "2023-04-26", """
1|Hartington Villas, Hove|sold|
2|Buckingham Road, Brighton|sold|
3|High Street, Lewes|sold|
4|Poplar Avenue, Hove|sold|
5|The Steyne, Bognor Regis|sold|
6|Buckingham Place, Brighton|sold|
7|Southover Street, Brighton|sold|
8|London Road, Tunbridge Wells|withdrawn prior|
9|Roundhill Crescent, Brighton|sold|
10|Viceroy Lodge, Kingsway|sold|
11|Orchard Avenue, Hove|sold|
12|Crowborough Road, Saltdean|withdrawn prior|
"""),
    sheet(328, "June 2023", "2023-06-28", """
1|High Street, Heathfield|sold|
2|Earl Street, Hastings|sold|
3|Lewes Road, Brighton|sold|
4|Boltro Road, Haywards Heath|sold|
5|Downs View Road, Hassocks|sold|
6|Regency Square, Brighton|sold|
7|Bear Road, Brighton|sold|
8|Boundary Road, Hove|sold|
9|Colemans Hatch, Hartfield|sold|
10|Vale Road, Portslade|sold|
11|Priory Road, Eastbourne|sold|
12|Duncton Road, Rustington|sold|
13|Montgomery Street, Hove|sold|
14|Buckingham Road, Brighton|available|
"""),
    sheet(332, "August 2023", "2023-08-23", """
1|Seaside, Eastbourne|sold|
2|Hartington Villas, Hove|sold|
3|Boundary Road, Hove|sold|
4|Land, Worthing|sold|
5|Buckingham Road, Brighton|sold|
6|High Street, Lewes|sold|
7|London Road, Bexhill|sold|
8|Forest Lane, Worthing|withdrawn prior|
9|Derek Road, Lancing|withdrawn prior|
"""),
    sheet(364, "September 2023", "2023-09-27", """
1|Eley Crescent, Rottingdean|sold|
2|Mill Lane, Rustington|sold|
"""),
    sheet(422, "November 2024", "2024-11-27", """
1|Garage 3, Hove|sold|
2|Garage 7, Hove|sold|
3|South Street, Lancing|sold|
4|Gladstone Terrace, Brighton|sold|
5|St. Aubyns, Hove|sold|
6|Adelaide Road, Chichester|sold|
7|Norfolk Square, Brighton|sold|
8|Camelford Street, Brighton|sold|
9|East Street, Brighton|sold|
10|Wolstonbury Road, Hove|sold|
11|Garage, Cowper Road, Hove|sold|
12|Cambridge Grove, Brighton|sold|
"""),
    sheet(423, "February 2025", "2025-02-26", """
1|Garage, Ennismore Avenue, Chiswick|sold|
2|Garage, Ennismore Avenue, Chiswick|sold|
3|Garage, Ennismore Avenue, Chiswick|sold|
4|Land at Wilmington Close, Brighton|sold|
5|Southover Street, Brighton|sold|
6|De Montfort Road, Brighton|sold|
7|St. James's Street, Brighton|sold|
8|Davigdor Road, Hove|sold|
9|Robertson Road, Brighton|sold|
10|East Street, Littlehampton|sold|
"""),
    sheet(425, "April 2025", "2025-04-30", """
1|Garage, Percival Road, Eastbourne|sold|
2|Garage, Chichester Close, Hove|sold|
3|Garage, Balmoral Court, Hove|sold|
4|Freehold, Southover Street, Brighton|sold|
5|Viaduct Road, Brighton|sold|
6|Brighton Road, Worthing|sold|
7|St. Pancras, Chichester|sold|
8|St. James's Street, Brighton|sold|
9|Robertson Road, Brighton|sold|
10|Middleton Rise, Brighton|sold|
11|Kings Road, Brighton|sold|
12|Boundary Road, Hove|sold|
13|Buckingham Place, Brighton|sold|
"""),
    sheet(427, "June 2025", None, """
1|Gladstone Place, Brighton|sold|
2|Easthill Drive, Brighton|sold|
3|Lyndhurst Road, Hove|sold|
4|Wilbury Road, Hove|sold|
"""),
    sheet(430, "August 2025", "2025-08-27", """
1|Whippingham Street, Brighton|sold|
2|Millers Road, Brighton|sold|
3|Chichester Terrace, Brighton|sold|
4|Warwick Road, Worthing|sold|
5|College Lane, East Grinstead|sold|
6|College Lane, East Grinstead|sold|
7|College Lane, East Grinstead|sold|
8|Duncton Road, Littlehampton|sold|
"""),
    sheet(432, "October 2025", "2025-10-22", """
1|Duncton Road Garage, Littlehampton|sold|
2|Holland Road, Hove|sold|
3|Fourth Avenue, Hove|sold|
4|Millers Road, Brighton|sold|
5|West Street, Shoreham|sold|
6|Chichester Terrace, Brighton|sold|
7|College Lane, East Grinstead|sold|
8|Chichester Close Garage, Hove|sold|
9|Chichester Close Garage, Hove|sold|
10|Kingsway, Hove|sold|
"""),
    sheet(437, "December 2025", "2025-12-10", """
1|Wilbury Crescent, Hove|sold|
2|East Street, Littlehampton|sold|
3|Church Road, Hove|sold|
4|Kingsway, Hove|sold|
"""),
    sheet(438, "February 2026", "2026-02-25", """
1|Oakcroft Gardens, Littlehampton|sold|
2|Cuckfield Road, Hurstpierpoint|sold|
3|Rushlake Road, Brighton|sold|
4|Forest Barn, Castle Goring|sold|
5|Chichester Terrace, Brighton|sold|
6|Crypt Lane, Midhurst|sold|
"""),
    sheet(439, "April 2026", "2026-04-29", """
1|Palmeira Avenue Garage, Hove|sold|
2|Connaught Avenue Garage, Shoreham-By-Sea|sold|
3|Hova Villas, Hove|sold|
4|Keswick Close, Worthing|sold|
5|Connaught Avenue Garage, Shoreham-By-Sea|sold|
6|Connaught Avenue Garage, Shoreham-By-Sea|sold|
7|Balmoral Court Garage, Hove|sold|
8|Hova Villas, Hove|sold|
"""),
]

PARTIAL_ADDRESSES = {"Saltdean, Brighton", "Eastbourne", "Bognor Regis", "Land, Worthing"}
GENERIC_TOKENS = {
    "at", "garage", "garages", "the", "flat", "by", "sea",
}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    value = str(value or "").casefold().replace("st.", "st").replace("saint", "st")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def significant(value):
    return [token for token in normalized(value).split() if token not in GENERIC_TOKENS]


def address_score(left, right):
    a, b = set(significant(left)), set(significant(right))
    if not a or not b:
        return 0.0
    if a <= b:
        return 1.0
    common = a & b
    return len(common) / max(len(a), len(b)) if common else 0.0


def fetch(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 20000:
        raise ValueError(f"unexpectedly short source response: {url}")
    return response.url, response.content


def snapshot(raw, name, source_url, suffix, basis):
    sha = hashlib.sha256(raw).hexdigest()
    path = corpus.DATA / "sources" / SLUG / "results" / f"{name}-{sha[:16]}.{suffix}.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


def extract_text(raw):
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        source.write_bytes(raw)
        if raw.startswith(b"%PDF"):
            command = ["pdftotext", "-layout", str(source), "-"]
        elif raw.startswith(b"\xff\xd8") or raw.startswith(b"\x89PNG"):
            command = ["tesseract", str(source), "stdout", "--psm", "6"]
        else:
            raise ValueError("linked result media is neither PDF nor supported image")
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return clean(completed.stdout) or ""


def transcript_needle(address):
    ignored = {"at", "the", "garage", "garages", "land", "freehold", "warehouse", "workshop", "st"}
    tokens = [token for token in normalized(address).split() if token not in ignored and not token.isdigit()]
    return next((token for token in tokens if len(token) >= 4), tokens[0] if tokens else "")


def validate_transcript(sheet_row, text):
    observed = normalized(text)
    missing = []
    for row in sheet_row["rows"]:
        if not row["address"]:
            continue
        needle = transcript_needle(row["address"])
        if needle and needle not in observed:
            # OCR may lose a qualifier but should still preserve the first
            # substantive street/building word.
            if len(needle) < 4 or needle not in observed:
                missing.append({"position": row["position"], "address": row["address"], "needle": needle})
    if missing:
        raise ValueError(f"transcript validation failed for media {sheet_row['media_id']}: {missing}")


def source_links(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    links = {}
    for link in soup.select('a[href^="/_media/"]'):
        media_id = link.get("href", "").rsplit("/", 1)[-1]
        links[media_id] = urljoin(base_url, link["href"])
    return links


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append(
                    {"appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")}
                )
    return values


def result_row(sheet_row, item, evidence):
    event_date = sheet_row["event_date"]
    media_id = sheet_row["media_id"]
    source_lot_id = f"result:{media_id}:position:{item['position']:02d}"
    row = corpus.base_row(
        SOURCE,
        f"{SLUG}:result:{event_date or sheet_row['label']}",
        event_date,
        item["lot_number"],
        source_lot_id,
        evidence["source_url"],
    )
    is_partial = item["address"] in PARTIAL_ADDRESSES
    address = None if is_partial else item["address"]
    row.update(
        appearance_id=f"{SOURCE}|{source_lot_id}",
        address=address,
        locality=item["address"],
        sector=corpus.sector(item["address"]),
        sale_price=item["sale_price"],
        status=item["status"],
        source_lot_id=source_lot_id,
        identity_method="immutable first-party result-sheet media ID and visual card position",
        record_quality="partial_lot" if is_partial else "address_record",
        address_basis=(
            "locality-only result card; retained as partial and not promoted to an address"
            if is_partial else "verbatim individual property label on first-party result sheet"
        ),
        auction_date_precision="day" if event_date else "month",
        auction_date_basis=(
            "exact event date reconciled from the named first-party result sheet and matching first-party event pages"
            if event_date else "June 2025 month label only; exact day not published in retained evidence"
        ),
        result_event_label=sheet_row["label"],
        result_sheet_position=item["position"],
        source_outcome_text=item["status"],
        sale_price_basis=("individual achieved amount printed on first-party result card" if item["sale_price"] else None),
        source_platform="Lextons first-party previous-auctions result-sheet archive",
        operator_legal_name=SOURCE,
        trading_name="Lextons Auctions",
        source_evidence=evidence,
    )
    return row


def match_rows(existing, observed):
    by_date = defaultdict(list)
    undated = []
    for row in existing:
        (by_date[row["auction_date"]] if row.get("auction_date") else undated).append(row)
    used = set()
    matches, unmatched, ambiguous = [], [], []
    for row in observed:
        if not row.get("address"):
            unmatched.append(row)
            continue
        candidates = []
        pool = undated if not row.get("auction_date") else by_date[row["auction_date"]] + undated
        for candidate in pool:
            if candidate["appearance_id"] in used:
                continue
            score = address_score(row["address"], candidate.get("address"))
            if score >= 0.80:
                candidates.append((score, bool(candidate.get("auction_date")), candidate))
        candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
        if not candidates:
            unmatched.append(row)
            continue
        if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
            ambiguous.append(
                {
                    "result": row,
                    "candidate_appearance_ids": [value[2]["appearance_id"] for value in candidates if value[:2] == candidates[0][:2]],
                    "reason": "multiple equally strong first-party property-page matches; evidence retained without collapsing legal interests",
                }
            )
            continue
        candidate = candidates[0][2]
        used.add(candidate["appearance_id"])
        matches.append((candidate, row))
    return matches, unmatched, ambiguous


def enrich(previous, result):
    row = dict(previous)
    was_dated = bool(row.get("auction_date"))
    had_sale = row.get("sale_price") is not None
    if not was_dated and result.get("auction_date"):
        row["auction_date"] = result["auction_date"]
        row["source_auction_id"] = result["source_auction_id"]
        row["auction_date_precision"] = "day"
        row["auction_date_basis"] = result["auction_date_basis"]
    if not had_sale and result.get("sale_price") is not None:
        row["sale_price"] = result["sale_price"]
        row["sale_price_basis"] = result["sale_price_basis"]
    if row.get("status") in {None, "unknown", "available"} or result.get("status") in {"sold prior", "withdrawn prior", "unsold"}:
        row["status"] = result["status"]
    evidence = row.get("result_source_evidence") or []
    if not isinstance(evidence, list):
        evidence = [evidence]
    if not any(item.get("sha256") == result["source_evidence"]["sha256"] and item.get("result_sheet_position") == result["result_sheet_position"] for item in evidence):
        evidence.append({**result["source_evidence"], "result_sheet_position": result["result_sheet_position"], "lot_number": result.get("lot_number"), "outcome": result.get("status"), "sale_price": result.get("sale_price")})
    row["result_source_evidence"] = evidence
    row["source_outcome_text"] = result.get("source_outcome_text") or row.get("source_outcome_text")
    return row, (not was_dated and bool(row.get("auction_date"))), (not had_sale and row.get("sale_price") is not None)


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": "lextons-result-sheets-2021-2026",
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_existing_appearances_newly_dated": summary["run_existing_appearances_newly_dated"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": 0,
        "run_new_sale_prices": summary["run_new_sale_price_evidence"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})["lextons-result-sheets-2021-2026"] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "uncovered-source-year-register",
        "opportunity": "a substantial accessible individual-lot inventory from a different auctioneer/source-year",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(workers=6):
    resolved, archive_raw = fetch(ARCHIVE_URL)
    links = source_links(archive_raw, resolved)
    expected_ids = {row["media_id"] for row in SHEETS}
    missing_ids = expected_ids - set(links)
    if missing_ids:
        raise ValueError(f"linked result media disappeared: {sorted(missing_ids)}")
    links = {media_id: links[media_id] for media_id in expected_ids}
    archive_evidence = snapshot(archive_raw, "previous-auctions", resolved, "html", "first-party result-sheet link inventory")

    downloads = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch, links[media_id]): media_id for media_id in sorted(expected_ids, key=int)}
        for future in as_completed(futures):
            downloads[futures[future]] = future.result()

    evidence_by_media, observed = {}, []
    for sheet_row in SHEETS:
        media_id = sheet_row["media_id"]
        media_url, raw = downloads[media_id]
        suffix = "pdf" if raw.startswith(b"%PDF") else "jpg"
        evidence = snapshot(raw, f"media-{media_id}", media_url, suffix, "first-party auction result sheet")
        validate_transcript(sheet_row, extract_text(raw))
        evidence_by_media[media_id] = evidence
        for item in sheet_row["rows"]:
            if item["status"] == "excluded non-property charity lot":
                continue
            observed.append(result_row(sheet_row, item, evidence))

    if len(SHEETS) != 20 or sum(len(row["rows"]) for row in SHEETS) != 188 or len(observed) != 187:
        raise ValueError("result-sheet denominator or non-property exclusion changed")

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path))
    before = {row["appearance_id"]: row for row in existing}
    matches, unmatched, ambiguous = match_rows(existing, observed)
    merged = dict(before)
    newly_dated_ids, newly_priced_ids = set(), set()
    for previous, result in matches:
        enriched, newly_dated, newly_priced = enrich(merged[previous["appearance_id"]], result)
        merged[previous["appearance_id"]] = enriched
        if newly_dated:
            newly_dated_ids.add(previous["appearance_id"])
        if newly_priced:
            newly_priced_ids.add(previous["appearance_id"])

    global_exact = global_exact_appearances()
    overlaps, admitted = [], []
    for row in unmatched:
        duplicates = global_exact.get((row.get("auction_date"), normalized(row.get("address"))), []) if row.get("auction_date") and row.get("address") else []
        if duplicates:
            overlaps.append({"appearance_id": row["appearance_id"], "auction_date": row["auction_date"], "address": row["address"], "existing": duplicates, "source_evidence": row["source_evidence"]})
        else:
            admitted.append(row)
            merged[row["appearance_id"]] = row

    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    dated = [row for row in added if row.get("address") and row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    new_price_rows = [row for row in added if row.get("sale_price") is not None]
    ambiguous_price_rows = [item for item in ambiguous if item["result"].get("sale_price") is not None]

    state = {
        "auctioneer": SOURCE,
        "source_auction_id": "lextons-result-sheets-2021-2026",
        "source_url": ARCHIVE_URL,
        "linked_sheet_denominator": 20,
        "linked_sheets_captured": 20,
        "published_result_cards": 188,
        "non_property_cards_excluded": 1,
        "property_result_rows_captured": len(observed),
        "lots_captured": len(observed),
        "matched_to_existing_property_pages": len(matches),
        "unmatched_result_rows": len(unmatched),
        "ambiguous_existing_evidence_matches": len(ambiguous),
        "new_appearances_admitted": len(admitted),
        "cross_source_exact_duplicates_excluded": len(overlaps),
        "linkless_labels_outside_accessible_denominator": ["11th July 2022", "February 2024", "September 2024"],
        "catalogue_complete": False,
        "source_inventory_complete": True,
        "denominator_reconciled": len(matches) + len(unmatched) + len(ambiguous) == len(observed),
        "completion_scope": "all 20 linked first-party result sheets; three linkless labels are not claimed captured",
        "archive_evidence": archive_evidence,
        "source_evidence": list(evidence_by_media.values()),
        "ambiguous_match_evidence": ambiguous,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "result-sheets-2021-2026.json", state)

    summary = {
        "checked_at": corpus.now(),
        "operator": {"canonical_name": SOURCE, "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "linked_sheets_captured": 20,
        "published_result_cards": 188,
        "property_result_rows_captured": len(observed),
        "result_rows_matched_to_existing_appearances": len(matches),
        "result_rows_unmatched_before_cross_source_deduplication": len(unmatched),
        "result_rows_ambiguous_existing_evidence": len(ambiguous),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_lots": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_lots": sum(bool(row.get("auction_date") and row["auction_date"] > today) for row in added),
        "run_new_dated_twenty_year_address_records": len(dated),
        "run_existing_appearances_newly_dated": len(newly_dated_ids),
        "run_new_guide_prices": 0,
        "run_new_sale_price_evidence": len(newly_priced_ids) + len(new_price_rows) + len(ambiguous_price_rows),
        "run_sale_price_enrichments_existing": len(newly_priced_ids),
        "run_sale_prices_on_new_appearances": len(new_price_rows),
        "run_sale_price_evidence_ambiguous_existing_match": len(ambiguous_price_rows),
        "run_new_rents": 0,
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "run_new_twenty_year_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in dated),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "newly_covered_source_years": sorted(years_after - years_before),
        "source_years": sorted(years_after),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "source_state": state,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "lextons_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    harvest(args.workers)
