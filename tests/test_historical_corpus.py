import json
from pathlib import Path

import pytest

import historical_corpus as h


def test_source_banking_preserves_prior_after_and_unsold_outcomes(tmp_path,monkeypatch):
    monkeypatch.setattr(h,'ROOT',tmp_path);monkeypatch.setattr(h,'DATA',tmp_path/'data/auction_history')
    folder=tmp_path/'data/historical_source_corpus';folder.mkdir(parents=True)
    statuses=['Sold prior','Sold after','Unsold','Withdrawn prior to auction']
    rows=[{'source':'Test','source_record_id':str(i),'source_url':'https://example.com/'+str(i),
           'auction_date':'2020-01-01','address':'1 High Street','result_status':status,
           'result_price_gbp':100000} for i,status in enumerate(statuses)]
    (folder/'example.json').write_text(json.dumps({'lot_records':rows}))
    h.bank_source_corpus()
    saved=list(h.iter_rows(h.DATA/'appearances/source-corpus/example.jsonl.gz'))
    assert [r['status'] for r in saved]==['sold_prior','sold_after','unsold','withdrawn']
    assert [r['sale_price'] for r in saved]==[100000,100000,None,None]


def test_source_banking_accepts_legacy_records_lots_but_not_auction_manifests(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    folder = tmp_path / "data/historical_source_corpus"
    folder.mkdir(parents=True)
    existing = h.base_row("Example Auctions", "canonical:2014-07-09", "2014-07-09", "2", "canonical:2",
                          "https://example.test/property/2")
    existing["address"] = "2 High Street, London SW1A 1AA"
    h.write_rows("example/canonical", [existing])
    (folder / "legacy_records.json").write_text(json.dumps({
        "auctioneer": "Example Auctions",
        "records": [
            {
                "record_type": "auction",
                "auction_date": "2014-07-09",
                "source_urls": ["https://example.test/archive"],
            },
            {
                "record_type": "lot",
                "source_record_id": "example:2014-07-09:1",
                "auction_date": "2014-07-09",
                "lot_number": "1",
                "address": "1 High Street, London SW1A 1AA",
                "source_urls": ["https://example.test/property/1"],
                "result_price": 125000,
                "rent_pa": 9000,
                "result_status": "Sold",
            },
            {
                "record_type": "lot",
                "source_record_id": "example:2014-07-09:2",
                "auction_date": "2014-07-09",
                "lot_number": "2",
                "address": "2 High Street, London SW1A 1AA",
                "source_urls": ["https://example.test/property/2?legacy=1"],
            },
        ],
    }))

    assert h.bank_source_corpus() == 1
    rows = list(h.iter_rows(h.DATA / "appearances/source-corpus/legacy_records.jsonl.gz"))
    assert len(rows) == 1
    assert rows[0]["source_lot_id"] == "example:2014-07-09:1"
    assert rows[0]["sale_price"] == 125000
    assert rows[0]["annual_rent"] == 9000
    assert h.bank_source_corpus() == 1
    assert len(list(h.iter_rows(h.DATA / "appearances/source-corpus/legacy_records.jsonl.gz"))) == 1


def test_source_banking_recovers_old_root_inherits_auction_fields_and_reconciles_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    folder = tmp_path / "data/source_corpus"
    reconciliation_folder = tmp_path / "data/historical_source_corpus"
    folder.mkdir(parents=True)
    reconciliation_folder.mkdir(parents=True)

    existing = h.base_row("Example Auctions", "example:2016-12-05", "2016-12-05", "unknown",
                          "canonical:1", "https://example.test/property/known")
    existing.update(address="1 Bank Street, York YO1 1AA", status="sold",
                    guide_price=120000, record_quality="address_record")
    h.write_rows("example/canonical", [existing])

    (folder / "saved.json").write_text(json.dumps({
        "auctioneer": "Example Auctions",
        "auction": {"auction_date": "2016-12-05", "source_urls": ["https://example.test/archive"]},
        "lots": [
            {"source_record_id": "saved:known", "lot_number": "1", "locality": "York",
             "property_type": "Bank", "result": "£125,000"},
            {"source_record_id": "saved:address-overlap", "lot_number": None,
             "address": "1 Bank Street, York YO1 1AA", "property_type": "Bank",
             "result": "Sold", "source_url": "https://legacy.example.test/property/known"},
            {"source_record_id": "saved:new", "lot_number": "2", "address": "2 High Street, York YO1 2BB",
             "property_type": "Shop", "guide_price": 90000, "hammer_or_sold_price": 110000,
             "rent_pa": 8000, "result": "Sold", "source_url": "https://example.test/property/new"},
        ],
    }))
    (reconciliation_folder / "reconciliation.json").write_text(json.dumps({
        "reconciled_source_record_ids": ["saved:known"],
        "appearance_enrichments": [{
            "target_shard": "example/canonical", "target_appearance_id": existing["appearance_id"],
            "lot_number": "1", "sale_price": 125000, "status": "sold",
            "source_url": "https://example.test/archive",
        }],
    }))

    assert h.bank_source_corpus() == 1
    recovered = list(h.iter_rows(h.DATA / "appearances/source-corpus/saved.jsonl.gz"))
    assert len(recovered) == 1
    assert recovered[0]["auction_date"] == "2016-12-05"
    assert recovered[0]["sale_price"] == 110000
    assert recovered[0]["annual_rent"] == 8000
    enriched = list(h.iter_rows(h.DATA / "appearances/example/canonical.jsonl.gz"))[0]
    assert enriched["lot_number"] == "1"
    assert enriched["sale_price"] == 125000
    assert enriched["enrichment_evidence"][0]["source_url"] == "https://example.test/archive"


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


def test_versioned_source_reparse_can_explicitly_replace_extraction_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path)
    valid = h.base_row("Test", "auction", "2018-01-01", "1", "1", "https://example.com/results")
    artifact = h.base_row("Test", "auction", "2018-01-01", "12", "12", "https://example.com/results")
    h.write_rows("test", [valid, artifact])
    h.write_rows("test", [valid], preserve_existing=False)
    saved = list(h.iter_rows(tmp_path / "appearances/test.jsonl.gz"))
    assert [row["appearance_id"] for row in saved] == [valid["appearance_id"]]


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


