"""Bank Bruton Knowles' surviving public-auction appearances in one batch.

The source has no single retained catalogue index.  This manifest-driven
runner therefore combines the accessible first-party Bruton Knowles article
and particulars with exact joint-agent lot pages/catalogues.  Every raw source
is snapshotted, every material fact is checked against extracted source text,
and exact date/address overlaps are excluded before growth is claimed.
"""
from __future__ import annotations

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

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Bruton Knowles"
SLUG = "bruton-knowles"
MANIFEST = corpus.ROOT / "config" / "bruton_knowles_archive.json"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PARSER_VERSION = 1


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def load_manifest(path=MANIFEST):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    events = payload.get("events") or []
    sources = payload.get("sources") or {}
    if len(events) != int(payload["expected_events"]):
        raise ValueError("manifest event denominator does not reconcile")
    if sum(int(event["expected_lots"]) for event in events) != int(payload["expected_lots"]):
        raise ValueError("manifest lot denominator does not reconcile")
    if sum(len(event.get("lots") or []) for event in events) != int(payload["expected_lots"]):
        raise ValueError("manifest row denominator does not reconcile")
    if len({event["auction_date"] for event in events}) != len(events):
        raise ValueError("manifest contains duplicate event dates")
    for event in events:
        if len(event["lots"]) != int(event["expected_lots"]):
            raise ValueError(f"event {event['auction_date']} lot denominator does not reconcile")
        unknown = set(event["source_keys"]) - set(sources)
        if unknown:
            raise ValueError(f"event references unknown sources: {sorted(unknown)}")
        for lot in event["lots"]:
            if set(lot.get("checks") or {}) - set(event["source_keys"]):
                raise ValueError("lot check references a source outside its event")
    return payload


def fetch(url):
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=180)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("source response is unexpectedly short")
            return response.url, response.content
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def snapshot(raw, key, kind, basis, source_url):
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{key}-{sha[:20]}.{kind}.gz"
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
        "snapshot_encoding": f"gzip-compressed original {kind.upper()} bytes",
        "basis": basis,
    }


def pdf_text(raw, pages=None):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required")
    with tempfile.TemporaryDirectory(prefix="bruton-knowles-") as directory:
        source = Path(directory) / "source.pdf"
        text_path = Path(directory) / "source.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(text_path)],
            check=True, capture_output=True, timeout=240,
        )
        output = text_path.read_text(errors="replace")
        if pages:
            if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
                raise RuntimeError("pdftoppm and tesseract are required for scanned source evidence")
            for page in pages:
                stem = Path(directory) / f"page-{page}"
                subprocess.run(
                    ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-png", "-r", "180", str(source), str(stem)],
                    check=True, capture_output=True, timeout=240,
                )
                result = subprocess.run(
                    ["tesseract", str(stem) + ".png", "stdout"],
                    check=True, capture_output=True, timeout=240,
                )
                output += "\n" + result.stdout.decode("utf-8", "replace")
    if len(output.strip()) < 100:
        raise ValueError("PDF contains no usable text")
    return output


def extracted_text(raw, spec):
    if spec["kind"] == "html":
        return BeautifulSoup(raw.decode("utf-8", "replace"), "lxml").get_text(" ", strip=True)
    if spec["kind"] == "pdf":
        return pdf_text(raw, spec.get("ocr_pages"))
    raise ValueError(f"unsupported source kind {spec['kind']}")


def assert_term(text, term, key):
    wanted = normalized(term)
    observed = normalized(text)
    if wanted not in observed:
        raise ValueError(f"source {key} does not contain required evidence term: {term}")


def validate_lot(lot, source_texts):
    checks = lot.get("checks") or {}
    if not checks:
        raise ValueError("lot has no source checks")
    for key, terms in checks.items():
        for term in terms:
            assert_term(source_texts[key], term, key)


def materialize(event, lot, evidence_by_key, position):
    auction_id = f"{SLUG}:{event['auction_date']}"
    original_url = lot.get("original_url") or evidence_by_key[event["source_keys"][0]]["source_url"]
    row = corpus.base_row(
        SOURCE, auction_id, event["auction_date"], lot.get("lot_number"),
        lot["source_lot_id"], original_url,
    )
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|{lot['source_lot_id']}",
        address=lot["address"], postcode=lot.get("postcode"), locality=lot["address"],
        sector=lot["sector"], property_type=lot.get("property_type"), tenure=lot.get("tenure"),
        guide_price=lot.get("guide_price"), guide_price_high=lot.get("guide_price_high"),
        sale_price=lot.get("sale_price"), status=lot.get("status") or "unknown",
        annual_rent=lot.get("annual_rent"), rent_text=lot.get("rent_text"),
        description=lot.get("property_type"), property_id=None,
        identity_method="exact_event_date_source_lot_identity_and_address",
        record_quality="address_record", source_position=position,
        source_guide_text=lot.get("source_guide_text"),
        source_result_text=lot.get("source_result_text"),
        auction_date_precision="day",
        auction_date_basis="exact date published by the first-party auction source",
        source_platform=event["platform"], trading_name=SOURCE,
        joint_platform_not_counted_as_separate_bruton_auctioneer=event["platform"] != SOURCE,
        source_evidence=[evidence_by_key[key] for key in event["source_keys"]],
    )
    return row


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


