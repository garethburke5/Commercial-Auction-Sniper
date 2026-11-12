"""Bank Venmore Auctions' accessible retained first-party catalogue PDFs.

The public past-auctions HTML is protected from non-browser clients, while its
immutable catalogue PDF links remain directly accessible.  This reusable,
manifest-driven runner parses only the printed contiguous order-of-lots table,
so stale template text elsewhere in a catalogue cannot create appearances.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Venmore Auctions"
SLUG = "venmore-auctions"
ARCHIVE = "https://www.venmoreauctions.co.uk/Past-Auctions"
MANIFEST = corpus.ROOT / "config" / "venmore_catalogues.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MAX_SNAPSHOT_PART_BYTES = 700_000
ORDER_HEADING = re.compile(r"order\s+of\s+lots", re.I)
ORDER_END = re.compile(
    r"(?:CLICK\s+PHOTO\s+TO\s+VIEW\s+PROPERTIES|CLICK\s+HERE\s+TO\s+REGISTER|"
    r"AUCTION\s+ON\s+\d|REGISTER\s+TO\s+BID|Contact\s+Venmore\s+Auctions)",
    re.I,
)
MONEY = re.compile(r"£?\s*([\d,]+(?:\.\d+)?)")
ORDER_VALUE = re.compile(
    r"(?P<value>(?:£\s*[\d,]+(?:\.\d+)?(?:\s*[-–]\s*£?\s*[\d,]+(?:\.\d+)?)?\s*(?:PLUS\s*)?\*?|"
    r"[\d,]+(?:\.\d+)?\s+PLUS\s*\*|"
    r"SOLD\s+PRIOR\s*\*?|WITHDRAWN\s*\*?|POSTPONED\s*\*?))\s*-?\s*$",
    re.I,
)
POSTCODE = corpus.PC
RENT_PCM = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?c\.?m\.?|per\s+calendar\s+month)", re.I)
RENT_PA = re.compile(r"£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?\s*a\.?|per\s+annum)", re.I)
NEXT_TARGET = (
    "Recover Venmore's surviving 2023 catalogues (11 January, 8 February, 8 March, 12 April, "
    "24 May, 6 September, 25 October and 6 December) plus 7 February 2024 through the same "
    "retained-userfiles batch runner, then continue into the 2022 archive. Reconcile the four "
    "known 2025-2026 online-only late lots through a materially different source route. "
    "National completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \xa0-") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def load_manifest(path=MANIFEST):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    events = payload.get("events") or []
    if len(events) != int(payload["expected_catalogues"]):
        raise ValueError("manifest catalogue denominator does not reconcile")
    if sum(int(event["expected_lots"]) for event in events) != int(payload["expected_lots"]):
        raise ValueError("manifest lot denominator does not reconcile")
    if len({event["source_url"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate source URLs")
    if len({event["auction_date"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate event dates")
    return payload


def fetch(url):
    response = None
    for attempt in range(5):
        response = requests.get(url, headers=HEADERS, timeout=120)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("catalogue URL did not return a PDF")
    return response.url, response.content


def pdf_text(raw):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for Venmore catalogue extraction")
    with tempfile.TemporaryDirectory(prefix="venmore-catalogue-") as directory:
        source = Path(directory) / "catalogue.pdf"
        output = Path(directory) / "catalogue.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(output)],
            check=True, capture_output=True, timeout=180,
        )
        text = output.read_text(errors="replace").replace("\x03", "")
    if len(text.strip()) < 500:
        raise ValueError("catalogue PDF contains no usable text")
    return text


def parse_price(raw):
    values = [corpus.money(value) for value in MONEY.findall(raw or "")]
    values = [value for value in values if value is not None]
    return values[0] if values else None, values[1] if len(values) > 1 else None


def parse_order_rows(text, expected):
    heading = ORDER_HEADING.search(text)
    if not heading:
        raise ValueError("catalogue has no printed order-of-lots table")
    tail = text[heading.start():]
    end = ORDER_END.search(tail)
    table = tail[:end.start()] if end else tail
    rows = []
    current = None
    guide_column = None
    for raw_line in table.splitlines():
        line = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", raw_line)
        line = re.sub(r"(?<=\d)\s*,\s*(?=\d)", ",", line)
        if re.search(r"Lot\s+Address", line, re.I) and re.search(r"Guide\s*Price", line, re.I):
            guide_column = re.search(r"Guide\s*Price", line, re.I).start()
            continue
        if guide_column is None or not clean(line):
            continue
        if current and int(current["lot_number"]) == expected and re.match(r"^\s*\d", line):
            rows.append(current)
            current = None
            break
        next_label = 1 if current is None else int(current["lot_number"]) + 1
        match = re.match(r"^\s*(\d{1,3})\s+", line)
        if match and int(match.group(1)) != next_label:
            match = None
        if not match:
            compact = re.match(rf"^\s*({next_label})(?=\S)", line)
            if compact and ORDER_VALUE.search(line):
                match = compact
        if match:
            if current:
                rows.append(current)
            body = line[match.end():]
            value_match = ORDER_VALUE.search(body)
            current = {
                "lot_number": match.group(1),
                "address_parts": [clean(body[:value_match.start()] if value_match else body)],
                "order_value_parts": [clean(value_match.group("value")) if value_match else None],
            }
            # Some catalogues begin the first detailed lot page immediately
            # after the final order row without a recognised section heading.
            # Once the asserted final label and its price/outcome are present,
            # the inventory is complete; do not let detailed-page text bleed
            # into that final address.
            if int(match.group(1)) == expected and value_match:
                rows.append(current)
                current = None
                break
            continue
        if not current:
            continue
        value_match = ORDER_VALUE.search(line)
        if value_match:
            left, right = clean(line[:value_match.start()]), clean(value_match.group("value"))
        else:
            left = clean(re.sub(r"\s+-\s*$", "", line[:guide_column]))
            right = None
        if left and not re.search(r"(?:CLICK ON ADDRESS|Lot Address|Order of Lots)", left, re.I):
            current["address_parts"].append(left)
        if right and right != "-":
            current["order_value_parts"].append(right)
    if current:
        rows.append(current)

    parsed = []
    for row in rows:
        address = clean(" ".join(filter(None, row["address_parts"])))
        order_value = clean(" ".join(filter(None, row["order_value_parts"])))
        status = "unknown"
        if re.search(r"sold\s+prior", order_value or "", re.I):
            status = "sold_prior"
        elif re.search(r"withdrawn", order_value or "", re.I):
            status = "withdrawn"
        elif re.search(r"postponed", order_value or "", re.I):
            status = "postponed"
        low, high = parse_price(order_value if status == "unknown" else None)
        parsed.append({
            "lot_number": row["lot_number"],
            "address": address,
            "status": status,
            "source_order_value": order_value,
            "guide_price": low,
            "guide_price_high": high,
        })
    labels = [int(row["lot_number"]) for row in parsed]
    if len(parsed) != expected or labels != list(range(1, expected + 1)):
        raise ValueError(f"order-of-lots table yielded {len(parsed)} rows {labels[:3]}..{labels[-3:]}; expected 1..{expected}")
    if any(not row["address"] for row in parsed):
        raise ValueError("order-of-lots table contains a blank address")
    return parsed


def validate_date(text, config):
    auction_date = config["auction_date"]
    year, month, day = map(int, auction_date.split("-"))
    month_name = date(year, month, day).strftime("%B")
    front = text[:20000]
    exact = re.search(rf"\b0?{day}(?:st|nd|rd|th)?\s+{month_name}\s+{year}\b", front, re.I)
    # Venmore's covers print the event day/month and the catalogue year's
    # auction calendar as separate elements.  Require both when the year is
    # not repeated inline; this still rejects a mismatched dated catalogue.
    split_cover = (
        re.search(rf"\b0?{day}(?:st|nd|rd|th)?\s+{month_name}\b", front, re.I)
        and re.search(rf"\b{year}\s+AUCTION\s+DATES\b", front, re.I)
    )
    if exact or split_cover:
        return "exact date printed in first-party catalogue"
    # Later catalogues print only the catalogue month on the cover because the
    # current event is omitted from the subsequent-auction calendar.  Admit
    # that layout only when the manifest also retains the exact first-party
    # event page; the date is never inferred from the month alone.
    month_cover = re.search(rf"\b{month_name}\s+CATALOGUE\b", front, re.I)
    if month_cover and config.get("event_url"):
        return (
            "exact date on first-party event page; matching month printed on "
            "first-party catalogue cover"
        )
    raise ValueError(f"exact auction date {auction_date} is absent from catalogue front matter")


def context_for_address(text, address):
    tokens = [re.escape(token) for token in re.findall(r"[A-Za-z0-9&]+", address) if len(token) > 1]
    if len(tokens) < 3:
        return ""
    pattern = re.compile(r"[^A-Za-z0-9]+".join(tokens), re.I)
    matches = list(pattern.finditer(text))
    marker = matches[-1] if matches else None
    if not marker:
        return ""
    candidate = text[marker.start():]
    boundary = re.search(r"(?m)\f|^\s*Lot\s*$", candidate[10:])
    end = 10 + boundary.start() if boundary else 2600
    return candidate[:min(end, 2600)]


def sector_and_rent(address, context):
    evidence = f"{address} {context}"
    residential = bool(re.search(r"\b(?:flat|apartment|house|bungalow|bedroom|terrace|cottage|hmo|dwelling)\b", evidence, re.I))
    commercial = bool(re.search(r"\b(?:commercial|retail|shop|office|industrial|warehouse|restaurant|takeaway|hotel|public house|workshop)\b", evidence, re.I))
    if residential and commercial:
        sector = "mixed-use"
    elif commercial:
        sector = "commercial"
    elif re.search(r"\b(?:land|site|plot)\b", address, re.I):
        sector = "land"
    elif residential:
        sector = "residential"
    else:
        sector = "unknown"
    rents = []
    for value in RENT_PA.findall(context):
        amount = corpus.money(value)
        if amount is not None:
            rents.append((amount, f"£{int(amount):,} per annum"))
    for value in RENT_PCM.findall(context):
        amount = corpus.money(value)
        if amount is not None:
            rents.append((amount * 12, f"£{int(amount):,} per calendar month"))
    return sector, rents[0] if rents else (None, None)


def save_snapshot(auction_date, raw, sha):
    base = corpus.DATA / "sources" / SLUG / f"catalogue-{auction_date}-{sha[:20]}.pdf.gz"
    compressed = gzip.compress(raw, mtime=0)
    paths = [base] if len(compressed) <= MAX_SNAPSHOT_PART_BYTES else [
        Path(f"{base}.part-{index // MAX_SNAPSHOT_PART_BYTES + 1:03d}")
        for index in range(0, len(compressed), MAX_SNAPSHOT_PART_BYTES)
    ]
    if not all(path.exists() for path in paths):
        if any(path.exists() for path in paths):
            raise ValueError(f"incomplete immutable snapshot at {base}")
        for index, path in enumerate(paths):
            start = index * MAX_SNAPSHOT_PART_BYTES
            corpus.atomic(path, compressed[start:start + MAX_SNAPSHOT_PART_BYTES])
    if corpus.digest(gzip.decompress(b"".join(path.read_bytes() for path in paths))) != sha:
        raise ValueError(f"immutable snapshot digest mismatch at {base}")
    if len(paths) == 1:
        return {"snapshot_path": str(paths[0].relative_to(corpus.ROOT))}
    return {
        "snapshot_parts": [str(path.relative_to(corpus.ROOT)) for path in paths],
        "snapshot_encoding": "concatenate parts, then gzip-decompress to recover source PDF",
    }


def retained_snapshot(auction_date):
    directory = corpus.DATA / "sources" / SLUG
    complete = sorted(directory.glob(f"catalogue-{auction_date}-*.pdf.gz"))
    if complete:
        path = complete[-1]
        return gzip.decompress(path.read_bytes()), {"snapshot_path": str(path.relative_to(corpus.ROOT))}
    parts = sorted(directory.glob(f"catalogue-{auction_date}-*.pdf.gz.part-*"))
    if not parts:
        return None
    prefixes = sorted({str(path).rsplit(".part-", 1)[0] for path in parts})
    selected = [path for path in parts if str(path).startswith(prefixes[-1] + ".part-")]
    return gzip.decompress(b"".join(path.read_bytes() for path in selected)), {
        "snapshot_parts": [str(path.relative_to(corpus.ROOT)) for path in selected],
        "snapshot_encoding": "concatenate parts, then gzip-decompress to recover source PDF",
    }


def materialize_event(config, source_url, evidence, text):
    date_basis = validate_date(text, config)
    parsed = parse_order_rows(text, int(config["expected_lots"]))
    auction_id = f"{SLUG}:{config['auction_date']}"
    rows = []
    for position, item in enumerate(parsed, 1):
        context = context_for_address(text, item["address"])
        sector, (annual_rent, rent_text) = sector_and_rent(item["address"], context)
        source_lot_id = f"lot:{item['lot_number']}"
        row = corpus.base_row(SOURCE, auction_id, config["auction_date"], item["lot_number"], source_lot_id, source_url)
        postcode = POSTCODE.search(item["address"])
        row.update(
            appearance_id=f"{SOURCE}|{auction_id}|{source_lot_id}",
            address=item["address"], postcode=postcode.group().upper() if postcode else None,
            locality=item["address"], sector=sector, property_type=None,
            status=item["status"], guide_price=item["guide_price"],
            guide_price_high=item["guide_price_high"], sale_price=None,
            annual_rent=annual_rent, rent_text=rent_text,
            identity_method="first_party_exact_event_date_order_of_lots_number_and_address",
            record_quality="address_record", source_position=position,
            source_order_value=item["source_order_value"], source_event_url=source_url,
            auction_date_precision="day",
            auction_date_basis=date_basis,
            source_platform="Venmore Auctions retained first-party catalogue PDF",
            trading_name=SOURCE, source_evidence=evidence,
        )
        rows.append(row)
    online_lots = int(config.get("online_listed_lots", len(rows)))
    online_gap = max(0, online_lots - len(rows))
    state = {
        "auctioneer": SOURCE, "trading_name": SOURCE,
        "source_auction_id": auction_id, "auction_date": config["auction_date"],
        "auction_date_precision": "day", "source_url": source_url,
        "published_lots": online_lots, "catalogue_published_lots": len(rows),
        "lots_captured": len(rows), "online_listing_gap": online_gap,
        "guides_captured": sum(row["guide_price"] is not None for row in rows),
        "rents_captured": sum(row["annual_rent"] is not None for row in rows),
        "published_outcomes_captured": sum(row["status"] != "unknown" for row in rows),
        "catalogue_complete": True, "source_rows_complete": online_gap == 0,
        "denominator_reconciled": online_gap == 0,
        "denominator_basis": (
            "first-party online property count compared with contiguous numbered "
            "order-of-lots table in complete first-party PDF"
            if "online_listed_lots" in config else
            "contiguous numbered order-of-lots table in complete first-party PDF; "
            "historical live grid no longer publishes a usable property denominator"
        ),
        "completion_scope": (
            "every numbered row in the printed order-of-lots table"
            if online_gap == 0 else
            f"every numbered catalogue row; {online_gap} later online-listed lot(s) absent from the PDF"
        ),
        "source_event_url": config.get("event_url"),
        "auction_date_basis": date_basis,
        "source_evidence": evidence, "errors": [], "checked_at": corpus.now(),
    }
    return state, rows


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


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": (
            "completed"
            if not summary["failures"] and not summary["unreconciled_online_listing_gap"]
            else "partial"
        ),
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload["runs"] = [
        run for run in payload.setdefault("runs", [])
        if run.get("source") != SLUG
    ] + [checkpoint]
    payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "venmore-auctions-2023-2024-retained-catalogues",
        "auctioneer": SOURCE,
        "source_format": "first-party retained catalogue PDFs",
        "opportunity": (
            "batch eight missing 2023 catalogue dates and 7 February 2024 through the "
            "existing Venmore runner, then continue into the surviving 2022 archive"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    manifest = load_manifest()
    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    summary_path = corpus.DATA / "venmore_catalogues_collection.json"
    previous_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    configured_baseline_dates = set(manifest.get("baseline_event_dates") or [])
    if configured_baseline_dates:
        baseline_ids = {
            row["appearance_id"] for row in existing
            if row.get("auction_date") in configured_baseline_dates
        }
    elif previous_summary and "batch_baseline_appearance_ids" in previous_summary:
        baseline_ids = set(previous_summary["batch_baseline_appearance_ids"])
    elif previous_summary and previous_summary.get("run_new_appearances") == len(existing):
        # Preserve the first successful batch's baseline while correcting or
        # enriching its parser fields on a retry.
        baseline_ids = set()
    else:
        baseline_ids = {row["appearance_id"] for row in existing}
    states, run_rows, failures = {}, [], []
    for position, config in enumerate(manifest["events"], 1):
        try:
            retained = retained_snapshot(config["auction_date"])
            if retained:
                raw, snapshot_fields = retained
                source_url = config["source_url"]
            else:
                source_url, raw = fetch(config["source_url"])
            sha, retrieved_at = corpus.digest(raw), corpus.now()
            if not retained:
                snapshot_fields = save_snapshot(config["auction_date"], raw, sha)
            evidence = {
                "source_url": source_url, "retrieved_at": retrieved_at, "sha256": sha,
                "basis": "complete first-party exact-dated property-auction catalogue PDF",
                "archive_url": ARCHIVE, "event_url": config.get("event_url"),
                **snapshot_fields,
            }
            state, rows = materialize_event(config, source_url, evidence, pdf_text(raw))
            states[state["auction_date"]] = state
            corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)
            run_rows.extend(rows)
            print("VENMORE", position, "/", len(manifest["events"]), "catalogues", len(run_rows), "lots", flush=True)
        except Exception as exc:
            failures.append({"auction_date": config["auction_date"], "source_url": config["source_url"], "error": f"{type(exc).__name__}: {exc}"[:500]})

    global_exact = global_exact_appearances()
    existing_ids = {row["appearance_id"] for row in existing}
    overlaps, admissible = [], []
    for row in run_rows:
        if row["appearance_id"] in existing_ids:
            admissible.append(row)
            continue
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({"auction_date": row["auction_date"], "lot_number": row["lot_number"], "address": row["address"], "existing": matches})
        else:
            admissible.append(row)
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in baseline_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    in_window = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {
        row["auction_date"][:4] for row in existing
        if row.get("auction_date") and row["appearance_id"] in baseline_ids
    }
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(), "auctioneer": SOURCE, "source_url": ARCHIVE,
        "catalogue_pdfs_in_batch": len(manifest["events"]),
        "catalogue_pdfs_captured": len(states),
        "published_property_rows_reconciled": len(run_rows),
        "online_listed_property_rows": sum(
            int(event.get("online_listed_lots", event["expected_lots"]))
            for event in manifest["events"]
        ),
        "unreconciled_online_listing_gap": sum(
            int(state.get("online_listing_gap", 0)) for state in states.values()
        ),
        "appearances_captured": total,
        "batch_baseline_appearance_ids": sorted(baseline_ids),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": len(in_window),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum(bool(row.get("auction_date") and row["auction_date"] > today) for row in added),
        "run_new_commercial": sum(row.get("sector") == "commercial" for row in added),
        "run_new_mixed_use": sum(row.get("sector") == "mixed-use" for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "auctions": states, "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "live_archive_route_blocker": (
            "historical event pages remain reachable, but most older live grids have "
            "been cleared to zero properties; retained first-party userfiles PDFs "
            "preserve the individual printed rows"
        ),
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "venmore_catalogues_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or len(states) != len(manifest["events"]) or len(run_rows) != int(manifest["expected_lots"]):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    harvest()