def test_modern_count_accepts_only_exhausted_underreported_filter():
    complete, detail = h.reconcile_modern_catalogue_count(110, 106, [100, 10], 2, 2)
    assert complete is True
    assert detail == {
        "method": "exhausted_pagination_source_filter_underreported",
        "observed": 110,
        "source_reported": 106,
        "difference": 4,
    }
    assert h.reconcile_modern_catalogue_count(105, 106, [100, 5], 2, 2)[0] is False
    assert h.reconcile_modern_catalogue_count(110, 106, [100, 10], 1, 2)[0] is False
    assert h.reconcile_modern_catalogue_count(200, 106, [100, 100], 2, 2)[0] is False


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


def test_retired_source_corpus_replaces_prior_shard_with_empty_tombstone(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    source = corpus / "retired.json"
    source.write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "lots": [{
            "source_record_id": "retired-lot-1",
            "source_auction_id": "retired-sale",
            "auction_date": "2010-01-01",
            "lot_number": "1",
            "source_url": "https://example.test/retired",
        }],
    }))
    assert h.bank_source_corpus() == 1
    shard = h.DATA / "appearances/source-corpus/retired.jsonl.gz"
    assert len(list(h.iter_rows(shard))) == 1

    source.write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "lots": [],
        "retire_empty_derived_shard": True,
    }))
    assert h.bank_source_corpus() == 0
    assert shard.exists()
    assert list(h.iter_rows(shard)) == []


