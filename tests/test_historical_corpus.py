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
