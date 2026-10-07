import json
from pathlib import Path

import pytest

import historical_corpus as h


def test_js_json_is_parsed_as_data_and_preserves_unicode():
    body = r'''lots: JSON.parse('[{"name":"O\'Brien – café","id":"3"}]')'''
    assert h.embedded(body, "lots", True) == [{"name": "O'Brien – café", "id": "3"}]
    with pytest.raises(ValueError):
        h.embedded("lots: maliciousFunction()", "lots", True)


def test_section_divider_is_not_a_property_and_wrong_auction_is_rejected():
    a = {"id": "241", "auction_date": "2026-09-02"}
    assert h.modern_row({"id": "1", "lot_number": "0", "name": "Commercial Section"}, a, {}, {}) is None
    with pytest.raises(ValueError, match="different auction"):
        h.modern_row({"id": "1", "lot_number": "10", "auction_id": "240"}, a, {}, {})


def test_prices_status_and_rent_are_distinct():
    lot = {"id": "99", "auction_id": "241", "lot_number": "71A", "name": "1 High Street, SW1A 1AA",
           "low_estimate": "180000", "hammer_price": "205000", "sold_prior": "1", "sold": "1",
           "rent": "£19,000 per annum", "description": "ERV £35,000 per annum"}
    row = h.modern_row(lot, {"id": "241", "auction_date": "2026-09-02"}, {}, {})
    assert row["guide_price"] == 180000
    assert row["sale_price"] == 205000
    assert row["status"] == "sold prior"
    assert row["annual_rent"] == 19000
    assert row["lot_number"] == "71A"


def test_repeat_appearances_survive_and_neighbouring_units_do_not_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path)
    rows = []
    for aid, address in [("a", "Unit 1, 10 High Street, AB1 2CD"), ("b", "Unit 1, 10 High Street, AB1 2CD"), ("c", "Unit 2, 10 High Street, AB1 2CD")]:
        row = h.base_row("Test", aid, "2018-01-01", "1", "1", "https://example.com/" + aid)
        row.update(address=address, postcode="AB1 2CD", record_quality="address_record")
        rows.append(row)
    h.write_rows("test", rows)
    h.write_rows("test", rows[:1])
    report = h.build_database()
    assert report["individual_lot_records_captured"] == 3
    assert report["exact_address_groups"] == 2
    assert report["groups_with_repeat_appearances"] == 1
    assert not list(tmp_path.glob(".auction-history-*.sqlite"))


def test_partial_lots_do_not_create_fictitious_properties(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path)
    row = h.base_row("Test", "a", "2018-01-01", "1", None, "https://example.com/results")
    row.update(locality="London W8", record_quality="partial_lot")
    h.write_rows("test", [row])
    report = h.build_database()
    assert report["partial_lot_records"] == 1
    assert report["exact_address_groups"] == 0


def test_failed_pagination_never_marks_auction_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path)
    monkeypatch.setattr(h, "modern_routes", lambda: {})
    monkeypatch.setattr(h, "fetch", lambda url: (_ for _ in ()).throw(TimeoutError("source offline")))
    state = h.harvest_modern(241)
    assert state["catalogue_complete"] is False
    assert state["lots_captured"] == 0
    assert state["errors"]


def test_financial_and_sector_edge_cases():
    assert h.money("£1.31M") == 1310000
    assert h.money("Available at £450,000") is None
    assert h.sector("Investment Apartment") == "residential"
    assert h.sector("Investment Public House") == "commercial"
    assert h.sector("Shop and Flat") == "mixed-use"


def test_withdrawn_lot_without_number_is_still_banked():
    html = '''<p>Showing results 1 - 1 of 1</p><div class="card-body">
    Auction Ended - 30/07/2026 15:52
    <h4>Portland House, Llandrindod Wells, LD1 5ER</h4>
    Commercial / Residential Opportunity Result: Withdrawn
    <a href="/lot/details/edaa1ac0-0424-41c2-8f6e-ad3e114b7601">View Result</a></div>'''
    start, end, total, rows, raw = h.parse_paul_fosh(html, "https://auction.paulfosh.com/past-auctions", {})
    assert total == len(rows) == 1
    assert rows[0]["lot_number"] is None
    assert rows[0]["status"] == "withdrawn"
    assert rows[0]["auction_date"] == "2026-07-30"
    assert rows[0]["source_lot_id"] == "edaa1ac0-0424-41c2-8f6e-ad3e114b7601"