def test_source_corpus_rejects_conditional_future_marketing_and_retires_old_row(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    source = corpus / "conditional.json"
    source.write_text(json.dumps({
        "auctioneer": "Savills Auctions",
        "lots": [{
            "auction_date": "2016-09-19",
            "address": "42 High Street, Ewell, Epsom, Surrey KT17 1RQ",
            "source_url": "https://example.test/ewell",
            "source_note": "The property would be placed in the auction if not sold prior.",
        }],
    }))
    old = h.base_row("Savills Auctions", "source-corpus:2016-09-19", "2016-09-19",
                     "unknown", "old-conditional", "https://example.test/ewell")
    old["address"] = "42 High Street, Ewell, Epsom, Surrey KT17 1RQ"
    h.write_rows("source-corpus/conditional", [old])

    assert h.bank_source_corpus() == 0
    shard = h.DATA / "appearances/source-corpus/conditional.jsonl.gz"
    assert shard.exists()
    assert list(h.iter_rows(shard)) == []


def test_source_corpus_preserves_explicit_sold_prior_outcome_despite_conditional_words(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "ROOT", tmp_path)
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    corpus = tmp_path / "data/historical_source_corpus"
    corpus.mkdir(parents=True)
    (corpus / "sold_prior.json").write_text(json.dumps({
        "auctioneer": "Example Auctions",
        "lots": [{
            "source_record_id": "example:sold-prior",
            "auction_date": "2016-09-19",
            "address": "1 High Street, London SW1A 1AA",
            "source_url": "https://example.test/sold-prior",
            "source_note": "It would be placed in the auction if not sold prior.",
            "result_status": "Sold prior",
        }],
    }))

    assert h.bank_source_corpus() == 1
    rows = list(h.iter_rows(h.DATA / "appearances/source-corpus/sold_prior.jsonl.gz"))
    assert len(rows) == 1
    assert rows[0]["status"] == "sold_prior"


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
    assert workflow.count("if: always() && steps.rebuild.outcome == 'success'") == 3


def test_database_builder_retries_disk_staging_error_in_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    attempts = []

    def fake_build(in_memory=False):
        attempts.append(in_memory)
        if not in_memory:
            raise h.sqlite3.DatabaseError("malformed staging inode")
        return {"individual_lot_records_captured": 1}

    monkeypatch.setattr(h, "_build_database", fake_build)
    assert h.build_database() == {"individual_lot_records_captured": 1}
    assert attempts == [False, True]


def test_database_builder_does_not_retry_integrity_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DATA", tmp_path / "data/auction_history")
    attempts = []

    def fake_build(in_memory=False):
        attempts.append(in_memory)
        raise h.sqlite3.IntegrityError("duplicate appearance")

    monkeypatch.setattr(h, "_build_database", fake_build)
    with pytest.raises(h.sqlite3.IntegrityError, match="duplicate appearance"):
        h.build_database()
    assert attempts == [False]


def test_partial_source_catalogue_remains_visible_in_coverage_gaps(tmp_path,monkeypatch):
    monkeypatch.setattr(h,'ROOT',tmp_path);monkeypatch.setattr(h,'DATA',tmp_path/'data/auction_history')
    folder=tmp_path/'data/historical_source_corpus';folder.mkdir(parents=True)
    (folder/'partial.json').write_text(json.dumps({'catalogue_complete':False,'source_reported_rows':2,
      'source_url':'https://example.com/catalogue','reconciliation_errors':['page totals disagree'],
      'lot_records':[{'source':'Example','source_record_id':'example:1','source_auction_id':'example:2026-10-01',
        'auction_date':'2026-10-01','lot_number':'1','address':'1 High Street','source_url':'https://example.com/lot/1'}]}))
    h.bank_source_corpus()
    state=json.loads((h.DATA/'auctions/source-corpus/partial.json').read_text())
    assert state['catalogue_complete'] is False
    assert state['lots_captured']==1 and state['expected_raw_records']==2
    assert state['errors']==['page totals disagree']


def test_source_status_badge_is_not_replaced_by_guide_caption(tmp_path,monkeypatch):
    monkeypatch.setattr(h,'ROOT',tmp_path);monkeypatch.setattr(h,'DATA',tmp_path/'data/auction_history')
    folder=tmp_path/'data/historical_source_corpus';folder.mkdir(parents=True)
    rows=[{'source':'Example','source_record_id':f'example:{i}','source_auction_id':'example:2026-10-01',
           'auction_date':'2026-10-01','lot_number':str(i),'address':f'{i} High Street','source_url':f'https://example.com/lot/{i}',
           'status':status,'result_status':caption,'guide_price_gbp':100000}
          for i,status,caption in [(1,'UNSOLD','Guide Price £100,000'),(2,'SOLD PRIOR','Sold for £110,000')]]
    (folder/'outcomes.json').write_text(json.dumps({'lot_records':rows}))
    h.bank_source_corpus()
    actual=list(h.iter_rows(h.DATA/'appearances/source-corpus/outcomes.jsonl.gz'))
    assert {r['status'] for r in actual}=={'unsold','sold_prior'}
    assert all(r['sale_price'] is None for r in actual)