def global_rows_by_id():
    values = {}
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            values[row["appearance_id"]] = (path, row)
    return values


def merge_related_evidence(visible_rows, manifest_lots, evidence_by_key, global_rows):
    """Enrich a known overlapping appearance without creating another one."""
    by_source_id = {row["source_lot_id"]: row for row in visible_rows}
    changes_by_path = defaultdict(dict)
    enriched = {"guides": 0, "sale_prices": 0, "rents": 0}
    conflicts = []
    for lot in manifest_lots:
        related_id = lot.get("related_existing_appearance_id")
        if not related_id:
            continue
        if related_id not in global_rows:
            raise ValueError(f"related existing appearance is missing: {related_id}")
        path, existing = global_rows[related_id]
        candidate = by_source_id[lot["source_lot_id"]]
        updated = dict(existing)
        for field, counter in (
            ("guide_price", "guides"), ("guide_price_high", None),
            ("sale_price", "sale_prices"), ("annual_rent", "rents"),
            ("rent_text", None), ("source_guide_text", None),
        ):
            incoming = candidate.get(field)
            current = updated.get(field)
            if incoming is None:
                continue
            if current is None:
                updated[field] = incoming
                if counter:
                    enriched[counter] += 1
            elif current != incoming:
                conflicts.append({
                    "appearance_id": related_id, "field": field,
                    "existing": current, "bruton_evidence": incoming,
                })
        related_evidence = list(updated.get("related_source_evidence") or [])
        known = {(item.get("sha256"), item.get("source_url")) for item in related_evidence}
        for item in candidate["source_evidence"]:
            key = (item.get("sha256"), item.get("source_url"))
            if key not in known:
                related_evidence.append(item)
                known.add(key)
        updated["related_source_evidence"] = related_evidence
        updated["joint_agent"] = SOURCE
        updated["joint_agent_evidence_basis"] = "same exact event and source-platform lot; not a second property appearance"
        changes_by_path[path][related_id] = updated

    for path, changes in changes_by_path.items():
        rows = list(corpus.iter_rows(path))
        before = len(rows)
        merged = [changes.get(row["appearance_id"], row) for row in rows]
        key = str(path.relative_to(corpus.DATA / "appearances")).removesuffix(".jsonl.gz")
        corpus.write_rows(key, merged, preserve_existing=False)
        persisted = list(corpus.iter_rows(path))
        if len(persisted) != before:
            raise RuntimeError(f"related appearance enrichment changed row count in {path}")
    return enriched, conflicts


