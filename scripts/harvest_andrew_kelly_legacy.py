"""Bank Andrew Kelly Auctions' retained first-party 2011 catalogue batch.

The surviving legacy first-party dates page publishes two complete catalogues
and an event timetable.  The February event also has a complete result sheet.
This manifest-driven runner snapshots every source, admits only contiguous
printed lot inventories, and merges the result evidence into the catalogue
appearance instead of double-counting it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Andrew Kelly Auctions"
SLUG = "andrew-kelly-auctions"
MANIFEST = corpus.ROOT / "config" / "andrew_kelly_legacy_catalogues.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PARSER_VERSION = 1
LOT_LINE = re.compile(
    r"^\s*LOT\s+(?P<lot>\d{1,3})\s+(?P<address>.*?)\s*[.…]{3,}\s*"
    r"(?P<guide>£?\s*[\d,]+(?:\s*[-–]\s*£?\s*[\d,]+)?\s*\+?)\s*$",
    re.I,
)
RESULT_LINE = re.compile(
    r"^\s*(?P<lot>\d{1,3})\s+(?P<address>.*?)\s{2,}"
    r"(?P<bid>-|[\d,]+)\s{2,}(?P<result>SOLD\s+PRIOR|SOLD|AVAILABLE)\s*$",
    re.I,
)
MONEY = re.compile(r"£?\s*([\d,]+(?:\.\d+)?)")
RENT = re.compile(
    r"(?:rental\s+income|rent(?:al)?)[^.\n]{0,80}?"
    r"£\s*([\d,]+(?:\.\d+)?)\s*(?:[-–]\s*£?\s*([\d,]+(?:\.\d+)?)\s*)?"
    r"(p\.?\s*c\.?\s*m\.?|per\s+calendar\s+month|p\.?\s*a\.?|per\s+annum)",
    re.I,
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def load_manifest(path=MANIFEST):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    events = payload.get("events") or []
    if len(events) != int(payload["expected_events"]):
        raise ValueError("manifest event denominator does not reconcile")
    if sum(int(event["expected_lots"]) for event in events) != int(payload["expected_lots"]):
        raise ValueError("manifest lot denominator does not reconcile")
    if len({event["auction_date"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate event dates")
    if len({event["catalogue_url"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate catalogue URLs")
    return payload


def fetch(url):
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=180)
            response.raise_for_status()
            if len(response.content) < 800:
                raise ValueError("source response is unexpectedly short")
            return response.url, response.content
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def pdf_text(raw):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for Andrew Kelly catalogue extraction")
    with tempfile.TemporaryDirectory(prefix="andrew-kelly-") as directory:
        source = Path(directory) / "source.pdf"
        output = Path(directory) / "source.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(output)],
            check=True, capture_output=True, timeout=180,
        )
        text = output.read_text(errors="replace")
    if len(text.strip()) < 100:
        raise ValueError("PDF contains no usable text")
    return text


def snapshot(raw, stem, suffix, basis, source_url):
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{stem}-{sha[:20]}.{suffix}.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    if corpus.digest(gzip.decompress(path.read_bytes())) != sha:
        raise ValueError(f"immutable snapshot digest mismatch at {path}")
    return {
        "source_url": source_url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "source_size_bytes": len(raw),
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "snapshot_encoding": f"gzip-compressed original {suffix.upper()} bytes",
        "basis": basis,
    }


def archive_dates(html, archive_url, events):
    raw = html if isinstance(html, bytes) else html.encode("utf-8")
    decoded = raw.decode("utf-8", "replace")
    soup = BeautifulSoup(decoded, "lxml")
    timetable = clean(soup.get_text(" ", strip=True)) or ""
    linked = {clean(link.get_text(" ", strip=True)) for link in soup.select("a[href]")}
    for event in events:
        parsed = datetime.strptime(event["auction_date"], "%Y-%m-%d").date()
        label = f"{parsed.day}{'th' if 10 < parsed.day % 100 < 14 else {1: 'st', 2: 'nd', 3: 'rd'}.get(parsed.day % 10, 'th')} {parsed:%B %Y}"
        if label not in timetable:
            raise ValueError(f"archive timetable does not publish {label}")
        filename = requests.utils.unquote(event["catalogue_url"].rsplit("/", 1)[-1])
        if filename not in linked:
            raise ValueError(f"archive does not link catalogue {filename}")
    return snapshot(
        raw, "archive", "html",
        "first-party catalogue index and exact auction timetable", archive_url,
    )


def parse_guide(text):
    values = [corpus.money(value) for value in MONEY.findall(text or "")]
    values = [int(value) for value in values if value is not None]
    return (values[0] if values else None, values[1] if len(values) > 1 else None)


def parse_rent(text):
    match = RENT.search(text or "")
    if not match:
        return None, None, None
    low = corpus.money(match.group(1))
    high = corpus.money(match.group(2))
    periodic = match.group(3).casefold()
    multiplier = 12 if "calendar" in periodic or "c" in periodic else 1
    source_text = clean(match.group(0))
    return int(low * multiplier), int(high * multiplier) if high else None, source_text


def sector(address, detail):
    evidence = f"{address or ''} {detail or ''}"
    if re.search(r"\b(?:land|site|plot)\b", address or "", re.I):
        return "land"
    commercial = bool(re.search(
        r"\b(?:commercial|shop|retail|industrial|warehouse|public house|restaurant|takeaway|workshop)\b",
        evidence, re.I,
    ))
    residential = bool(re.search(
        r"\b(?:residential|flats?|apartments?|bungalows?|house|dwellings?|bedrooms?|living accommodation|home)\b",
        re.sub(r"public house", "pub", evidence, flags=re.I), re.I,
    ))
    # "Potential residential conversion" does not make a current public
    # house mixed-use. Require present physical residential accommodation for
    # a commercial lot to be classified mixed-use.
    present_residential = bool(re.search(
        r"\b(?:flats?|apartments?|bungalows?|dwellings?|bedrooms?|living accommodation)\b",
        evidence, re.I,
    ))
    if commercial and present_residential:
        return "mixed-use"
    if commercial:
        return "commercial"
    if residential:
        return "residential"
    return "unknown"


def parse_catalogue(text, expected):
    rows = []
    for line in text.splitlines():
        match = LOT_LINE.match(line)
        if not match:
            continue
        low, high = parse_guide(match.group("guide"))
        rows.append({
            "lot_number": match.group("lot"),
            "address": clean(match.group("address")),
            "guide_price": low,
            "guide_price_high": high,
            "source_guide_text": clean(match.group("guide")),
        })
    labels = [int(row["lot_number"]) for row in rows]
    if labels != list(range(1, expected + 1)):
        raise ValueError(f"catalogue inventory yielded {labels}; expected 1..{expected}")
    # The legacy PDF stores two catalogue panels on some physical pages.  A
    # printed "Guide Price:" begins each property panel more reliably than a
    # form-feed, so split on those markers and assert one panel per lot.
    markers = list(re.finditer(r"Guide\s+Price\s*:", text, re.I))
    detail_panels = []
    for index, marker in enumerate(markers):
        candidates = [markers[index + 1].start() if index + 1 < len(markers) else len(text)]
        page_end = text.find("\f", marker.start())
        if page_end >= 0:
            candidates.append(page_end)
        detail_panels.append(text[marker.start() : min(candidates)])
    if len(detail_panels) != expected:
        raise ValueError(f"catalogue yielded {len(detail_panels)} detail panels; expected {expected}")
    for row, panel in zip(rows, detail_panels):
        row["detail_text"] = clean(panel)
        row["sector"] = sector(row["address"], panel)
        annual, annual_high, rent_text = parse_rent(panel)
        row.update(annual_rent=annual, annual_rent_high=annual_high, rent_text=rent_text)
    return rows


def parse_results(text, expected):
    rows = []
    for line in text.splitlines():
        match = RESULT_LINE.match(line)
        if not match:
            continue
        bid = corpus.money(match.group("bid"))
        result = match.group("result").upper()
        rows.append({
            "lot_number": match.group("lot"),
            "result_address": clean(match.group("address")),
            "status": {"SOLD": "sold", "SOLD PRIOR": "sold_prior", "AVAILABLE": "available"}[result],
            "sale_price": int(bid) if bid is not None and result.startswith("SOLD") else None,
            "source_result_text": result,
            "source_bid_text": clean(match.group("bid")),
        })
    labels = [int(row["lot_number"]) for row in rows]
    if labels != list(range(1, expected + 1)):
        raise ValueError(f"result inventory yielded {labels}; expected 1..{expected}")
    return {row["lot_number"]: row for row in rows}


def materialize(event, rows, catalogue_evidence, archive_evidence, result_rows=None, result_evidence=None):
    auction_date = event["auction_date"]
    auction_id = f"{SLUG}:{auction_date}"
    output = []
    for position, item in enumerate(rows, 1):
        lot = item["lot_number"]
        result = (result_rows or {}).get(lot)
        source_lot_id = f"lot:{lot}"
        row = corpus.base_row(SOURCE, auction_id, auction_date, lot, source_lot_id, event["catalogue_url"])
        postcode = corpus.PC.search(item["address"] or "")
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
            address=item["address"], postcode=postcode.group().upper() if postcode else None,
            locality=item["address"], sector=item["sector"],
            guide_price=item["guide_price"], guide_price_high=item["guide_price_high"],
            sale_price=result["sale_price"] if result else None,
            status=result["status"] if result else "unknown",
            annual_rent=item["annual_rent"], rent_text=item["rent_text"],
            property_id=None,
            identity_method="first_party_exact_event_date_catalogue_lot_number_and_address",
            record_quality="address_record", source_position=position,
            source_guide_text=item["source_guide_text"],
            source_result_address=result["result_address"] if result else None,
            source_result_text=result["source_result_text"] if result else None,
            source_bid_text=result["source_bid_text"] if result else None,
            auction_date_precision="day",
            auction_date_basis="exact date in first-party auction timetable",
            source_platform="Andrew Kelly Auctions retained first-party catalogue PDF",
            trading_name=SOURCE,
            source_evidence=[archive_evidence, catalogue_evidence] + ([result_evidence] if result_evidence else []),
        )
        if item["annual_rent_high"] is not None:
            row["annual_rent_high"] = item["annual_rent_high"]
        output.append(row)
    state = {
        "auctioneer": SOURCE, "trading_name": SOURCE,
        "source_auction_id": auction_id, "auction_date": auction_date,
        "source_url": event["catalogue_url"], "result_url": event.get("result_url"),
        "published_lots": int(event["expected_lots"]), "lots_captured": len(output),
        "catalogue_complete": True, "source_rows_complete": True,
        "denominator_reconciled": True,
        "denominator_basis": "contiguous 1..N printed catalogue lot inventory",
        "guides_captured": sum(row["guide_price"] is not None for row in output),
        "sale_prices_captured": sum(row["sale_price"] is not None for row in output),
        "published_outcomes_captured": sum(row["status"] != "unknown" for row in output),
        "rents_captured": sum(row["annual_rent"] is not None for row in output),
        "source_evidence": [archive_evidence, catalogue_evidence] + ([result_evidence] if result_evidence else []),
        "errors": [], "checked_at": corpus.now(),
    }
    return state, output


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer"),
                })
    return values


def harvest():
    manifest = load_manifest()
    archive_url, archive_raw = fetch(manifest["archive_url"])
    archive_evidence = archive_dates(archive_raw, archive_url, manifest["events"])
    all_rows, states = [], []
    for event in manifest["events"]:
        catalogue_url, catalogue_raw = fetch(event["catalogue_url"])
        if not catalogue_raw.startswith(b"%PDF-"):
            raise ValueError("catalogue URL did not return a PDF")
        catalogue_evidence = snapshot(
            catalogue_raw, f"catalogue-{event['auction_date']}", "pdf",
            "complete first-party property-auction catalogue PDF", catalogue_url,
        )
        rows = parse_catalogue(pdf_text(catalogue_raw), int(event["expected_lots"]))
        result_rows = result_evidence = None
        if event.get("result_url"):
            result_url, result_raw = fetch(event["result_url"])
            if not result_raw.startswith(b"%PDF-"):
                raise ValueError("result URL did not return a PDF")
            result_evidence = snapshot(
                result_raw, f"result-{event['auction_date']}", "pdf",
                "complete first-party individual-lot auction result PDF", result_url,
            )
            result_rows = parse_results(pdf_text(result_raw), int(event["expected_lots"]))
        state, materialized = materialize(
            event, rows, catalogue_evidence, archive_evidence, result_rows, result_evidence,
        )
        states.append(state)
        all_rows.extend(materialized)

    if len(all_rows) != int(manifest["expected_lots"]):
        raise ValueError("batch lot denominator does not reconcile")
    exact_global = global_exact_appearances()
    exclusions, admissible = [], []
    for row in all_rows:
        matches = exact_global.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            exclusions.append({
                "auction_date": row["auction_date"], "address": row["address"],
                "andrew_kelly_appearance_id": row["appearance_id"], "existing": matches,
            })
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    summary_path = corpus.DATA / "andrew_kelly_legacy_collection.json"
    previous_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    if previous_summary and "batch_baseline_appearance_ids" in previous_summary:
        baseline_ids = set(previous_summary["batch_baseline_appearance_ids"])
    elif previous_summary and previous_summary.get("appearances_captured") == len(existing):
        # Preserve the initial successful batch delta across parser-enrichment
        # retries made before publication.
        baseline_ids = set()
    else:
        baseline_ids = {row["appearance_id"] for row in existing}
    existing_by_id = {row["appearance_id"]: row for row in existing}
    merged = dict(existing_by_id)
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    persisted = list(corpus.iter_rows(path))
    if {row["appearance_id"] for row in persisted} != set(merged):
        raise RuntimeError("Andrew Kelly rows did not persist exactly")
    new_rows = [row for key, row in merged.items() if key not in baseline_ids]

    for state in states:
        state["exact_global_overlaps_excluded"] = sum(
            item["andrew_kelly_appearance_id"].startswith(f"{SOURCE}|{state['source_auction_id']}|")
            for item in exclusions
        )
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)

    today_value = date.today()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    today = today_value.isoformat()
    historical_new = [row for row in new_rows if cutoff <= row["auction_date"] <= today]
    summary = {
        "checked_at": corpus.now(), "auctioneer": SOURCE,
        "operator_legal_name": "ANDREW KELLY & ASSOCIATES LIMITED",
        "trading_name_not_counted_as_separate_auctioneer": "Andrew Kelly Auctions",
        "branches_not_counted_as_separate_auctioneers": True,
        "parser_version": PARSER_VERSION, "source_url": archive_url,
        "catalogue_events": len(manifest["events"]), "visible_source_rows": len(all_rows),
        "appearances_captured": len(merged), "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical_new),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_new_undated": sum(not row.get("auction_date") for row in new_rows),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(exclusions),
        "exact_global_overlap_exclusions": exclusions,
        "new_source_years": sorted({int(row["auction_date"][:4]) for row in new_rows}),
        "source_years_visible": [2011], "date_range": ["2011-02-23", "2011-04-20"],
        "by_status": dict(Counter(row["status"] for row in merged.values())),
        "by_sector": dict(Counter(row["sector"] for row in merged.values())),
        "batch_baseline_appearance_ids": sorted(baseline_ids),
        "completion_scope": "all 21 contiguous printed lots in both retained first-party catalogues; all 12 February result rows merged without duplicate appearances",
        "failures": [], "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "andrew_kelly_legacy_collection.json", summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    harvest()
