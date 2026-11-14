import gzip
import json
from datetime import date
from pathlib import Path

import historical_corpus as corpus
from scripts import import_shepherd_saved_properties as shepherd


def saved_record(identifier, auction_date, address, guide, bucket_status="CURRENT"):
    return {
        "source": shepherd.SOURCE_NAME,
        "url": f"https://www.shepherd.co.uk/property/details/{identifier}/example-auction-property",
        "address": address,
        "lot_number": str(identifier),
        "auction_date": auction_date,
        "auction_id": f"shepherd:{auction_date}",
        "guide_price": guide,
        "guide_price_upper": None,
        "sale_price": None,
        "annual_rent": 12000 if identifier == 1 else None,
        "status": bucket_status,
        "source_availability": bucket_status,
        "property_type": "Retail",
        "description": "First-party auction detail",
        "image_url": f"https://images.example/{identifier}.jpg",
        "collected_at": "2026-11-09T06:41:00+00:00",
    }


def configure_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(corpus, "ROOT", tmp_path)
    monkeypatch.setattr(corpus, "DATA", tmp_path / "data/auction_history")
    monkeypatch.setattr(shepherd.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(shepherd.corpus, "DATA", tmp_path / "data/auction_history")
    source = tmp_path / "data/properties.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({
        "generated_at": "2026-11-14T06:49:00+00:00",
        "properties": [saved_record(2, "2026-12-03", "2 Future Street, Ayr", 50000)],
        "archive": [saved_record(1, "2026-10-22", "1 Historic Street, Ayr", 40000, "ARCHIVED")],
        "excluded_properties": [],
    }))
    return source


def test_imports_saved_historical_and_future_rows(monkeypatch, tmp_path):
    source = configure_tmp(monkeypatch, tmp_path)
    summary = shepherd.run_import(source, date(2026, 11, 14))

    assert summary["run_new_appearances"] == 2
    assert summary["run_new_dated_twenty_year_address_records"] == 1
    assert summary["run_new_future_dated"] == 1
    assert summary["run_new_commercial_or_mixed"] == 2
    assert summary["run_new_guide_prices"] == 2
    assert summary["run_new_sale_prices"] == 0
    assert summary["run_new_rents"] == 1
    assert summary["new_source_years"] == ["2026"]
    assert summary["historical_archive_complete"] is False

    shard = corpus.DATA / "appearances/shepherd-commercial/saved-properties.jsonl.gz"
    rows = list(corpus.iter_rows(shard))
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"unknown"}
    assert all(row["source_evidence"]["snapshot_path"] for row in rows)
    snapshot = corpus.ROOT / rows[0]["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)
    assert len(saved["rows"]) == 2

    rerun = shepherd.run_import(source, date(2026, 11, 14))
    assert rerun["run_new_appearances"] == 0
    assert rerun["appearances_captured"] == 2


def test_excludes_strong_exact_evidence_overlap(monkeypatch, tmp_path):
    source = configure_tmp(monkeypatch, tmp_path)
    existing = corpus.base_row(
        "Another source", "other:2026-10-22", "2026-10-22", "1", "existing", "https://example.test/existing"
    )
    existing.update(
        address="1 Historic Street, Ayr",
        guide_price=40000,
        description="Different wording",
    )
    corpus.write_rows("other/existing", [existing])

    summary = shepherd.run_import(source, date(2026, 11, 14))
    assert summary["run_duplicate_source_evidence_excluded"] == 1
    assert summary["run_new_appearances"] == 1
    assert summary["run_new_future_dated"] == 1