def harvest():
    manifest = load_manifest()
    evidence_by_key = {}
    source_texts = {}
    for key, spec in manifest["sources"].items():
        source_url, raw = fetch(spec["url"])
        expected_magic = b"%PDF-" if spec["kind"] == "pdf" else b"<"
        if not raw.lstrip().startswith(expected_magic):
            raise ValueError(f"source {key} did not return expected {spec['kind']} content")
        evidence_by_key[key] = snapshot(raw, key, spec["kind"], spec["basis"], source_url)
        source_texts[key] = extracted_text(raw, spec)

    visible_rows = []
    states = []
    for event in manifest["events"]:
        materialized = []
        for position, lot in enumerate(event["lots"], 1):
            validate_lot(lot, source_texts)
            materialized.append(materialize(event, lot, evidence_by_key, position))
        if len(materialized) != int(event["expected_lots"]):
            raise ValueError("materialized event denominator does not reconcile")
        visible_rows.extend(materialized)
        states.append({
            "auctioneer": SOURCE, "trading_name": SOURCE,
            "source_auction_id": f"{SLUG}:{event['auction_date']}",
            "auction_date": event["auction_date"], "source_platform": event["platform"],
            "source_url": evidence_by_key[event["source_keys"][0]]["source_url"],
            "published_lots": int(event["expected_lots"]), "lots_captured": len(materialized),
            "catalogue_complete": event["auction_date"] == "2014-10-16",
            "source_rows_complete": True, "denominator_reconciled": True,
            "denominator_basis": "all individually named Bruton Knowles or joint-agent lots in the retained source",
            "guides_captured": sum(row["guide_price"] is not None for row in materialized),
            "sale_prices_captured": sum(row["sale_price"] is not None for row in materialized),
            "published_outcomes_captured": sum(row["status"] != "unknown" for row in materialized),
            "rents_captured": sum(row["annual_rent"] is not None for row in materialized),
            "source_evidence": [evidence_by_key[key] for key in event["source_keys"]],
            "errors": [], "checked_at": corpus.now(),
        })

    if len(visible_rows) != int(manifest["expected_lots"]):
        raise ValueError("batch lot denominator does not reconcile")
    exact_global = global_exact_appearances()
    rows_global = global_rows_by_id()
    manifest_lots = [lot for event in manifest["events"] for lot in event["lots"]]
    enriched, enrichment_conflicts = merge_related_evidence(
        visible_rows, manifest_lots, evidence_by_key, rows_global,
    )
    exclusions, admissible = [], []
    related_by_source_id = {
        lot["source_lot_id"]: lot.get("related_existing_appearance_id")
        for lot in manifest_lots if lot.get("related_existing_appearance_id")
    }
    for row in visible_rows:
        related_id = related_by_source_id.get(row["source_lot_id"])
        if related_id:
            exclusions.append({
                "auction_date": row["auction_date"], "address": row["address"],
                "bruton_appearance_id": row["appearance_id"],
                "existing": [{
                    "appearance_id": related_id,
                    "auctioneer": rows_global[related_id][1].get("auctioneer"),
                }],
                "basis": "same exact source-platform event lot; retained as related joint-agent evidence",
            })
            continue
        matches = exact_global.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            exclusions.append({
                "auction_date": row["auction_date"], "address": row["address"],
                "bruton_appearance_id": row["appearance_id"], "existing": matches,
            })
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    summary_path = corpus.DATA / "bruton_knowles_archive_collection.json"
    previous = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    baseline_ids = set(previous.get("batch_baseline_appearance_ids", [])) if previous else {
        row["appearance_id"] for row in existing
    }
    superseded_related_ids = {
        row["appearance_id"] for row in visible_rows
        if row["source_lot_id"] in related_by_source_id
    }
    # Parser v1 initially admitted one differently formatted Cottons address.
    # Its source evidence is now attached to the original Cottons appearance;
    # remove only that redundant identity, never the evidence or legal interest.
    existing = [row for row in existing if row["appearance_id"] not in superseded_related_ids]
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    persisted = list(corpus.iter_rows(path))
    if {row["appearance_id"] for row in persisted} != set(merged):
        raise RuntimeError("Bruton Knowles rows did not persist exactly")
    new_rows = [row for key, row in merged.items() if key not in baseline_ids]

    for state in states:
        state["exact_global_overlaps_excluded"] = sum(
            item["bruton_appearance_id"].startswith(f"{SOURCE}|{state['source_auction_id']}|")
            for item in exclusions
        )
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{state['auction_date']}.json", state)

    today_value = date.today()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    today = today_value.isoformat()
    historical_new = [row for row in new_rows if cutoff <= row["auction_date"] <= today]
    summary = {
        "checked_at": corpus.now(), "auctioneer": SOURCE,
        "canonical_auctioneer_label": SOURCE,
        "joint_platforms_not_counted_as_separate_bruton_auctioneers": sorted({
            event["platform"] for event in manifest["events"] if event["platform"] != SOURCE
        }),
        "parser_version": PARSER_VERSION, "source_events": len(manifest["events"]),
        "source_snapshots": len(evidence_by_key), "visible_source_rows": len(visible_rows),
        "appearances_captured": len(merged), "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical_new),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows) + enriched["guides"],
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows) + enriched["sale_prices"],
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows) + enriched["rents"],
        "related_duplicate_guides_enriched": enriched["guides"],
        "related_duplicate_sale_prices_enriched": enriched["sale_prices"],
        "related_duplicate_rents_enriched": enriched["rents"],
        "related_evidence_conflicts_preserved": enrichment_conflicts,
        "run_new_undated": sum(not row.get("auction_date") for row in new_rows),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(exclusions),
        "exact_global_overlap_exclusions": exclusions,
        "new_source_years": sorted({int(row["auction_date"][:4]) for row in new_rows}),
        "source_years_visible": sorted({int(row["auction_date"][:4]) for row in visible_rows}),
        "date_range": [min(row["auction_date"] for row in visible_rows), max(row["auction_date"] for row in visible_rows)],
        "by_status": dict(Counter(row["status"] for row in merged.values())),
        "by_sector": dict(Counter(row["sector"] for row in merged.values())),
        "batch_baseline_appearance_ids": sorted(baseline_ids),
        "completion_scope": "all ten individually evidenced lots across five retained Bruton Knowles or joint-agent source-events; not proof of the firm's complete historical output",
        "failures": [], "national_completeness_verified": False,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    harvest()