def test_source_corpus_enriches_exact_appearance_without_duplication(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    row = h.base_row("Savills Auctions", "propertyauctions:973", "2015-11-02", "52", None,
                     "https://www.propertyauctions.com/Results/LotList.aspx?AID=973")
    row.update(locality="London SE1", record_quality="partial_lot")
    h.write_rows("savills/legacy-973", [row])
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    (corpus / "test.json").write_text(json.dumps({
        "appearance_enrichments": [{
            "target_shard": "savills/legacy-973",
            "target_appearance_id": row["appearance_id"],
            "address": "122 Fort Road, London SE1 5PT",
            "source_url": "https://example.test/sav52.pdf",
        }]
    }))

    assert h.bank_source_corpus() == 0
    enriched = list(h.iter_rows(h.DATA / "appearances/savills/legacy-973.jsonl.gz"))
    assert len(enriched) == 1
    assert enriched[0]["address"] == "122 Fort Road, London SE1 5PT"
    assert enriched[0]["postcode"] == "SE1 5PT"
    assert enriched[0]["record_quality"] == "address_record"
    assert enriched[0]["address_enrichment_evidence"][0]["source_url"].endswith("sav52.pdf")

    snapshot = next((h.DATA / "sources/source-corpus").glob("*.json.gz"))
    snapshot_bytes = snapshot.read_bytes()
    assert h.bank_source_corpus() == 0
    assert snapshot.read_bytes() == snapshot_bytes
    enriched = list(h.iter_rows(h.DATA / "appearances/savills/legacy-973.jsonl.gz"))
    assert len(enriched[0]["address_enrichment_evidence"]) == 1


def test_postcode_pattern_accepts_london_outward_code_suffix():
    assert h.PC.fullmatch("WC1X 9PD")
    assert h.PC.search("Land at Granville Square, London WC1X 9PD").group() == "WC1X 9PD"


def test_source_corpus_exact_partial_lot_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    (corpus / "test.json").write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "lot_records": [{
            "source_record_id": "savills-nottingham:2014-01-23:lot:2",
            "source_auction_id": "savills-nottingham:2014-01-23",
            "auction_date": "2014-01-23",
            "lot_number": "2",
            "address": None,
            "locality": "Bridgnorth, Shropshire",
            "property_type": "Former fish and chip shop",
            "result_price_gbp": 73000,
            "source_url": "https://example.test/nottingham-results",
        }]
    }))

    assert h.bank_source_corpus() == 1
    assert h.bank_source_corpus() == 1
    rows = list(h.iter_rows(h.DATA / "appearances/source-corpus/test.jsonl.gz"))
    assert len(rows) == 1
    assert rows[0]["appearance_id"] == "source-corpus|savills-nottingham:2014-01-23:lot:2"
    assert rows[0]["record_quality"] == "partial_lot"


def test_source_corpus_can_bank_a_reconciled_complete_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    lots = [{
        "source_record_id": f"savills-nottingham-aid677-lot-{lot}",
        "source_auction_id": "savills-nottingham-aid677",
        "auction_date": "2010-05-13",
        "lot_number": str(lot),
        "address": None,
        "locality": locality,
        "property_type": "Retail",
        "source_url": "https://propertyauctions.com/Results/LotList.aspx?AID=677",
    } for lot, locality in ((1, "Nottingham"), (2, "Hucknall"))]
    (corpus / "complete.json").write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "catalogue_complete": True,
        "catalogue_lot_count": 2,
        "captured_at_utc": "2026-10-07T05:00:00Z",
        "lots": lots,
    }))

    assert h.bank_source_corpus() == 2
    state = json.loads((h.DATA / "auctions/source-corpus/complete.json").read_text())
    assert state["source_auction_id"] == "source-corpus:savills-nottingham-aid677"
    assert state["catalogue_complete"] is True
    assert state["lots_captured"] == state["expected_raw_records"] == 2


def test_source_corpus_refuses_false_complete_catalogue_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    (corpus / "incomplete.json").write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "catalogue_complete": True,
        "catalogue_lot_count": 2,
        "lots": [{
            "source_record_id": "only-one",
            "source_auction_id": "savills-nottingham-aid677",
            "auction_date": "2010-05-13",
            "lot_number": "1",
            "source_url": "https://propertyauctions.com/Results/LotList.aspx?AID=677",
        }],
    }))

    with pytest.raises(ValueError, match="does not reconcile"):
        h.bank_source_corpus()


def test_later_base_source_does_not_erase_earlier_address_enrichment(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    base = {
        "auctioneer": "Savills Auctions",
        "lot_records": [{
            "source_record_id": "saved:lot:1",
            "auction_date": "2014-01-23",
            "lot_number": "1",
            "address": None,
            "source_url": "https://example.test/base",
        }],
    }
    (corpus / "z_base.json").write_text(json.dumps(base))
    assert h.bank_source_corpus() == 1
    (corpus / "a_enrichment.json").write_text(json.dumps({
        "appearance_enrichments": [{
            "target_shard": "source-corpus/z_base",
            "target_appearance_id": "source-corpus|saved:lot:1",
            "address": "1 High Street, London SW1A 1AA",
            "source_url": "https://example.test/evidence",
        }],
    }))

    assert h.bank_source_corpus() == 1
    rows = list(h.iter_rows(h.DATA / "appearances/source-corpus/z_base.jsonl.gz"))
    assert rows[0]["address"] == "1 High Street, London SW1A 1AA"
    assert rows[0]["address_enrichment_evidence"][0]["source_url"].endswith("evidence")


def test_historical_workflow_stages_every_collection_summary():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/historical-lot-corpus.yml").read_text()
    assert "git add data/auction_history/*_collection.json" in workflow
